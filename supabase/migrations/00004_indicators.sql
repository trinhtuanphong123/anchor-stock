-- =============================================================================
-- 00004_indicators.sql — technical indicators for dashboard visualisation.
--
-- PRESENTATION LAYER ONLY. Nothing here is an input to the similarity matrix or
-- the selection objective, and nothing here is gated by a model run
-- (docs/04 §5: "technical indicators and price history use the full available
-- history, are not gated by a model_run, and never touch selection").
--
-- Explicit typed columns rather than JSONB: these are filtered, sorted and
-- charted, so they need indexes and a checkable shape. A jsonb blob would make
-- every dashboard query a runtime cast.
--
-- Every column is NULLABLE by design. During the warm-up at the start of a
-- series there is not yet enough history for a 200-day average, and NULL states
-- that honestly. Refusing to write the row, or writing a zero, would both lie.
-- This is the same principle as the removal of minimum-session gates: take what
-- is available and say what is missing.
--
-- Baseline migration 4 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

CREATE TABLE technical_indicators_daily (
    ticker                  text        NOT NULL REFERENCES stocks,
    bar_date                date        NOT NULL,
    source                  text        NOT NULL DEFAULT 'VCI',

    -- --- trend ---
    sma_20                  numeric,
    sma_50                  numeric,
    sma_200                 numeric,
    ema_12                  numeric,
    ema_26                  numeric,

    -- --- momentum ---
    macd                    numeric,    -- ema_12 - ema_26
    macd_signal             numeric,    -- 9-period EMA of macd
    macd_hist               numeric,    -- macd - macd_signal
    rsi_14                  numeric CHECK (rsi_14 IS NULL OR rsi_14 BETWEEN 0 AND 100),
    stoch_k_14              numeric,
    stoch_d_14              numeric,

    -- --- volatility ---
    atr_14                  numeric CHECK (atr_14 IS NULL OR atr_14 >= 0),
    bb_mid_20               numeric,
    bb_upper_20             numeric,
    bb_lower_20             numeric,
    bb_width_20             numeric,
    realized_vol_20d        numeric CHECK (realized_vol_20d IS NULL OR realized_vol_20d >= 0),
    realized_vol_60d        numeric CHECK (realized_vol_60d IS NULL OR realized_vol_60d >= 0),

    -- --- volume ---
    obv                     numeric,
    volume_sma_20           numeric,
    turnover_value          numeric,    -- close * volume

    -- --- returns ---
    ret_1d                  numeric,
    ret_5d                  numeric,
    ret_20d                 numeric,
    ret_60d                 numeric,
    ret_ytd                 numeric,

    -- --- position within the recent range ---
    dist_from_sma_200_pct   numeric,
    high_252d               numeric,
    low_252d                numeric,
    drawdown_from_252d_high numeric,

    computed_at             timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT technical_indicators_daily_pk PRIMARY KEY (ticker, bar_date, source)
);

CREATE INDEX idx_tid_date        ON technical_indicators_daily (bar_date);
CREATE INDEX idx_tid_ticker_date ON technical_indicators_daily (ticker, bar_date DESC);

COMMENT ON TABLE technical_indicators_daily IS
    'Display-only technical indicators computed from daily_bars. Never an input to the factor '
    'model, the similarity matrix, or anchor selection (docs/04 §5). NULL means insufficient '
    'history at that date, not a failure.';

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
