"""pipelines.common.upsert — idempotent upsert helpers for the daily-bar tables.

Every helper submits its whole batch in one transaction via ``executemany``, returns the
number of records submitted, is a no-op returning 0 on empty input, and raises on a DB error
so the caller decides whether to quarantine or fail.

These are the Postgres half of the storage seam: ``pipelines.storage.pg.PostgresSink``
delegates to them verbatim, and ``LocalSink`` writes the *same record dicts* to files. That
shared record shape is what keeps the local and dashboard tracks the same pipeline.

Usage::

    from pipelines.common.upsert import upsert_daily_bars, upsert_daily_returns

    n = upsert_daily_bars(records)      # returns rows submitted
    n = upsert_daily_returns(records)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ON CONFLICT key matches daily_bars UNIQUE (ticker, bar_date, source).
_DAILY_BARS_SQL = """
INSERT INTO daily_bars
    (ticker, bar_date, source, open, high, low, close, volume,
     is_adjusted, ingested_at, updated_at)
VALUES
    (%(ticker)s, %(bar_date)s, %(source)s, %(open)s, %(high)s, %(low)s,
     %(close)s, %(volume)s, %(is_adjusted)s, %(ingested_at)s, %(updated_at)s)
ON CONFLICT (ticker, bar_date, source) DO UPDATE SET
    open        = EXCLUDED.open,
    high        = EXCLUDED.high,
    low         = EXCLUDED.low,
    close       = EXCLUDED.close,
    volume      = EXCLUDED.volume,
    is_adjusted = EXCLUDED.is_adjusted,
    updated_at  = EXCLUDED.updated_at
"""


def upsert_daily_bars(records: list[dict[str, Any]]) -> int:
    """Idempotent upsert into daily_bars on (ticker, bar_date, source).

    Each record must contain:
        ticker, bar_date, source, open, high, low, close, volume,
        is_adjusted, ingested_at, updated_at.

    All records are submitted in a single transaction via executemany.
    Returns the number of records submitted (inserts + updates combined —
    Postgres does not distinguish them with executemany).

    Raises on DB error; the caller is responsible for catching and quarantining.
    """
    if not records:
        return 0

    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.executemany(_DAILY_BARS_SQL, records)
    return len(records)


# ON CONFLICT key matches market_index_bars UNIQUE (index_symbol, bar_date, source).
_MARKET_INDEX_BARS_SQL = """
INSERT INTO market_index_bars
    (index_symbol, bar_date, source, open, high, low, close, volume,
     ingested_at, updated_at)
VALUES
    (%(index_symbol)s, %(bar_date)s, %(source)s, %(open)s, %(high)s, %(low)s,
     %(close)s, %(volume)s, %(ingested_at)s, %(updated_at)s)
ON CONFLICT (index_symbol, bar_date, source) DO UPDATE SET
    open       = EXCLUDED.open,
    high       = EXCLUDED.high,
    low        = EXCLUDED.low,
    close      = EXCLUDED.close,
    volume     = EXCLUDED.volume,
    updated_at = EXCLUDED.updated_at
"""


def upsert_market_index_bars(records: list[dict[str, Any]]) -> int:
    """Idempotent upsert into market_index_bars on (index_symbol, bar_date, source).

    Each record must contain:
        index_symbol, bar_date, source, open, high, low, close, volume,
        ingested_at, updated_at.

    ``close`` must be non-null (the factor source); open/high/low/volume are
    nullable. All records are submitted in one transaction via executemany.
    Returns the number of records submitted. Raises on DB error.
    """
    if not records:
        return 0

    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.executemany(_MARKET_INDEX_BARS_SQL, records)
    return len(records)


# ON CONFLICT key matches staging.ohlc_raw PK (symbol, bar_type, bar_date).
# Re-fetching the same day overwrites the same key (spec #5 §5.3).
_OHLC_RAW_SQL = """
INSERT INTO staging.ohlc_raw
    (symbol, bar_type, bar_date, payload, fetched_at)
