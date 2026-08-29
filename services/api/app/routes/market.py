"""GET /api/market/* — the market screen's aggregates (D-18).

Five routes over four views: three from ``supabase/migrations/00010_dashboard_views.sql`` and
``v_index_history`` from ``00013_market_home_views.sql``. None computes: everything here
selects, orders, limits and serialises.

``/movers`` and ``/liquidity`` read the SAME view. That is the point of ``v_top_movers`` being
unordered and unlimited — "the ten biggest gainers over three months" and "the ten most traded
names today" are two orderings of one row set, not two aggregations, and giving the second its
own view would have duplicated the joins that produce the first.

Unit contract, inherited from those views and not restated at every field: **ratios are
fractions**. ``ret_1d = 0.07`` means +7%. That is what ``technical_indicators_daily`` stores,
and converting to percent here would leave two conventions in one system. Formatting belongs at
the display edge.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query

from app.db.connection import NoData, as_float, fetch_all, fetch_one, iso_date

router = APIRouter(prefix="/api/market", tags=["market"])

# as_float() rounds to 3 decimals by default, which on a fraction is 0.1% granularity — coarse
# enough to visibly move a return. Ratios get an explicit width; prices get their own.
_RATIO_DIGITS = 6
_PRICE_DIGITS = 2

_OVERVIEW_SQL = """
SELECT session_date, n_tickers, n_with_return,
       total_turnover, total_volume,
       advancers, decliners, unchanged,
       index_symbol, index_close, index_ret_1d
  FROM v_market_overview
"""

# Ordering is this route's job, the same reasoning as _movers_order below: the treemap wants
# its biggest tiles first, and baking an order into the view would still need a tie-break
# argued about later. total_turnover is never NULL (the view coalesces it to 0), but NULLS LAST
# costs nothing and keeps this identical in shape to the movers ordering next door. sector ASC
# breaks ties, including the NULL-sector group, so the response is deterministic.
_SECTORS_SQL = """
SELECT sector, n_tickers, n_with_return, mean_ret_1d, total_turnover, total_volume
  FROM v_sector_performance
 ORDER BY total_turnover DESC NULLS LAST, sector ASC
"""

# v_top_movers is deliberately UNORDERED and UNLIMITED — its header says so explicitly, because
# baking in "top 10 gainers" would need a second view for losers and a third for a limit of 20.
# Horizon, direction and limit are therefore this route's job.

#: The five horizons the movers table ranks at, mapped to the column each one means.
#:
#: The labels are trading conventions and the columns are session counts, and the two are only
#: approximately the same thing: 1M is 20 sessions, 3M is 60, 1Y is 252. That approximation is
#: the reason the schema names the columns for session counts (docs/RUNBOOK and 00013) while the
#: display names them for months — the mapping is written down HERE, once, rather than being
#: re-derived by every caller.
#:
#: A dict, not string interpolation of the query value: ``horizon`` is constrained by a Literal
#: so FastAPI rejects anything else, and even then the value only ever selects a key.
_HORIZON_COLUMN = {
    "1d": "ret_1d",
    "5d": "ret_5d",
    "1m": "ret_20d",
    "3m": "ret_60d",
    "1y": "ret_252d",
}


def _movers_order(horizon: str, direction: str) -> str:
    """``ORDER BY`` text for one (horizon, direction), built from constants only.

    Two details that are wrong by default and right here:

    * ``NULLS LAST`` is explicit in both directions. Postgres defaults DESC to NULLS FIRST,
      which would put tickers with no return at the TOP of the gainers table — and at 1Y that
      is not a rare case: every ticker with fewer than 253 loaded sessions has a NULL there.
    * ``ticker ASC`` breaks ties, so the same data always yields the same response — the same
      determinism rule greedy follows when it breaks ties by smallest index.
    """
    col = _HORIZON_COLUMN[horizon]
    sense = "DESC" if direction == "up" else "ASC"
    return f"t.{col} {sense} NULLS LAST, t.ticker ASC"


#: Every column both the movers table and the liquidity table read. One list, because the two
#: render the same row with a different column emphasised, and a row shape that differed between
#: them would be a difference the reader could see with no reason behind it.
_MOVERS_COLUMNS = """t.ticker, t.company_name, t.sector, t.bar_date, t.close_price,
       t.volume, t.turnover_value,
       t.ret_1d, t.ret_5d, t.ret_20d, t.ret_60d, t.ret_252d"""

# The `{col} IS NOT NULL` filter is not hiding rows: a ticker with no return AT THE REQUESTED
# HORIZON cannot be ranked over that horizon at all. It filters on the horizon's own column
# rather than always on ret_1d, which matters at 1Y — a ticker with 200 loaded sessions has a
# ret_1d and no ret_252d, and ranking it into a 1Y table on the strength of a one-day move
# would be the exact error NULLS LAST exists to prevent.
#
# The count of excluded tickers stays visible on the wire next door: /api/market/overview
# publishes n_tickers and n_with_return side by side.
_MOVERS_SQL = f"""
SELECT {_MOVERS_COLUMNS}
  FROM v_top_movers t
 WHERE t.{{filter_col}} IS NOT NULL
 ORDER BY {{order}}
 LIMIT %s
