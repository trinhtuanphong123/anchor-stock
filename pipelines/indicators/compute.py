"""pipelines.indicators.compute — the indicator formulas, pinned. Pure numpy, no I/O.

Why this file states every formula rather than calling a library
---------------------------------------------------------------
"RSI" names a *family*, not a formula. Wilder smoothing, a simple moving average of gains, and
an EMA of gains all ship under that name and disagree by several points on the same series. The
same is true of Stochastic (%D as SMA or EMA), Bollinger (population or sample sigma), and ATR.

``pandas-ta`` is installed on this machine but undeclared — exactly ``pyarrow``'s status before
D-3 — and adopting it would make that library's smoothing defaults an unwritten part of this
project's specification. It would also make verification circular: checking an RSI against
another RSI implementation proves the two agree, not that either is right. So the formulas live
here, in one file, and :mod:`pipelines.indicators.build`'s ``--selftest`` checks them against
series whose correct answer is known *by construction* (a linear ramp's SMA, a monotone series'
RSI, a constant-true-range series' ATR). No cross-check against ``pandas-ta`` exists or should
be added.

Conventions that hold for every function here
---------------------------------------------
* Input is one ticker's ascending session series, as a float64 array. Index ``i`` is 0-based.
* **Warm-up is ``np.nan``**, never 0 and never a back-filled value. A 200-day average has no
  value on bar 37, and NaN is how that is said in an array. :mod:`pipelines.indicators.build`
  converts NaN to ``None`` exactly once, at the record boundary — the sink rejects non-finite
  values, so nothing else may leak.
* **A NaN anywhere in a window makes that window's output NaN.** The rule is "NULL window →
  NULL indicator, never a substituted close". Note the consequence for the *recursive*
  indicators (EMA, MACD, RSI, ATR): a single NaN close poisons every later value, not just its
  own window. That is accepted rather than patched, because ``daily_bars`` refuses to store a
  null close at all (``localfs._validate_records``), so the input cannot contain one.
* **Ratios are fractions, not percents** (S2): ``0.07`` means +7%. This holds for ``ret_*``,
  ``dist_from_sma_200_pct`` (the ``_pct`` in that DDL column name is legacy and does *not*
  change its unit), ``drawdown_from_252d_high`` and ``bb_width_20``. It matches
  ``daily_returns.log_return`` sitting beside them in the database. Formatting to "%" is a
  display-edge concern and belongs to P9/P10.
* **Prices are adjusted closes** (D-15, consistent with D-6). An adjusted chart will not match a
  broker's raw chart across an ex-date; that has to be said on the dashboard, not fixed here.
* Every function returns an array the same length as its input, so callers can index it by ``i``
  with no offset arithmetic. Offsets are where this kind of code goes wrong.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np

__all__ = [
    "ANNUALISATION",
    "FLAT_RANGE_K",
    "NO_LOSS_RSI",
    "atr",
    "bollinger",
    "ema",
    "obv",
    "realized_vol",
    "rolling_max",
    "rolling_min",
    "rsi",
    "sma",
    "stochastic",
    "trailing_return",
    "wilder",
    "ytd_return",
]

#: Trading sessions per year, for annualising a daily standard deviation. 252 is the convention
#: docs/01 uses for the noise floor; keeping the same constant here means a realized-vol figure
#: and a noise-floor figure are on the same scale.
ANNUALISATION: float = 252.0

#: Stochastic %K when the 14-session range is exactly flat (high == low all window). The ratio
#: is 0/0, so *some* value has to be chosen. 50.0 is the midpoint, which is what "where in its
#: range is the close" means when the range has no width. The alternative — NaN — would report
#: a flat, untraded stock as missing data rather than as unremarkable.
FLAT_RANGE_K: float = 50.0

#: RSI when there are no losses in the window. ``avg_loss == 0`` makes RS infinite, so the limit
#: is taken directly instead of dividing. Without this the column would hold inf, which the sink
#: rejects at the end of a long compute, or NaN, which reads as "no history".
NO_LOSS_RSI: float = 100.0


def _windows(x: np.ndarray, n: int) -> np.ndarray:
    """Sliding windows of width ``n``, shape ``(len(x) - n + 1, n)``. Raises for ``n < 1``.

    A view, not a copy. NaN is deliberately NOT masked out: a window holding one is meant to
    produce NaN.
    """
    if n < 1:
        raise ValueError(f"window must be >= 1, got {n}")
    return np.lib.stride_tricks.sliding_window_view(x, n)


def _empty(x: np.ndarray) -> np.ndarray:
    return np.full(x.shape, np.nan, dtype=np.float64)


def sma(x: np.ndarray, n: int) -> np.ndarray:
    """Simple moving average. ``out[i] = mean(x[i-n+1 ... i])``; NaN for ``i < n-1``.

    Deliberately a windowed mean rather than a cumulative-sum difference. ``cumsum`` is O(N)
    instead of O(N*n) but propagates a single NaN to every subsequent value, which would turn
    one missing bar into a permanently blank column.
    """
    out = _empty(x)
    if x.size >= n:
        out[n - 1 :] = _windows(x, n).mean(axis=1)
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """Exponential moving average, alpha = 2/(n+1), **seeded with the SMA of the first n values**.

    ``out[n-1] = mean(x[0 ... n-1])``, then ``out[i] = a*x[i] + (1-a)*out[i-1]``. NaN before.

    The seed is the choice that matters and the one libraries disagree on. Seeding with ``x[0]``
    instead makes the first few dozen values depend heavily on one arbitrary session; seeding
    with the SMA is Wilder's own presentation and is what makes ``ema_12``/``ema_26`` — and
    therefore MACD — reproducible from this docstring alone.
    """
    out = _empty(x)
    if x.size < n:
        return out
    alpha = 2.0 / (n + 1.0)
    prev = float(np.mean(x[:n]))
    out[n - 1] = prev
    for i in range(n, x.size):
        prev = alpha * float(x[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


def wilder(x: np.ndarray, n: int, *, first: int) -> np.ndarray:
    """Wilder smoothing of ``x``, seeded at index ``first`` with ``mean(x[first-n+1 ... first])``.

    ``out[i] = (out[i-1]*(n-1) + x[i]) / n`` thereafter. This is *not* an EMA with
    alpha = 2/(n+1): Wilder's recursion is alpha = 1/n, i.e. the alpha = 2/(2n-1) EMA. RSI and
    ATR both use it, and substituting the ordinary EMA is the single most common way these two
    columns come out wrong.
    """
    out = _empty(x)
    if first >= x.size or first - n + 1 < 0:
        return out
    prev = float(np.mean(x[first - n + 1 : first + 1]))
    out[first] = prev
    for i in range(first + 1, x.size):
        prev = (prev * (n - 1) + float(x[i])) / n
        out[i] = prev
    return out


def rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    """Wilder's RSI. First valid at ``i = n``.

    ``avg_gain``/``avg_loss`` start as the simple mean of the first ``n`` up/down close changes
    (the changes at ``i = 1 ... n``), then follow Wilder's recursion.
    ``RSI = 100 - 100/(1 + RS)``.

    ``avg_loss == 0`` returns exactly :data:`NO_LOSS_RSI` rather than dividing — see that
    constant. Note the consequence for a perfectly flat series: no losses *and* no gains still
    reports 100. That follows from the rule as stated and is left as stated, because the
    alternative (special-casing "flat" to 50) would make the column's definition depend on two
    thresholds instead of one.
    """
    out = _empty(close)
    if close.size <= n:
        return out
    delta = np.diff(close)                       # delta[k] is the change at close index k+1
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = float(np.mean(gain[:n]))
    avg_loss = float(np.mean(loss[:n]))

    def _rsi(g: float, ell: float) -> float:
        if not (np.isfinite(g) and np.isfinite(ell)):
            return float("nan")
        if ell == 0.0:
            return NO_LOSS_RSI
        return 100.0 - 100.0 / (1.0 + g / ell)

    out[n] = _rsi(avg_gain, avg_loss)
    for i in range(n + 1, close.size):
        avg_gain = (avg_gain * (n - 1) + float(gain[i - 1])) / n
        avg_loss = (avg_loss * (n - 1) + float(loss[i - 1])) / n
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    """``max(x[i-n+1 ... i])``; NaN for ``i < n-1``."""
    out = _empty(x)
    if x.size >= n:
        out[n - 1 :] = _windows(x, n).max(axis=1)
    return out


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    """``min(x[i-n+1 ... i])``; NaN for ``i < n-1``."""
    out = _empty(x)
    if x.size >= n:
        out[n - 1 :] = _windows(x, n).min(axis=1)
    return out


def stochastic(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, k: int = 14, d: int = 3
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic ``(%K, %D)``.

    ``%K[i] = 100 * (close[i] - min(low[i-k+1 ... i])) / (max(high[i-k+1 ... i]) - min(low))``,
    first valid at ``i = k-1``. A zero denominator gives :data:`FLAT_RANGE_K`.

    ``%D`` is the **simple** ``d``-period moving average of %K (first valid at ``i = k+d-2``),
    not an EMA — the other common convention, and one that would put a second smoothing
    parameter into a column the DDL names only ``stoch_d_14``.
    """
    hh = rolling_max(high, k)
    ll = rolling_min(low, k)
    rng = hh - ll
    with np.errstate(invalid="ignore", divide="ignore"):
        pct_k = np.where(rng == 0.0, FLAT_RANGE_K, 100.0 * (close - ll) / rng)
    # np.where evaluates both branches, so a NaN window has to be restored explicitly. A *zero*
    # range only occurs where hh and ll are both finite, which is exactly when the flat-range
    # value is the right answer.
    pct_k = np.where(np.isnan(rng) | np.isnan(close), np.nan, pct_k)
    return pct_k, sma(pct_k, d)


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    """Wilder's Average True Range. First valid at ``i = n``.

    ``TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|, |low[i] - close[i-1]|)``, defined
    from ``i = 1`` — the first session has no prior close, so it has no true range, and the
    common shortcut of substituting ``high[0] - low[0]`` is deliberately not taken. The first
    ATR is ``mean(TR[1 ... n])``, then :func:`wilder`.
    """
    out = _empty(close)
    if close.size <= n:
        return out
    prev_close = close[:-1]
    tr_tail = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - prev_close), np.abs(low[1:] - prev_close)),
    )
    tr = np.concatenate(([np.nan], tr_tail))     # tr[0] is undefined, by construction
    out[n:] = wilder(tr, n, first=n)[n:]
    return out


