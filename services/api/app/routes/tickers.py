"""GET /api/tickers/* — the searchable universe and one ticker's full state (D-18).

Five routes. The list and detail routes read ``v_active_assignment`` (00009) LEFT-joined to
``v_latest_indicators`` (00009). The two series routes, ``/history`` and ``/indicators``, and
``/analysis`` read ``daily_bars`` and ``technical_indicators_daily`` directly -- the sanctioned
exception ``00009_views.sql``'s header states outright: "The API and the dashboard read ONLY
these views plus daily_bars and technical_indicators_daily."

Unit contract, inherited and not restated per field: ratios are fractions (``ret_1d = 0.07`` is
+7%). ``bb_width_20``, ``dist_from_sma_200_pct`` and ``drawdown_from_252d_high`` are ratios too,
despite two of them looking like prices or percents by name (P7 decision S2) -- everything else
priced in ``close``'s own unit (SMA/EMA/Bollinger bands, MACD family, ATR, the 252-session
high/low) stays at 2 decimals, and RSI/Stochastic (bounded 0-100, not a fraction) get their own
width for the same reason.

``/analysis`` is the one route that computes anything -- a rule-based narrative from
``app.narrative``, kept in its own pure module precisely so this file stays "select, serialise."
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.db.connection import NotFound, as_float, fetch_all, fetch_one, iso_date
from app.narrative import build_narrative
from app.routes._errors import ApiError

router = APIRouter(prefix="/api/tickers", tags=["tickers"])

_RATIO_DIGITS = 6  # ret_*, coverage_c, alpha_hat/beta_hat/sigma_hat/r2, bb_width_20,
# dist_from_sma_200_pct, drawdown_from_252d_high, realized_vol_*d
_VALUE_DIGITS = 2  # OHLC, SMA/EMA/Bollinger, MACD family, ATR, high/low_252d, volume_sma_20
_OSC_DIGITS = 2  # RSI, Stochastic %K/%D -- bounded [0, 100], not a fraction

# The two series routes' shared parameter contract (P9.3). No from/to given at all -> the most
# recent DEFAULT_WINDOW sessions, the common "just show me the chart" case. Either one given ->
# the row cap becomes a pure safety net rather than a default, so an explicit wide range still
# cannot return the full history by accident.
_DEFAULT_WINDOW = 252  # one calendar year of sessions (docs/01 §1)
_MAX_ROWS = 2000  # headroom above the 1,424 sessions trading_calendar holds today

# position ASC, not alphabetical: the ordered universe pins every position in this system
# (AGENTS.md), and serving the list in that order rather than re-sorting it keeps that visible.
_LIST_SQL = """
SELECT a.position, a.ticker, a.company_name, a.sector, a.industry,
       a.anchor_ticker, a.coverage_c, a.is_anchor, a.under_tau,
       li.bar_date, li.ret_1d
  FROM v_active_assignment a
  LEFT JOIN v_latest_indicators li ON li.ticker = a.ticker
 ORDER BY a.position ASC
"""

# One statement, the same join v_top_movers performs (00010) plus the full indicator column set
# v_top_movers deliberately trims. read_cursor() opens a fresh connection per call, so composing
# three sources here rather than three round trips is the same reasoning app/routes/model.py's
# CROSS JOIN already states.
_DETAIL_SQL = """
SELECT a.position, a.ticker, a.company_name, a.sector, a.industry,
       a.anchor_ticker, a.coverage_c, a.is_anchor, a.under_tau,
       a.alpha_hat, a.beta_hat, a.sigma_hat, a.r2,
       li.bar_date,
       b.open, b.high, b.low, b.close, b.volume,
       li.sma_20, li.sma_50, li.sma_200, li.ema_12, li.ema_26,
       li.macd, li.macd_signal, li.macd_hist,
       li.rsi_14, li.stoch_k_14, li.stoch_d_14,
       li.atr_14, li.bb_mid_20, li.bb_upper_20, li.bb_lower_20, li.bb_width_20,
       li.realized_vol_20d, li.realized_vol_60d,
       li.obv, li.volume_sma_20, li.turnover_value,
       li.ret_1d, li.ret_5d, li.ret_20d, li.ret_60d, li.ret_ytd,
       li.dist_from_sma_200_pct, li.high_252d, li.low_252d, li.drawdown_from_252d_high
  FROM v_active_assignment a
  LEFT JOIN v_latest_indicators li ON li.ticker = a.ticker
  LEFT JOIN daily_bars b ON b.ticker = li.ticker
                        AND b.bar_date = li.bar_date
                        AND b.source = li.source
 WHERE a.ticker = %s
