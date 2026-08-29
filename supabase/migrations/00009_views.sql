-- =============================================================================
-- 00009_views.sql — the read surface.
--
-- This is where docs/04 §5's guard rail — "no path from the dashboard to the
-- greedy algorithm" — stops being aspirational and becomes structural.
--
-- The API and the dashboard read ONLY these views plus daily_bars and
-- technical_indicators_daily. Every one of them starts from the single active
-- model run, so a reader cannot accidentally serve an inactive artifact, a
-- research-only dCor run (the CHECK in 00005 forbids activating one at all), or
-- a set from a different universe version. Selection itself is not reachable from
-- here: there is nothing to call, only rows to read.
--
-- Baseline migration 9 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- v_active_model_run — the one served parameter set, with its scalars.
-- At most one row: enforced by ux_model_runs_one_active in 00005.
-- -----------------------------------------------------------------------------
CREATE VIEW v_active_model_run AS
SELECT
    r.id                AS run_id,
    r.artifact_id,
    r.scope,
    r.scope_label,
    r.similarity_measure,
    r.universe_version,
    r.index_symbol,
    r.window_start,
    r.window_end,
    r.prior_close_date,
    r.n_sessions,
    r.n_tickers,
    r.q,
    r.k,
    r.k_max,
    r.tau,
    r.coverage_f,
    r.coverage_fbar,
    r.n_under_tau,
    r.is_primary,
    r.created_at,
    r.loaded_at
FROM model_runs r
WHERE r.is_active;

COMMENT ON VIEW v_active_model_run IS
    'The parameter set the dashboard is currently serving. Every other read view joins through '
    'this one, so "which run am I looking at?" has exactly one answer.';

-- -----------------------------------------------------------------------------
-- v_active_assignment — every ticker, its anchor, and its coverage.
--
-- Carries sector and company name from stocks for display. Note the direction:
-- sector is attached to the OUTPUT for rendering and external validation; it
-- never entered the similarity matrix or the objective (docs/02 §3g). Showing
-- that return-derived groups line up with sectors is evidence the method found
-- real structure — feeding sectors in would make that circular.
-- -----------------------------------------------------------------------------
CREATE VIEW v_active_assignment AS
SELECT
    a.run_id,
    p.position,
    p.ticker,
    s.company_name,
    s.sector,
    s.industry,
    p.anchor_ticker,
    p.coverage_c,
    p.is_anchor,
    p.under_tau,
    p.alpha_hat,
    p.beta_hat,
    p.sigma_hat,
    p.r2
FROM v_active_model_run a
JOIN model_ticker_params p ON p.run_id = a.run_id
LEFT JOIN stocks s ON s.ticker = p.ticker;

-- -----------------------------------------------------------------------------
-- v_active_group_health — per anchor group, the active run's published stats.
--
-- THE MONITOR HALF IS GONE (P15), and it is worth saying why rather than leaving
-- a reader to wonder what "health" now means. This view used to LEFT JOIN
-- LATERAL onto live_coverage_monitor for seven drift columns — monitor_date,
-- fbar_rolling, fbar_published, coverage_drift, n_assignment_challenges,
-- is_warm, serving_run_id. That table was withdrawn in P15 along with the rest
-- of 00007: it held zero rows and nothing in this repository ever wrote to it,
-- because the live-monitoring track was never built.
--
-- So those seven columns were NULL on every row, on every query, by
-- construction. The LEFT JOIN made that look like "no drift data yet" — a state
-- that would resolve — when it was in fact a state that never could. Publishing
-- a permanently-null column is worse than not publishing it: a reader has to
-- discover by experiment that it is never populated.
--
-- What remains is what was always real: the group's frozen figures from
-- model_groups, gated to the active run.
-- -----------------------------------------------------------------------------
CREATE VIEW v_active_group_health AS
SELECT
    a.run_id,
    g.anchor_ticker,
    g.size,
    g.f_j,
    g.rho2_mean,
    g.rho2_min,
    g.sector_composition
FROM v_active_model_run a
JOIN model_groups g ON g.run_id = a.run_id;

-- -----------------------------------------------------------------------------
-- v_latest_indicators — most recent indicator row per ticker.
--
-- NOT gated by a model run, deliberately: the presentation layer uses the full
-- available history and is unaffected by which artifact is active (docs/04 §5).
-- A ticker that entered the market after the active run's universe was frozen
-- still charts correctly here.
-- -----------------------------------------------------------------------------
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
    t.ret_1d, t.ret_5d, t.ret_20d, t.ret_60d, t.ret_ytd,
    t.dist_from_sma_200_pct,
    t.high_252d, t.low_252d, t.drawdown_from_252d_high,
    t.computed_at
FROM technical_indicators_daily t
ORDER BY t.ticker, t.bar_date DESC;

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
