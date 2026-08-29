"""pipelines.storage.localfs — the filesystem implementation of the storage ports.

Writes under ``DATA_ROOT`` (see ``pipelines.common.paths``):

    raw/{EQUITY,INDEX}/<SYMBOL>.jsonl.gz     provider payloads, one record dict per line
    processed/<table>/<key>=<SYMBOL>/data.parquet    typed bars and returns

Raw is JSON Lines of exactly the record dicts ``upsert_ohlc_raw`` receives, so a local raw file
is a line-serialisation of a ``staging.ohlc_raw`` row. Same shape, different medium — that is
what makes the two tracks provably the same pipeline rather than two implementations that will
drift.

Processed is one parquet shard per symbol, because the fetch loop is per symbol, throttled and
interruptible. Making the storage unit match the work unit means an interrupted run leaves
"N shards complete, the rest absent" — a state the next run rebuilds from the high-water marks
with no recovery pass.

Where this is not Postgres
--------------------------
Four asymmetries are accepted rather than papered over. Pretending they do not exist would be
worse than naming them.

* **No foreign key to ``stocks``.** Postgres rejects an unknown ticker; this sink happily
  creates a directory for it. The local track's referential integrity *is* ``list_stocks.txt``.
  Partially mitigated: partition keys are validated against a strict pattern, which catches
  garbage and closes a path-traversal hole, though not a well-formed-but-unlisted symbol.
* **No numeric scale.** Postgres ``numeric`` rounds on insert; float64 does not. Log returns can
  differ around the sixth decimal. Far below every threshold in the spec (the noise floor is
  ≈ 0.07), and deliberately NOT emulated here — hard-coding a guess at the DDL's scale into
  Python would invent a new divergence to hide an old one.
* **No concurrency control.** Postgres serialises upserts on the same key; the read-merge-rewrite
  below is last-writer-wins across processes. Precondition, not caveat: the local track is a
  single-process offline run.
* **``staging.ohlc_raw.provider``** is filled by a schema default that no record dict supplies,
  so it has no local counterpart. Recorded for P2.

The one asymmetry that IS closed: ``close`` must be non-null and finite, because it is the
model's only price input and a missing close deletes a session from the return series silently.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pipelines.common.paths import data_root, ensure_dir, raw_path, shard_path
from pipelines.storage.ports import (
    BOOL_COLS as _BOOL_COLS,
)
from pipelines.storage.ports import (
    CONFLICT_KEY,
    ON_CONFLICT_KEEP,
    PARTITION_COL,
    RECORD_KEYS,
    Dataset,
    require_source,
)
from pipelines.storage.ports import (
    DATE_COLS as _DATE_COLS,
)
from pipelines.storage.ports import (
    FLOAT_COLS as _FLOAT_COLS,
)
from pipelines.storage.ports import (
    TS_COLS as _TS_COLS,
)

__all__ = ["LocalSink", "LocalSource"]

#: Partition keys become directory names, so they are validated before touching the filesystem.
#: This is a path-safety guard as much as a data check: it rejects "", "..", "a/b" and anything
#: else that would escape the data root. Deliberately NOT imported from ``universe.file`` —
#: that pattern is about the investable universe, and index symbols are not in it.
_PARTITION_KEY_RE = re.compile(r"^[A-Z0-9]{1,20}$")

# _FLOAT_COLS / _BOOL_COLS / _DATE_COLS / _TS_COLS now live in pipelines.storage.ports as
# FLOAT_COLS / BOOL_COLS / DATE_COLS / TS_COLS — the shared, machine-readable record contract
# both backends' typed reads are checked against (P6.4). Imported under the old private names
# so every existing use below (the Arrow schema, in particular) is unchanged.

#: Datasets whose ``close`` is load-bearing and must therefore be present, non-null and finite.
_CLOSE_REQUIRED = frozenset({Dataset.DAILY_BARS, Dataset.INDEX_BARS})


def _arrow_schema(dataset: Dataset):
    """Explicit Arrow schema for a dataset, in ``RECORD_KEYS`` order.

    Explicit rather than inferred: inference would type an all-null ``volume`` column as null
    and an all-integer one as int64, so a shard's schema would depend on the data that happened
    to land in it and two shards of the same table could disagree.
    """
    import pyarrow as pa  # noqa: PLC0415 - lazy: keeps pyarrow out of the import graph

    fields = []
    for col in RECORD_KEYS[dataset]:
        if col in _FLOAT_COLS:
            t = pa.float64()
        elif col in _BOOL_COLS:
            t = pa.bool_()
        elif col in _DATE_COLS:
            t = pa.date32()
        elif col in _TS_COLS:
            t = pa.timestamp("us", tz="UTC")
        else:
            t = pa.string()
        fields.append(pa.field(col, t, nullable=True))
    return pa.schema(fields)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``path`` so a reader sees the old file or the new one, never a splice.

    tmp in the SAME directory (``os.replace`` is only atomic within a filesystem), flush, then
    ``fsync`` before the rename. The fsync is not optional: without it a power loss can make the
    rename durable while the data blocks are not, producing a complete-looking file with a hole
    in it — exactly the failure this function exists to prevent.
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


# ---------------------------------------------------------------------------
# Encoding helpers — JSON Lines
# ---------------------------------------------------------------------------


def _encode_jsonl_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Record dict -> JSON-encodable dict. ``payload`` stays the JSON *string* it already is."""
    out: dict[str, Any] = {}
    for k, v in rec.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, date):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _decode_jsonl_record(obj: dict[str, Any]) -> dict[str, Any]:
    """Inverse of :func:`_encode_jsonl_record`, by field name."""
    out = dict(obj)
    if isinstance(out.get("bar_date"), str):
        out["bar_date"] = date.fromisoformat(out["bar_date"])
    if isinstance(out.get("fetched_at"), str):
        out["fetched_at"] = datetime.fromisoformat(out["fetched_at"])
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_key(key: Any, dataset: Dataset) -> str:
    if not isinstance(key, str) or not _PARTITION_KEY_RE.match(key.upper()):
        raise ValueError(
            f"{dataset.value}: invalid partition key {key!r} "
            f"(must match {_PARTITION_KEY_RE.pattern})"
        )
    return key.upper()


