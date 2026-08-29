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
-- THIS TABLE IS A CACHE, NOT A SOURCE OF RECORD (P15)
-- ---------------------------------------------------
-- Every value below is a pure function of daily_bars. Dropping this table loses
-- nothing that `python -m pipelines.indicators.build` cannot put back. It sits
-- beside daily_bars in the schema, which invites a reader to assume the two are
-- equally fundamental — they are not, and the COMMENT at the bottom says so to
-- anyone reading the database instead of this file.
--
-- It stays materialised rather than becoming a view, unlike 00003's returns,
-- for one concrete reason: EMA is RECURSIVE (ema_t = a*close_t + (1-a)*ema_t-1).
-- A window function cannot express it, and seven columns inherit that —
-- ema_12, ema_26, macd, macd_signal, macd_hist, rsi_14 and atr_14 (the last two
-- use Wilder smoothing, which is an EMA). Expressing those in SQL means a
-- recursive CTE, and it would discard pipelines/indicators/compute.py, whose
-- --selftest checks the formulas against closed-form fixtures.
--
-- WHY double precision AND NOT numeric (P15)
-- ------------------------------------------
-- These were numeric until P15: 31 columns x 121,014 rows = 94 MB of heap for
-- values that are float64 the whole way. numeric is variable-length decimal, so
-- a full-precision float64 costs ~26 bytes per value; float8 costs 8. Measured
-- on the 2026-08-29 database: 94 MB heap, ~815 bytes per row.
--
-- It also removes a round trip that existed only to be undone. The pipeline
-- computes float64, numeric stores it as decimal, psycopg2 returns Decimal, and
-- pipelines/storage/pg.py:_f() converts it straight back to float.
--
-- numeric buys exact decimal arithmetic, and NOTHING here needs it. docs/04 §5
-- is explicit that these are display-only and never reach the factor model or
-- selection, so float8 is a consequence of that rule rather than an exception to
-- it. The model's own frozen parameters (00005) stay numeric, where exactness
-- IS the point.
--
-- Baseline migration 4 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

CREATE TABLE technical_indicators_daily (
    ticker                  text        NOT NULL REFERENCES stocks,
    bar_date                date        NOT NULL,
    source                  text        NOT NULL DEFAULT 'VCI',

    -- --- trend ---
    sma_20                  double precision,
    sma_50                  double precision,
    sma_200                 double precision,
    ema_12                  double precision,
    ema_26                  double precision,

    -- --- momentum ---
    macd                    double precision,    -- ema_12 - ema_26
    macd_signal             double precision,    -- 9-period EMA of macd
    macd_hist               double precision,    -- macd - macd_signal
    rsi_14                  double precision CHECK (rsi_14 IS NULL OR rsi_14 BETWEEN 0 AND 100),
    stoch_k_14              double precision,
    stoch_d_14              double precision,

    -- --- volatility ---
    atr_14                  double precision CHECK (atr_14 IS NULL OR atr_14 >= 0),
    bb_mid_20               double precision,
    bb_upper_20             double precision,
    bb_lower_20             double precision,
    bb_width_20             double precision,
    realized_vol_20d        double precision
        CHECK (realized_vol_20d IS NULL OR realized_vol_20d >= 0),
    realized_vol_60d        double precision
        CHECK (realized_vol_60d IS NULL OR realized_vol_60d >= 0),

    -- --- volume ---
    obv                     double precision,
    volume_sma_20           double precision,
    turnover_value          double precision,    -- close * volume

    -- --- returns ---
    ret_1d                  double precision,
    ret_5d                  double precision,
    ret_20d                 double precision,
    ret_60d                 double precision,
    ret_ytd                 double precision,

    -- --- position within the recent range ---
    dist_from_sma_200_pct   double precision,
    high_252d               double precision,
    low_252d                double precision,
    drawdown_from_252d_high double precision,

    computed_at             timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT technical_indicators_daily_pk PRIMARY KEY (ticker, bar_date, source)
);

CREATE INDEX idx_tid_date        ON technical_indicators_daily (bar_date);
CREATE INDEX idx_tid_ticker_date ON technical_indicators_daily (ticker, bar_date DESC);

COMMENT ON TABLE technical_indicators_daily IS
    'A CACHE, not a source of record: every column is a pure function of daily_bars and is '
    'rebuilt by `python -m pipelines.indicators.build`. Losing this table loses nothing. '
    'Display-only — never an input to the factor model, the similarity matrix, or anchor '
    'selection (docs/04 §5), which is why the columns are float8 rather than numeric. '
    'NULL means insufficient history at that date, not a failure.';

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
