"""pipelines.common.returns — pure log-return + flag helpers for the anchor model.

Stateless, no I/O. Given a per-series ordered sequence of daily bars, produce the
log returns the factor model consumes plus the two recorded flags.

Definitions (spec 01-data-pipeline §1.4)
----------------------------------------
- Log return:  x_t = ln(P_t / P_{t-1}) on the source-adjusted close. The first
  session of a series has no return and is dropped.
- Index factor: f_t = ln(I_t / I_{t-1}) — same formula on the index close.
- Flags per observation (recorded, NEVER used to exclude):
    * at_limit    — the close-to-close move reaches the exchange daily band.
    * zero_volume — volume == 0.
  Flags let the exclusion be tested later without re-ingesting anything.

at_limit note
-------------
This is a recorded diagnostic, not a trading rule. The exact ceiling/floor price
rounds to the tick, so the realized close-to-close move can sit just under the
nominal band; we flag when |simple return| >= band - tolerance. The band defaults
to the HOSE ±7% band; pass another band for HNX (0.10) / UPCOM (0.15).
"""

from __future__ import annotations

import math
from typing import Any

# HOSE daily price band; tolerance absorbs tick-rounding of the limit price.
DEFAULT_LIMIT_BAND: float = 0.07
DEFAULT_LIMIT_TOLERANCE: float = 0.003


def _as_pos_float(value: Any) -> float | None:
    """Return a strictly-positive float, or None (invalid price for a log return)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def compute_return_rows(
    bars: list[tuple[Any, Any, Any]],
    *,
    band: float = DEFAULT_LIMIT_BAND,
    tolerance: float = DEFAULT_LIMIT_TOLERANCE,
) -> list[dict[str, Any]]:
    """Log returns + flags for one ticker.

    ``bars`` is ascending ``(bar_date, close, volume)`` over consecutive trading
    sessions. Returns one row per session that has a valid prior close (the first
    session, and any session following an unusable close, is dropped):

        {bar_date, close, prev_close, log_return, at_limit, zero_volume}

    ``close``/``prev_close`` are the return's own inputs, stored beside it (spec
    #5 §5.5) so it can be checked without a self-join.

    ``at_limit`` uses the simple close-to-close return vs. ``band``; ``zero_volume``
    is ``volume == 0`` (unknown volume → False, not fabricated).
    """
    out: list[dict[str, Any]] = []
    prev_close: float | None = None
    for bar_date, close, volume in bars:
        c = _as_pos_float(close)
        if prev_close is not None and c is not None:
            simple = c / prev_close - 1.0
            vol = None
            try:
                vol = float(volume) if volume is not None else None
            except (TypeError, ValueError):
                vol = None
            out.append(
                {
                    "bar_date": bar_date,
                    "close": c,
                    "prev_close": prev_close,
                    "log_return": math.log(c / prev_close),
                    "at_limit": abs(simple) >= (band - tolerance),
                    "zero_volume": (vol == 0.0) if vol is not None else False,
                }
            )
        if c is not None:
            prev_close = c
    return out


def compute_index_return_rows(bars: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
    """Index log returns from ascending ``(bar_date, close)`` →
    ``{bar_date, close, prev_close, log_return}``.

    First session (and any following an unusable close) is dropped; no flags — the index has
    no daily band and no volume column, so ``at_limit``/``zero_volume`` don't apply here.
    ``close``/``prev_close`` are stored beside the return for the same reason
    ``compute_return_rows`` stores them: so the value can be checked without a self-join.
    """
    out: list[dict[str, Any]] = []
    prev_close: float | None = None
    for bar_date, close in bars:
        c = _as_pos_float(close)
        if prev_close is not None and c is not None:
            out.append({
                "bar_date": bar_date,
                "close": c,
                "prev_close": prev_close,
                "log_return": math.log(c / prev_close),
            })
        if c is not None:
            prev_close = c
    return out
