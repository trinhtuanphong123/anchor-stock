"""pipelines.common.paths — filesystem locations, resolved in exactly one place.

No module hard-codes a path. ``DATA_ROOT`` is read from ``$DATN_DATA_ROOT`` and falls back to
``<repo>/data``, so a developer can point the local track at a scratch disk without editing
code, and a test can point it at a temporary directory.

Layout under ``DATA_ROOT``::

    raw/{EQUITY,INDEX}/<SYMBOL>.jsonl.gz   provider payloads, exactly as received
    processed/*.parquet                     typed bars and returns
    artifacts/<artifact_id>/                frozen parameter sets
    research/*.csv                          stability and measure-comparison outputs

``raw/`` and ``processed/`` are regenerable and gitignored. ``artifacts/`` and ``research/``
are the study's results and are kept.
"""

from __future__ import annotations

import os
from pathlib import Path

# <repo>/pipelines/common/paths.py -> parents[2] is <repo>
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

#: Default universe file. Overridable per call; never silently replaced by a DB lookup.
UNIVERSE_FILE: Path = REPO_ROOT / "list_stocks.txt"

#: Frozen research-track universe (D-12) — the subset of ``UNIVERSE_FILE`` with a return on
#: every session of every research year. Derived once, not recomputed per run; see the file's
#: own header for how and why.
RESEARCH_UNIVERSE_FILE: Path = REPO_ROOT / "list_stocks_research.txt"

_DATA_ROOT_ENV = "DATN_DATA_ROOT"


def data_root() -> Path:
    """Return the local data root: ``$DATN_DATA_ROOT`` if set, else ``<repo>/data``.

    Resolved on every call rather than cached at import, so a process that sets the variable
    after importing this module still gets the location it asked for.
    """
    raw = os.environ.get(_DATA_ROOT_ENV, "").strip()
    return Path(raw).expanduser().resolve() if raw else REPO_ROOT / "data"


def raw_dir(kind: str) -> Path:
    """Directory holding untouched provider payloads for ``kind`` (EQUITY or INDEX)."""
    return data_root() / "raw" / kind.upper()


def raw_path(symbol: str, kind: str) -> Path:
    """Gzipped JSON Lines file for one symbol. One line per raw bar."""
    return raw_dir(kind) / f"{symbol.upper()}.jsonl.gz"


def processed_dir() -> Path:
    """Directory holding typed Parquet tables."""
    return data_root() / "processed"


def processed_path(name: str) -> Path:
    """Parquet file for one processed table held as a single file, e.g. an export."""
    return processed_dir() / f"{name}.parquet"


def processed_table_dir(table: str) -> Path:
    """Directory holding one processed table's per-symbol shards."""
    return processed_dir() / table


def shard_path(table: str, key_col: str, key: str) -> Path:
    """Parquet shard for one symbol of one table.

    ``processed/<table>/<key_col>=<KEY>/data.parquet``

    One shard per symbol, because the fetch loop is per symbol, throttled, and interruptible —
    making the storage unit match the work unit means "interrupted after 60 of 100 symbols"
    is exactly "60 shards complete, 40 absent", a state the next run rebuilds from the high-water
    marks with no special handling.

    The filename is always ``data.parquet``. It must not be generated (``part-0``, ``part-1``,
    …): a per-run filename accumulates duplicate rows across runs and breaks idempotency
    silently, which is the failure mode this whole layout exists to avoid.
    """
    return processed_table_dir(table) / f"{key_col}={key.upper()}" / "data.parquet"


def artifacts_dir() -> Path:
    """Directory holding one subdirectory per frozen parameter set."""
    return data_root() / "artifacts"


def artifact_dir(artifact_id: str) -> Path:
    """Directory for one artifact. Its name *is* the artifact id."""
    return artifacts_dir() / artifact_id


def research_dir() -> Path:
    """Directory holding the stability and comparison CSVs quoted by the report."""
    return data_root() / "research"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if absent, and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