def bollinger(
    close: np.ndarray, n: int = 20, k: float = 2.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger bands: ``(mid, upper, lower, width)``. First valid at ``i = n-1``.

    ``mid`` is the ``n``-period SMA; sigma is the **population** standard deviation of the same
    window (``ddof=0``, the original definition — the sample form would widen every band by
    sqrt(20/19) ~ 2.6%); ``upper/lower = mid +/- k*sigma``.

    ``width = (upper - lower) / mid = 2*k*sigma/mid``, a **fraction** (S2). It is NaN where
    ``mid <= 0``: dividing there would produce an inf that the sink rejects at the very end of a
    long compute, or a negative width, and neither is a number anyone should chart.
    """
    mid = sma(close, n)
    sd = _empty(close)
    if close.size >= n:
        sd[n - 1 :] = _windows(close, n).std(axis=1, ddof=0)
    upper = mid + k * sd
    lower = mid - k * sd
    with np.errstate(invalid="ignore", divide="ignore"):
        width = np.where(mid > 0.0, (upper - lower) / mid, np.nan)
    return mid, upper, lower, width


def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """On-balance volume. First valid at ``i = 1``.

    Running total from 0: ``+volume`` when the close rose, ``-volume`` when it fell, ``0`` when
    unchanged. ``i = 0`` has no prior close and is therefore NaN, not 0 — the level of an OBV
    series is arbitrary anyway, so the honest statement at the first bar is "undefined", not a
    zero that looks like a measurement.
    """
    out = _empty(close)
    if close.size < 2:
        return out
    total = 0.0
    for i in range(1, close.size):
        step = float(np.sign(close[i] - close[i - 1]) * volume[i])
        total += step
        out[i] = total
    return out


def realized_vol(close: np.ndarray, n: int, *, annualisation: float = ANNUALISATION) -> np.ndarray:
    """Annualised realised volatility: ``std(log_return[i-n+1 ... i], ddof=1) * sqrt(252)``.

    First valid at ``i = n`` — ``n`` log returns need ``n+1`` closes. ``ddof=1`` (sample) here
    and ``ddof=0`` (population) in :func:`bollinger` is not an inconsistency: Bollinger's bands
    are defined on the population form, while this is an estimate of an unobserved parameter
    from a sample and the sample form is the unbiased one.
    """
    out = _empty(close)
    if close.size <= n:
        return out
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.log(close[1:] / close[:-1])
    r = np.where(np.isfinite(r), r, np.nan)
    if r.size >= n:
        out[n:] = _windows(r, n).std(axis=1, ddof=1) * np.sqrt(annualisation)
    return out


def trailing_return(close: np.ndarray, n: int) -> np.ndarray:
    """``close[i] / close[i-n] - 1``, a **simple** return and a fraction. First valid ``i = n``.

    Deliberately simple rather than log, unlike ``daily_returns.log_return`` sitting beside it in
    the database. These columns are for display: a screen reading "+7.00%" has to be the simple
    figure, because that is the number a reader will check against their broker.
    """
    out = _empty(close)
    if close.size > n:
        with np.errstate(invalid="ignore", divide="ignore"):
            out[n:] = np.where(close[:-n] > 0.0, close[n:] / close[:-n] - 1.0, np.nan)
    return out


def ytd_return(close: np.ndarray, dates: Sequence[date]) -> np.ndarray:
    """``close[i] / (last close before 1 Jan of dates[i]'s year) - 1``, a fraction.

    NaN for every session in the earliest calendar year of the loaded history: there is no
    prior-year close to measure from, and anchoring to the first session of the current year
    instead would silently report a different quantity (year-to-date *excluding* the first day's
    move) under the same column name.

    "Last session before 1 Jan" rather than "last session of year-1" so a gap year cannot make
    the column vanish; on contiguous daily data the two are the same session.
    """
    out = _empty(close)
    if close.size == 0:
        return out
    if len(dates) != close.size:
        raise ValueError(f"dates has {len(dates)} entries, close has {close.size}")
    base: float | None = None
    seen_year: int | None = None
    for i in range(close.size):
        year = dates[i].year
        if seen_year is None or year > seen_year:
            # A new calendar year starts at i. Its base is the immediately preceding session,
            # provided one exists and belongs to an earlier year. The first year of the loaded
            # history has none, and keeps base = None.
            base = float(close[i - 1]) if i > 0 and dates[i - 1].year < year else None
            seen_year = year
        if base is not None and base > 0.0 and np.isfinite(close[i]):
            out[i] = float(close[i]) / base - 1.0
    return out
