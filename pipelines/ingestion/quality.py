"""pipelines.ingestion.quality — row-level quality checks for a fetched batch.

Pure. No I/O. Named the same as :mod:`pipelines.common.quality`, which is safe — Python 3.13 has
no implicit relative imports and this repo uses absolute imports throughout, so
``from pipelines.common.quality import write_dqr`` inside this file resolves without ambiguity.
The split is deliberate: this module COMPUTES; ``common.quality`` PERSISTS the computed result
as a ``data_quality_reports`` row.

The central departure from the old ``daily.py`` / ``index_bars.py`` checks: **row-level
quarantine**. The old code computed violations, reported them, and then upserted the whole batch
anyway — offending rows included. Here every :class:`CheckResult` names the exact row *indices*
that failed (``bad_indices``), and :func:`run_checks` uses the union of those to split the batch
into ``kept`` and ``quarantined``. A single bad bar can no longer either poison the batch (by
being written) or remove a whole symbol from the universe (by being quarantined as a unit).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from pipelines.storage.ports import CONFLICT_KEY, Dataset

__all__ = [
    "CheckResult",
    "QualityOutcome",
    "Severity",
    "check_coverage",
    "check_duplicates",
    "check_sanity",
    "check_window",
    "run_checks",
]


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict. ``details`` is JSON-safe and goes straight to ``write_dqr``."""

    check_name: str
    passed: bool
    severity: Severity
    details: dict[str, Any] = field(default_factory=dict)
    #: Positions in the input list this check wants removed. Empty means "flags, does not cut" —
    #: that is what makes ``check_coverage`` an aggregate check rather than a row-level one.
    bad_indices: frozenset[int] = frozenset()


@dataclass(frozen=True)
class QualityOutcome:
    kept: list[dict[str, Any]]
    quarantined: list[tuple[dict[str, Any], str]]  # (record, reason)
    checks: list[CheckResult]


_MAX_REPORT = 20  # the one thing both old implementations got right


# ---------------------------------------------------------------------------
# check_sanity — one threshold per KIND of column, not one threshold for all
# ---------------------------------------------------------------------------

_PRICE_COLS = ("open", "high", "low", "close")


def check_sanity(dataset: Dataset, records: list[dict[str, Any]]) -> CheckResult:
    """Reject non-positive prices, negative volume, and high < low.

    The old code had two thresholds that quietly disagreed: ``daily._check_sanity_bounds``
    rejected ``v <= 0``, ``index_bars._check_sanity`` rejected ``v < 0`` — so a price of exactly
    ``0.0`` failed in one file and passed in the other. Neither was right on its own terms,
    because both applied ONE threshold to TWO kinds of column.

    **Prices use ``<= 0``; volume uses ``< 0``.** A price of exactly zero is not merely wrong,
    it is the one value that makes the model UNDEFINED rather than just implausible: every
    downstream quantity is a log return (``docs/01-data-pipeline.md`` §2), and ``ln(0/P)`` is
    ``-inf`` while ``ln(P/0)`` divides by zero. Volume of exactly zero, on the other hand, is a
    real and frequent observation — a session with no matched trades — and rejecting it would
    delete a genuine trading day. Only a NEGATIVE volume is nonsensical.

    Non-finite values are also flagged here as a belt-and-braces measure, even though
    ``normalize._num`` already maps them to ``None`` before they would reach this check.
    """
    violations: list[str] = []
    bad: set[int] = set()
    n_null = {c: 0 for c in (*_PRICE_COLS, "volume")}

    for i, rec in enumerate(records):
        bd = rec.get("bar_date")
        for col in _PRICE_COLS:
            v = rec.get(col)
            if v is None:
                n_null[col] += 1
                continue
            if v <= 0:
                violations.append(f"{bd}: {col}={v} not > 0")
                bad.add(i)
        vol = rec.get("volume")
        if vol is None:
            n_null["volume"] += 1
        elif vol < 0:
            violations.append(f"{bd}: volume={vol} < 0")
            bad.add(i)
        h, lo = rec.get("high"), rec.get("low")
        if h is not None and lo is not None and h < lo:
            violations.append(f"{bd}: high={h} < low={lo}")
            bad.add(i)

    passed = not violations
    return CheckResult(
        check_name="sanity_bounds",
        passed=passed,
        severity=Severity.INFO if passed else Severity.ERROR,
        details={
            "dataset": dataset.value,
            "records_checked": len(records),
            "n_violations": len(violations),
            "violations": violations[:_MAX_REPORT],
            "n_null": n_null,
        },
        bad_indices=frozenset(bad),
    )


