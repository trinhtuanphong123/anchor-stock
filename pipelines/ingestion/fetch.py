"""pipelines.ingestion.fetch — orchestration: provider -> normalize -> quality -> storage.

Replaces the old asymmetric pair ``pipelines/ingestion/daily.py`` (no CLI, high-water-mark
incremental) and ``pipelines/ingestion/index_bars.py`` (its own CLI, a different frontier) with
one command and one code path for both equities and the index.

Two passes, both bounded by the SAME explicit ``[start, end]`` window:

    land   provider.fetch  -> normalize.build_raw_records -> sink.write_raw_bars
    parse  source.raw_bars -> normalize.normalize_bars -> quality.run_checks -> sink.write_*_bars

**No high-water mark drives either pass.** ``docs/decisions/D-06-adjusted-close-semantics.md``
established that vnstock's adjusted-close series re-anchors to the present on every new
corporate action — appending new rows to an old series would splice two different adjustment
bases and create a fake jump at the seam. Log returns are invariant under a uniform rescale
(``ln(a*P_t / a*P_{t-1}) == ln(P_t/P_{t-1})``), so re-fetching the FULL window every run makes
that re-adjustment completely harmless to this model. ``BarSource.high_water_marks`` still
exists and is not used here to drive the price fetch.

Land and parse stay two passes even under full-window refetch: ``--parse-only`` re-runs
normalize and quality against real landed history with ZERO network access, which is what makes
every future change to those two modules testable against the actual data without spending
provider quota.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pipelines.common.quality import write_dqr
from pipelines.ingestion.normalize import build_raw_records, normalize_bars
from pipelines.ingestion.provider import (
    MockProvider,
    ProviderRateLimited,
    ProviderUnavailable,
    SymbolFetchError,
    VnstockProvider,
)
from pipelines.ingestion.quality import CheckResult, Severity, check_coverage, run_checks
from pipelines.storage.factory import make_sink, make_source
from pipelines.storage.ports import BarSink, BarSource, Dataset

__all__ = ["FetchReport", "SymbolReport", "run_fetch"]

DEFAULT_INDEX_SYMBOL = "VNINDEX"
DEFAULT_MIN_SUCCESS = 0.9

_STATUSES = (
    "pending", "ok", "empty", "fetch_failed", "quality_empty", "write_failed",
    "rate_limited", "not_attempted", "skipped",
)
#: Statuses pass B must not attempt to parse — each already has a terminal, explained outcome.
_SKIP_IN_PARSE = frozenset({"fetch_failed", "write_failed", "rate_limited", "not_attempted"})


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@dataclass
class SymbolReport:
    symbol: str
    dataset: str  # Dataset.value of the TYPED dataset (daily_bars / index_bars)
    #: "pending" means "not yet resolved by either pass" — the initial value, and what a symbol
    #: keeps if --parse-only is used (pass A never ran, so nothing marked it any other way).
    #: "not_attempted" is different and NARROWER: it means a rate-limit abort explicitly ruled
    #: this symbol out before pass A reached it. Conflating the two used to make pass B skip
    #: every symbol that had just been landed successfully, because "not_attempted" was both the
    #: default AND the skip condition.
    status: str = "pending"
    rows_fetched: int = 0
    rows_before_trim: int = 0
    rows_trimmed: int = 0
    rows_landed: int = 0
    rows_normalized: int = 0
    rows_dropped: int = 0
    rows_quarantined: int = 0
    rows_written: int = 0
    first_bar: str | None = None
    last_bar: str | None = None
    elapsed_s: float = 0.0
    error: str | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FetchReport:
    run_id: str
    started_at: str
    fetched_at: str  # THE adjustment basis — identical on every raw record this run writes
    start: str
    end: str
    source: str
    storage: str
    universe_version: str
    universe_sha256: str
    universe_path: str
    index_symbol: str | None
    throttle_s: float
    mock: bool
    did_land: bool
    did_parse: bool
    min_success: float = DEFAULT_MIN_SUCCESS
    finished_at: str | None = None
    aborted: bool = False
    abort_reason: str | None = None
    symbols: list[SymbolReport] = field(default_factory=list)

    @property
    def n_attempted(self) -> int:
        return sum(1 for s in self.symbols if s.status != "not_attempted")

    @property
    def n_ok(self) -> int:
        return sum(1 for s in self.symbols if s.status == "ok")

    @property
    def n_empty(self) -> int:
        return sum(1 for s in self.symbols if s.status == "empty")

    @property
    def n_failed(self) -> int:
        failed = ("fetch_failed", "quality_empty", "write_failed")
        return sum(1 for s in self.symbols if s.status in failed)

    @property
    def rows_written_total(self) -> int:
        return sum(s.rows_written for s in self.symbols)

    @property
    def success_ratio(self) -> float:
        total = len(self.symbols)
        if total == 0:
            return 1.0
        # A "pending" symbol counts as good only when this run never intended to parse it
        # (--land-only): landing succeeded and nothing was asked to resolve it further. In a
        # normal or --parse-only run, "pending" this late means pass B never reached it, which
        # is a real gap, not a success.
        good_statuses = {"ok", "empty", "pending"} if not self.did_parse else {"ok", "empty"}
        good = sum(1 for s in self.symbols if s.status in good_statuses)
        return good / total

    @property
    def index_ok(self) -> bool:
        if self.index_symbol is None:
            return True
        want = {"pending"} if not self.did_parse else {"ok"}
        for s in self.symbols:
            if s.symbol == self.index_symbol:
                return s.status in want
        return False

    @property
    def overall_status(self) -> str:
        """Deliberately NOT "every symbol must fail to count as failed" (the old rule).

        Order: an abort (rate limit / provider unavailable) wins outright. Otherwise: any
        write_failed, or a requested index that produced no written bars, or the success ratio
        falling below the threshold, makes the run "failed" — 99/100 tickers missing is a
        failure, not a success with footnotes. Short of that, anything less than fully clean is
        "degraded" rather than silently "ok".
        """
        if self.aborted:
            return "aborted"
        if any(s.status == "write_failed" for s in self.symbols):
            return "failed"
        if self.index_symbol is not None and not self.index_ok:
            return "failed"
        if self.success_ratio < self.min_success:
            return "failed"
        if any(s.status not in ("ok", "empty") for s in self.symbols):
            return "degraded"
        return "ok"

    def to_json(self) -> str:
        payload = asdict(self)
        payload["n_attempted"] = self.n_attempted
        payload["n_ok"] = self.n_ok
        payload["n_empty"] = self.n_empty
        payload["n_failed"] = self.n_failed
        payload["rows_written_total"] = self.rows_written_total
        payload["success_ratio"] = round(self.success_ratio, 4)
        payload["overall_status"] = self.overall_status
        return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _typed_dataset(raw_dataset: Dataset) -> Dataset:
    return Dataset.DAILY_BARS if raw_dataset is Dataset.RAW_EQUITY else Dataset.INDEX_BARS


def _write_typed(sink: BarSink, dataset: Dataset, records: list[dict[str, Any]]) -> int:
    if dataset is Dataset.DAILY_BARS:
        return sink.write_daily_bars(records)
    return sink.write_index_bars(records)


def _dqr_scope(dataset: Dataset, symbol: str) -> str:
    if dataset is Dataset.RAW_EQUITY:
        return f"daily_ohlcv:ticker:{symbol}"
    return f"index_bars:{symbol}"


def _emit(
    pipeline_run_id: int | None, scope: str, ref_date: date | None, result: CheckResult
) -> None:
    write_dqr(pipeline_run_id, scope, ref_date, result.check_name, result.passed,
             result.severity.value, result.details)


def run_fetch(
    *,
    start: date,
    end: date,
    tickers: list[str] | None = None,
    universe_file: Path | None = None,
    index_symbol: str | None = DEFAULT_INDEX_SYMBOL,
    source: str = "VCI",
    storage: str | None = None,
    throttle_s: float = 5.0,
    do_land: bool = True,
    do_parse: bool = True,
    mock: bool = False,
    min_success: float = DEFAULT_MIN_SUCCESS,
    provider: Any = None,
    sink: BarSink | None = None,
    src: BarSource | None = None,
    pipeline_run_id: int | None = None,
    now: datetime | None = None,
) -> FetchReport:
    """Run the two-pass fetch. See the module docstring for the full design.

    ``start`` is required — there is deliberately no lookback default, unlike the old
    ``_DEFAULT_LOOKBACK_DAYS = 90`` anchored inconsistently on ``ref_date`` in one file and
    ``date.today()`` in the other.

    ``now`` overrides the run's ``fetched_at`` / adjustment-basis clock; ``None`` reads the real
    clock. Exposed mainly so tests can prove exact re-run idempotency: two calls with the same
    ``now`` produce byte-identical shards, since only the wall clock — not the fetched content —
    would otherwise differ between them.
    """
    fetched_at = now if now is not None else datetime.now(UTC)

    if tickers is None:
        from pipelines.universe.file import resolve_universe  # noqa: PLC0415

        uf = resolve_universe(None, universe_file)
        resolved_tickers = list(uf.tickers)
        universe_version, universe_sha256, universe_path = uf.version, uf.sha256, str(uf.path)
    else:
        resolved_tickers = list(tickers)
        universe_version = universe_sha256 = ""
        universe_path = "<explicit>"

    if provider is not None:
        prov = provider
    elif mock:
        prov = MockProvider(source=source)
    else:
        prov = VnstockProvider(source=source, throttle_s=throttle_s)
    writer = sink if sink is not None else make_sink(storage)
    reader = src if src is not None else make_source(storage)

    report = FetchReport(
        run_id=uuid.uuid4().hex[:12],
        started_at=fetched_at.isoformat(),
        fetched_at=fetched_at.isoformat(),
        start=start.isoformat(), end=end.isoformat(),
        source=source.upper(), storage=storage or "local",
        universe_version=universe_version, universe_sha256=universe_sha256,
        universe_path=universe_path,
        index_symbol=index_symbol, throttle_s=throttle_s, mock=mock,
        did_land=do_land, did_parse=do_parse, min_success=min_success,
    )

    symbols_in_order: list[tuple[str, Dataset]] = []
    if index_symbol:
        symbols_in_order.append((index_symbol, Dataset.RAW_INDEX))
    symbols_in_order.extend((t, Dataset.RAW_EQUITY) for t in resolved_tickers)

    reports_by_symbol: dict[str, SymbolReport] = {
        sym: SymbolReport(symbol=sym, dataset=_typed_dataset(ds).value)
        for sym, ds in symbols_in_order
    }
    report.symbols = list(reports_by_symbol.values())

    # ---- provider availability gate (land only; parse-only never touches it) ----
    if do_land and not mock:
        try:
            from pipelines.ingestion.provider import available  # noqa: PLC0415

            if not available():
                raise ProviderUnavailable("vnstock is not importable")
        except ProviderUnavailable as exc:
            report.aborted = True
            report.abort_reason = f"provider unavailable: {exc}"
            report.finished_at = datetime.now(UTC).isoformat()
            _emit(pipeline_run_id, "daily_ohlcv:run", end, CheckResult(
                check_name="run_summary", passed=False,
                severity=Severity.ERROR,
                details={"aborted": True, "reason": report.abort_reason},
            ))
            return report

    try:
        # ============================= PASS A — land =============================
        if do_land:
            for symbol, raw_dataset in symbols_in_order:
                sr = reports_by_symbol[symbol]
                t0 = datetime.now(UTC)
                try:
                    rf = prov.fetch(symbol, start, end)
                except ProviderRateLimited as exc:
                    sr.status = "rate_limited"
                    sr.error = str(exc)
                    report.aborted = True
                    report.abort_reason = f"rate limited at {symbol}: {exc}"
                    _mark_remaining_not_attempted(reports_by_symbol, symbols_in_order, symbol)
                    break
                except SymbolFetchError as exc:
                    sr.status = "fetch_failed"
                    sr.error = str(exc)
                    continue

                sr.rows_fetched = len(rf.rows)
                sr.rows_before_trim = rf.rows_before_trim
                sr.rows_trimmed = rf.trimmed_leading + rf.trimmed_trailing
                sr.elapsed_s += rf.elapsed_s

                if not rf.rows:
                    sr.status = "empty"
                    continue

                raw_records = build_raw_records(raw_dataset, symbol, rf.rows, fetched_at=fetched_at)
                try:
                    sr.rows_landed = writer.write_raw_bars(raw_records)
                except Exception as exc:  # noqa: BLE001 - ports raise; caller decides
                    sr.status = "write_failed"
                    sr.error = f"land write failed: {type(exc).__name__}: {exc}"
                    continue
                sr.elapsed_s += (datetime.now(UTC) - t0).total_seconds()

        if report.aborted:
            report.finished_at = datetime.now(UTC).isoformat()
            _emit(pipeline_run_id, "daily_ohlcv:run", end, CheckResult(
                check_name="rate_limit", passed=False,
                severity=Severity.ERROR,
                details={"aborted_at": report.abort_reason},
            ))
            return report

        # ============================= PASS B — parse =============================
        n_index_sessions = 0
        if do_parse:
            for symbol, raw_dataset in symbols_in_order:
                sr = reports_by_symbol[symbol]
                if sr.status in _SKIP_IN_PARSE:
                    continue

                raw_rows = reader.raw_bars(raw_dataset, symbol, start, end)
                if not raw_rows:
                    if sr.status != "empty":
                        sr.status = "empty"
                    continue

                typed_dataset = _typed_dataset(raw_dataset)
                nres = normalize_bars(
                    typed_dataset, symbol, [payload for _, payload in raw_rows],
                    source=report.source, now=fetched_at,
                )
                sr.rows_normalized = len(nres.records)
                sr.rows_dropped = len(nres.dropped)

                n_expected = n_index_sessions if symbol != index_symbol else len(nres.records)
                outcome = run_checks(typed_dataset, nres.records, start=start, end=end)
                cov = check_coverage(
                    len(outcome.kept), max(n_expected, len(outcome.kept)),
                    scope=symbol,
                )
                sr.checks = [
                    {"check_name": c.check_name, "passed": c.passed, "severity": c.severity.value,
                     "details": c.details}
                    for c in (*outcome.checks, cov)
                ]
                sr.rows_quarantined = len(outcome.quarantined)

                for c in (*outcome.checks, cov):
                    _emit(pipeline_run_id, _dqr_scope(raw_dataset, symbol), end, c)

                if not outcome.kept:
                    sr.status = "quality_empty"
                    continue

                try:
                    sr.rows_written = _write_typed(writer, typed_dataset, outcome.kept)
                except Exception as exc:  # noqa: BLE001
                    sr.status = "write_failed"
                    sr.error = f"parse write failed: {type(exc).__name__}: {exc}"
                    continue

                dates = sorted(r["bar_date"] for r in outcome.kept)
                sr.first_bar = dates[0].isoformat()
                sr.last_bar = dates[-1].isoformat()
                sr.status = "ok"

                if symbol == index_symbol:
                    n_index_sessions = len(outcome.kept)

    finally:
        report.finished_at = datetime.now(UTC).isoformat()

    run_cov = check_coverage(report.n_ok, len(report.symbols), scope="run")
    _emit(pipeline_run_id, "daily_ohlcv:run", end, run_cov)

    return report


def _mark_remaining_not_attempted(
    reports_by_symbol: dict[str, SymbolReport],
    symbols_in_order: list[tuple[str, Dataset]],
    from_symbol: str,
) -> None:
    started = False
    for sym, _ in symbols_in_order:
        if sym == from_symbol:
            started = True
            continue
        if started:
            reports_by_symbol[sym].status = "not_attempted"


# ---------------------------------------------------------------------------
# Self-check — offline, temp DATA_ROOT, mock provider
# ---------------------------------------------------------------------------


def _selftest() -> int:  # noqa: PLR0915
    import os
    import shutil
    import tempfile

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

    tmp = Path(tempfile.mkdtemp(prefix="datn_fetch_"))
    os.environ["DATN_DATA_ROOT"] = str(tmp)
    os.environ["DATN_STORAGE"] = "local"
    try:
        start, end = date(2025, 1, 1), date(2025, 3, 31)

        def _end_to_end() -> None:
            rep = run_fetch(
                start=start, end=end, tickers=["VCB", "FPT", "HPG"],
                index_symbol="VNINDEX", mock=True,
                provider=MockProvider(seed=7),
            )
            assert rep.overall_status == "ok", (rep.overall_status, [s.status for s in rep.symbols])
            for s in rep.symbols:
                assert s.rows_fetched == s.rows_landed, s
                assert s.rows_normalized - s.rows_quarantined == s.rows_written, s

        check("full mock run end-to-end; per-symbol counts reconcile", _end_to_end)

        def _idempotent() -> None:
            from pipelines.common.paths import shard_path

            # A fixed `now` is required for a true byte-identity check: ON_CONFLICT_KEEP
            # preserves ingested_at across a re-run but NOT updated_at, so two calls with the
            # real wall clock legitimately produce different bytes. That is correct behaviour,
            # not a bug — this test isolates content-idempotency from that expected timestamp
            # drift by pinning the clock.
            fixed_now = datetime(2025, 6, 1, tzinfo=UTC)
            run_fetch(start=start, end=end, tickers=["VCB", "FPT", "HPG"],
                     index_symbol="VNINDEX", mock=True, provider=MockProvider(seed=7),
                     now=fixed_now)
            p = shard_path("daily_bars", "ticker", "VCB")
            before = p.read_bytes()
            run_fetch(start=start, end=end, tickers=["VCB", "FPT", "HPG"],
                     index_symbol="VNINDEX", mock=True, provider=MockProvider(seed=7),
                     now=fixed_now)
            assert p.read_bytes() == before, "re-running the identical fetch changed the shard"

        check("re-running the same fetch (same clock) is byte-identical", _idempotent)

        def _fault_statuses() -> None:
            rep = run_fetch(
                start=start, end=end, tickers=["MTY", "NANC", "ALLB"],
                index_symbol="VNINDEX", mock=True,
                provider=MockProvider(seed=7, faults={
                    "MTY": "no_rows", "NANC": "nan_close", "ALLB": "all_bad",
                }),
            )
            by = {s.symbol: s for s in rep.symbols}
            assert by["MTY"].status == "empty", by["MTY"]
            assert by["NANC"].status == "ok" and by["NANC"].rows_dropped > 0, by["NANC"]
            assert by["ALLB"].status == "quality_empty", by["ALLB"]

        check("injected faults produce the documented per-symbol statuses", _fault_statuses)

        def _write_failure_fails_the_run() -> None:
            class _FailingSink:
                def write_raw_bars(self, records):  # noqa: ANN001, ANN201
                    return len(records)
                def write_daily_bars(self, records):  # noqa: ANN001, ANN201
                    raise RuntimeError("disk full")
                def write_index_bars(self, records):  # noqa: ANN001, ANN201
                    return len(records)
                def write_daily_returns(self, records):  # noqa: ANN001, ANN201
                    return len(records)
                def write_index_returns(self, records):  # noqa: ANN001, ANN201
                    return len(records)

            rep = run_fetch(
                start=start, end=end, tickers=["VCB"], index_symbol="VNINDEX",
                mock=True, provider=MockProvider(seed=7), sink=_FailingSink(),
                src=make_source("local"),
            )
            by = {s.symbol: s for s in rep.symbols}
            assert by["VCB"].status == "write_failed", by["VCB"]
            assert rep.overall_status == "failed", rep.overall_status

        check(
            "a storage write failure marks the symbol AND fails the whole run",
            _write_failure_fails_the_run,
        )

        def _rate_limit_aborts_but_keeps_prior_shards() -> None:
            from pipelines.common.paths import raw_path, shard_path

            rep1 = run_fetch(start=start, end=end, tickers=["AAA"], index_symbol=None,
                             mock=True, provider=MockProvider(seed=7))
            assert rep1.overall_status == "ok", rep1.overall_status
            typed_shard = shard_path("daily_bars", "ticker", "AAA")
            typed_before = typed_shard.read_bytes()

            rep2 = run_fetch(
                start=start, end=end, tickers=["AAA", "BBB", "CCC"], index_symbol=None,
                mock=True,
                provider=MockProvider(seed=7, faults={"BBB": "rate_limit"}),
            )
            by = {s.symbol: s for s in rep2.symbols}
            # Pass B (parse) never runs once an abort is detected in pass A — see run_fetch's
            # docstring on `now` and the module-level "Xử lý lỗi" table: an abort promises
            # already-LANDED data survives, not that it gets parsed too. AAA landed successfully
            # in THIS run (rows_landed > 0) but stays "pending" because parse never got a turn.
            assert by["AAA"].status == "pending", by["AAA"]
            assert by["AAA"].rows_landed > 0, by["AAA"]
            assert by["BBB"].status == "rate_limited", by["BBB"]
            assert by["CCC"].status == "not_attempted", by["CCC"]
            assert rep2.aborted is True, rep2.aborted
            assert rep2.overall_status == "aborted", rep2.overall_status
            # The TYPED shard written by rep1 (a prior, separate, completed run) is untouched —
            # rep2's abort happens before pass B, so it never even attempts to write daily_bars.
            assert typed_shard.read_bytes() == typed_before, (
                "a prior run's typed shard must survive a later rate limit untouched"
            )
            assert raw_path("AAA", "EQUITY").is_file(), "AAA's raw landing from rep2 must persist"

        check(
            "rate limit aborts before parse; landed data persists, prior typed data untouched",
            _rate_limit_aborts_but_keeps_prior_shards,
        )

        def _parse_only_touches_no_network() -> None:
            assert "vnstock" not in sys.modules, "vnstock must not be imported by any prior check"
            run_fetch(
                start=start, end=end, tickers=["VCB"], index_symbol="VNINDEX",
                do_land=False, do_parse=True, mock=False,
            )
            assert "vnstock" not in sys.modules, "parse-only imported vnstock"

        check("--parse-only never imports vnstock", _parse_only_touches_no_network)

        def _report_json_roundtrip() -> None:
            rep = run_fetch(start=start, end=end, tickers=["VCB"], index_symbol="VNINDEX",
                            mock=True, provider=MockProvider(seed=7))
            payload = json.loads(rep.to_json())
            for key in ("fetched_at", "universe_version", "source", "run_id", "overall_status"):
                assert key in payload, (key, payload.keys())

        check("FetchReport.to_json() round-trips with the expected keys", _report_json_roundtrip)

    finally:
        os.environ.pop("DATN_DATA_ROOT", None)
        os.environ.pop("DATN_STORAGE", None)
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failed:
        print(f"fetch selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"fetch selftest: {passed} passed, 0 failed")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.ingestion.fetch",
        description="Fetch daily bars: provider -> normalize -> quality -> storage.",
    )
    parser.add_argument("--start", metavar="YYYY-MM-DD", default=None)
    parser.add_argument("--end", metavar="YYYY-MM-DD", default=None)
    parser.add_argument("--tickers", default=None, metavar="LIST")
    parser.add_argument("--universe-file", default=None, metavar="PATH")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--index", default=DEFAULT_INDEX_SYMBOL, metavar="SYM")
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--source", default="VCI")
    parser.add_argument("--storage", default=None, choices=("local", "pg"))
    parser.add_argument("--throttle", type=float, default=5.0)
    parser.add_argument("--land-only", action="store_true")
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--min-success", type=float, default=DEFAULT_MIN_SUCCESS)
    parser.add_argument("--report", default=None, metavar="PATH")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.start:
        parser.error("--start is required (no lookback default — see the module docstring)")
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.replace(",", " ").split() if t.strip()]
    if args.limit and tickers is None:
        from pipelines.universe.file import resolve_universe  # noqa: PLC0415

        tickers = list(resolve_universe(None, args.universe_file).tickers)[: args.limit]
    elif args.limit and tickers is not None:
        tickers = tickers[: args.limit]

    report = run_fetch(
        start=start, end=end, tickers=tickers,
        universe_file=Path(args.universe_file) if args.universe_file else None,
        index_symbol=None if args.no_index else args.index,
        source=args.source, storage=args.storage, throttle_s=args.throttle,
        do_land=not args.parse_only, do_parse=not args.land_only,
        mock=args.mock, min_success=args.min_success,
    )

    report_path = Path(args.report) if args.report else None
    if report_path is None:
        from pipelines.common.paths import ensure_dir, research_dir

        report_path = ensure_dir(research_dir()) / f"fetch_{report.run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.to_json(), encoding="utf-8")

    print(f"=== fetch {report.overall_status} — run_id={report.run_id} ===")
    print(f"attempted={report.n_attempted} ok={report.n_ok} empty={report.n_empty} "
          f"failed={report.n_failed} success_ratio={report.success_ratio:.3f}")
    print(f"rows_written_total={report.rows_written_total}")
    print(f"report: {report_path}")
    if report.aborted:
        print(f"ABORTED: {report.abort_reason}")

    return {"ok": 0, "degraded": 0, "failed": 1, "aborted": 2}[report.overall_status]


if __name__ == "__main__":
    sys.exit(main())