"""


# The inner subquery does the filtering, ordering DESC so LIMIT keeps the most RECENT rows
# under the default window; the outer query re-sorts ASC, which is what a chart wants. The
# %s::date IS NULL guard lets one prepared statement serve "no bound", "lower bound only",
# "upper bound only" and "both bounds" without four separate SQL strings.
_HISTORY_SQL = """
SELECT bar_date, open, high, low, close, volume, is_adjusted
  FROM (
    SELECT bar_date, open, high, low, close, volume, is_adjusted
      FROM daily_bars
     WHERE ticker = %s
       AND (%s::date IS NULL OR bar_date >= %s)
       AND (%s::date IS NULL OR bar_date <= %s)
     ORDER BY bar_date DESC
     LIMIT %s
  ) recent
 ORDER BY bar_date ASC
"""

# close/volume are duplicated from daily_bars here rather than omitted -- deliberate (P9 S6):
# the combined chart needs Close alongside every indicator on one axis, and a response that
# needs the /history response merged in by date would break exactly where one side is missing
# a session. Each series response is self-sufficient.
_INDICATORS_SQL = """
SELECT t.bar_date, b.close, b.volume,
       t.sma_20, t.sma_50, t.sma_200, t.ema_12, t.ema_26,
       t.macd, t.macd_signal, t.macd_hist,
       t.rsi_14, t.stoch_k_14, t.stoch_d_14,
       t.atr_14, t.bb_mid_20, t.bb_upper_20, t.bb_lower_20, t.bb_width_20,
       t.realized_vol_20d, t.realized_vol_60d,
       t.obv, t.volume_sma_20, t.turnover_value,
       t.ret_1d, t.ret_5d, t.ret_20d, t.ret_60d, t.ret_ytd,
       t.dist_from_sma_200_pct, t.high_252d, t.low_252d, t.drawdown_from_252d_high
  FROM (
    SELECT *
      FROM technical_indicators_daily
     WHERE ticker = %s
       AND (%s::date IS NULL OR bar_date >= %s)
       AND (%s::date IS NULL OR bar_date <= %s)
     ORDER BY bar_date DESC
     LIMIT %s
  ) t
  LEFT JOIN daily_bars b ON b.ticker = t.ticker AND b.bar_date = t.bar_date AND b.source = t.source
 ORDER BY t.bar_date ASC
"""

# Whether a ticker exists at all, independent of any date range -- used only to disambiguate an
# empty series result (D-16: stocks is already scoped to the 85-ticker serving universe, so this
# check answers the same question v_active_assignment would).
_TICKER_EXISTS_SQL = "SELECT 1 FROM stocks WHERE ticker = %s"

# Not gated by the active run, deliberately -- v_latest_indicators isn't either (00009): the
# narrative is a property of the ticker's own recent history, unaffected by which artifact is
# active. Every column app.narrative.RULES reads, named explicitly rather than SELECT *, so a
# future indicator column does not silently start feeding an unreviewed rule.
_ANALYSIS_SQL = """
SELECT li.bar_date, b.close, b.volume,
       li.sma_20, li.sma_50, li.sma_200,
       li.rsi_14, li.macd_hist,
       li.bb_upper_20, li.bb_lower_20, li.bb_mid_20,
       li.volume_sma_20,
       li.drawdown_from_252d_high,
       li.ret_5d, li.ret_20d, li.ret_60d, li.ret_ytd
  FROM v_latest_indicators li
  LEFT JOIN daily_bars b ON b.ticker = li.ticker
                        AND b.bar_date = li.bar_date
                        AND b.source = li.source
 WHERE li.ticker = %s
"""

# Column set _ANALYSIS_SQL selects beyond bar_date -- used to build an all-NULL row when a known
# ticker has no indicator history yet at all (v_latest_indicators returns no row for it).
_ANALYSIS_COLUMNS = (
    "close", "volume", "sma_20", "sma_50", "sma_200", "rsi_14", "macd_hist",
    "bb_upper_20", "bb_lower_20", "bb_mid_20", "volume_sma_20",
    "drawdown_from_252d_high", "ret_5d", "ret_20d", "ret_60d", "ret_ytd",
)


def _as_int(value: Any) -> int | None:
    """Whole-number column -> ``int`` (None passes through). See app.routes.market._as_int."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ticker_known(ticker: str) -> bool:
    return fetch_one(_TICKER_EXISTS_SQL, (ticker,)) is not None