# ---------------------------------------------------------------------------
# check_duplicates — key comes from ports.CONFLICT_KEY, not hand-written
# ---------------------------------------------------------------------------


def check_duplicates(dataset: Dataset, records: list[dict[str, Any]]) -> CheckResult:
    """Reject repeats of the dataset's own conflict key within one batch.

    The old ``daily._check_duplicates`` / ``index_bars._check_duplicates`` differed only in the
    key tuple (``ticker`` vs ``index_symbol``) — a difference that already lives in
    ``ports.CONFLICT_KEY`` and does not need a second, hand-written copy here.

    Keep-first: every occurrence AFTER the first per key is quarantined. Without row-level
    quarantine the old code produced keep-last by accident, because ``localfs._merge`` and
    Postgres' ``ON CONFLICT`` both apply a batch in order; keep-first makes the same outcome a
    stated rule instead of an implementation detail, and ``details`` records both colliding
    values so a genuine provider disagreement is visible rather than silently resolved.
    """
    key_cols = CONFLICT_KEY[dataset]
    seen: dict[tuple, int] = {}
    dupes: list[str] = []
    bad: set[int] = set()

    for i, rec in enumerate(records):
        key = tuple(rec.get(c) for c in key_cols)
        if key in seen:
            first_i = seen[key]
            dupes.append(f"{key}: index {i} duplicates index {first_i}")
            bad.add(i)
        else:
            seen[key] = i

    passed = not dupes
    return CheckResult(
        check_name="duplicates",
        passed=passed,
        severity=Severity.INFO if passed else Severity.ERROR,
        details={
            "dataset": dataset.value,
            "key_columns": list(key_cols),
            "records_checked": len(records),
            "n_duplicates": len(dupes),
            "duplicates": dupes[:_MAX_REPORT],
        },
        bad_indices=frozenset(bad),
    )


# ---------------------------------------------------------------------------
# check_window — new. The regression witness for the provider's leading overshoot.
# ---------------------------------------------------------------------------


def check_window(records: list[dict[str, Any]], *, start: date, end: date) -> CheckResult:
    """Every ``bar_date`` must lie inside ``[start, end]``.

    New relative to the old code. ``provider.py`` trims the vnstock leading-window overshoot
    (verified: a 2020-01-01 request returned rows from 2019-09-26) client-side before this check
    ever runs — so under normal operation this check should never fire. Its purpose is to be the
    thing that DOES fire, with an exact count, the day that trim breaks, instead of the run
    quietly producing a longer series than requested.
    """
    bad: set[int] = set()
    offenders: list[str] = []
    for i, rec in enumerate(records):
        bd = rec.get("bar_date")
        if bd is None or bd < start or bd > end:
            offenders.append(f"index {i}: bar_date={bd} outside [{start}, {end}]")
            bad.add(i)

    passed = not offenders
    return CheckResult(
        check_name="window",
        passed=passed,
        severity=Severity.INFO if passed else Severity.ERROR,
        details={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "records_checked": len(records),
            "n_outside": len(offenders),
            "offenders": offenders[:_MAX_REPORT],
        },
        bad_indices=frozenset(bad),
    )


# ---------------------------------------------------------------------------
# check_coverage — aggregate; never quarantines
# ---------------------------------------------------------------------------


