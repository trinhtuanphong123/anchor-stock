"""pipelines.ingestion.normalize — raw payloads and provider rows -> typed records.

Pure. No I/O, no database, no network. Everything here is a function of its arguments, which is
what makes the ``--selftest`` below provable with no network and no database.

Two layers:

**Raw-record construction** (absorbed from the old ``pipelines/ingestion/staging.py``):
:func:`build_raw_records` turns provider rows into the exact dicts
:meth:`~pipelines.storage.ports.BarSink.write_raw_bars` expects — ``RECORD_KEYS[Dataset.RAW_*]``.
``payload`` is a pre-serialised JSON **string**, matching the ``::jsonb`` cast on the Postgres
side and the byte-identical-file guarantee on the local side.

**Bar normalisation**: :func:`normalize_bars` turns landed raw payloads into the typed records
``write_daily_bars`` / `write_index_bars`` expect. ONE function for both datasets — the old code
had two (``daily._normalize_row`` and ``index_bars._normalize_index_row``) that disagreed on
which fields were required. See the docstring on :func:`normalize_bars` for the resolution.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from pipelines.storage.ports import PARTITION_COL, RECORD_KEYS, Dataset

__all__ = [
    "DroppedRow",
    "NormalizeResult",
    "build_raw_records",
    "extract_bar_date",
    "json_safe",
    "normalize_bars",
]


# ---------------------------------------------------------------------------
# Raw-record construction (moved from staging.py, unchanged behaviour)
# ---------------------------------------------------------------------------


def json_safe(v: Any) -> Any:
    """Coerce one raw cell to a JSON-native value (dates→ISO, numpy→scalar, non-finite→None).

    Non-finite floats become ``None``, not just NaN. ``json.dumps`` emits bare ``Infinity`` for
    an infinity, which is not valid JSON: Postgres ``::jsonb`` rejects the whole statement and a
    best-effort caller can turn that into a silently missing audit row. Mapping it to NULL here,
    plus ``allow_nan=False`` at the dump site, means a future gap raises loudly instead of
    disappearing.
    """
    if v is None:
        return None
    if isinstance(v, (datetime, date)):  # pandas Timestamp is a datetime subclass
        return v.isoformat()
    if hasattr(v, "item"):  # numpy / pandas scalar
        try:
            v = v.item()
        except Exception:  # noqa: BLE001
            return str(v)
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, (str, int, bool)):
        return v
    return str(v)


def extract_bar_date(raw: dict[str, Any]) -> date | None:
    """Parse the bar date from a raw row's ``time`` field, or ``None``."""
    t = raw.get("time")
    if t is None:
        return None
    try:
        import pandas as pd  # type: ignore[import-untyped]  # noqa: PLC0415

        if pd.isna(t):
            return None
        return pd.to_datetime(t).date()
    except Exception:  # noqa: BLE001
        return None