def _validate_range(from_: date | None, to: date | None) -> None:
    if from_ is not None and to is not None and from_ > to:
        raise ApiError(400, "invalid_params", "`from` must not be later than `to`.")


@router.get("")
def list_tickers() -> dict:
    """Return the active run's full universe, in universe order, each with its latest move."""
    rows = fetch_all(_LIST_SQL)

    return {
        "count": len(rows),
        "tickers": [
            {
                "position": r["position"],
                "ticker": r["ticker"],
                "company_name": r["company_name"],
                "sector": r["sector"],
                "industry": r["industry"],
                "anchor_ticker": r["anchor_ticker"],
                "coverage_c": as_float(r["coverage_c"], _RATIO_DIGITS),
                "is_anchor": r["is_anchor"],
                "under_tau": r["under_tau"],
                "bar_date": iso_date(r["bar_date"]),
                "ret_1d": as_float(r["ret_1d"], _RATIO_DIGITS),
            }
            for r in rows
        ],
    }


@router.get("/{ticker}")
def ticker_detail(ticker: str) -> dict:
    """Return one ticker's identity, model assignment and latest indicator row.

    404, not an empty 200, when the ticker is not in the active run's universe. D-16 makes the
    serving universe and the model universe the same 85, so today "unknown ticker" and "not in
    this run" are the same condition -- this route does not distinguish them. A future second
    universe would need to.
    """
    row = fetch_one(_DETAIL_SQL, (ticker.strip().upper(),))
    if row is None:
        raise NotFound(f"'{ticker}' is not in the active run's universe.")

    return {
        "identity": {
            "ticker": row["ticker"],
            "company_name": row["company_name"],
            "sector": row["sector"],
            "industry": row["industry"],
        },
        "assignment": {
            "position": row["position"],
            "anchor_ticker": row["anchor_ticker"],
            "coverage_c": as_float(row["coverage_c"], _RATIO_DIGITS),
            "is_anchor": row["is_anchor"],
            "under_tau": row["under_tau"],
            "alpha_hat": as_float(row["alpha_hat"], _RATIO_DIGITS),
            "beta_hat": as_float(row["beta_hat"], _RATIO_DIGITS),
            "sigma_hat": as_float(row["sigma_hat"], _RATIO_DIGITS),
            "r2": as_float(row["r2"], _RATIO_DIGITS),
        },
        "latest": {
            "bar_date": iso_date(row["bar_date"]),
            "open": as_float(row["open"], _VALUE_DIGITS),
            "high": as_float(row["high"], _VALUE_DIGITS),
            "low": as_float(row["low"], _VALUE_DIGITS),
            "close": as_float(row["close"], _VALUE_DIGITS),
            "volume": _as_int(row["volume"]),
            "turnover_value": as_float(row["turnover_value"], _VALUE_DIGITS),
            "sma_20": as_float(row["sma_20"], _VALUE_DIGITS),
            "sma_50": as_float(row["sma_50"], _VALUE_DIGITS),
            "sma_200": as_float(row["sma_200"], _VALUE_DIGITS),
            "ema_12": as_float(row["ema_12"], _VALUE_DIGITS),
            "ema_26": as_float(row["ema_26"], _VALUE_DIGITS),
            "macd": as_float(row["macd"], _VALUE_DIGITS),
            "macd_signal": as_float(row["macd_signal"], _VALUE_DIGITS),
            "macd_hist": as_float(row["macd_hist"], _VALUE_DIGITS),
            "rsi_14": as_float(row["rsi_14"], _OSC_DIGITS),
            "stoch_k_14": as_float(row["stoch_k_14"], _OSC_DIGITS),
            "stoch_d_14": as_float(row["stoch_d_14"], _OSC_DIGITS),
            "atr_14": as_float(row["atr_14"], _VALUE_DIGITS),
            "bb_mid_20": as_float(row["bb_mid_20"], _VALUE_DIGITS),
            "bb_upper_20": as_float(row["bb_upper_20"], _VALUE_DIGITS),
            "bb_lower_20": as_float(row["bb_lower_20"], _VALUE_DIGITS),
            "bb_width_20": as_float(row["bb_width_20"], _RATIO_DIGITS),
            "realized_vol_20d": as_float(row["realized_vol_20d"], _RATIO_DIGITS),
            "realized_vol_60d": as_float(row["realized_vol_60d"], _RATIO_DIGITS),
            "obv": _as_int(row["obv"]),
            "volume_sma_20": as_float(row["volume_sma_20"], _VALUE_DIGITS),
            "ret_1d": as_float(row["ret_1d"], _RATIO_DIGITS),
            "ret_5d": as_float(row["ret_5d"], _RATIO_DIGITS),
            "ret_20d": as_float(row["ret_20d"], _RATIO_DIGITS),
            "ret_60d": as_float(row["ret_60d"], _RATIO_DIGITS),
            "ret_ytd": as_float(row["ret_ytd"], _RATIO_DIGITS),
            "dist_from_sma_200_pct": as_float(row["dist_from_sma_200_pct"], _RATIO_DIGITS),
            "high_252d": as_float(row["high_252d"], _VALUE_DIGITS),
            "low_252d": as_float(row["low_252d"], _VALUE_DIGITS),
            "drawdown_from_252d_high": as_float(row["drawdown_from_252d_high"], _RATIO_DIGITS),
        },
    }