VALUES
    (%(symbol)s, %(bar_type)s, %(bar_date)s, %(payload)s::jsonb, %(fetched_at)s)
ON CONFLICT (symbol, bar_type, bar_date) DO UPDATE SET
    payload    = EXCLUDED.payload,
    fetched_at = EXCLUDED.fetched_at
"""


def upsert_ohlc_raw(records: list[dict[str, Any]]) -> int:
    """Land raw payloads into staging.ohlc_raw on (symbol, bar_type, bar_date).

    Each record: symbol, bar_type, bar_date, payload (JSON string), fetched_at.
    One transaction via executemany. Returns rows submitted. Raises on DB error.
    """
    if not records:
        return 0

    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.executemany(_OHLC_RAW_SQL, records)
    return len(records)


# ON CONFLICT key matches daily_returns PK (ticker, bar_date, source).
_DAILY_RETURNS_SQL = """
INSERT INTO daily_returns
    (ticker, bar_date, source, close, prev_close, log_return,
     at_limit, zero_volume, computed_at)
VALUES
    (%(ticker)s, %(bar_date)s, %(source)s, %(close)s, %(prev_close)s,
     %(log_return)s, %(at_limit)s, %(zero_volume)s, %(computed_at)s)
ON CONFLICT (ticker, bar_date, source) DO UPDATE SET
    close       = EXCLUDED.close,
    prev_close  = EXCLUDED.prev_close,
    log_return  = EXCLUDED.log_return,
    at_limit    = EXCLUDED.at_limit,
    zero_volume = EXCLUDED.zero_volume,
    computed_at = EXCLUDED.computed_at
"""


def upsert_daily_returns(records: list[dict[str, Any]]) -> int:
    """Idempotent upsert into daily_returns on (ticker, bar_date, source).

    Each record: ticker, bar_date, source, close, prev_close, log_return,
    at_limit, zero_volume, computed_at. One transaction via executemany.
    Returns rows submitted.
    """
    if not records:
        return 0

    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.executemany(_DAILY_RETURNS_SQL, records)
    return len(records)


# ON CONFLICT key matches index_returns PK (index_symbol, bar_date, source).
_INDEX_RETURNS_SQL = """
INSERT INTO index_returns
    (index_symbol, bar_date, source, close, prev_close, log_return, computed_at)
VALUES
    (%(index_symbol)s, %(bar_date)s, %(source)s, %(close)s, %(prev_close)s, %(log_return)s,
     %(computed_at)s)
ON CONFLICT (index_symbol, bar_date, source) DO UPDATE SET
    close       = EXCLUDED.close,
    prev_close  = EXCLUDED.prev_close,
    log_return  = EXCLUDED.log_return,
    computed_at = EXCLUDED.computed_at
"""


def upsert_index_returns(records: list[dict[str, Any]]) -> int:
    """Idempotent upsert into index_returns on (index_symbol, bar_date, source)."""
    if not records:
        return 0

    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.executemany(_INDEX_RETURNS_SQL, records)
    return len(records)


# ON CONFLICT key matches technical_indicators_daily PK (ticker, bar_date, source).
#
# Every non-key column is in the DO UPDATE SET, ``computed_at`` included: an indicator is
# derived, so a recompute has nothing to preserve from the incumbent row. That is the opposite
# of ``daily_bars``, where ``ingested_at`` records a first arrival and is deliberately kept.
#
# The placeholder order below IS ``RECORD_KEYS[Dataset.INDICATORS_DAILY]``, and
# ``localfs.py --selftest`` (assertion 1) parses this string to prove it. Do not reorder one
# without the other.
_TECHNICAL_INDICATORS_SQL = """
INSERT INTO technical_indicators_daily
    (ticker, bar_date, source, sma_20, sma_50, sma_200, ema_12, ema_26, macd, macd_signal,
     macd_hist, rsi_14, stoch_k_14, stoch_d_14, atr_14, bb_mid_20, bb_upper_20, bb_lower_20,
     bb_width_20, realized_vol_20d, realized_vol_60d, obv, volume_sma_20, turnover_value, ret_1d,
     ret_5d, ret_20d, ret_60d, ret_252d, ret_ytd, dist_from_sma_200_pct, high_252d, low_252d,
     drawdown_from_252d_high, computed_at)