def check_coverage(
    n_rows: int, n_expected: int, *, min_ratio: float = 0.5, scope: str = ""
) -> CheckResult:
    """Flag a symbol (or a run) whose row count falls short of what was expected.

    ``n_expected`` should be the number of distinct trading sessions VNINDEX produced over the
    SAME window — not ``pandas.bdate_range``, which counts Vietnamese public holidays as sessions
    and therefore permanently under-reports coverage. This also matches the project's own
    definition of a session (``supabase/migrations/00001_reference.sql``: a session exists iff
    the index has a bar for that date), so the same number means the same thing everywhere.

    Never quarantines — ``bad_indices`` is always empty. Coverage is a statement about the SET of
    rows a symbol produced, not a verdict on any individual row; a low ratio is real evidence
    that a ticker listed late or was suspended, not a data-quality defect to cut around.
    """
    ratio = (n_rows / n_expected) if n_expected > 0 else (1.0 if n_rows == 0 else 0.0)
    passed = ratio >= min_ratio
    return CheckResult(
        check_name="coverage",
        passed=passed,
        severity=Severity.INFO if passed else Severity.WARNING,
        details={
            "scope": scope,
            "n_rows": n_rows,
            "n_expected": n_expected,
            "ratio": round(ratio, 4),
            "min_ratio": min_ratio,
        },
    )


# ---------------------------------------------------------------------------
# run_checks — apply sanity + duplicates + window, split kept / quarantined
# ---------------------------------------------------------------------------


def run_checks(
    dataset: Dataset,
    records: list[dict[str, Any]],
    *,
    start: date,
    end: date,
) -> QualityOutcome:
    """Run the row-level checks and split ``records`` into ``kept`` / ``quarantined``.

    A failing check never removes a symbol as a whole and never aborts anything — it removes
    exactly the rows it names. ``quarantined`` carries a reason string per record so a caller can
    report WHY a bar was cut, not just that it was.
    """
    sanity = check_sanity(dataset, records)
    dupes = check_duplicates(dataset, records)
    window = check_window(records, start=start, end=end)
    checks = [sanity, dupes, window]

    reason_by_index: dict[int, str] = {}
    for check in checks:
        for i in check.bad_indices:
            reason_by_index.setdefault(i, check.check_name)

    kept: list[dict[str, Any]] = []
    quarantined: list[tuple[dict[str, Any], str]] = []
    for i, rec in enumerate(records):
        if i in reason_by_index:
            quarantined.append((rec, reason_by_index[i]))
        else:
            kept.append(rec)

    return QualityOutcome(kept=kept, quarantined=quarantined, checks=checks)


# ---------------------------------------------------------------------------
# Self-check — pure, no network, no database
# ---------------------------------------------------------------------------