@router.get("/{ticker}/history")
def ticker_history(
    ticker: str,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
) -> dict:
    """Return OHLCV bars for one ticker, oldest first.

    No ``from``/``to`` -> the most recent 252 sessions. Either bound given -> every row in
    range, up to a hard safety cap (``_MAX_ROWS``) rather than a curated default, so an
    accidentally wide range cannot return the full history unbounded.

    ``is_adjusted`` is on the wire because an adjusted chart will not match a broker's raw chart
    across an ex-date (D-15) -- the caption the screen owes the reader needs this flag.
    """
    ticker = ticker.strip().upper()
    _validate_range(from_, to)
    limit_value = _DEFAULT_WINDOW if from_ is None and to is None else _MAX_ROWS

    rows = fetch_all(_HISTORY_SQL, (ticker, from_, from_, to, to, limit_value))
    if not rows and not _ticker_known(ticker):
        raise NotFound(f"'{ticker}' is not in the active run's universe.")

    return {
        "ticker": ticker,
        "count": len(rows),
        "bars": [
            {
                "bar_date": iso_date(r["bar_date"]),
                "open": as_float(r["open"], _VALUE_DIGITS),
                "high": as_float(r["high"], _VALUE_DIGITS),
                "low": as_float(r["low"], _VALUE_DIGITS),
                "close": as_float(r["close"], _VALUE_DIGITS),
                "volume": _as_int(r["volume"]),
                "is_adjusted": r["is_adjusted"],
            }
            for r in rows
        ],
    }


@router.get("/{ticker}/indicators")
def ticker_indicators(
    ticker: str,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
) -> dict:
    """Return the full indicator series for one ticker, oldest first.

    Same ``from``/``to`` contract as ``/history`` (P9.3 S6). ``close`` and ``volume`` are
    duplicated from ``daily_bars`` here rather than omitted, deliberately: the combined chart
    needs Close alongside every indicator on one axis, and each series response must be
    self-sufficient so the client never merges two arrays by date.
    """
    ticker = ticker.strip().upper()
    _validate_range(from_, to)
    limit_value = _DEFAULT_WINDOW if from_ is None and to is None else _MAX_ROWS

    rows = fetch_all(_INDICATORS_SQL, (ticker, from_, from_, to, to, limit_value))
    if not rows and not _ticker_known(ticker):
        raise NotFound(f"'{ticker}' is not in the active run's universe.")

    return {
        "ticker": ticker,
        "count": len(rows),
        "indicators": [
            {
                "bar_date": iso_date(r["bar_date"]),
                "close": as_float(r["close"], _VALUE_DIGITS),
                "volume": _as_int(r["volume"]),
                "sma_20": as_float(r["sma_20"], _VALUE_DIGITS),
                "sma_50": as_float(r["sma_50"], _VALUE_DIGITS),
                "sma_200": as_float(r["sma_200"], _VALUE_DIGITS),
                "ema_12": as_float(r["ema_12"], _VALUE_DIGITS),
                "ema_26": as_float(r["ema_26"], _VALUE_DIGITS),
                "macd": as_float(r["macd"], _VALUE_DIGITS),
                "macd_signal": as_float(r["macd_signal"], _VALUE_DIGITS),
                "macd_hist": as_float(r["macd_hist"], _VALUE_DIGITS),
                "rsi_14": as_float(r["rsi_14"], _OSC_DIGITS),
                "stoch_k_14": as_float(r["stoch_k_14"], _OSC_DIGITS),
                "stoch_d_14": as_float(r["stoch_d_14"], _OSC_DIGITS),
                "atr_14": as_float(r["atr_14"], _VALUE_DIGITS),
                "bb_mid_20": as_float(r["bb_mid_20"], _VALUE_DIGITS),
                "bb_upper_20": as_float(r["bb_upper_20"], _VALUE_DIGITS),
                "bb_lower_20": as_float(r["bb_lower_20"], _VALUE_DIGITS),
                "bb_width_20": as_float(r["bb_width_20"], _RATIO_DIGITS),
                "realized_vol_20d": as_float(r["realized_vol_20d"], _RATIO_DIGITS),
                "realized_vol_60d": as_float(r["realized_vol_60d"], _RATIO_DIGITS),
                "obv": _as_int(r["obv"]),
                "volume_sma_20": as_float(r["volume_sma_20"], _VALUE_DIGITS),
                "turnover_value": as_float(r["turnover_value"], _VALUE_DIGITS),
                "ret_1d": as_float(r["ret_1d"], _RATIO_DIGITS),
                "ret_5d": as_float(r["ret_5d"], _RATIO_DIGITS),
                "ret_20d": as_float(r["ret_20d"], _RATIO_DIGITS),
                "ret_60d": as_float(r["ret_60d"], _RATIO_DIGITS),
                "ret_ytd": as_float(r["ret_ytd"], _RATIO_DIGITS),
                "dist_from_sma_200_pct": as_float(r["dist_from_sma_200_pct"], _RATIO_DIGITS),
                "high_252d": as_float(r["high_252d"], _VALUE_DIGITS),
                "low_252d": as_float(r["low_252d"], _VALUE_DIGITS),
                "drawdown_from_252d_high": as_float(
                    r["drawdown_from_252d_high"], _RATIO_DIGITS
                ),
            }
            for r in rows
        ],
    }


