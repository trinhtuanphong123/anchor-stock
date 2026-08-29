-- =============================================================================
-- 00010_dashboard_views.sql — the aggregate read surface (P7.3).
--
-- 00009 gave the API the model's own views. These four are what the two
-- reference screens actually render: the market KPI row, the sector treemap,
-- the movers table, and the anchor group page.
--
-- They exist as VIEWS rather than as SQL inside a router so that docs/04 §5's
-- guard rail — "the API reads views, not ad-hoc SQL" — stays structural. An
-- aggregation scattered across FastAPI handlers is one refactor away from a
-- handler that reads model_ticker_params directly.
--
-- Four properties every view here holds
-- -------------------------------------
-- 1. NOTHING IS HARD-CODED. No ticker, no ticker count, no sector name, no
--    date. "Today" is (SELECT max(bar_date) FROM daily_bars); the universe is
--    whatever rows exist. Replacing list_stocks.txt with a differently balanced
--    set and re-running the pipeline changes every number below and requires no
--    edit here. That is deliberate: the current 85 are known to be uneven by
--    sector (two sectors hold two tickers each), and rebalancing them must not
--    be a schema change.
--
-- 2. They read technical_indicators_daily, so THEY RETURN ZERO ROWS UNTIL
--    pipelines.indicators.build HAS RUN. Applying this migration to a database
--    whose indicator table is empty produces an empty dashboard that looks like
--    a bug and is not one.
--
-- 3. Model-aware views join through v_active_model_run, so "which run am I
--    looking at" keeps exactly one answer (00009's rule, unchanged).
--
-- 4. Ratios are FRACTIONS, not percents: ret_1d = 0.07 means +7%. That is the
--    unit technical_indicators_daily stores (P7 decision S2), and converting
--    here would leave two conventions in one schema. Formatting to "%" belongs
--    to the display edge.
--
-- One assumption, stated rather than enforced: at most one `source` per
-- (ticker, bar_date) is landed. Every sum below would double-count under two.
-- This matches v_latest_indicators in 00009, which already resolves "latest per
-- ticker" without regard to source; landing a second provider is the point at
-- which both need a precedence rule, and inventing one now would be guessing.
--
-- No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- v_latest_session — the one date every view below means by "today".
--
-- Factored out so the definition appears once. daily_bars rather than
-- technical_indicators_daily deliberately: the bars are the ground truth for
-- "did the market trade", and an indicator table lagging a bar behind should
-- show as missing rows, not silently move the date backwards.
-- -----------------------------------------------------------------------------
CREATE VIEW v_latest_session AS
SELECT max(bar_date) AS session_date FROM daily_bars;

COMMENT ON VIEW v_latest_session IS
    'The most recent session in daily_bars. The single definition of "today" for every '
    'dashboard aggregate — a view takes no parameters, and a hard-coded date would go stale '
    'silently.';

-- -----------------------------------------------------------------------------
-- v_market_overview — the KPI row (reference image 1).
--
-- Exactly one row, always: the aggregates are scalar subqueries, so the row
-- exists even before any indicator has been computed (every figure then reads
-- 0 or NULL, which is the truth).
--
-- advancers/decliners/unchanged are counted on ret_1d, which is NULL for a
-- ticker whose first ever session is today. Such a ticker is in n_tickers and
-- in none of the three counts — the three therefore need not sum to n_tickers,
-- and n_with_return says by how much.
--
-- The index columns come from the ACTIVE RUN's index_symbol rather than a
-- literal 'VNINDEX', so this view has no market-specific string in it. With no
-- active run they are NULL; the rest of the row is unaffected.
-- -----------------------------------------------------------------------------
CREATE VIEW v_market_overview AS
SELECT
    s.session_date,
    (SELECT count(*) FROM technical_indicators_daily t
      WHERE t.bar_date = s.session_date)                        AS n_tickers,
    (SELECT count(*) FROM technical_indicators_daily t
      WHERE t.bar_date = s.session_date AND t.ret_1d IS NOT NULL) AS n_with_return,
    (SELECT coalesce(sum(t.turnover_value), 0) FROM technical_indicators_daily t
      WHERE t.bar_date = s.session_date)                        AS total_turnover,
    (SELECT coalesce(sum(b.volume), 0) FROM daily_bars b
      WHERE b.bar_date = s.session_date)                        AS total_volume,
    (SELECT count(*) FROM technical_indicators_daily t
      WHERE t.bar_date = s.session_date AND t.ret_1d > 0)       AS advancers,
    (SELECT count(*) FROM technical_indicators_daily t
      WHERE t.bar_date = s.session_date AND t.ret_1d < 0)       AS decliners,
    (SELECT count(*) FROM technical_indicators_daily t
      WHERE t.bar_date = s.session_date AND t.ret_1d = 0)       AS unchanged,
    i.index_symbol,
    i.close                                                     AS index_close,
    CASE WHEN i.prev_close > 0 THEN i.close / i.prev_close - 1.0 END AS index_ret_1d
