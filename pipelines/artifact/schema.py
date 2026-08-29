"""pipelines.artifact.schema — the frozen artifact's shape.

Mirrors ``supabase/migrations/00005_model_artifact.sql`` table for table, so the
correspondence between a Python field and a Postgres column is checkable by eye rather than by
memory. Two tables are deliberately absent as dataclasses:

- ``model_similarity_full`` — its ``values``/``n``/``ordering``/``p_sha256`` are all fully
  derivable from :class:`Artifact`'s own ``P`` and ``universe``; storing them again in the
  dataclass would create a second copy that could drift from the first.
- ``model_similarity_anchor`` — ``P[:, S]`` is a slice of the same ``P``. ``artifact.io``
  exposes ``anchor_columns()`` to materialise it on read, for P6.

Every dataclass here is pure data: no I/O, no numpy beyond ``Artifact.P`` itself, matching how
``pipelines.storage.ports`` stays dependency-free. Identity (hashing) lives in
``pipelines.artifact.identity``; reading and writing live in ``pipelines.artifact.io``;
correctness checks live in ``pipelines.artifact.validate``. This module only says what a run
*is*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np

#: Bump when a field is added, removed, or its meaning changes. artifact.io refuses to load an
#: artifact whose version it does not recognise (V1) rather than guess at a migration.
ARTIFACT_SCHEMA_VERSION: int = 1

#: Mirrors ``model_runs_measure_check``.
SIMILARITY_MEASURES: frozenset[str] = frozenset({"pearson_rho2", "dcor2"})

#: Mirrors ``model_runs_scope_check``.
SCOPES: frozenset[str] = frozenset({"year", "live"})

#: The tie-break the greedy algorithm actually uses (pipelines.anchors.greedy); recorded rather
#: than assumed so a future alternate tie-break shows up as a changed field, not silent drift.
TIE_BREAK: str = "smallest_index"


class ArtifactSchemaVersionError(ValueError):
    """An artifact on disk carries a schema version this code does not know how to read."""


def _parse_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _parse_datetime(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


# ---------------------------------------------------------------------------
# model_runs
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class RunMeta:
    """One row of ``model_runs``, minus ``id`` and ``loaded_at`` (database-assigned), plus
    ``p_sha256`` — logically a ``model_similarity_full`` column, carried here because that is
    where ``identity.seal()`` needs to write it (see below).

    Three fields start empty and are filled in by :func:`pipelines.artifact.identity.seal`, in
    this order: ``p_sha256`` first (hashed *from* ``P``), then ``content_sha256`` (hashed from
    everything else, ``p_sha256`` included — this is how ``P`` enters the digest without being
    hashed twice), then ``artifact_id`` (derived from ``content_sha256``). ``content_sha256``
    itself, plus ``created_at`` and ``code_version``, are excluded from what gets hashed: a
    rerun on unchanged data must produce the same id regardless of when it ran or what commit is
    checked out.
    """

    artifact_schema_version: int
    scope: str                          # 'year' | 'live'
    scope_label: str                    # '2025' | '2026-03'
    similarity_measure: str             # 'pearson_rho2' | 'dcor2'

    universe_version: str
    index_symbol: str
    source: str

    window_start: date
    window_end: date
    prior_close_date: date

    n_sessions: int                     # T
    n_tickers: int                      # N
    q: float                            # N / T

    k: int
    k_max: int
    tau: float

    coverage_f: float                   # F(S) at k
    coverage_fbar: float                # F/N at k
    n_under_tau: int                    # |U_tau|

    alignment: dict[str, Any]           # AlignmentReport, embedded verbatim

    p_sha256: str = ""                  # sha256 of P.npy — set BEFORE sealing (see identity.py)
    artifact_id: str = ""               # set by identity.seal(), from content_sha256
    content_sha256: str = ""            # set by identity.seal()
    tie_break: str = TIE_BREAK
    is_primary: bool = False
    is_active: bool = False
    code_version: str | None = None
    created_at: str = ""                # ISO 8601 datetime, set at build time

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> RunMeta:
        d = dict(d)
        d["window_start"] = _parse_date(d["window_start"])
        d["window_end"] = _parse_date(d["window_end"])
        d["prior_close_date"] = _parse_date(d["prior_close_date"])
        return RunMeta(**d)


# ---------------------------------------------------------------------------
# model_universe
# ---------------------------------------------------------------------------


@dataclass
class UniverseEntry:
    """One row of ``model_universe`` — the run's own ordered ticker list.

    Deliberately separate from ``universe_members`` (what the universe *file* said): this is
    what the run actually used, positions ``0..N-1`` in the order ``P`` is indexed by.
    """

    position: int
    ticker: str


# ---------------------------------------------------------------------------
# model_ticker_params
# ---------------------------------------------------------------------------


@dataclass
class TickerParams:
    """One row of ``model_ticker_params`` — docs/04 §2 "per ticker i"."""

    ticker: str
    position: int
    alpha_hat: float
    beta_hat: float
    sigma_hat: float
    r2: float
    anchor_ticker: str                  # a(i)
    coverage_c: float                   # c_i = rho2(i, a(i))
    is_anchor: bool
    under_tau: bool


# ---------------------------------------------------------------------------
# model_anchors
# ---------------------------------------------------------------------------


@dataclass
class AnchorStep:
    """One row of ``model_anchors`` — one greedy round, stored to ``k_max`` (D-9)."""

    step_k: int                         # 1..k_max, selection order
    anchor_ticker: str
    position: int
    marginal_gain: float                # Delta_step, non-increasing
    coverage_f: float                   # F(S) after this round
    coverage_fbar: float                # F/N after this round
    in_published_set: bool              # step_k <= k


# ---------------------------------------------------------------------------
# model_groups
# ---------------------------------------------------------------------------


@dataclass
class Group:
    """One row of ``model_groups`` — docs/02 §3g. ``sector_composition`` defaults to ``{}``:

    no sector data is collected locally, and docs/02 §3g makes sector composition external
    validation only — it never enters ``P`` or the objective, so an empty dict here is a
    deferred field, not a placeholder standing in for something the model needed.
    """

    anchor_ticker: str
    size: int                           # |C_j|
    f_j: float                          # sum_{i in C_j} c_i
    rho2_mean: float
    rho2_min: float
    sector_composition: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The whole artifact
# ---------------------------------------------------------------------------


@dataclass
class Artifact:
    """One complete run: metadata + the four per-entity tables + the archived matrix P.

    ``P`` is never embedded in the JSON manifest (see ``artifact.io``) — it is written
    separately as ``P.npy`` and referenced by its own hash, so the manifest stays small and
    human-readable while the matrix stays exact (JSON floats would round-trip losslessly too,
    but ``np.save`` is simpler and is what the rest of the local track already uses).
    """

    run: RunMeta
    universe: list[UniverseEntry]
    ticker_params: list[TickerParams]
    anchors: list[AnchorStep]
    groups: list[Group]
    P: np.ndarray

    def to_manifest_dict(self) -> dict[str, Any]:
        """Everything except ``P`` — what ``manifest.json`` holds."""
        return {
            "run": self.run.to_dict(),
            "universe": [asdict(u) for u in self.universe],
            "ticker_params": [asdict(t) for t in self.ticker_params],
            "anchors": [asdict(a) for a in self.anchors],
            "groups": [asdict(g) for g in self.groups],
        }

    @staticmethod
    def from_manifest_dict(d: dict[str, Any], P: np.ndarray) -> Artifact:
        return Artifact(
            run=RunMeta.from_dict(d["run"]),
            universe=[UniverseEntry(**u) for u in d["universe"]],
            ticker_params=[TickerParams(**t) for t in d["ticker_params"]],
            anchors=[AnchorStep(**a) for a in d["anchors"]],
            groups=[Group(**g) for g in d["groups"]],
            P=P,
        )

    def position_of(self, ticker: str) -> int:
        """Index of ``ticker`` in ``universe`` order — the column/row P is indexed by."""
        for u in self.universe:
            if u.ticker == ticker:
                return u.position
        raise KeyError(ticker)

    def published_tickers(self) -> set[str]:
        """S — the k published anchor tickers (docs/02 §3a), not the full k_max curve."""
        return {a.anchor_ticker for a in self.anchors if a.in_published_set}