VALUES
    (%(ticker)s, %(bar_date)s, %(source)s, %(sma_20)s, %(sma_50)s, %(sma_200)s, %(ema_12)s,
     %(ema_26)s, %(macd)s, %(macd_signal)s, %(macd_hist)s, %(rsi_14)s, %(stoch_k_14)s,
     %(stoch_d_14)s, %(atr_14)s, %(bb_mid_20)s, %(bb_upper_20)s, %(bb_lower_20)s, %(bb_width_20)s,
     %(realized_vol_20d)s, %(realized_vol_60d)s, %(obv)s, %(volume_sma_20)s, %(turnover_value)s,
     %(ret_1d)s, %(ret_5d)s, %(ret_20d)s, %(ret_60d)s, %(ret_252d)s, %(ret_ytd)s,
     %(dist_from_sma_200_pct)s,
     %(high_252d)s, %(low_252d)s, %(drawdown_from_252d_high)s, %(computed_at)s)
ON CONFLICT (ticker, bar_date, source) DO UPDATE SET
    sma_20                  = EXCLUDED.sma_20,
    sma_50                  = EXCLUDED.sma_50,
    sma_200                 = EXCLUDED.sma_200,
    ema_12                  = EXCLUDED.ema_12,
    ema_26                  = EXCLUDED.ema_26,
    macd                    = EXCLUDED.macd,
    macd_signal             = EXCLUDED.macd_signal,
    macd_hist               = EXCLUDED.macd_hist,
    rsi_14                  = EXCLUDED.rsi_14,
    stoch_k_14              = EXCLUDED.stoch_k_14,
    stoch_d_14              = EXCLUDED.stoch_d_14,
    atr_14                  = EXCLUDED.atr_14,
    bb_mid_20               = EXCLUDED.bb_mid_20,
    bb_upper_20             = EXCLUDED.bb_upper_20,
    bb_lower_20             = EXCLUDED.bb_lower_20,
    bb_width_20             = EXCLUDED.bb_width_20,
    realized_vol_20d        = EXCLUDED.realized_vol_20d,
    realized_vol_60d        = EXCLUDED.realized_vol_60d,
    obv                     = EXCLUDED.obv,
    volume_sma_20           = EXCLUDED.volume_sma_20,
    turnover_value          = EXCLUDED.turnover_value,
    ret_1d                  = EXCLUDED.ret_1d,
    ret_5d                  = EXCLUDED.ret_5d,
    ret_20d                 = EXCLUDED.ret_20d,
    ret_60d                 = EXCLUDED.ret_60d,
    ret_252d                = EXCLUDED.ret_252d,
    ret_ytd                 = EXCLUDED.ret_ytd,
    dist_from_sma_200_pct   = EXCLUDED.dist_from_sma_200_pct,
    high_252d               = EXCLUDED.high_252d,
    low_252d                = EXCLUDED.low_252d,
    drawdown_from_252d_high = EXCLUDED.drawdown_from_252d_high,
    computed_at             = EXCLUDED.computed_at
"""


def upsert_technical_indicators(records: list[dict[str, Any]]) -> int:
    """Idempotent upsert into technical_indicators_daily on (ticker, bar_date, source).

    Each record: ticker, bar_date, source, the 30 indicator columns, computed_at. Every
    indicator may legitimately be ``None`` — that is the warm-up, and it is the honest value
    when there is not yet enough history. It may never be NaN or infinity: Postgres ``numeric``
    rejects both, so the conversion happens once, upstream, in ``pipelines.indicators.build``.

    One transaction via executemany. Returns rows submitted. Raises on DB error.
    """
    if not records:
        return 0

    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.executemany(_TECHNICAL_INDICATORS_SQL, records)
    return len(records)