"""

# Liquidity: the same view, ordered by money traded rather than by price move.
#
# turnover_value is nghìn đồng (docs/01 §1) — close × volume, inheriting close's unit. It is
# published unconverted, as every other turnover figure on this API is; converting to tỷ đồng
# is a display-edge job and doing it here would leave two conventions in one system.
#
# No NOT NULL filter and no direction: every ticker that traded has a turnover, "least traded"
# is not a question the screen asks, and a NULL turnover sorts last on its own.
_LIQUIDITY_SQL = f"""
SELECT {_MOVERS_COLUMNS}
  FROM v_top_movers t
 ORDER BY t.turnover_value DESC NULLS LAST, t.ticker ASC
 LIMIT %s
"""

#: Ranges the index chart offers, as a count of SESSIONS back from the latest one.
#:
#: Sessions, not calendar dates, for the same reason the movers horizons are session counts: a
#: window measured in days silently shortens across Tết, and the two panels would then disagree
#: about what "3M" spans while sitting on the same screen.
#:
#: ``ytd`` and ``all`` are not counts and are handled separately — YTD is a calendar question by
#: definition, and ALL has no window at all.
_INDEX_RANGE_SESSIONS = {
    "1m": 20,
    "3m": 60,
    "6m": 126,
    "1y": 252,
}

# The subquery takes the most recent N sessions; the outer query puts them back in ascending
# order, which is the order a line chart draws in. Doing it in one ORDER BY is not possible —
# LIMIT needs DESC to mean "most recent", and the chart needs ASC.
_INDEX_HISTORY_TAIL_SQL = """
SELECT * FROM (
    SELECT index_symbol, bar_date, open, high, low, close, volume, ret_1d
      FROM v_index_history
     ORDER BY bar_date DESC
     LIMIT %s
) t
ORDER BY t.bar_date ASC
"""

# YTD is anchored to the LATEST SESSION's year, not to the wall clock. On 3 January the two
# agree; on a database whose last load was in December of the previous year they do not, and
# anchoring to now() would return an empty chart for a series that has plenty of data.
_INDEX_HISTORY_YTD_SQL = """
SELECT index_symbol, bar_date, open, high, low, close, volume, ret_1d
  FROM v_index_history
 WHERE bar_date >= date_trunc('year', (SELECT max(bar_date) FROM v_index_history))
 ORDER BY bar_date ASC
"""

_INDEX_HISTORY_ALL_SQL = """
SELECT index_symbol, bar_date, open, high, low, close, volume, ret_1d
  FROM v_index_history
 ORDER BY bar_date ASC