FROM v_latest_session s
LEFT JOIN LATERAL (
    -- index_returns already stores close and prev_close beside the log return, so the
    -- SIMPLE return the screen needs is a subtraction here rather than an exp() of the
    -- stored log return.
    SELECT r.index_symbol, r.close, r.prev_close
    FROM index_returns r
    JOIN v_active_model_run a ON a.index_symbol = r.index_symbol
    WHERE r.bar_date = s.session_date
    LIMIT 1
) i ON true;

COMMENT ON VIEW v_market_overview IS
    'One row: the latest session''s breadth, turnover and index move. ret_1d-based counts are '
    'fractions, and exclude tickers whose ret_1d is NULL (see n_with_return).';

-- -----------------------------------------------------------------------------
-- v_sector_performance — the "Diễn biến ngành" treemap.
--
-- Tile COLOUR is mean_ret_1d: the EQUAL-WEIGHTED mean of member ret_1d, i.e.
-- "the average stock in this sector today" (P7 decision S3). A cap-weighted
-- alternative is not available — no market-cap data is collected anywhere in
-- this project. Tile SIZE is total_turnover.
--
-- n_tickers counts every member; n_with_return is the mean's actual
-- denominator, because avg() skips NULLs. Publishing both means a sector whose
-- "average" rests on two names cannot be mistaken for one resting on twenty —
-- which matters here: the current universe has sectors with as few as two
-- members, and a two-stock average gets the same visual authority on a treemap
-- as a twenty-four-stock one. That is a caption the dashboard owes the reader
-- (P10), and this view supplies the number the caption needs.
--
-- A NULL sector stays NULL and forms its own group. Rendering it as "Khác" is a
-- display choice, the same rule P6.3 set for stocks.sector itself.
-- -----------------------------------------------------------------------------
CREATE VIEW v_sector_performance AS
SELECT
    st.sector,
    count(*)                                    AS n_tickers,
    count(t.ret_1d)                             AS n_with_return,
    avg(t.ret_1d)                               AS mean_ret_1d,
    coalesce(sum(t.turnover_value), 0)          AS total_turnover,
    coalesce(sum(b.volume), 0)                  AS total_volume
FROM v_latest_session s
JOIN technical_indicators_daily t ON t.bar_date = s.session_date
JOIN stocks st                    ON st.ticker  = t.ticker
LEFT JOIN daily_bars b            ON b.ticker   = t.ticker
                                 AND b.bar_date = t.bar_date
                                 AND b.source   = t.source
GROUP BY st.sector;

COMMENT ON VIEW v_sector_performance IS
    'Per sector on the latest session: equal-weighted mean ret_1d (treemap colour) and summed '
    'turnover (treemap size). n_with_return is the mean''s denominator — a sector of two is not '
    'the same claim as a sector of twenty-four.';

-- -----------------------------------------------------------------------------
-- v_top_movers — "Top 10 cổ phiếu tăng/giảm mạnh trong phiên".
--
-- Deliberately UNORDERED and UNLIMITED. Direction and limit are the caller's
-- question, not the view's: baking in "top 10 gainers" would need a second view
-- for losers and a third the first time someone wants 20.
--
-- Built on v_latest_indicators (00009) rather than re-deriving "latest row per
-- ticker". bar_date is exposed so a ticker that stopped trading is visible as a
-- stale date rather than silently ranked beside today's movers.
-- -----------------------------------------------------------------------------
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
    li.ret_20d
FROM v_latest_indicators li
LEFT JOIN stocks st    ON st.ticker  = li.ticker
LEFT JOIN daily_bars b ON b.ticker   = li.ticker
                      AND b.bar_date = li.bar_date
                      AND b.source   = li.source;

COMMENT ON VIEW v_top_movers IS
    'One row per ticker at its latest indicator date: name, sector, volume, turnover and the '
    'trailing returns. Unordered and unlimited — the API applies direction and limit.';

-- -----------------------------------------------------------------------------
-- v_anchor_group_detail — the /anchors/[anchor] page.
--
-- One row per (anchor, member) of the ACTIVE run, so a group's membership and
-- its members' latest move arrive in one read. is_anchor marks the row where
-- the member IS the anchor; coverage_c is that member's coverage under this
-- anchor (docs/02 §4).
--
-- The indicator join is LEFT: membership is a property of the frozen artifact,
-- and a member whose indicators have not been computed yet must still appear in
-- its group with NULL price columns rather than disappear from it.
-- -----------------------------------------------------------------------------
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
-- =============================================================================