def _selftest() -> int:  # noqa: PLR0915
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

    d0 = date(2025, 1, 2)

    def bar(day: int, **overrides) -> dict:  # noqa: ANN003
        base = {
            "ticker": "VCB", "bar_date": date(2025, 1, day), "source": "VCI",
            "open": 90.0, "high": 91.0, "low": 89.0, "close": 90.5, "volume": 1_000_000.0,
        }
        base.update(overrides)
        return base

    def _zero_price_violates_zero_volume_does_not() -> None:
        recs = [bar(2, close=0.0), bar(3, volume=0.0)]
        r = check_sanity(Dataset.DAILY_BARS, recs)
        assert r.passed is False, r
        assert 0 in r.bad_indices, r.bad_indices
        assert 1 not in r.bad_indices, r.bad_indices

    check(
        "close == 0.0 violates sanity; volume == 0 does not",
        _zero_price_violates_zero_volume_does_not,
    )

    def _negative_volume_violates() -> None:
        r = check_sanity(Dataset.DAILY_BARS, [bar(2, volume=-1.0)])
        assert r.passed is False and 0 in r.bad_indices, r

    check("negative volume violates sanity", _negative_volume_violates)

    def _high_lt_low() -> None:
        r = check_sanity(Dataset.DAILY_BARS, [bar(2, high=80.0, low=90.0)])
        assert r.passed is False and 0 in r.bad_indices, r

    check("high < low violates sanity", _high_lt_low)

    def _null_columns_counted_not_flagged() -> None:
        r = check_sanity(Dataset.DAILY_BARS, [bar(2, open=None, volume=None)])
        assert r.passed is True, r
        assert r.details["n_null"]["open"] == 1, r.details
        assert r.details["n_null"]["volume"] == 1, r.details

    check(
        "null price/volume columns are counted, not treated as violations",
        _null_columns_counted_not_flagged,
    )

    def _duplicate_key_from_conflict_key() -> None:
        recs = [bar(2), bar(2)]  # same (ticker, bar_date, source)
        r = check_duplicates(Dataset.DAILY_BARS, recs)
        assert r.bad_indices == frozenset({1}), r.bad_indices  # keep-first

        idx_recs = [
            {"index_symbol": "VNINDEX", "bar_date": d0, "source": "VCI"},
            {"index_symbol": "VNINDEX", "bar_date": d0, "source": "VCI"},
        ]
        r2 = check_duplicates(Dataset.INDEX_BARS, idx_recs)
        assert r2.bad_indices == frozenset({1}), r2.bad_indices
        assert r2.details["key_columns"] == ["index_symbol", "bar_date", "source"], r2.details

    check(
        "duplicate key is CONFLICT_KEY[dataset], proven for both ticker and index_symbol",
        _duplicate_key_from_conflict_key,
    )

    def _row_level_quarantine() -> None:
        recs = [bar(i) for i in range(2, 12)]  # 10 good rows
        recs[3] = bar(5, close=0.0)  # 1 bad
        recs[7] = bar(9, close=-1.0)  # another bad
        outcome = run_checks(
            Dataset.DAILY_BARS, recs, start=date(2025, 1, 1), end=date(2025, 1, 31)
        )
        assert len(outcome.kept) == 8, len(outcome.kept)
        assert len(outcome.quarantined) == 2, len(outcome.quarantined)
        kept_dates = {r["bar_date"] for r in outcome.kept}
        assert date(2025, 1, 5) not in kept_dates and date(2025, 1, 9) not in kept_dates, kept_dates

    check(
        "row-level quarantine removes exactly the bad rows, keeps the rest",
        _row_level_quarantine,
    )

    def _window_check() -> None:
        recs = [bar(2), {**bar(3), "bar_date": date(2025, 2, 1)}]
        r = check_window(recs, start=date(2025, 1, 1), end=date(2025, 1, 31))
        assert r.bad_indices == frozenset({1}), r.bad_indices

    check("check_window quarantines a bar_date outside [start, end]", _window_check)

    def _coverage_never_quarantines() -> None:
        r = check_coverage(3, 100, min_ratio=0.5)
        assert r.passed is False and r.severity is Severity.WARNING, r
        assert r.bad_indices == frozenset(), "coverage must never quarantine rows"

        r2 = check_coverage(0, 0, min_ratio=0.5)
        assert r2.passed is True, r2  # 0 expected, 0 got -> vacuously fine, not a failure

    check(
        "check_coverage flags low ratio but never quarantines; 0/0 passes",
        _coverage_never_quarantines,
    )

    def _max_report_caps_but_counts_true() -> None:
        recs = [bar(2, close=0.0) for _ in range(30)]
        for i, r in enumerate(recs):
            r["bar_date"] = date(2025, 1, 1) + __import__("datetime").timedelta(days=i)
        result = check_sanity(Dataset.DAILY_BARS, recs)
        assert result.details["n_violations"] == 30, result.details
        assert len(result.details["violations"]) == 20, result.details

    check(
        "violation list capped at 20 while n_violations reports the true count",
        _max_report_caps_but_counts_true,
    )

    print()
    if failed:
        print(f"quality selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"quality selftest: {passed} passed, 0 failed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.ingestion.quality",
        description="Pure row-level quality checks; --selftest needs no network or database.",
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if not args.selftest:
        parser.error("--selftest is the only mode; this module is a library otherwise.")
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