def build_raw_records(
    dataset: Dataset,
    symbol: str,
    raw_rows: list[dict[str, Any]],
    *,
    fetched_at: datetime,
) -> list[dict[str, Any]]:
    """Build ``staging.ohlc_raw`` records from raw provider rows.

    ``dataset`` must be a raw dataset (``RAW_EQUITY`` / ``RAW_INDEX``); its ``.bar_type`` supplies
    the stored discriminator, so ``bar_type="EQUITIES"`` (a typo) is unconstructible here.

    ``fetched_at`` is a required keyword, not read from the clock internally. That is the whole
    point: every record built by one call to this function — and, by convention, every call made
    during one run of ``pipelines.ingestion.fetch`` — carries the SAME timestamp. Because the
    provider's adjusted-close series is re-anchored to the present on every corporate action
    (verified empirically — see ``docs/decisions/D-06``), that shared timestamp is the run's
    adjustment basis: "this is the series as the provider had it adjusted at exactly this
    instant". Letting each row stamp itself with ``datetime.now()`` would give one run as many
    different answers to "adjusted as of when?" as it has rows.

    One row per parseable bar date; the full raw dict is stored JSON-safe as the payload. Rows
    without a usable date are skipped, not counted here — the caller (``fetch.py``) knows how
    many rows it started with and can compute the drop count itself; duplicating that arithmetic
    inside a pure builder would be a second source of truth for the same number.
    """
    if not dataset.is_raw:
        raise ValueError(f"build_raw_records needs a raw dataset, got {dataset.value}")
    bar_type = dataset.bar_type
    out: list[dict[str, Any]] = []
    for raw in raw_rows:
        bar_date = extract_bar_date(raw)
        if bar_date is None:
            continue
        payload = json.dumps(
            {str(k): json_safe(val) for k, val in raw.items()}, allow_nan=False
        )
        out.append(
            {
                "symbol": symbol,
                "bar_type": bar_type,
                "bar_date": bar_date,
                "payload": payload,
                "fetched_at": fetched_at,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Bar normalisation — one function for both typed datasets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DroppedRow:
    """A raw payload that could not become a typed record, and why."""

    index: int
    bar_date: date | None
    reason: str  # "no_date" | "no_close"


@dataclass(frozen=True)
class NormalizeResult:
    dataset: Dataset
    records: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[DroppedRow] = field(default_factory=list)
    n_input: int = 0


def _num(v: Any) -> float | None:
    """Coerce a raw cell to ``float | None``, never NaN/inf.

    The finiteness test is the LAST statement, outside every exception handler. This is a
    deliberate departure from the old ``daily._float``, which put ``raise ValueError("null")``
    for a NaN *inside* a ``try`` whose own ``except (TypeError, ValueError): pass`` swallowed
    that very exception — so a NaN fell through to ``float(nan)`` and reached the record intact,
    later passing ``_check_sanity_bounds`` (``nan <= 0`` is ``False``) and getting upserted. There
    is no ``raise`` inside a ``try`` anywhere in this function; a non-finite value simply becomes
    ``None`` and is handled by the normal nullable-field path.
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalize_bars(
    dataset: Dataset,
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    source: str,
    now: datetime,
) -> NormalizeResult:
    """Turn raw payloads into typed records for ``dataset`` (``DAILY_BARS`` or ``INDEX_BARS``).

    One function for both datasets, where the old code had two that quietly disagreed:
    ``daily._normalize_row`` required ALL of open/high/low/close/volume and dropped the whole
    bar if any was missing; ``index_bars._normalize_index_row`` required only ``close``.

    **The index rule wins: only ``close`` is required.** ``close`` is the model's only price
    input (the same rule ``pipelines.storage.localfs._CLOSE_REQUIRED`` enforces at the storage
    boundary — restating it here would be a second source of truth). Requiring the other four
    is actively harmful: dropping a bar because ``volume`` is null on a genuinely illiquid
    session deletes a real trading day, and the next computed return silently becomes
    ``ln(P_t / P_{t-2})`` wearing the shape of a one-day return — a FABRICATED return, exactly
    what ``docs/01-data-pipeline.md`` §1 forbids, arriving through a different door. The
    strictness is not lost, it is relocated: a null count per column is available to the caller
    via ``pipelines.ingestion.quality``, which reports it rather than silently deleting the row.

    ``dataset`` fixes which columns the emitted records carry, driven by ``RECORD_KEYS`` and
    ``PARTITION_COL`` rather than two hand-written key lists: ``DAILY_BARS`` records get
    ``is_adjusted``; ``INDEX_BARS`` records do not. That structural difference is now DATA (a
    lookup against ``ports.RECORD_KEYS``), not two separate functions that can drift apart.

    ``source`` and ``now`` are required keywords, not module constants. The old files each
    hardcoded their own ``SOURCE = "VCI"``; a single caller-supplied value means there is exactly
    one place that can disagree with ``pipelines/returns/build.py``'s own ``SOURCE`` constant.
    ``ingested_at`` and ``updated_at`` are both set to ``now`` (equal only on first write — the
    storage layer's ``ON_CONFLICT_KEEP`` preserves the original ``ingested_at`` on a re-run).
    """
    if dataset not in (Dataset.DAILY_BARS, Dataset.INDEX_BARS):
        raise ValueError(f"normalize_bars needs a typed bar dataset, got {dataset.value}")

    key_col = PARTITION_COL[dataset]
    keys = RECORD_KEYS[dataset]
    is_adjusted = dataset is Dataset.DAILY_BARS

    records: list[dict[str, Any]] = []
    dropped: list[DroppedRow] = []

    for i, raw in enumerate(rows):
        bar_date = extract_bar_date(raw)
        if bar_date is None:
            dropped.append(DroppedRow(index=i, bar_date=None, reason="no_date"))
            continue

        close = _num(raw.get("close"))
        if close is None:
            dropped.append(DroppedRow(index=i, bar_date=bar_date, reason="no_close"))
            continue

        values: dict[str, Any] = {
            key_col: symbol,
            "bar_date": bar_date,
            "source": source,
            "open": _num(raw.get("open")),
            "high": _num(raw.get("high")),
            "low": _num(raw.get("low")),
            "close": close,
            "volume": _num(raw.get("volume")),
            "ingested_at": now,
            "updated_at": now,
        }
        if is_adjusted:
            values["is_adjusted"] = True

        record = {k: values[k] for k in keys}
        assert set(record) == set(keys), (
            f"{dataset.value}: built {sorted(record)}, RECORD_KEYS wants {sorted(keys)}"
        )
        records.append(record)

    return NormalizeResult(dataset=dataset, records=records, dropped=dropped, n_input=len(rows))


# ---------------------------------------------------------------------------
# Self-check — pure, no network, no database
# ---------------------------------------------------------------------------


def _selftest() -> int:  # noqa: PLR0915 - a linear checklist
    from pipelines.storage.localfs import _validate_records
    from pipelines.storage.ports import CONFLICT_KEY

    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed.append(label)
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    now = datetime(2025, 1, 2, 9, 0, tzinfo=UTC)

    def row(t: str, o=90.0, h=91.0, lo=89.0, c=90.5, v=1_000_000):  # noqa: ANN001
        return {"time": t, "open": o, "high": h, "low": lo, "close": c, "volume": v}

    good_daily = [row("2025-01-02"), row("2025-01-03", c=91.0)]
    good_index = [row("2025-01-02", o=None, h=None, lo=None, v=None), row("2025-01-03")]

    def _record_keys_exact() -> None:
        r = normalize_bars(Dataset.DAILY_BARS, "VCB", good_daily, source="VCI", now=now)
        assert len(r.records) == 2, r
        assert set(r.records[0]) == set(RECORD_KEYS[Dataset.DAILY_BARS]), r.records[0]
        r2 = normalize_bars(Dataset.INDEX_BARS, "VNINDEX", good_index, source="VCI", now=now)
        assert set(r2.records[0]) == set(RECORD_KEYS[Dataset.INDEX_BARS]), r2.records[0]
        assert "is_adjusted" not in r2.records[0], r2.records[0]

    check("record keys match RECORD_KEYS exactly for both datasets", _record_keys_exact)

    def _nan_close_dropped() -> None:
        rows = [row("2025-01-02", c=float("nan")), row("2025-01-03")]
        r = normalize_bars(Dataset.DAILY_BARS, "VCB", rows, source="VCI", now=now)
        assert len(r.records) == 1, r
        assert r.dropped == [DroppedRow(index=0, bar_date=date(2025, 1, 2), reason="no_close")]
        for rec in r.records:
            for v in rec.values():
                assert not (isinstance(v, float) and math.isnan(v)), rec

    check("NaN close is dropped and no record ever contains NaN", _nan_close_dropped)

    def _inf_close_dropped() -> None:
        rows = [row("2025-01-02", c=float("inf"))]
        r = normalize_bars(Dataset.DAILY_BARS, "VCB", rows, source="VCI", now=now)
        assert r.records == [] and r.dropped[0].reason == "no_close"

    check("infinite close is dropped like NaN", _inf_close_dropped)

    def _null_volume_kept() -> None:
        rows = [row("2025-01-02", v=None)]
        r = normalize_bars(Dataset.DAILY_BARS, "VCB", rows, source="VCI", now=now)
        assert len(r.records) == 1, r
        assert r.records[0]["volume"] is None, r.records[0]
        assert r.dropped == [], r.dropped

    check("null volume KEEPS the row (only close is required)", _null_volume_kept)

    def _no_date_dropped() -> None:
        rows = [{"open": 1.0, "close": 1.0}, row("not-a-date")]
        r = normalize_bars(Dataset.DAILY_BARS, "VCB", rows, source="VCI", now=now)
        assert r.records == [], r.records
        assert [d.reason for d in r.dropped] == ["no_date", "no_date"], r.dropped

    check("missing or unparseable time is dropped as no_date", _no_date_dropped)

    def _is_adjusted() -> None:
        r = normalize_bars(Dataset.DAILY_BARS, "VCB", good_daily, source="VCI", now=now)
        assert all(rec["is_adjusted"] is True for rec in r.records), r.records

    check("every DAILY_BARS record has is_adjusted = True", _is_adjusted)

    def _purity() -> None:
        a = normalize_bars(Dataset.DAILY_BARS, "VCB", good_daily, source="VCI", now=now)
        b = normalize_bars(Dataset.DAILY_BARS, "VCB", good_daily, source="VCI", now=now)
        assert a.records == b.records, (a.records, b.records)
        stamps = {rec["ingested_at"] for rec in a.records}
        stamps |= {rec["updated_at"] for rec in a.records}
        assert stamps == {now}, stamps

    check("same input + same now -> identical output; one timestamp for the whole call", _purity)

    def _survives_storage_validation() -> None:
        r = normalize_bars(Dataset.DAILY_BARS, "VCB", good_daily, source="VCI", now=now)
        _validate_records(Dataset.DAILY_BARS, r.records)  # raises on failure
        r2 = normalize_bars(Dataset.INDEX_BARS, "VNINDEX", good_index, source="VCI", now=now)
        _validate_records(Dataset.INDEX_BARS, r2.records)

    check("normalized records pass localfs._validate_records", _survives_storage_validation)

    def _raw_records_shape() -> None:
        raw = [{"time": "2025-01-02", "close": 90.5, "note": float("inf")}]
        recs = build_raw_records(Dataset.RAW_EQUITY, "VCB", raw, fetched_at=now)
        assert len(recs) == 1, recs
        rec = recs[0]
        assert rec["bar_type"] == "EQUITY", rec
        assert rec["fetched_at"] == now, rec
        decoded = json.loads(rec["payload"])
        assert decoded["note"] is None, decoded  # inf -> None, never bare Infinity
        assert decoded["close"] == 90.5, decoded

    check(
        "build_raw_records: dataset.bar_type used, inf sanitised, payload round-trips",
        _raw_records_shape,
    )

    def _raw_records_reject_typed() -> None:
        try:
            build_raw_records(Dataset.DAILY_BARS, "VCB", [], fetched_at=now)
        except ValueError:
            return
        raise AssertionError("expected ValueError for a non-raw dataset")

    check("build_raw_records rejects a non-raw Dataset", _raw_records_reject_typed)

    def _conflict_key_present() -> None:
        for ds in (Dataset.DAILY_BARS, Dataset.INDEX_BARS):
            for col in CONFLICT_KEY[ds]:
                assert col in RECORD_KEYS[ds], (ds, col)

    check("every conflict-key column is among the emitted keys", _conflict_key_present)

    print()
    if failed:
        print(f"normalize selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"normalize selftest: {passed} passed, 0 failed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.ingestion.normalize",
        description="Pure raw->typed normalisation; --selftest needs no network or database.",
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if not args.selftest:
        parser.error("--selftest is the only mode; this module is a library otherwise.")
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
