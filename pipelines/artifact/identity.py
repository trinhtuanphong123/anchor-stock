"""pipelines.artifact.identity — content-addressing (docs/04 §2, migration 00005 comment).

``model_runs.artifact_id`` is the reproducibility proof: re-training on unchanged data must
yield the same id, because the digest excludes everything that varies between two runs of the
*same* computation (``created_at``, ``code_version``) and includes everything that defines the
computation's result (``P``, via ``p_sha256``, plus every other field of the artifact).

What this does and does not cover
----------------------------------
Identical input data, on the same numpy/BLAS build, reproduces ``artifact_id`` exactly — this
has been verified in practice (see ``pipelines.model.train --dry-run`` re-runs). A *different*
BLAS implementation or a different numpy build can change floating-point results in the last
bit or two (matrix multiplication is not required to be associative in any particular order),
which would change ``P`` and therefore the digest. That is a real, known limitation of
content-addressing over floats, not a bug in this module — it is written down here rather than
discovered later.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Any

import numpy as np

from pipelines.artifact.schema import Artifact

#: Fields excluded from the digest — see RunMeta's own docstring for why each one.
_EXCLUDED_FROM_DIGEST: tuple[str, ...] = ("content_sha256", "artifact_id", "created_at",
                                          "code_version")

#: Prefix distinguishing an artifact id from a universe version's "u..." (universe/file.py).
_ID_PREFIX = "a"
_ID_DIGEST_CHARS = 12


def npy_bytes(P: np.ndarray) -> bytes:
    """Canonical ``.npy`` serialisation of ``P`` — always float64, never pickled.

    Shared by :func:`compute_p_sha256` (hashing) and ``artifact.io.write_artifact`` (writing to
    disk), so the bytes that get hashed and the bytes that get written are the *same* bytes by
    construction, not two independently-written serialisations that happen to agree today.
    """
    buf = BytesIO()
    np.save(buf, np.asarray(P, dtype=np.float64), allow_pickle=False)
    return buf.getvalue()


def compute_p_sha256(P: np.ndarray) -> str:
    """sha256 of the canonical ``P.npy`` bytes (``model_similarity_full.p_sha256``)."""
    return hashlib.sha256(npy_bytes(P)).hexdigest()


def canonical_payload(artifact: Artifact) -> dict[str, Any]:
    """The manifest dict with the four excluded ``run`` fields stripped.

    ``artifact.run.p_sha256`` must already be set (via :func:`compute_p_sha256`) before calling
    this — it is *not* excluded, which is how ``P`` enters the digest without being hashed a
    second time as raw bytes.
    """
    payload = artifact.to_manifest_dict()
    run = dict(payload["run"])
    for key in _EXCLUDED_FROM_DIGEST:
        run.pop(key, None)
    payload["run"] = run
    return payload


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Deterministic serialisation: sorted keys, no incidental whitespace, no NaN token.

    ``allow_nan=False`` matches the precedent in ``storage/localfs.py`` — a non-finite value
    would serialise to the non-standard ``NaN``/``Infinity`` token, which round-trips through
    this module's own ``json.loads`` but not through Postgres or a stricter JSON reader.
    ``default=str`` handles ``date`` objects the same way ``AlignmentReport.to_json`` already
    does, so the embedded alignment report serialises identically in both places.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
    ).encode("utf-8")


def compute_content_sha256(artifact: Artifact) -> str:
    """sha256 over the canonical JSON of everything except the four excluded fields."""
    return hashlib.sha256(canonical_json_bytes(canonical_payload(artifact))).hexdigest()


def artifact_id_from_digest(content_sha256: str) -> str:
    return _ID_PREFIX + content_sha256[:_ID_DIGEST_CHARS]


def seal(artifact: Artifact) -> Artifact:
    """Compute and set ``p_sha256``, ``content_sha256``, ``artifact_id`` on ``artifact.run``.

    Mutates ``artifact.run`` in place (dataclasses are mutable) and returns the same artifact,
    so callers can write ``artifact = identity.seal(artifact)``. Order matters: ``p_sha256``
    must be set first, because ``content_sha256``'s computation reads it.
    """
    artifact.run.p_sha256 = compute_p_sha256(artifact.P)
    digest = compute_content_sha256(artifact)
    artifact.run.content_sha256 = digest
    artifact.run.artifact_id = artifact_id_from_digest(digest)
    return artifact


def verify_content_sha256(artifact: Artifact) -> bool:
    """Recompute the digest from ``artifact``'s current content and compare to the stored one.

    Trusts ``artifact.run.p_sha256`` as data (it is included in the payload, not recomputed from
    ``artifact.P`` here) — that P actually hashes to the stored ``p_sha256`` is a separate check
    (``artifact.validate`` V13), deliberately kept apart so each check names exactly one failure
    mode.
    """
    return compute_content_sha256(artifact) == artifact.run.content_sha256