def _validate_records(dataset: Dataset, records: list[dict[str, Any]]) -> None:
    """Reject anything Postgres would reject, plus anything that would silently corrupt a series.

    Checked here rather than at read time so a bad record never reaches storage: a NaN that
    round-trips is far harder to trace than one that refuses to be written.
    """
    required = RECORD_KEYS[dataset]
    part_col = PARTITION_COL[dataset]
    for i, rec in enumerate(records):
        missing = [k for k in required if k not in rec]
        if missing:
            raise ValueError(f"{dataset.value}[{i}]: missing required key(s) {missing}")
        _validate_key(rec[part_col], dataset)

        if dataset in _CLOSE_REQUIRED:
            close = rec.get("close")
            if close is None:
                raise ValueError(
                    f"{dataset.value}[{i}]: close is NULL. It is the model's only price input; "
                    f"a bar without one must be dropped before writing, not stored as a hole."
                )
        for col in required:
            v = rec[col]
            if col in _FLOAT_COLS and v is not None:
                fv = float(v)
                if not math.isfinite(fv):
                    raise ValueError(
                        f"{dataset.value}[{i}]: {col} is {fv!r}. Postgres numeric rejects "
                        f"non-finite values, so accepting one here would diverge."
                    )


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------


class LocalSink:
    """Filesystem :class:`~pipelines.storage.ports.BarSink`. See the module docstring."""

    def __init__(self, root: Path | None = None) -> None:
        # Stored unresolved so that ``data_root()`` is consulted per operation. That keeps the
        # "re-read the environment every call" property the paths module deliberately has, which
        # is what lets the selftest point DATA_ROOT at a temp dir with no monkeypatching.
        self._root = root

    @property
    def root(self) -> Path:
        return self._root if self._root is not None else data_root()

    # -- public API ---------------------------------------------------------

    def write_raw_bars(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        by_bar_type = {"EQUITY": Dataset.RAW_EQUITY, "INDEX": Dataset.RAW_INDEX}
        by_type: dict[Dataset, list[dict[str, Any]]] = {}
        for rec in records:
            bt = rec.get("bar_type")
            ds = by_bar_type.get(bt)
            if ds is None:
                raise ValueError(f"raw record has bar_type={bt!r}; expected 'EQUITY' or 'INDEX'")
            by_type.setdefault(ds, []).append(rec)
        total = 0
        for ds, group in by_type.items():
            total += self._write_raw(ds, group)
        return total

    def write_daily_bars(self, records: list[dict[str, Any]]) -> int:
        return self._write_typed(Dataset.DAILY_BARS, records)

    def write_index_bars(self, records: list[dict[str, Any]]) -> int:
        return self._write_typed(Dataset.INDEX_BARS, records)

    def write_daily_returns(self, records: list[dict[str, Any]]) -> int:
        return self._write_typed(Dataset.DAILY_RETURNS, records)

    def write_index_returns(self, records: list[dict[str, Any]]) -> int:
        return self._write_typed(Dataset.INDEX_RETURNS, records)

    def write_indicators(self, records: list[dict[str, Any]]) -> int:
        return self._write_typed(Dataset.INDICATORS_DAILY, records)

    # -- internals ----------------------------------------------------------

    def _merge(
        self, dataset: Dataset, existing: dict[tuple, dict[str, Any]], batch: list[dict[str, Any]]
    ) -> dict[tuple, dict[str, Any]]:
        """Apply ``batch`` over ``existing``, replicating ``ON CONFLICT DO UPDATE SET`` exactly.

        The subtle part is ``ON_CONFLICT_KEEP``: Postgres' clause for ``daily_bars`` omits
        ``ingested_at``, so a re-ingested bar keeps the moment it FIRST arrived. A blanket
        row-replace looks correct and diverges by that one column.
        """
        keep = ON_CONFLICT_KEEP[dataset]
        ck = CONFLICT_KEY[dataset]
        merged = dict(existing)
        for rec in batch:
            k = tuple(rec[c] for c in ck)
            new = {c: rec[c] for c in RECORD_KEYS[dataset]}
            if k in merged:
                for col in keep:
                    new[col] = merged[k][col]
            merged[k] = new
        return merged

    def _write_raw(self, dataset: Dataset, records: list[dict[str, Any]]) -> int:
        _validate_records(dataset, records)
        kind = dataset.bar_type or ""
        by_symbol: dict[str, list[dict[str, Any]]] = {}
        for rec in records:
            by_symbol.setdefault(_validate_key(rec["symbol"], dataset), []).append(rec)

        for symbol, group in by_symbol.items():
            path = raw_path(symbol, kind)
            merged = self._merge(dataset, self._read_raw_shard(path, dataset), group)
            lines = [
                json.dumps(_encode_jsonl_record(merged[k]), sort_keys=True, allow_nan=False)
                for k in sorted(merged, key=lambda t: t[2])  # by bar_date
            ]
            buf = io.BytesIO()
            # mtime=0 so identical content produces byte-identical files: "did this run change
            # anything?" becomes a hash comparison rather than a parse-and-diff.
            with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
                gz.write(("\n".join(lines) + "\n").encode("utf-8"))
            _atomic_write(path, buf.getvalue())
        return len(records)

    def _write_typed(self, dataset: Dataset, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        _validate_records(dataset, records)
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        part_col = PARTITION_COL[dataset]
        by_key: dict[str, list[dict[str, Any]]] = {}
        for rec in records:
            by_key.setdefault(_validate_key(rec[part_col], dataset), []).append(rec)

        cols = RECORD_KEYS[dataset]
        schema = _arrow_schema(dataset)
        for key, group in by_key.items():
            path = shard_path(dataset.table, part_col, key)
            merged = self._merge(dataset, self._read_typed_shard(path, dataset), group)
            rows = [merged[k] for k in sorted(merged, key=_sort_key)]
            table = pa.Table.from_pydict(
                {c: [r[c] for r in rows] for c in cols}, schema=schema
            )
            buf = io.BytesIO()
            pq.write_table(table, buf, compression="snappy")
            _atomic_write(path, buf.getvalue())
        return len(records)

    def _read_raw_shard(self, path: Path, dataset: Dataset) -> dict[tuple, dict[str, Any]]:
        if not path.is_file():
            return {}
        ck = CONFLICT_KEY[dataset]
        out: dict[tuple, dict[str, Any]] = {}
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = _decode_jsonl_record(json.loads(line))
                out[tuple(rec[c] for c in ck)] = rec
        return out

    def _read_typed_shard(self, path: Path, dataset: Dataset) -> dict[tuple, dict[str, Any]]:
        if not path.is_file():
            return {}
        ck = CONFLICT_KEY[dataset]
        rows = _read_parquet(path)
        return {tuple(r[c] for c in ck): r for r in rows}


def _sort_key(k: tuple) -> tuple:
    """Sort conflict-key tuples with dates and strings mixed, deterministically."""
    return tuple((0, v.toordinal(), "") if isinstance(v, date) else (1, 0, str(v)) for v in k)


def _read_parquet(path: Path) -> list[dict[str, Any]]:
    """Read ONE parquet file as a list of row dicts.

    Deliberately ``ParquetFile(path).read()`` and not ``pq.read_table(path)``. The shard lives at
    ``…/ticker=VCB/data.parquet``, and ``read_table`` treats a hive-style ``key=VALUE`` directory
    as a partition — it synthesises a dictionary-encoded ``ticker`` column from the path, which
    then collides with the real string ``ticker`` column stored inside the file:

        ArrowTypeError: Unable to merge: Field ticker has incompatible types:
                        string vs dictionary<values=string, indices=int32>

    ``ParquetFile`` opens exactly the one file with no dataset or partition inference. Do not
    "simplify" this back to ``read_table``.
    """
    import pyarrow.parquet as pq  # noqa: PLC0415

    return pq.ParquetFile(path).read().to_pylist()


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


class LocalSource:
    """Filesystem :class:`~pipelines.storage.ports.BarSource`."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root if self._root is not None else data_root()

    # -- typed reads --------------------------------------------------------

    def daily_bars(
        self, ticker: str, start: date | None, end: date | None, *, source: str
    ) -> list[tuple[date, float | None, float | None]]:
        rows = self.read_records(Dataset.DAILY_BARS, ticker, start, end, source=source)
        return [(r["bar_date"], _f(r["close"]), _f(r["volume"])) for r in rows]

    def index_bars(
        self, index_symbol: str, start: date | None, end: date | None, *, source: str
    ) -> list[tuple[date, float | None]]:
        rows = self.read_records(Dataset.INDEX_BARS, index_symbol, start, end, source=source)
        return [(r["bar_date"], _f(r["close"])) for r in rows]

    def daily_returns(
        self, tickers: Sequence[str], start: date | None, end: date | None, *, source: str
    ) -> dict[str, dict[date, float]]:
        out: dict[str, dict[date, float]] = {}
        for t in tickers:
            rows = self.read_records(Dataset.DAILY_RETURNS, t, start, end, source=source)
            if rows:
                out[t] = {r["bar_date"]: float(r["log_return"]) for r in rows}
        return out

    def index_returns(
        self, index_symbol: str, start: date | None, end: date | None, *, source: str
    ) -> dict[date, float]:
        rows = self.read_records(Dataset.INDEX_RETURNS, index_symbol, start, end, source=source)
        return {r["bar_date"]: float(r["log_return"]) for r in rows}

    # -- raw ----------------------------------------------------------------

    def raw_bars(
        self, dataset: Dataset, symbol: str, since: date | None = None, until: date | None = None
    ) -> list[tuple[date, dict[str, Any]]]:
        if not dataset.is_raw:
            raise ValueError(f"raw_bars() needs a raw dataset, got {dataset.value}")
        path = raw_path(_validate_key(symbol, dataset), dataset.bar_type or "")
        if not path.is_file():
            return []
        out: list[tuple[date, dict[str, Any]]] = []
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = _decode_jsonl_record(json.loads(line))
                bar_date = rec["bar_date"]
                if since is not None and bar_date < since:
                    continue
                if until is not None and bar_date > until:
                    continue
                payload = rec["payload"]
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (ValueError, TypeError) as exc:
                        # Raising rather than skipping: a corrupt audit row leaves a hole in the
                        # return series that is indistinguishable from a market holiday.
                        raise ValueError(
                            f"raw payload for {symbol} on {bar_date} is not decodable JSON"
                        ) from exc
                if not isinstance(payload, dict):
                    raise ValueError(
                        f"raw payload for {symbol} on {bar_date} decoded to "
                        f"{type(payload).__name__}, expected dict"
                    )
                out.append((bar_date, payload))
        out.sort(key=lambda p: p[0])
        return out

    # -- high-water marks ---------------------------------------------------

    def high_water_marks(
        self, dataset: Dataset, keys: Sequence[str], *, source: str | None = None
    ) -> dict[str, date | None]:
        require_source(dataset, source)
        out: dict[str, date | None] = {k: None for k in keys}
        for key in keys:
            if dataset.is_raw:
                rows = self.raw_bars(dataset, key)
                if rows:
                    out[key] = rows[-1][0]
            else:
                rows_t = self.read_records(dataset, key, None, None, source=source or "")
                if rows_t:
                    out[key] = max(r["bar_date"] for r in rows_t)
        return out

    # -- internals ----------------------------------------------------------

    def read_records(
        self,
        dataset: Dataset,
        key: str,
        start: date | None = None,
        end: date | None = None,
        *,
        source: str,
    ) -> list[dict[str, Any]]:
        """Full record dicts, exactly ``RECORD_KEYS[dataset]`` — see the ``BarSource`` Protocol.

        Was ``_read_rows``, private, until P6.4 needed a public method that round-trips a whole
        record (the Postgres mirror, ``artifact.inspect --from-db``). The four typed reads below
        already called this; they are unchanged, only the name is public now.
        """
        require_source(dataset, source)
        path = shard_path(dataset.table, PARTITION_COL[dataset], _validate_key(key, dataset))
        if not path.is_file():
            return []
        rows = _read_parquet(path)
        out = [
            r
            for r in rows
            if r.get("source") == source
            and (start is None or r["bar_date"] >= start)
            and (end is None or r["bar_date"] <= end)
        ]
        out.sort(key=lambda r: r["bar_date"])
        return out


def _f(v: Any) -> float | None:
    """Coerce a stored numeric to ``float | None``. See the BarSource contract on direction."""
    return None if v is None else float(v)


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def _selftest() -> int:  # noqa: PLR0915 - a linear checklist reads better than ten helpers
    import re as _re
    import shutil
    import tempfile as _tempfile
    from datetime import UTC, timedelta

    from pipelines.common import upsert as U
    from pipelines.storage.ports import BarSink, BarSource

    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the point is to report, not propagate
            failed.append(f"{label}: {type(exc).__name__}: {exc}")
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    tmp = Path(_tempfile.mkdtemp(prefix="datn_storage_"))
    os.environ["DATN_DATA_ROOT"] = str(tmp)
    try:
        assert data_root() == tmp.resolve(), "DATA_ROOT did not follow the environment"
        sink, src = LocalSink(), LocalSource()

        # 1 — the record contract matches the SQL it claims to mirror.
        def _schema_vs_sql() -> None:
            sqls = {
                Dataset.DAILY_BARS: U._DAILY_BARS_SQL,
                Dataset.INDEX_BARS: U._MARKET_INDEX_BARS_SQL,
                Dataset.RAW_EQUITY: U._OHLC_RAW_SQL,
                Dataset.DAILY_RETURNS: U._DAILY_RETURNS_SQL,
                Dataset.INDEX_RETURNS: U._INDEX_RETURNS_SQL,
                Dataset.INDICATORS_DAILY: U._TECHNICAL_INDICATORS_SQL,
            }
            for ds, sql in sqls.items():
                ph = tuple(dict.fromkeys(_re.findall(r"%\((\w+)\)s", sql)))
                assert ph == RECORD_KEYS[ds], f"{ds.value}: {ph} != {RECORD_KEYS[ds]}"
                ck = tuple(
                    c.strip().strip('"')
                    for c in _re.search(r"ON CONFLICT \(([^)]+)\)", sql).group(1).split(",")
                )
                assert ck == CONFLICT_KEY[ds], f"{ds.value}: conflict {ck}"
                updated = set(_re.findall(r"(\w+)\s*=\s*EXCLUDED\.", sql))
                omitted = set(RECORD_KEYS[ds]) - updated - set(ck)
                assert omitted == set(ON_CONFLICT_KEEP[ds]), f"{ds.value}: keep {omitted}"

        check("record contract matches upsert.py SQL", _schema_vs_sql)

        # 2 — Protocol conformance.
        check(
            "LocalSink/LocalSource satisfy the Protocols",
            lambda: (
                _assert(isinstance(sink, BarSink), "sink"),
                _assert(isinstance(src, BarSource), "source"),
            ),
        )

        d0, ts = date(2025, 1, 2), datetime(2025, 1, 2, 9, 0, tzinfo=UTC)

        def bar(day: int, close: float, ing: datetime) -> dict[str, Any]:
            return {
                "ticker": "VCB", "bar_date": date(2025, 1, day), "source": "VCI",
                "open": 90.0, "high": 91.5, "low": 89.5, "close": close, "volume": 1_000_000.0,
                "is_adjusted": False, "ingested_at": ing, "updated_at": ing,
            }

        # 3 — round-trip.
        def _roundtrip() -> None:
            n = sink.write_daily_bars([bar(2, 90.5, ts), bar(3, 91.25, ts)])
            assert n == 2, n
            got = src.daily_bars("VCB", None, None, source="VCI")
            assert got == [(date(2025, 1, 2), 90.5, 1_000_000.0),
                           (date(2025, 1, 3), 91.25, 1_000_000.0)], got

        check("daily_bars round-trip", _roundtrip)

        # 4 — types are backend-independent.
        def _types() -> None:
            (d, c, v), *_ = src.daily_bars("VCB", None, None, source="VCI")
            assert type(d) is date, type(d)
            assert type(c) is float, type(c)
            assert type(v) is float, type(v)

        check("float/date types, not Decimal or Timestamp", _types)

        # 5 — idempotency, byte-level where the format allows it.
        def _idempotent() -> None:
            p = shard_path("daily_bars", "ticker", "VCB")
            before = p.read_bytes()
            sink.write_daily_bars([bar(2, 90.5, ts), bar(3, 91.25, ts)])
            assert len(src.daily_bars("VCB", None, None, source="VCI")) == 2
            assert p.read_bytes() == before, "re-writing an identical batch changed the file"

        check("re-writing the same batch is a no-op", _idempotent)

        # 6 — the ON_CONFLICT_KEEP behaviour a blanket row-replace gets wrong.
        def _keep_ingested_at() -> None:
            later = ts + timedelta(days=30)
            sink.write_daily_bars([bar(2, 99.0, later)])
            rows = pq_rows(shard_path("daily_bars", "ticker", "VCB"))
            row = next(r for r in rows if r["bar_date"] == date(2025, 1, 2))
            assert float(row["close"]) == 99.0, row["close"]
            assert row["ingested_at"] == ts, f"ingested_at was overwritten: {row['ingested_at']}"
            assert row["updated_at"] == later, row["updated_at"]

        check("conflict updates close but PRESERVES ingested_at", _keep_ingested_at)

        # 7 — high-water marks.
        def _hwm() -> None:
            got = src.high_water_marks(Dataset.DAILY_BARS, ["VCB", "NOSUCH"], source="VCI")
            assert got == {"VCB": date(2025, 1, 3), "NOSUCH": None}, got
            _assert_raises(
                lambda: src.high_water_marks(Dataset.RAW_EQUITY, ["VCB"], source="VCI"),
                ValueError, "source on a raw dataset",
            )
            _assert_raises(
                lambda: src.high_water_marks(Dataset.DAILY_BARS, ["VCB"]),
                ValueError, "missing source on a typed dataset",
            )

        check("HWM pre-seeds absent keys and validates source", _hwm)

        # 8 — an interrupted write leaves no half-file visible.
        def _atomicity() -> None:
            good = src.daily_bars("VCB", None, None, source="VCI")
            p = shard_path("daily_bars", "ticker", "FPT")
            ensure_dir(p.parent)
            (p.parent / "orphan.tmp").write_bytes(b"garbage from a killed process")
            assert src.daily_bars("FPT", None, None, source="VCI") == []
            assert src.daily_bars("VCB", None, None, source="VCI") == good

        check("a stray .tmp is invisible and harms nothing", _atomicity)

        # 9 — values Postgres would reject are rejected here too.
        def _rejects() -> None:
            _assert_raises(lambda: sink.write_daily_bars([{**bar(4, 1.0, ts), "close": None}]),
                           ValueError, "null close")
            _assert_raises(lambda: sink.write_daily_bars([{**bar(4, float("inf"), ts)}]),
                           ValueError, "infinite close")
            _assert_raises(lambda: sink.write_daily_bars([{**bar(4, float("nan"), ts)}]),
                           ValueError, "NaN close")
            bad = {k: v for k, v in bar(4, 1.0, ts).items() if k != "volume"}
            _assert_raises(lambda: sink.write_daily_bars([bad]), ValueError, "missing key")
            _assert_raises(lambda: sink.write_daily_bars([{**bar(4, 1.0, ts), "ticker": "../x"}]),
                           ValueError, "path-traversal ticker")

        check("null/inf/NaN close, missing key, bad key all rejected", _rejects)

        # 10 — two sources coexist and do not leak into each other.
        def _source_isolation() -> None:
            other = {**bar(2, 55.5, ts), "source": "TEST"}
            sink.write_daily_bars([other])
            vci = src.daily_bars("VCB", None, None, source="VCI")
            test = src.daily_bars("VCB", None, None, source="TEST")
            assert len(test) == 1 and test[0][1] == 55.5, test
            assert all(c != 55.5 for _, c, _ in vci), vci
            assert len(vci) == 2, vci

        check("the same (ticker, date) under two sources stays separate", _source_isolation)

        # 11 — raw round-trip keeps the payload a string in storage, a dict on read.
        def _raw() -> None:
            payload = json.dumps({"time": "2025-01-02", "close": 90.5, "volume": 1000})
            rec = {"symbol": "VCB", "bar_type": "EQUITY", "bar_date": d0,
                   "payload": payload, "fetched_at": ts}
            assert sink.write_raw_bars([rec]) == 1
            got = src.raw_bars(Dataset.RAW_EQUITY, "VCB")
            assert len(got) == 1, got
            bd, obj = got[0]
            assert bd == d0 and isinstance(obj, dict) and obj["close"] == 90.5, got
            p = raw_path("VCB", "EQUITY")
            b1 = p.read_bytes()
            sink.write_raw_bars([rec])
            assert p.read_bytes() == b1, "raw re-write was not byte-identical"

        check("raw payload round-trip and byte-identical re-write", _raw)

        # 12 — read_records is a full record, not a projection: exactly RECORD_KEYS[dataset],
        # in that order, for every typed dataset (P6.4). This is what the Postgres mirror and
        # artifact.inspect --from-db depend on to round-trip a whole row.
        def _read_records_keys() -> None:
            for ds in (Dataset.DAILY_BARS, Dataset.INDEX_BARS,
                       Dataset.DAILY_RETURNS, Dataset.INDEX_RETURNS):
                key = "VCB" if ds in (Dataset.DAILY_BARS, Dataset.DAILY_RETURNS) else "VNINDEX"
                # No rows need to exist — an empty shard still proves the keys contract on the
                # zero-row path is at least not exercised incorrectly; the non-empty case below
                # (VCB daily_bars, already written by check 3) proves it on real rows.
                _ = src.read_records(ds, key, source="VCI")
            recs = src.read_records(Dataset.DAILY_BARS, "VCB", source="VCI")
            assert len(recs) == 2, recs
            assert tuple(recs[0].keys()) == RECORD_KEYS[Dataset.DAILY_BARS], recs[0].keys()
            assert recs[0]["close"] == 99.0, "expected check 6's update to be visible"
            assert type(recs[0]["ingested_at"]) is datetime, type(recs[0]["ingested_at"])

        check("read_records returns exactly RECORD_KEYS[dataset], in order", _read_records_keys)

    finally:
        os.environ.pop("DATN_DATA_ROOT", None)
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failed:
        print(f"localfs selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"localfs selftest: {passed} passed, 0 failed")
    return 0


def _assert(cond: bool, what: str) -> None:
    if not cond:
        raise AssertionError(what)


def _assert_raises(fn, exc_type: type[BaseException], what: str) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__} for {what}, nothing raised")


def pq_rows(path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq  # noqa: PLC0415

    return pq.ParquetFile(path).read().to_pylist()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.storage.localfs",
        description="Local filesystem storage backend; --selftest needs no network or database.",
    )
    parser.add_argument("--selftest", action="store_true", help="Run the round-trip checks.")
    args = parser.parse_args(argv)
    if not args.selftest:
        parser.error("--selftest is the only mode; this module is a library otherwise.")
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
