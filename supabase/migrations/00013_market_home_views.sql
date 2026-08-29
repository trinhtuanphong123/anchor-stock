-- =============================================================================
-- 00013_market_home_views.sql — what the redesigned market home page reads.
--
-- The home page gained three panels that no existing view could answer:
--
--   1. a VNINDEX line chart over a selectable range  -> v_index_history (new)
--   2. movers ranked at 1D / 5D / 1M / 3M / 1Y       -> ret_252d (new column)
--   3. a session liquidity ranking                   -> v_top_movers already
--                                                       carries turnover_value;
--                                                       no new view needed
--
-- Two of those are schema changes and one is not, which is the whole content of
-- this file. It follows 00010's four properties unchanged — nothing hard-coded,
-- ratios stay FRACTIONS, model-aware reads go through v_active_model_run, and
-- every view returns zero rows until the pipeline has run.
--
-- WHY ret_252d IS A COLUMN AND NOT A SQL EXPRESSION
-- -------------------------------------------------
-- `close / lag(close, 252) - 1` is a one-line window function, and writing it
-- here would have avoided a backfill. It is deliberately not written here.
-- pipelines/indicators/compute.py's header states the rule this file obeys:
-- every indicator formula lives in that one module, pinned, so that "RSI" or
-- "the 1-year return" cannot come to mean two things in one system depending on
-- whether the reader looked at Python or at SQL. ret_252d is computed by
-- `trailing_return(close, 252)` beside the other four trailing returns and is
-- stored, exactly like ret_1d..ret_60d before it.
--
-- The lookback is 252 SESSIONS, not 365 days — the same convention high_252d
-- and low_252d already use in 00004, and the reason the column is named for a
-- session count rather than for "1Y". The display labels it 1Y; the schema does
-- not pretend the two are identical.
--
-- WHY THE VIEWS ARE DROPPED AND RECREATED
-- ---------------------------------------
-- CREATE OR REPLACE VIEW may only APPEND columns, so replacing would have put
-- ret_252d after computed_at in v_latest_indicators — the trailing returns
-- split across the row with an unrelated timestamp between them. The three
-- views are dropped in dependency order and recreated with the column where it
-- belongs. Their definitions are otherwise reproduced verbatim from 00009 and
-- 00010; the diff is ret_60d/ret_252d in v_top_movers and ret_252d in
-- v_latest_indicators, and nothing else.
--
-- No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. The column.
--
-- Nullable with no default and no CHECK, matching ret_1d..ret_ytd beside it: a
-- return is legitimately negative, and NULL means "not computed" — which for
-- ret_252d is every row whose ticker has fewer than 253 loaded sessions behind
-- it. Existing rows get NULL and stay NULL until the indicator build reruns.
--
-- `double precision`, matching the columns it sits beside since P15 changed them
-- from numeric. A `numeric` here would be the one decimal column in a float8
-- table, which psycopg2 would hand back as a lone Decimal among floats.
-- -----------------------------------------------------------------------------
ALTER TABLE technical_indicators_daily
    ADD COLUMN IF NOT EXISTS ret_252d double precision;

COMMENT ON COLUMN technical_indicators_daily.ret_252d IS
    'Trailing simple return over 252 SESSIONS (not 365 days), as a fraction. NULL until the '
    'ticker has 253 loaded bars. Computed by pipelines.indicators.compute.trailing_return.';

-- -----------------------------------------------------------------------------
-- 2. v_index_history — the VNINDEX line chart's source.
--
-- UNRANGED and UNLIMITED, for the same reason v_top_movers is unordered: the
-- range (1M / 3M / 6M / YTD / 1Y / ALL) is the caller's question. A view takes
-- no parameters, so baking one range in would need six views.
--
-- The symbol comes from the ACTIVE RUN, never a literal 'VNINDEX' — the same
-- rule v_market_overview follows, and the reason neither view contains a
-- market-specific string. With no active run this returns zero rows, which is
-- the truth: there is no index to chart until a run says which one.
--
-- ret_1d is the SIMPLE return, derived here from index_returns' stored close
-- and prev_close rather than from exp() of its log return — the same
-- subtraction v_market_overview already does for the KPI row, so the figure at
-- the chart's right edge and the figure in the KPI row cannot disagree.
--
-- The join to index_returns is LEFT: the first session of the series has no
-- previous close and therefore no return, and it must still be drawn. Its
-- ret_1d is NULL, never 0 — a flat first point would be a fabricated one.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_index_history AS
SELECT
    b.index_symbol,
    b.bar_date,
    b.open,
    b.high,
    b.low,
    b.close,
    b.volume,
    CASE WHEN r.prev_close > 0 THEN r.close / r.prev_close - 1.0 END AS ret_1d
