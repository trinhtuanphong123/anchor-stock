"""pipelines.storage.mirror — LocalSource -> BarSink, port to port, no transformation.

P6.2: the two-track promise is that flipping the sink is the only difference between the local
train track and the dashboard track. This module is what makes that literal for market data
already on disk, rather than re-fetching six years against a throttled provider a second time.

Deliberately thin: every record crosses the seam through :meth:`~pipelines.storage.ports.
BarSource.read_records` (P6.4) unmodified, then a dataset-specific ``BarSink`` write method.
No field is renamed, computed, or dropped here — if the two backends ever disagree about a
record's shape, that is ``RECORD_KEYS`` drifting, and ``localfs.py``/``pg.py``'s own
``--selftest``s are where that gets caught, not this module.

Raw payloads (``staging.ohlc_raw``) are deliberately NOT mirrored (D-14): a local-track
artefact nothing serving reads, and mirroring it would also need
:meth:`~pipelines.storage.ports.BarSource.raw_bars` — a different, non-``read_records`` read
path — for zero downstream benefit.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pipelines.storage.ports import BarSink, BarSource, Dataset

__all__ = ["MIRRORED", "MirrorDatasetReport", "mirror_all", "mirror_dataset"]

#: The typed datasets landed in Postgres — two from P6, plus ``technical_indicators_daily``
#: from P7. Order matches the parent plan's FK note: bars before the indicators derived from
#: them, though only ``stocks`` (populated by ``pipelines.universe.sync``, P6.3) is actually
#: load-bearing for the FK on this list — ``daily_bars.ticker`` and
#: ``technical_indicators_daily.ticker`` both ``REFERENCES stocks``; ``market_index_bars``
#: carries no such FK.
#:
#: Indicators come last because they are derived from ``daily_bars``: mirroring them after the
#: bars they were computed from keeps the FK order and the causal order the same.
#:
#: ``DAILY_RETURNS`` / ``INDEX_RETURNS`` were here through P14 and are gone as of P15
#: (supabase/migrations/00003_returns.sql): both are now VIEWs over ``daily_bars`` /
#: ``market_index_bars``, so there is nothing for the Postgres mirror to submit — mirroring a
#: view's own source data INTO it would be a no-op at best and a conflict at worst. The local
#: track still writes them (research archive); this asymmetry is the same shape D-14 already
#: established for ``staging.ohlc_raw`` — local writes it, the Postgres track does not.
MIRRORED: tuple[Dataset, ...] = (
    Dataset.DAILY_BARS, Dataset.INDEX_BARS, Dataset.INDICATORS_DAILY,
)

#: Dataset -> the BarSink write method that accepts its records, keyed by name so this module
#: never has to import a backend and can be handed any BarSink implementation.
_SINK_METHOD: dict[Dataset, str] = {
    Dataset.DAILY_BARS: "write_daily_bars",
    Dataset.INDEX_BARS: "write_index_bars",
    Dataset.INDICATORS_DAILY: "write_indicators",
}


@dataclass
class MirrorDatasetReport:
    """One dataset's mirror outcome. A partial mirror is visible here, not inferred from a
    row count check run separately afterwards.
    """

    dataset: str
    keys_attempted: int
    keys_empty: list[str] = field(default_factory=list)
    records_read: int = 0
    records_submitted: int = 0

    @property
    def ok(self) -> bool:
        """True iff every attempted key produced at least one record.

        An empty key is not automatically a failure — a ticker with no bars in the requested
        window is a legitimate state (a listing gap, a name that IPO'd mid-window) — but it must
        be named, which is exactly what ``keys_empty`` is for.
        """
        return self.records_read == self.records_submitted


def mirror_dataset(
    dataset: Dataset,
    keys: Sequence[str],
    *,
    src: BarSource,
    sink: BarSink,
    source: str,
    batch: int = 5000,
) -> MirrorDatasetReport:
    """Mirror one dataset for ``keys`` (tickers, or the one index symbol).

    Reads the FULL history per key via :meth:`BarSource.read_records` (no date window — the
    frozen 2020-2025 shards and any 2026 append both cross in one call) and submits it to
    ``sink`` in batches of ``batch``. Both backends' writes are idempotent upserts (P0/P1), so
    re-running this function is always safe.
    """
    write: Callable[[list[dict[str, Any]]], int] = getattr(sink, _SINK_METHOD[dataset])
    report = MirrorDatasetReport(dataset=dataset.value, keys_attempted=len(keys))

    for key in keys:
        records = src.read_records(dataset, key, source=source)
        if not records:
            report.keys_empty.append(key)
            continue
        report.records_read += len(records)
        for i in range(0, len(records), batch):
            report.records_submitted += write(records[i : i + batch])

    return report


def mirror_all(
    tickers: Sequence[str],
    index_symbols: Sequence[str],
    *,
    src: BarSource,
    sink: BarSink,
    source: str,
) -> list[MirrorDatasetReport]:
    """Mirror every :data:`MIRRORED` dataset: per-ticker datasets keyed by ``tickers``, index
    datasets keyed by ``index_symbols``. Returns one report per dataset, in ``MIRRORED`` order.

    ``technical_indicators_daily`` is keyed by ticker like the other per-ticker datasets, so it
    needs no routing of its own — but it reports every ticker in ``keys_empty`` until
    ``pipelines.indicators.build`` has actually run, which is a real state and not a failure.
    """
    reports: list[MirrorDatasetReport] = []
    for dataset in MIRRORED:
        keys = index_symbols if dataset in (Dataset.INDEX_BARS, Dataset.INDEX_RETURNS) else tickers
        reports.append(mirror_dataset(dataset, keys, src=src, sink=sink, source=source))
    return reports


# ---------------------------------------------------------------------------
# Self-check — no database, no network. A fake BarSink/BarSource pair proves the batching,
# empty-key reporting, and full-history (no date window) behaviour without either backend.
# ---------------------------------------------------------------------------


class _FakeSource:
    def __init__(self, table: dict[tuple[Dataset, str], list[dict[str, Any]]]) -> None:
        self._table = table

    def read_records(self, dataset, key, start=None, end=None, *, source):  # noqa: ANN001
        return list(self._table.get((dataset, key), []))


class _FakeSink:
    def __init__(self) -> None:
        self.written: dict[str, list[dict[str, Any]]] = {
            "write_daily_bars": [], "write_index_bars": [], "write_indicators": [],
        }

    def _record(self, method: str, records: list[dict[str, Any]]) -> int:
        self.written[method].extend(records)
        return len(records)

    def write_raw_bars(self, records):  # noqa: ANN001, D102
        raise AssertionError("mirror must never call write_raw_bars (D-14)")

    def write_daily_bars(self, records):  # noqa: ANN001, D102
        return self._record("write_daily_bars", records)

    def write_index_bars(self, records):  # noqa: ANN001, D102
        return self._record("write_index_bars", records)

    def write_daily_returns(self, records):  # noqa: ANN001, D102
        raise AssertionError("mirror must never call write_daily_returns (P15: view, not table)")

    def write_index_returns(self, records):  # noqa: ANN001, D102
        raise AssertionError("mirror must never call write_index_returns (P15: view, not table)")

    def write_indicators(self, records):  # noqa: ANN001, D102
        return self._record("write_indicators", records)


def _selftest() -> int:
    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:  # noqa: ANN001
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed.append(label)
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    def rec(i: int) -> dict[str, Any]:
        return {"ticker": "VCB", "bar_date": i, "source": "VCI", "close": float(i)}

    table = {
        (Dataset.DAILY_BARS, "VCB"): [rec(i) for i in range(3)],
        (Dataset.DAILY_BARS, "EMPTY"): [],
        (Dataset.DAILY_BARS, "BATCH"): [rec(i) for i in range(12)],
        (Dataset.INDEX_BARS, "VNINDEX"): [rec(i) for i in range(2)],
        (Dataset.INDICATORS_DAILY, "VCB"): [rec(i) for i in range(4)],
    }
    src = _FakeSource(table)

    def _basic() -> None:
        sink = _FakeSink()
        r = mirror_dataset(Dataset.DAILY_BARS, ["VCB"], src=src, sink=sink, source="VCI")
        _assert(r.records_read == 3 and r.records_submitted == 3, r)
        _assert(r.keys_empty == [], r)
        _assert(r.ok, r)
        _assert(len(sink.written["write_daily_bars"]) == 3, sink.written)

    check("basic mirror: read == submitted, no empty keys", _basic)

    def _empty_key_visible() -> None:
        sink = _FakeSink()
        r = mirror_dataset(Dataset.DAILY_BARS, ["VCB", "EMPTY"], src=src, sink=sink, source="VCI")
        _assert(r.keys_attempted == 2, r)
        _assert(r.keys_empty == ["EMPTY"], r)
        _assert(r.records_read == 3, r)

    check("a key with no records is named in keys_empty, not silently skipped", _empty_key_visible)

    def _batching() -> None:
        sink = _FakeSink()
        r = mirror_dataset(Dataset.DAILY_BARS, ["BATCH"], src=src, sink=sink, source="VCI",
                            batch=5)
        _assert(r.records_read == 12 and r.records_submitted == 12, r)
        _assert(len(sink.written["write_daily_bars"]) == 12, "batching lost records")

    check("batch=5 over 12 records submits all 12 across 3 batches", _batching)

    def _returns_never_mirrored() -> None:
        sink = _FakeSink()
        _assert(Dataset.DAILY_RETURNS not in MIRRORED and Dataset.INDEX_RETURNS not in MIRRORED,
                "P15: daily_returns/index_returns are views now — must not be in MIRRORED")
        _assert_raises(
            lambda: sink.write_daily_returns([{"ticker": "VCB"}]),
            AssertionError, "a caller that still points a Postgres sink at daily_returns",
        )
        _assert_raises(
            lambda: sink.write_index_returns([{"index_symbol": "VNINDEX"}]),
            AssertionError, "a caller that still points a Postgres sink at index_returns",
        )

    check("P15: DAILY_RETURNS/INDEX_RETURNS are out of MIRRORED and the sink refuses them",
          _returns_never_mirrored)

    def _no_date_window() -> None:
        sink = _FakeSink()

        class _RecordingSource(_FakeSource):
            def __init__(self, table):  # noqa: ANN001
                super().__init__(table)
                self.calls: list[tuple] = []

            def read_records(self, dataset, key, start=None, end=None, *, source):  # noqa: ANN001
                self.calls.append((dataset, key, start, end, source))
                return super().read_records(dataset, key, start, end, source=source)

        rsrc = _RecordingSource(table)
        mirror_dataset(Dataset.DAILY_BARS, ["VCB"], src=rsrc, sink=sink, source="VCI")
        _, _, start, end, _ = rsrc.calls[0]
        _assert(start is None and end is None, "mirror must read the FULL history, no window")

    check("mirror requests the full history — no start/end window", _no_date_window)

    def _mirror_all_routing() -> None:
        sink = _FakeSink()
        reports = mirror_all(["VCB"], ["VNINDEX"], src=src, sink=sink, source="VCI")
        by_dataset = {r.dataset: r for r in reports}
        _assert(by_dataset[Dataset.DAILY_BARS.value].records_read == 3, by_dataset)
        _assert(by_dataset[Dataset.INDEX_BARS.value].records_read == 2, by_dataset)
        _assert(by_dataset[Dataset.INDICATORS_DAILY.value].records_read == 4, by_dataset)
        _assert([r.dataset for r in reports] == [d.value for d in MIRRORED],
                "reports must be in MIRRORED order")
        _assert(len(reports) == 3, "P15: only 3 datasets are mirrored (returns are views)")
        _assert(len(sink.written["write_daily_bars"]) == 3, "daily_bars routed to tickers")
        _assert(len(sink.written["write_index_bars"]) == 2, "index_bars routed to index_symbols")
        _assert(len(sink.written["write_indicators"]) == 4, "indicators routed to tickers")

    check("mirror_all routes tickers vs index_symbols to the right dataset, raw untouched",
          _mirror_all_routing)

    print()
    if failed:
        print(f"mirror selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"mirror selftest: {passed} passed, 0 failed")
    return 0


def _assert(cond: bool, what: object) -> None:
    if not cond:
        raise AssertionError(str(what))


def _assert_raises(fn, exc_type: type[BaseException], what: str) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__} for {what}, nothing raised")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.storage.mirror",
        description="Mirror local-track market data into Postgres; --selftest needs neither.",
    )
    parser.add_argument("--selftest", action="store_true", help="Run the fake-backend checklist.")
    parser.add_argument(
        "--run", action="store_true",
        help="Live: mirror the research universe + VNINDEX from local to pg.",
    )
    parser.add_argument("--source", default="VCI")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.run:
        from pipelines.storage.localfs import LocalSource  # noqa: PLC0415
        from pipelines.storage.pg import PostgresSink  # noqa: PLC0415
        from pipelines.universe.file import read_universe_file  # noqa: PLC0415

        uf = read_universe_file("list_stocks_research.txt")
        src, sink = LocalSource(), PostgresSink()
        reports = mirror_all(list(uf.tickers), ["VNINDEX"], src=src, sink=sink, source=args.source)
        for r in reports:
            print(f"{r.dataset:16s} attempted={r.keys_attempted:3d}  read={r.records_read:6d}  "
                  f"submitted={r.records_submitted:6d}  empty={r.keys_empty}")
        return 0 if all(r.ok for r in reports) else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
