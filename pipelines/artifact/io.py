"""pipelines.artifact.io — read and write one artifact directory.

``data/artifacts/<artifact_id>/`` holds exactly two files:

    manifest.json   everything except P — indented, human-readable; what an examiner opens
    P.npy           the N×N similarity matrix, float64, ``allow_pickle=False``

Writing always calls :func:`pipelines.artifact.identity.seal` first, so the id and hashes on
disk are guaranteed to describe the content being written — a caller cannot forget to seal, or
seal and then mutate the artifact before writing, and end up with a manifest that lies about
its own hash.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from pipelines.artifact import identity
from pipelines.artifact.schema import ARTIFACT_SCHEMA_VERSION, Artifact, ArtifactSchemaVersionError
from pipelines.common.paths import artifact_dir, artifacts_dir, ensure_dir

MANIFEST_NAME = "manifest.json"
MATRIX_NAME = "P.npy"


class ArtifactCollisionError(RuntimeError):
    """A content-addressed id already exists on disk with *different* content.

    SHA-256 collisions are not a practical concern; this fires when the on-disk bytes have
    drifted from what the id claims to describe — a bug upstream, not a normal re-run. A normal
    re-run on unchanged data writes byte-identical files and is a silent no-op instead.
    """


def _atomic_write(path: Path, payload: bytes) -> None:
    """tmp-in-same-dir + fsync + replace, so a reader never sees a partial file.

    Mirrors ``pipelines.storage.localfs._atomic_write``. Kept as a local copy rather than an
    import: ``artifact/`` stays independent of ``storage/`` the same way ``storage/ports.py``
    stays independent of the rest of the repo — each layer names its own dependencies.
    """
    ensure_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _manifest_bytes(artifact: Artifact) -> bytes:
    return (
        json.dumps(artifact.to_manifest_dict(), indent=2, sort_keys=True, default=str) + "\n"
    ).encode("utf-8")


def write_artifact(artifact: Artifact, root: Path | None = None) -> Path:
    """Seal ``artifact`` and write it to ``<root>/<artifact_id>/``. Returns the directory.

    Idempotent on identical *content*: two runs that produce the same digest are the same
    artifact, computed at two different times. The check that decides this is
    ``content_sha256`` equality plus a byte comparison of ``P.npy`` — deliberately **not** a raw
    byte comparison of ``manifest.json``, because ``created_at`` and ``code_version`` are
    excluded from the digest on purpose (identity.py) and legitimately differ between two
    otherwise-identical runs. When content matches, the existing files are left untouched —
    same reason ``ON_CONFLICT_KEEP`` preserves ``ingested_at`` in ``storage/ports.py``: the
    first-written timestamp is the more meaningful one, not the latest re-run's.

    Content that does *not* match under an id that already exists on disk raises
    :class:`ArtifactCollisionError` — see that class's docstring.
    """
    identity.seal(artifact)

    manifest_bytes = _manifest_bytes(artifact)
    p_bytes = identity.npy_bytes(artifact.P)

    out_dir = (root / artifact.run.artifact_id) if root is not None else artifact_dir(
        artifact.run.artifact_id
    )
    manifest_path = out_dir / MANIFEST_NAME
    p_path = out_dir / MATRIX_NAME

    if out_dir.is_dir() and manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            existing_digest = existing["run"]["content_sha256"]
        except (json.JSONDecodeError, KeyError):
            existing_digest = None
        existing_p = p_path.read_bytes() if p_path.is_file() else None
        if existing_digest == artifact.run.content_sha256 and existing_p == p_bytes:
            return out_dir
        raise ArtifactCollisionError(
            f"{artifact.run.artifact_id} already exists at {out_dir} with different content — "
            "a content-addressed id must not collide. If this is a genuine re-run on the same "
            "data, the two writes should have produced the same content_sha256 and P.npy; "
            "investigate before retrying."
        )

    ensure_dir(out_dir)
    _atomic_write(manifest_path, manifest_bytes)
    _atomic_write(p_path, p_bytes)
    return out_dir


def read_artifact(artifact_id_or_path: str | Path, root: Path | None = None) -> Artifact:
    """Load an artifact by id (resolved under ``root``) or by an explicit directory path."""
    p = Path(artifact_id_or_path)
    if p.is_dir():
        out_dir = p
    else:
        out_dir = (root / str(artifact_id_or_path)) if root is not None else artifact_dir(
            str(artifact_id_or_path)
        )

    manifest_path = out_dir / MANIFEST_NAME
    p_path = out_dir / MATRIX_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no {MANIFEST_NAME} under {out_dir}")
    if not p_path.is_file():
        raise FileNotFoundError(f"no {MATRIX_NAME} under {out_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest.get("run", {}).get("artifact_schema_version")
    if version != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactSchemaVersionError(
            f"{out_dir} has artifact_schema_version={version!r}, this code knows "
            f"{ARTIFACT_SCHEMA_VERSION!r} — refusing to guess at a migration"
        )

    P = np.load(p_path, allow_pickle=False)
    return Artifact.from_manifest_dict(manifest, P)


def find_artifacts(root: Path | None = None) -> list[tuple[str, str, str]]:
    """``[(scope_label, similarity_measure, artifact_id), ...]`` under ``root``, sorted.

    ``scope_label`` alone is not unique once a year has both a ``pearson_rho2`` and a ``dcor2``
    artifact (P5) — ``similarity_measure`` is carried so a caller can select "the 2023 Pearson
    run" without opening every manifest first. Scans the directories directly rather than
    maintaining a separate index file that could drift out of sync with what is actually on disk.
    """
    base = root if root is not None else artifacts_dir()
    if not base.is_dir():
        return []
    out: list[tuple[str, str, str]] = []
    for child in base.iterdir():
        manifest_path = child / MANIFEST_NAME
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            run = manifest["run"]
            out.append((run["scope_label"], run["similarity_measure"], run["artifact_id"]))
        except (json.JSONDecodeError, KeyError):
            continue
    return sorted(out)


def anchor_columns(artifact: Artifact) -> list[dict[str, Any]]:
    """``P[:, S]`` as row dicts, S = the published k anchors (mirrors ``model_similarity_anchor``).

    N*k rows, one per (ticker, anchor) pair. Derived from ``P``/``anchors`` on every call rather
    than stored on the artifact — see ``schema.py``'s module docstring for why storing it a
    second time would create a second source of truth.
    """
    published = [a for a in artifact.anchors if a.in_published_set]
    tickers_by_position = sorted(artifact.universe, key=lambda u: u.position)
    rows: list[dict[str, Any]] = []
    for anchor in published:
        j = anchor.position
        for u in tickers_by_position:
            rows.append({
                "ticker": u.ticker,
                "anchor_ticker": anchor.anchor_ticker,
                "rho2": float(artifact.P[u.position, j]),
            })
    return rows