FROM market_index_bars b
JOIN v_active_model_run a  ON a.index_symbol = b.index_symbol
LEFT JOIN index_returns r  ON r.index_symbol = b.index_symbol
                          AND r.bar_date     = b.bar_date;

COMMENT ON VIEW v_index_history IS
    'Full OHLCV series of the ACTIVE run''s index, one row per session, with the simple daily '
    'return. Unranged and unlimited — the API applies the window. Empty when no run is active.';

-- -----------------------------------------------------------------------------
-- 3. Recreate the two views that must carry the new column, plus the one that
--    depends on them. Dependency order: dropping v_latest_indicators requires
--    both its dependents gone first.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_anchor_group_detail;
DROP VIEW IF EXISTS v_top_movers;
DROP VIEW IF EXISTS v_latest_indicators;

-- Verbatim from 00009 with ret_252d added beside the other trailing returns.
CREATE VIEW v_latest_indicators AS
SELECT DISTINCT ON (t.ticker)
    t.ticker,
    t.bar_date,
    t.source,
    t.sma_20, t.sma_50, t.sma_200,
    t.ema_12, t.ema_26,
    t.macd, t.macd_signal, t.macd_hist,
    t.rsi_14, t.stoch_k_14, t.stoch_d_14,
    t.atr_14,
    t.bb_mid_20, t.bb_upper_20, t.bb_lower_20, t.bb_width_20,
    t.realized_vol_20d, t.realized_vol_60d,
    t.obv, t.volume_sma_20, t.turnover_value,
    t.ret_1d, t.ret_5d, t.ret_20d, t.ret_60d, t.ret_252d, t.ret_ytd,
    t.dist_from_sma_200_pct,
    t.high_252d, t.low_252d, t.drawdown_from_252d_high,
    t.computed_at
FROM technical_indicators_daily t
ORDER BY t.ticker, t.bar_date DESC;

COMMENT ON VIEW v_latest_indicators IS
    'Most recent indicator row per ticker. Not gated by a model run (docs/04 §5): the '
    'presentation layer uses the full available history whatever artifact is active.';

-- Verbatim from 00010 with ret_60d and ret_252d added. The movers table now
-- ranks at five horizons, and a horizon the view does not expose is a horizon
-- the route would have to reach past the view to get.
CREATE VIEW v_top_movers AS
SELECT
    li.ticker,
    st.company_name,
    st.sector,
    li.bar_date,
    b.close                 AS close_price,
    b.volume                AS volume,          -- KL GD
    li.turnover_value,                          -- GT GD
    li.ret_1d,
    li.ret_5d,
    li.ret_20d,
    li.ret_60d,
    li.ret_252d
FROM v_latest_indicators li
LEFT JOIN stocks st    ON st.ticker  = li.ticker
LEFT JOIN daily_bars b ON b.ticker   = li.ticker
                      AND b.bar_date = li.bar_date
                      AND b.source   = li.source;

COMMENT ON VIEW v_top_movers IS
    'One row per ticker at its latest indicator date: name, sector, volume, turnover and the '
    'five trailing returns the movers table ranks by (1D/5D/1M/3M/1Y). Unordered and '
    'unlimited — the API applies horizon, direction and limit. Also backs the liquidity '
    'ranking, which is the same rows ordered by turnover_value.';

-- Verbatim from 00010, unchanged. Recreated only because it was dropped to free
-- v_latest_indicators.
CREATE VIEW v_anchor_group_detail AS
SELECT
    a.run_id,
    a.anchor_ticker,
    a.ticker            AS member_ticker,
    a.company_name,
    a.sector,
    a.position,
    a.coverage_c,
    a.is_anchor,
    a.under_tau,
    li.bar_date         AS indicator_date,
    li.ret_1d,
    li.ret_5d,
    li.ret_20d,
    li.turnover_value,
    li.rsi_14,
    li.dist_from_sma_200_pct,
    li.drawdown_from_252d_high
FROM v_active_assignment a
LEFT JOIN v_latest_indicators li ON li.ticker = a.ticker;

COMMENT ON VIEW v_anchor_group_detail IS
    'Active run, one row per (anchor, member): the group''s published figures plus the '
    'member''s latest indicators. LEFT-joined, so a member with no indicators yet still '
    'appears in its group.';

-- =============================================================================
-- Done. No production data inserted.
--
-- ret_252d is NULL on every existing row until `python -m pipelines.indicators.build
-- --storage pg` reruns — see docs/RUNBOOK.md §3.5. An empty 1Y column in the movers
-- table after applying this file is the expected intermediate state, not a bug.
-- =============================================================================