"""


def _as_int(value: Any) -> int | None:
    """Whole-number column -> ``int`` (None passes through).

    ``sum()`` over ``bigint`` returns ``numeric``, so psycopg2 hands back ``Decimal`` even for a
    share count. Routing those through ``as_float`` would put ``1.23e9`` on the wire and lose
    exactness above 2^53. Volumes are exact integers and stay that way.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.get("/overview")
def market_overview() -> dict:
    """Return the latest session's breadth, turnover and index move — exactly one row."""
    row = fetch_one(_OVERVIEW_SQL)
    # The view always yields a row, because its aggregates are scalar subqueries. An empty
    # daily_bars therefore surfaces as a NULL session_date rather than as zero rows — so the
    # emptiness has to be detected on the value.
    if row is None or row["session_date"] is None:
        raise NoData()

    return {
        "session_date": iso_date(row["session_date"]),
        "n_tickers": row["n_tickers"],
        # advancers + decliners + unchanged need NOT equal n_tickers: a ticker whose first ever
        # session is today has a NULL ret_1d and is counted in none of the three. n_with_return
        # is the difference, published so the screen cannot present the three as a partition.
        "n_with_return": row["n_with_return"],
        "advancers": row["advancers"],
        "decliners": row["decliners"],
        "unchanged": row["unchanged"],
        "total_turnover": as_float(row["total_turnover"], _PRICE_DIGITS),
        "total_volume": _as_int(row["total_volume"]),
        # The index half is NULL when no run is active — v_market_overview resolves the symbol
        # through v_active_model_run rather than hard-coding 'VNINDEX'. NULL passes through.
        "index_symbol": row["index_symbol"],
        "index_close": as_float(row["index_close"], _PRICE_DIGITS),
        "index_ret_1d": as_float(row["index_ret_1d"], _RATIO_DIGITS),
    }


@router.get("/sectors")
def market_sectors() -> dict:
    """Return every sector's latest-session breadth, mean move and turnover — the treemap."""
    rows = fetch_all(_SECTORS_SQL)

    return {
        "count": len(rows),
        "sectors": [
            {
                # A NULL sector is a real group (tickers with no assigned sector), not an
                # error — passed through as null. Rendering it as "Khác" is a P10 display
                # choice, the same rule P6.3 set for stocks.sector itself.
                "sector": r["sector"],
                "n_tickers": r["n_tickers"],
                # avg() skips NULLs, so n_with_return is mean_ret_1d's actual denominator —
                # published beside it rather than hidden. A two-stock sector average carries
                # the same visual weight on a treemap as a twenty-four-stock one without this.
                "n_with_return": r["n_with_return"],
                # Unlike total_turnover, mean_ret_1d is NOT coalesced in the view: a sector
                # with zero tickers holding a return today (n_with_return == 0) yields a real
                # NULL here, and NULL is the truth — there is no "average" to report.
                "mean_ret_1d": as_float(r["mean_ret_1d"], _RATIO_DIGITS),
                "total_turnover": as_float(r["total_turnover"], _PRICE_DIGITS),
                "total_volume": _as_int(r["total_volume"]),
            }
            for r in rows
        ],
    }


def _mover_row(r: dict[str, Any]) -> dict[str, Any]:
    """Serialise one ``v_top_movers`` row. Shared by /movers and /liquidity."""
    return {
        "ticker": r["ticker"],
        "company_name": r["company_name"],
        "sector": r["sector"],
        # Per-ticker, and deliberately exposed: a ticker that stopped trading shows a stale
        # date here instead of being silently ranked beside today's movers.
        "bar_date": iso_date(r["bar_date"]),
        "close_price": as_float(r["close_price"], _PRICE_DIGITS),
        "volume": _as_int(r["volume"]),
        "turnover_value": as_float(r["turnover_value"], _PRICE_DIGITS),
        # All five horizons on every row, whichever one was ranked by: the table shows the
        # other four as context columns, and a second request per horizon would be four
        # round-trips to a pooler an ocean away for data already in hand.
        "ret_1d": as_float(r["ret_1d"], _RATIO_DIGITS),
        "ret_5d": as_float(r["ret_5d"], _RATIO_DIGITS),
        "ret_20d": as_float(r["ret_20d"], _RATIO_DIGITS),
        "ret_60d": as_float(r["ret_60d"], _RATIO_DIGITS),
        "ret_252d": as_float(r["ret_252d"], _RATIO_DIGITS),
    }