@router.get("/{ticker}/analysis")
def ticker_analysis(ticker: str) -> dict:
    """Return a rule-based narrative from the ticker's latest indicator row.

    Descriptive only -- ``docs/02`` §4 forbids a probabilistic statement or a portfolio weight,
    and ``app.narrative`` enforces that in its wording. This route's only job is to fetch one
    row, convert it to plain floats/ints (the same serialisation every other route performs),
    and hand it to the pure rule engine.

    A ticker with no indicators computed yet is not an error: it returns every rule skipped
    rather than a 503, because the ticker itself is real (``docs/04`` §5's NULL-is-the-truth
    rule applied to prose, not just to numbers).
    """
    ticker = ticker.strip().upper()
    row = fetch_one(_ANALYSIS_SQL, (ticker,))
    if row is None:
        if not _ticker_known(ticker):
            raise NotFound(f"'{ticker}' is not in the active run's universe.")
        row = dict.fromkeys(_ANALYSIS_COLUMNS)
        row["bar_date"] = None

    latest = {
        "close": as_float(row["close"], _VALUE_DIGITS),
        "volume": _as_int(row["volume"]),
        "sma_20": as_float(row["sma_20"], _VALUE_DIGITS),
        "sma_50": as_float(row["sma_50"], _VALUE_DIGITS),
        "sma_200": as_float(row["sma_200"], _VALUE_DIGITS),
        "rsi_14": as_float(row["rsi_14"], _OSC_DIGITS),
        "macd_hist": as_float(row["macd_hist"], _VALUE_DIGITS),
        "bb_upper_20": as_float(row["bb_upper_20"], _VALUE_DIGITS),
        "bb_lower_20": as_float(row["bb_lower_20"], _VALUE_DIGITS),
        "bb_mid_20": as_float(row["bb_mid_20"], _VALUE_DIGITS),
        "volume_sma_20": as_float(row["volume_sma_20"], _VALUE_DIGITS),
        "drawdown_from_252d_high": as_float(row["drawdown_from_252d_high"], _RATIO_DIGITS),
        "ret_5d": as_float(row["ret_5d"], _RATIO_DIGITS),
        "ret_20d": as_float(row["ret_20d"], _RATIO_DIGITS),
        "ret_60d": as_float(row["ret_60d"], _RATIO_DIGITS),
        "ret_ytd": as_float(row["ret_ytd"], _RATIO_DIGITS),
    }

    narrative = build_narrative(latest)

    return {
        "ticker": ticker,
        "bar_date": iso_date(row["bar_date"]),
        # D-15: indicators are computed on the adjusted price basis. A narrative about a price
        # is a narrative about WHICH price, and this is the caption that says so.
        "price_basis": "adjusted",
        "statements": narrative["statements"],
        "skipped": narrative["skipped"],
    }
