-- =============================================================================
-- 00003_returns.sql — persisted log-return series.
--
--     daily_returns   x_i(t) = ln( P_i(t) / P_i(t-1) )    per equity
--     index_returns   m(t)   = ln( I(t)   / I(t-1)   )    per index
--
-- Universe-independent and stored per series, so a run for any ticker set and
-- any window reads them by (ticker, date) without recomputing. The first session
-- of a series has no return and is not stored.
--
-- The return's own inputs (close, prev_close) sit beside it so a return is
-- checkable without a self-join, and the previous-trading-day logic is verified
-- once rather than re-derived by every reader.
--
-- Baseline migration 3 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- daily_returns
--
-- at_limit / zero_volume are RECORDED, never used to exclude an observation
-- (docs/01 §1 forbids fabricating or dropping returns silently). They exist so
-- that the question "does excluding limit moves change the result?" can be asked
-- later as an explicit, reported robustness check rather than being baked in
-- invisibly now.
-- -----------------------------------------------------------------------------
CREATE TABLE daily_returns (
    ticker      text        NOT NULL REFERENCES stocks,
    bar_date    date        NOT NULL,
    source      text        NOT NULL DEFAULT 'VCI',
    close       numeric,
    prev_close  numeric,
    log_return  numeric     NOT NULL,
    at_limit    boolean     NOT NULL DEFAULT false,  -- close-to-close hit the daily band
    zero_volume boolean     NOT NULL DEFAULT false,  -- volume = 0
    computed_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT daily_returns_pk PRIMARY KEY (ticker, bar_date, source)
);

CREATE INDEX idx_daily_returns_date        ON daily_returns (bar_date);
CREATE INDEX idx_daily_returns_ticker_date ON daily_returns (ticker, bar_date);

COMMENT ON COLUMN daily_returns.at_limit IS
    'Recorded, never used to exclude. HOSE''s +/-7% band produces frequent large moves; '
    'flagging them keeps the option of a robustness check without contaminating the base run.';

-- -----------------------------------------------------------------------------
-- index_returns — the factor series f consumed by the one-factor model.
-- -----------------------------------------------------------------------------
CREATE TABLE index_returns (
    index_symbol text        NOT NULL,
    bar_date     date        NOT NULL,
    source       text        NOT NULL DEFAULT 'VCI',
    close        numeric,
    prev_close   numeric,
    log_return   numeric     NOT NULL,
    computed_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT index_returns_pk PRIMARY KEY (index_symbol, bar_date, source)
);

CREATE INDEX idx_index_returns_date ON index_returns (bar_date);

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