@router.get("/movers")
def top_movers(
    direction: Literal["up", "down"] = "up",
    horizon: Literal["1d", "5d", "1m", "3m", "1y"] = "1d",
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    """Return the strongest movers over one horizon in one direction, most extreme first."""
    # Both query values are constrained by Literals, so FastAPI rejects anything else into the
    # 400 envelope before this body runs. Even then neither value reaches SQL: they select a
    # key in _HORIZON_COLUMN and a branch in _movers_order, and the text those return is built
    # from constants. limit is bound as a parameter.
    sql = _MOVERS_SQL.format(
        filter_col=_HORIZON_COLUMN[horizon],
        order=_movers_order(horizon, direction),
    )
    rows = fetch_all(sql, (limit,))

    return {
        "direction": direction,
        "horizon": horizon,
        "limit": limit,
        "count": len(rows),
        "movers": [_mover_row(r) for r in rows],
    }


@router.get("/liquidity")
def market_liquidity(limit: int = Query(10, ge=1, le=100)) -> dict:
    """Return the session's most heavily traded names, by turnover value.

    ``session_date`` is the LATEST SESSION, resolved the same way /overview resolves it, and is
    published beside the rows so the screen can say which day it is ranking. Individual rows
    carry their own ``bar_date`` as well: a delisted ticker's last turnover would otherwise sit
    in a "today's liquidity" table with nothing marking it as stale.
    """
    rows = fetch_all(_LIQUIDITY_SQL, (limit,))
    session = fetch_one("SELECT session_date FROM v_latest_session")

    return {
        "session_date": iso_date(session["session_date"]) if session else None,
        "limit": limit,
        "count": len(rows),
        "stocks": [_mover_row(r) for r in rows],
    }


@router.get("/index-history")
def index_history(
    range: Literal["1m", "3m", "6m", "ytd", "1y", "all"] = "1y",  # noqa: A002
) -> dict:
    """Return the active run's index series over ``range``, oldest session first.

    Empty when no run is active — ``v_index_history`` joins through ``v_active_model_run``
    rather than hard-coding a symbol, so "which index" has exactly one answer and it is the
    same answer /overview gives. That is reported as a 503 rather than as an empty chart: a
    line with no points and a line the database cannot name are different failures, and 503 is
    what /api/model/active already answers for this same condition.
    """
    if range == "all":
        rows = fetch_all(_INDEX_HISTORY_ALL_SQL)
    elif range == "ytd":
        rows = fetch_all(_INDEX_HISTORY_YTD_SQL)
    else:
        rows = fetch_all(_INDEX_HISTORY_TAIL_SQL, (_INDEX_RANGE_SESSIONS[range],))

    if not rows:
        raise NoData()

    return {
        # Read off the data rather than passed in, for the same reason /overview reads it off
        # the view: the caller never names the symbol and must not be able to.
        "index_symbol": rows[0]["index_symbol"],
        "range": range,
        "count": len(rows),
        "bars": [
            {
                "bar_date": iso_date(r["bar_date"]),
                "open": as_float(r["open"], _PRICE_DIGITS),
                "high": as_float(r["high"], _PRICE_DIGITS),
                "low": as_float(r["low"], _PRICE_DIGITS),
                "close": as_float(r["close"], _PRICE_DIGITS),
                "volume": _as_int(r["volume"]),
                # NULL on the first session of the whole series — no previous close exists, and
                # a fabricated 0 there would draw a flat first step the market never had.
                "ret_1d": as_float(r["ret_1d"], _RATIO_DIGITS),
            }
            for r in rows
        ],
    }
