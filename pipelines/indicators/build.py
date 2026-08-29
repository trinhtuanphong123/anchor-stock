"""pipelines.indicators.build — compute and persist technical_indicators_daily.

Reads typed equity bars and writes the display-only indicator series the dashboard charts:

    daily_bars -> technical_indicators_daily

Shape deliberately mirrors :mod:`pipelines.returns.build`: a pure row-builder
(:func:`compute_indicator_rows`, the analogue of ``compute_return_rows``) plus a runner
(:func:`run_build_indicators`) that resolves storage, loops tickers, and reports. Anything you
know about running ``python -m pipelines.returns.build`` transfers.

Read path
---------
Bars come through :meth:`BarSource.read_records`, not ``daily_bars()``. The latter is a lossy
projection returning only ``(date, close, volume)``, and ATR, Stochastic and the 252-day extremes
all need intraday ``high``/``low``. ``read_records`` was built generically from ``RECORD_KEYS``
in P6.4, so it served this dataset the moment ``ports.py`` learned about it.

Universe
--------
The ticker list is resolved exactly like every other CLI here: ``--tickers`` first, else the
universe file (:func:`pipelines.universe.file.resolve_universe`). Nothing in this module, or in
the views it feeds, knows how many tickers there are. Replacing ``list_stocks.txt`` with a
differently-balanced set and re-running the pipeline is therefore a data change, not a code
change — no count, no sector, and no ticker is hard-coded anywhere in P7.

NaN and NULL
------------
:mod:`pipelines.indicators.compute` produces ``np.nan`` during warm-up. **The conversion to
``None`` happens exactly once, here, in :func:`_clean`.** This is not stylistic: the storage
layer's ``_validate_records`` rejects any non-finite value in a ``FLOAT_COLS`` column, so a NaN
that survives to the sink is a hard stop at the end of a long compute. One conversion point
means there is one place for that to be right, rather than thirty.

Environment variables
---------------------
    DATN_STORAGE   ``local`` (default) or ``pg``; ``--storage`` overrides.
    DATABASE_URL   Postgres connection string, for ``--storage pg`` only. Never logged.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np

from pipelines.indicators.compute import (
    atr,
    bollinger,
    ema,
    obv,
    realized_vol,
    rolling_max,
    rolling_min,
    rsi,
    sma,
    stochastic,
    trailing_return,
    ytd_return,
)
from pipelines.storage.ports import INDICATOR_COLS, RECORD_KEYS, Dataset

logger = logging.getLogger(__name__)

__all__ = [
    "FIRST_VALID",
    "BuildIndicatorsResult",
    "bars_from_records",
    "compute_indicator_rows",
    "first_valid_report",
    "run_build_indicators",
]

SOURCE: str = "VCI"
MOCK_DEFAULT_TICKERS: list[str] = ["VCB", "FPT", "HPG"]

#: Mock series depth. Long enough that every column including the 252-session extremes has a
#: warm-up boundary inside the series, which is what makes ``--selftest``'s warm-up table a real
#: check rather than a check of NaN-everywhere.
_MOCK_DEPTH: int = 320


# ---------------------------------------------------------------------------
# The warm-up contract, machine-readable
# ---------------------------------------------------------------------------

#: The smallest index ``i`` at which each column is non-NULL, for a series with no missing
#: inputs. Stated once and asserted mechanically (``--selftest``, and
#: :func:`first_valid_report` on live data) rather than eyeballed off a chart — an off-by-one in
#: a warm-up is invisible in a plot and permanent in a database.
#:
#: ``ret_ytd`` is absent on purpose: its first valid index depends on where the calendar year
#: boundary falls in the loaded history, not on a fixed lookback.
FIRST_VALID: dict[str, int] = {
    "sma_20": 19, "sma_50": 49, "sma_200": 199,
    "ema_12": 11, "ema_26": 25,
    "macd": 25, "macd_signal": 33, "macd_hist": 33,
    "rsi_14": 14, "stoch_k_14": 13, "stoch_d_14": 15,
    "atr_14": 14,
    "bb_mid_20": 19, "bb_upper_20": 19, "bb_lower_20": 19, "bb_width_20": 19,
    "realized_vol_20d": 20, "realized_vol_60d": 60,
    "obv": 1, "volume_sma_20": 19, "turnover_value": 0,
    "ret_1d": 1, "ret_5d": 5, "ret_20d": 20, "ret_60d": 60, "ret_252d": 252,
    "dist_from_sma_200_pct": 199,
    "high_252d": 251, "low_252d": 251, "drawdown_from_252d_high": 251,
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class BuildIndicatorsResult:
    """Aggregate outcome of one indicator-build run. Shaped like ``BuildReturnsResult``."""

    tickers_attempted: int = 0
    tickers_succeeded: int = 0
    tickers_failed: int = 0
    tickers_empty: list[str] = field(default_factory=list)
    indicator_rows: int = 0
    null_counts: dict[str, int] = field(default_factory=dict)
    warmup_mismatches: list[str] = field(default_factory=list)
    live: bool = True
    errors: list[str] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        if self.tickers_attempted > 0 and self.tickers_failed == self.tickers_attempted:
            return "failed"
        if self.warmup_mismatches or self.errors:
            return "succeeded_with_findings"
        return "succeeded"


# ---------------------------------------------------------------------------
# Pure row building
# ---------------------------------------------------------------------------

#: One ascending session: ``(bar_date, high, low, close, volume)``. ``open`` is not carried —
#: no declared indicator uses it, and passing a column nothing reads invites someone to start.
Bar = tuple[date, Any, Any, Any, Any]


def bars_from_records(records: Sequence[Mapping[str, Any]]) -> list[Bar]:
    """Project ``daily_bars`` record dicts onto the tuples :func:`compute_indicator_rows` takes.

    Kept separate from the compute so the compute stays free of any storage vocabulary, and so a
    caller with bars from somewhere else (a fixture, a mock generator) uses the identical entry
    point.
    """
    return [
        (r["bar_date"], r.get("high"), r.get("low"), r["close"], r.get("volume"))
        for r in records
    ]


def _arr(values: Sequence[Any]) -> np.ndarray:
    """Coerce a column of possibly-``None`` numbers to float64, with ``None`` becoming NaN.

    NaN is how "missing" is spelled inside :mod:`pipelines.indicators.compute`, and a NaN in a
    window makes that window's output NaN — so a missing high propagates into ATR and the
    252-day extremes as NULL rather than as a substituted close.
    """
    return np.array([np.nan if v is None else float(v) for v in values], dtype=np.float64)


def _clean(v: Any) -> float | None:
    """The single NaN/inf -> ``None`` conversion point for this whole module. See the docstring.

    Anything non-finite becomes ``None``: NaN is warm-up, and an inf that slipped past a guard
    is a bug whose correct storage value is still "no number", not a row the sink rejects after
    an hour of compute. The guards in :mod:`~pipelines.indicators.compute` are what stop infs
    arising; this is the belt to their braces.
    """
    if v is None:
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def compute_indicator_rows(bars: Sequence[Bar]) -> list[dict[str, Any]]:
    """Every declared indicator for one ticker, one row per session.

    ``bars`` is ascending ``(bar_date, high, low, close, volume)``. Returns one dict per bar
    holding ``bar_date`` plus all 30 columns of ``technical_indicators_daily``; the caller adds
    ``ticker``, ``source`` and ``computed_at``.

    **A row is emitted for every session, including the warm-up.** Withholding the early rows
    and writing them as NULL are not equivalent: ``turnover_value`` is valid from the first bar,
    and a chart that starts 200 sessions late because bar 0 had no 200-day average would be
    wrong in a way nothing downstream could detect. NULL means "not enough history", which is
    exactly what is true there.

    Formula definitions are in :mod:`pipelines.indicators.compute`; warm-up boundaries are in
    :data:`FIRST_VALID`.
    """
    if not bars:
        return []

    dates = [b[0] for b in bars]
    high = _arr([b[1] for b in bars])
    low = _arr([b[2] for b in bars])
    close = _arr([b[3] for b in bars])
    volume = _arr([b[4] for b in bars])

    ema_12 = ema(close, 12)
    ema_26 = ema(close, 26)
    macd = ema_12 - ema_26
    macd_signal = _signal(macd, 9)
    macd_hist = macd - macd_signal

    pct_k, pct_d = stochastic(high, low, close, 14, 3)
    bb_mid, bb_upper, bb_lower, bb_width = bollinger(close, 20, 2.0)
    sma_200 = sma(close, 200)
    high_252 = rolling_max(high, 252)
    low_252 = rolling_min(low, 252)

    with np.errstate(invalid="ignore", divide="ignore"):
        dist_200 = np.where(sma_200 > 0.0, close / sma_200 - 1.0, np.nan)
        drawdown = np.where(high_252 > 0.0, close / high_252 - 1.0, np.nan)

    cols: dict[str, np.ndarray] = {
        "sma_20": sma(close, 20),
        "sma_50": sma(close, 50),
        "sma_200": sma_200,
        "ema_12": ema_12,
        "ema_26": ema_26,
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "rsi_14": rsi(close, 14),
        "stoch_k_14": pct_k,
        "stoch_d_14": pct_d,
        "atr_14": atr(high, low, close, 14),
        "bb_mid_20": bb_mid,
        "bb_upper_20": bb_upper,
        "bb_lower_20": bb_lower,
        "bb_width_20": bb_width,
        "realized_vol_20d": realized_vol(close, 20),
        "realized_vol_60d": realized_vol(close, 60),
        "obv": obv(close, volume),
        "volume_sma_20": sma(volume, 20),
        "turnover_value": close * volume,
        "ret_1d": trailing_return(close, 1),
        "ret_5d": trailing_return(close, 5),
        "ret_20d": trailing_return(close, 20),
        "ret_60d": trailing_return(close, 60),
        # 252 SESSIONS, not 365 days — the same convention high_252d/low_252d use, and the
        # reason the column is named for a session count while the dashboard labels it 1Y.
        "ret_252d": trailing_return(close, 252),
        "ret_ytd": ytd_return(close, dates),
        "dist_from_sma_200_pct": dist_200,
        "high_252d": high_252,
        "low_252d": low_252,
        "drawdown_from_252d_high": drawdown,
    }
    missing = set(INDICATOR_COLS) - set(cols)
    extra = set(cols) - set(INDICATOR_COLS)
    if missing or extra:
        raise AssertionError(
            f"column set drifted from ports.INDICATOR_COLS: missing={sorted(missing)} "
            f"extra={sorted(extra)}"
        )

    return [
        {"bar_date": dates[i], **{c: _clean(cols[c][i]) for c in INDICATOR_COLS}}
        for i in range(len(bars))
    ]


def _signal(macd: np.ndarray, n: int) -> np.ndarray:
    """``n``-period EMA of the MACD line, seeded with the mean of its first ``n`` valid values.

    The seeding runs over the *valid* stretch of ``macd``, not over the whole array: MACD is NaN
    until ``i = 25``, and feeding those NaNs to :func:`~pipelines.indicators.compute.ema` would
    make every signal value NaN forever.
    """
    out = np.full(macd.shape, np.nan, dtype=np.float64)
    valid = np.flatnonzero(np.isfinite(macd))
    if valid.size == 0:
        return out
    start = int(valid[0])
    out[start:] = ema(macd[start:], n)
    return out


# ---------------------------------------------------------------------------
# Warm-up verification, usable on live data
# ---------------------------------------------------------------------------


def first_valid_report(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, int | None], list[str]]:
    """``(first non-NULL index per column, mismatches against :data:`FIRST_VALID`)``.

    The mechanical form of the plan's validation check 5. A column whose warm-up is longer than
    the loaded series legitimately has no non-NULL index at all — that is reported as ``None``
    and is not a mismatch. ``ret_ytd`` is not checked (see :data:`FIRST_VALID`).
    """
    n = len(rows)
    first: dict[str, int | None] = {}
    for col in INDICATOR_COLS:
        idx = next((i for i in range(n) if rows[i].get(col) is not None), None)
        first[col] = idx

    mismatches: list[str] = []
    for col, expected in FIRST_VALID.items():
        got = first[col]
        if expected >= n:
            if got is not None:
                mismatches.append(f"{col}: series has {n} rows (< warm-up {expected}) but "
                                  f"first non-NULL is {got}")
        elif got != expected:
            mismatches.append(f"{col}: first non-NULL {got}, expected {expected}")
    return first, mismatches


# ---------------------------------------------------------------------------
# Mock generator — generated, never read, so --mock needs no storage at all
# ---------------------------------------------------------------------------


def _mock_series(seed: int, base: float, depth: int = _MOCK_DEPTH) -> list[Bar]:
    """Deterministic synthetic ``(date, high, low, close, volume)`` walk ending today.

    Spans two calendar years by construction (``depth`` >= 320 calendar days back), so ``--mock``
    exercises ``ret_ytd``'s year boundary rather than leaving it permanently NULL.
    """
    rng = random.Random(seed)
    today = date.today()
    out: list[Bar] = []
    level = base
    for i in range(depth):
        d = today - timedelta(days=depth - 1 - i)
        level *= 1.0 + rng.gauss(0.0005, 0.012)
        c = round(level, 2)
        hi = round(c * (1.0 + abs(rng.gauss(0.0, 0.006))), 2)
        lo = round(c * (1.0 - abs(rng.gauss(0.0, 0.006))), 2)
        vol = round(max(0.0, rng.gauss(1_000_000, 250_000)), 0)
        out.append((d, hi, lo, c, vol))
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_build_indicators(
    tickers: Sequence[str],
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    mock: bool = False,
    source: str = SOURCE,
    reader: Any = None,
    writer: Any = None,
    batch: int = 5000,
) -> BuildIndicatorsResult:
    """Compute and (live) persist indicators for ``tickers``.

    ``reader``/``writer`` are a :class:`~pipelines.storage.ports.BarSource` and
    :class:`~pipelines.storage.ports.BarSink`; ``None`` resolves them from ``$DATN_STORAGE``.
    Named reader/writer rather than source/sink because ``source`` already means the provider
    column written into every record.

    **Read the full history even when only recent rows are wanted.** ``start_date`` bounds what
    is *loaded*, and every warm-up is measured from the first loaded bar — asking for the last
    30 sessions produces 30 rows of almost entirely NULL, not 30 correct rows. The default is
    unbounded for exactly that reason; the argument exists for inspection, not for incremental
    runs.
    """
    result = BuildIndicatorsResult(tickers_attempted=len(tickers), live=not mock)
    computed_at = datetime.now(UTC)
    null_counts: dict[str, int] = dict.fromkeys(INDICATOR_COLS, 0)

    if not mock and (reader is None or writer is None):
        from pipelines.storage.factory import make_sink, make_source  # noqa: PLC0415

        reader = reader if reader is not None else make_source()
        writer = writer if writer is not None else make_sink()

    for i, ticker in enumerate(tickers):
        try:
            if mock:
                bars = _mock_series(seed=1000 + i, base=10.0 + i)
            else:
                bars = bars_from_records(
                    reader.read_records(
                        Dataset.DAILY_BARS, ticker, start_date, end_date, source=source
                    )
                )
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not end the run
            result.tickers_failed += 1
            result.errors.append(f"{ticker}: load failed: {type(exc).__name__}: {exc}")
            continue

        if not bars:
            result.tickers_empty.append(ticker)
            result.tickers_succeeded += 1
            logger.info("[%s] no bars; nothing to compute.", ticker)
            continue

        rows = compute_indicator_rows(bars)
        for r in rows:
            r.update({"ticker": ticker, "source": source, "computed_at": computed_at})
        for col in INDICATOR_COLS:
            null_counts[col] += sum(1 for r in rows if r[col] is None)

        _, mismatches = first_valid_report(rows)
        result.warmup_mismatches.extend(f"{ticker}: {m}" for m in mismatches)

        if not mock:
            try:
                for j in range(0, len(rows), batch):
                    writer.write_indicators(rows[j : j + batch])
            except Exception as exc:  # noqa: BLE001
                result.tickers_failed += 1
                result.errors.append(f"{ticker}: write failed: {type(exc).__name__}: {exc}")
                continue

        result.indicator_rows += len(rows)
        result.tickers_succeeded += 1
        logger.info("[%s] %d indicator rows (%s .. %s).",
                    ticker, len(rows), rows[0]["bar_date"], rows[-1]["bar_date"])

    result.null_counts = null_counts
    return result


# ---------------------------------------------------------------------------
# Self-check — closed-form fixtures only. No network, no database, no pandas-ta.
# ---------------------------------------------------------------------------


def _selftest() -> int:  # noqa: PLR0915 - a linear checklist reads better than twenty helpers
    import shutil  # noqa: PLC0415
    import tempfile as _tempfile  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:  # noqa: ANN001
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the point is to report, not propagate
            failed.append(label)
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    def close(a: float, b: float, tol: float = 1e-9) -> bool:
        return abs(a - b) <= tol * max(1.0, abs(b))

    # --- 1. SMA of a linear ramp is exact, in closed form ------------------
    def _sma_ramp() -> None:
        a, b, n = 5.0, 0.75, 20
        x = np.array([a + b * i for i in range(60)], dtype=np.float64)
        got = sma(x, n)
        for i in range(n - 1):
            _assert(np.isnan(got[i]), f"sma_{n}[{i}] should be NaN, got {got[i]}")
        for i in range(n - 1, x.size):
            want = x[i] - b * (n - 1) / 2.0
            _assert(close(float(got[i]), want), f"sma[{i}] = {got[i]}, want {want}")

    check("SMA of a linear ramp equals close - b(n-1)/2, exactly", _sma_ramp)

    # --- 2. EMA against the explicit recursion, term by term ---------------
    def _ema_recursion() -> None:
        x = np.array([1.0, 3.0, 2.0, 8.0, 5.0, 4.0, 9.0], dtype=np.float64)
        n = 3
        got = ema(x, n)
        _assert(np.isnan(got[0]) and np.isnan(got[1]), "EMA warm-up is not NaN")
        alpha = 2.0 / (n + 1.0)
        want = (1.0 + 3.0 + 2.0) / 3.0
        _assert(close(float(got[2]), want), f"EMA seed {got[2]} != SMA {want}")
        for i in range(3, x.size):
            want = alpha * float(x[i]) + (1.0 - alpha) * want
            _assert(close(float(got[i]), want), f"EMA[{i}] = {got[i]}, want {want}")

    check("EMA matches its own recursion, seeded with the SMA", _ema_recursion)

    # --- 3. The MACD identity, on a full synthetic build -------------------
    bars = _mock_series(seed=7, base=42.0)
    rows = compute_indicator_rows(bars)

    def _macd_identity() -> None:
        n = 0
        for r in rows:
            if r["macd"] is None:
                _assert(r["ema_12"] is None or r["ema_26"] is None,
                        f"macd NULL on {r['bar_date']} but both EMAs present")
                continue
            _assert(close(r["macd"], r["ema_12"] - r["ema_26"], 1e-12),
                    f"macd != ema_12 - ema_26 on {r['bar_date']}")
            n += 1
        _assert(n > 200, f"only {n} rows exercised the identity")
        for r in rows:
            if r["macd_hist"] is not None:
                _assert(close(r["macd_hist"], r["macd"] - r["macd_signal"], 1e-12),
                        f"macd_hist != macd - macd_signal on {r['bar_date']}")

    check("macd == ema_12 - ema_26 and macd_hist == macd - macd_signal, every row",
          _macd_identity)

    # --- 4/5. RSI extremes and the zero-loss edge --------------------------
    def _rsi_monotone() -> None:
        up = np.array([100.0 + i for i in range(40)], dtype=np.float64)
        down = np.array([100.0 - i for i in range(40)], dtype=np.float64)
        gu, gd = rsi(up, 14), rsi(down, 14)
        _assert(np.isnan(gu[13]), "RSI valid one bar too early")
        _assert(gu[14] == 100.0, f"strictly increasing RSI = {gu[14]}, want exactly 100.0")
        _assert(gd[14] == 0.0, f"strictly decreasing RSI = {gd[14]}, want exactly 0.0")
        for i in range(14, 40):
            _assert(gu[i] == 100.0 and gd[i] == 0.0, f"RSI drifted off the extreme at {i}")

    check("RSI is exactly 100 on a rising series and exactly 0 on a falling one", _rsi_monotone)

    def _rsi_no_loss() -> None:
        # Rises then flattens: still zero losses, so still the limit — not inf, not NaN.
        x = np.array([10.0 + i for i in range(20)] + [29.0] * 10, dtype=np.float64)
        got = rsi(x, 14)
        for i in range(14, x.size):
            _assert(np.isfinite(got[i]), f"RSI[{i}] is {got[i]} — inf/NaN escaped the guard")
            _assert(got[i] == 100.0, f"RSI[{i}] = {got[i]} with no losses in the window")

    check("RSI with zero losses is 100.0, never inf or NaN", _rsi_no_loss)

    # --- 6. ATR on a series engineered to have constant true range ---------
    def _atr_constant() -> None:
        c = np.full(40, 25.0)
        got = atr(c + 1.0, c - 1.0, c, 14)          # TR = max(2, 1, 1) = 2 every session
        _assert(np.isnan(got[13]), "ATR valid one bar too early")
        for i in range(14, 40):
            _assert(close(float(got[i]), 2.0), f"ATR[{i}] = {got[i]}, want 2.0")

    check("ATR of a constant-true-range series equals that constant", _atr_constant)

    # --- 7. Bollinger on a constant series ---------------------------------
    def _bollinger_constant() -> None:
        x = np.full(40, 17.5)
        mid, up, lo, w = bollinger(x, 20, 2.0)
        _assert(np.isnan(mid[18]), "bb valid one bar too early")
        for i in range(19, 40):
            _assert(close(float(mid[i]), 17.5), f"mid[{i}] = {mid[i]}")
            _assert(float(up[i]) == float(lo[i]) == float(mid[i]), "sigma != 0 on a constant")
            _assert(float(w[i]) == 0.0, f"width[{i}] = {w[i]}, want 0.0")

    check("Bollinger on a constant series: sigma = 0, upper == lower == mid, width == 0",
          _bollinger_constant)

    # --- 8. Stochastic at both rails and on a flat range -------------------
    def _stoch_rails() -> None:
        n = 20
        hi = np.array([50.0 + (i % 5) for i in range(n)], dtype=np.float64)
        lo = np.array([40.0 - (i % 5) for i in range(n)], dtype=np.float64)
        at_high = np.array([float(np.max(hi[max(0, i - 13): i + 1])) for i in range(n)])
        at_low = np.array([float(np.min(lo[max(0, i - 13): i + 1])) for i in range(n)])
        k_hi, _ = stochastic(hi, lo, at_high, 14, 3)
        k_lo, _ = stochastic(hi, lo, at_low, 14, 3)
        for i in range(13, n):
            _assert(close(float(k_hi[i]), 100.0), f"%K at the window high = {k_hi[i]}")
            _assert(close(float(k_lo[i]), 0.0, 1e-12), f"%K at the window low = {k_lo[i]}")
        flat = np.full(n, 30.0)
        k_flat, d_flat = stochastic(flat, flat, flat, 14, 3)
        _assert(np.isnan(k_flat[12]), "%K valid one bar too early")
        _assert(float(k_flat[13]) == 50.0, f"flat-range %K = {k_flat[13]}, want exactly 50.0")
        _assert(np.isnan(d_flat[14]) and float(d_flat[15]) == 50.0, "%D warm-up is wrong")

    check("Stochastic: 100 at the window high, 0 at the low, 50 on a flat range", _stoch_rails)

    # --- 9. OBV on an alternating series, hand-computed --------------------
    def _obv_alternating() -> None:
        c = np.array([10.0, 11.0, 10.0, 10.0, 12.0], dtype=np.float64)
        v = np.array([100.0, 200.0, 300.0, 400.0, 500.0], dtype=np.float64)
        got = obv(c, v)
        want = [None, 200.0, -100.0, -100.0, 400.0]   # +200, -300, 0 (unchanged), +500
        _assert(np.isnan(got[0]), "OBV at i=0 must be NaN, not 0")
        for i in range(1, 5):
            _assert(close(float(got[i]), want[i]), f"OBV[{i}] = {got[i]}, want {want[i]}")

    check("OBV on an alternating series matches the hand-computed running total", _obv_alternating)

    # --- 10. Realised vol of a geometric series is exactly zero ------------
    def _vol_geometric() -> None:
        x = np.array([10.0 * (1.01 ** i) for i in range(80)], dtype=np.float64)
        got = realized_vol(x, 20)
        _assert(np.isnan(got[19]), "realized_vol valid one bar too early")
        for i in range(20, 80):
            _assert(abs(float(got[i])) < 1e-9, f"vol[{i}] = {got[i]}, want ~0 on constant returns")

    check("realized_vol of a constant-growth series is 0", _vol_geometric)

    # --- 11. Trailing returns are simple returns, as fractions -------------
    def _trailing() -> None:
        x = np.array([100.0, 105.0, 110.0, 99.0, 107.0], dtype=np.float64)
        got = trailing_return(x, 1)
        _assert(np.isnan(got[0]), "ret_1d at i=0 must be NaN")
        _assert(close(float(got[1]), 0.05), f"ret_1d[1] = {got[1]}, want 0.05 (a fraction)")
        g5 = trailing_return(x, 4)
        _assert(close(float(g5[4]), 0.07), f"ret_4[4] = {g5[4]}, want 0.07")

    check("trailing_return is the simple return, stored as a fraction not a percent", _trailing)

    # --- 12. ret_ytd across a real year boundary ---------------------------
    def _ytd() -> None:
        dates = [date(2024, 12, 30), date(2024, 12, 31),
                 date(2025, 1, 2), date(2025, 1, 3), date(2026, 1, 5)]
        x = np.array([90.0, 100.0, 110.0, 121.0, 60.5], dtype=np.float64)
        got = ytd_return(x, dates)
        _assert(np.isnan(got[0]) and np.isnan(got[1]), "2024 sessions have no prior-year close")
        _assert(close(float(got[2]), 0.10), f"ytd[2] = {got[2]}, want 0.10")
        _assert(close(float(got[3]), 0.21), f"ytd[3] = {got[3]}, want 0.21")
        _assert(close(float(got[4]), -0.50), f"ytd[4] = {got[4]}, want -0.50 (base = 121.0)")

    check("ret_ytd rebases at each year boundary and is NULL in the first year", _ytd)

    # --- 13. The warm-up table, asserted mechanically ----------------------
    def _warmup() -> None:
        first, mismatches = first_valid_report(rows)
        _assert(not mismatches, "; ".join(mismatches))
        for col, expected in FIRST_VALID.items():
            _assert(rows[expected][col] is not None, f"{col} is NULL at its first valid index")
            if expected > 0:
                _assert(rows[expected - 1][col] is None,
                        f"{col} is non-NULL one bar before {expected}")
        _assert(first["ret_ytd"] is not None, "the mock series should cross a year boundary")

    check("every column is NULL below its warm-up index and non-NULL at it", _warmup)

    # --- 14. Nothing non-finite can reach the sink -------------------------
    def _no_nan_escapes() -> None:
        for r in rows:
            for col in INDICATOR_COLS:
                v = r[col]
                _assert(v is None or (isinstance(v, float) and math.isfinite(v)),
                        f"{col} on {r['bar_date']} is {v!r}")

    check("no record holds NaN or inf — warm-up is None, nothing else", _no_nan_escapes)

    # --- 15. The record shape the sink expects -----------------------------
    def _record_shape() -> None:
        ts = datetime.now(UTC)
        r = dict(rows[-1])
        r.update({"ticker": "VCB", "source": "VCI", "computed_at": ts})
        want = set(RECORD_KEYS[Dataset.INDICATORS_DAILY])
        _assert(set(r) == want, f"record keys differ: missing {want - set(r)}, extra {set(r)-want}")

    check("a built record carries exactly RECORD_KEYS[INDICATORS_DAILY]", _record_shape)

    # --- 16. The FLOAT_COLS trap: parquet dtypes, checked not trusted ------
    def _parquet_dtypes() -> None:
        import pyarrow.parquet as pq  # noqa: PLC0415

        from pipelines.common.paths import shard_path  # noqa: PLC0415
        from pipelines.storage.localfs import LocalSink, LocalSource  # noqa: PLC0415

        tmp = Path(_tempfile.mkdtemp(prefix="datn_indicators_"))
        prev = os.environ.get("DATN_DATA_ROOT")
        os.environ["DATN_DATA_ROOT"] = str(tmp)
        try:
            res = run_build_indicators(
                ["VCB"], reader=_FixtureSource(bars), writer=LocalSink(), source="VCI"
            )
            _assert(res.indicator_rows == len(bars), f"wrote {res.indicator_rows} rows")
            _assert(not res.errors, str(res.errors))

            schema = pq.ParquetFile(
                shard_path("technical_indicators_daily", "ticker", "VCB")
            ).schema_arrow
            for col in INDICATOR_COLS:
                t = str(schema.field(col).type)
                _assert(t == "double", f"{col} landed in parquet as {t!r}, not float64 — "
                                       f"the FLOAT_COLS trap")

            back = LocalSource().read_records(Dataset.INDICATORS_DAILY, "VCB", source="VCI")
            _assert(len(back) == len(bars), f"read back {len(back)} of {len(bars)}")
            _assert(tuple(back[0]) == RECORD_KEYS[Dataset.INDICATORS_DAILY], "key order changed")
            _assert(back[-1]["rsi_14"] is not None, "rsi_14 vanished on the round trip")
            _assert(type(back[-1]["turnover_value"]) is float, "turnover_value is not a float")
        finally:
            if prev is None:
                os.environ.pop("DATN_DATA_ROOT", None)
            else:
                os.environ["DATN_DATA_ROOT"] = prev
            shutil.rmtree(tmp, ignore_errors=True)

    check("indicators round-trip through LocalSink as float64, not string", _parquet_dtypes)

    # --- 17. Re-running writes the same bytes ------------------------------
    def _empty_and_short() -> None:
        _assert(compute_indicator_rows([]) == [], "empty input must give no rows")
        short = compute_indicator_rows(bars[:3])
        _assert(len(short) == 3, "a 3-bar series must still produce 3 rows")
        _assert(short[0]["turnover_value"] is not None, "turnover_value needs no history")
        _assert(short[2]["sma_20"] is None, "sma_20 cannot exist on bar 2")
        _, mismatches = first_valid_report(short)
        _assert(not mismatches, "; ".join(mismatches))

    check("a series shorter than the warm-up yields rows, all NULL above turnover",
          _empty_and_short)

    print()
    if failed:
        print(f"indicators selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"indicators selftest: {passed} passed, 0 failed")
    return 0


class _FixtureSource:
    """A ``BarSource``-shaped stub returning one fixed bar series. Selftest only."""

    def __init__(self, bars: Sequence[Bar]) -> None:
        self._records = [
            {"ticker": "VCB", "bar_date": d, "source": "VCI", "open": c, "high": h,
             "low": lo, "close": c, "volume": v, "is_adjusted": True,
             "ingested_at": None, "updated_at": None}
            for (d, h, lo, c, v) in bars
        ]

    def read_records(self, dataset, key, start=None, end=None, *, source):  # noqa: ANN001, ARG002
        return [dict(r) for r in self._records]


def _assert(cond: bool, what: object) -> None:
    if not cond:
        raise AssertionError(str(what))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_tickers(arg_tickers: str | None, mock: bool) -> list[str]:
    """Explicit ``--tickers`` first, else the universe file. Never a silent database fallback.

    Identical to ``returns/build.py``'s resolution, deliberately: swapping the universe file is
    how the ticker set changes, and every stage of the pipeline has to read it the same way for
    that to be a single edit.
    """
    if mock and not arg_tickers:
        return list(MOCK_DEFAULT_TICKERS)

    from pipelines.universe.file import resolve_universe  # noqa: PLC0415

    return list(resolve_universe(arg_tickers).tickers)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.indicators.build",
        description=(
            "Compute & persist technical_indicators_daily from daily_bars. Display only — "
            "never an input to the factor model or anchor selection (docs/04 §5)."
        ),
    )
    parser.add_argument("--selftest", action="store_true",
                        help="Closed-form fixture checklist. No network, no database.")
    parser.add_argument("--mock", action="store_true",
                        help="Synthetic bars; computes but writes nothing.")
    parser.add_argument("--tickers", type=str, default=None, metavar="LIST",
                        help="Comma/space tickers. Default: mock set, or the universe file.")
    parser.add_argument("--universe", type=str, default=None, metavar="PATH",
                        help="Universe file to read instead of list_stocks.txt.")
    parser.add_argument("--storage", type=str, default=None, choices=["local", "pg"],
                        help="Backend. Default: $DATN_STORAGE, else local.")
    parser.add_argument("--source", type=str, default=SOURCE, metavar="SRC",
                        help=f"Provider column value to read and write (default {SOURCE}).")
    parser.add_argument("--start", type=str, default=None, metavar="YYYY-MM-DD",
                        help="Load bars from this date. Warm-ups measure from the first LOADED "
                             "bar, so a narrow window yields mostly-NULL rows. Default: all.")
    parser.add_argument("--end", type=str, default=None, metavar="YYYY-MM-DD",
                        help="Load bars through this date (inclusive). Default: all.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.selftest:
        return _selftest()

    def _parse(s: str | None) -> date | None:
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            logger.error("Invalid date %r (expected YYYY-MM-DD).", s)
            sys.exit(2)

    if args.universe and args.tickers:
        logger.error("Pass --tickers or --universe, not both.")
        return 2
    if args.universe:
        from pipelines.universe.file import read_universe_file  # noqa: PLC0415

        tickers = list(read_universe_file(args.universe).tickers)
    else:
        tickers = _resolve_tickers(args.tickers, args.mock)

    reader = writer = None
    if not args.mock:
        from pipelines.storage.factory import make_sink, make_source  # noqa: PLC0415

        reader, writer = make_source(args.storage), make_sink(args.storage)

    logger.info("=== build_indicators starting (tickers=%d storage=%s mock=%s) ===",
                len(tickers), args.storage or os.environ.get("DATN_STORAGE") or "local", args.mock)
    result = run_build_indicators(
        tickers, start_date=_parse(args.start), end_date=_parse(args.end),
        mock=args.mock, source=args.source, reader=reader, writer=writer,
    )

    logger.info("build_indicators %s — tickers=%d/%d rows=%d empty=%s live=%s",
                result.overall_status, result.tickers_succeeded, result.tickers_attempted,
                result.indicator_rows, result.tickers_empty or "none", result.live)
    if result.indicator_rows:
        print()
        print(f"{'column':<26}{'NULLs':>9}{'of rows':>10}")
        for col in INDICATOR_COLS:
            print(f"{col:<26}{result.null_counts[col]:>9}{result.indicator_rows:>10}")
    for m in result.warmup_mismatches[:20]:
        logger.warning("warm-up mismatch: %s", m)
    if len(result.warmup_mismatches) > 20:
        logger.warning("... and %d more warm-up mismatches", len(result.warmup_mismatches) - 20)
    for e in result.errors:
        logger.error("%s", e)

    return 0 if result.overall_status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
