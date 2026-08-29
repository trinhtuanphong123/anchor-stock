-- =============================================================================
-- 00007_live_monitors.sql — the daily apply path and its monitors.
--
-- This is where time returns to a system that discarded it. The similarity matrix
-- collapsed a whole window into one still picture; these tables are the rolling
-- quantities the dashboard shows on top of a FROZEN parameter set.
--
-- Everything here is computed by APPLYING stored coefficients to new sessions —
-- a projection of new observations onto a fixed model, not an estimation
-- (docs/04 §3). It travels one way only: nothing here ever feeds back into
-- selection, and none of these monitors triggers anything automatically.
-- Automatic retraining on a drift trigger would make the parameter set a moving
-- target and defeat the whole design (docs/04 §4).
--
-- Baseline migration 7 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- live_residuals — docs/04 §3 step 4.
--   residual = log_return - alpha_hat - beta_hat * factor_return
-- with alpha_hat/beta_hat taken from model_ticker_params. No refit.
-- residual_z expresses it in training-window units via sigma_hat, which is
-- exactly why sigma_hat is stored even though the similarity step normalises it
-- away (docs/01 §8).
-- -----------------------------------------------------------------------------
CREATE TABLE live_residuals (
    run_id        bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    ticker        text    NOT NULL,
    bar_date      date    NOT NULL,
    log_return    numeric NOT NULL,
    factor_return numeric NOT NULL,
    residual      numeric NOT NULL,
    residual_z    numeric,                       -- residual / sigma_hat

    CONSTRAINT live_residuals_pk PRIMARY KEY (run_id, ticker, bar_date)
);

CREATE INDEX idx_live_residuals_date ON live_residuals (bar_date DESC);

-- -----------------------------------------------------------------------------
-- live_rolling_similarity — docs/04 §3 step 5.
--
-- ρ² over a trailing window W ending at bar_date. Stored for EVERY (ticker,
-- anchor) pair, not only for the assigned anchor, because the assignment-
-- challenge monitor needs argmax over all j ∈ S — with only the assigned column
-- it could never notice that some other anchor now explains the ticker better.
--
-- window_w is a column, not a constant, so a second window can be added without a
-- migration (docs/decisions D-7 chose W = 120).
--
-- Row budget: N*k per session ≈ 1,000 at N=100, k=10, so ≈ 250k rows/year.
-- Retention: keep two years, prune older.
-- -----------------------------------------------------------------------------
CREATE TABLE live_rolling_similarity (
    run_id        bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    bar_date      date    NOT NULL,
    ticker        text    NOT NULL,
    anchor_ticker text    NOT NULL,
    window_w      int     NOT NULL CHECK (window_w > 0),
    rho2_w        numeric NOT NULL CHECK (rho2_w BETWEEN 0 AND 1),

    CONSTRAINT live_rolling_similarity_pk
        PRIMARY KEY (run_id, bar_date, ticker, anchor_ticker)
);

CREATE INDEX idx_lrs_date ON live_rolling_similarity (bar_date DESC);

-- -----------------------------------------------------------------------------
-- live_coverage_monitor — docs/04 §4, one row per session.
--
-- Four monitors rolled into one daily row because they are read together:
--   coverage drift        fbar_rolling vs fbar_published — the same quantity the
--                         cross-year evaluation measures, observed continuously
--                         instead of once a year
--   assignment challenges count of tickers a fresh assignment would move. A
--                         MONITOR, not an action: a(i) does not change between
--                         rebuilds. A rising count is early warning that the next
--                         rebuild will look different.
--   warm-up state         whether the live track has accumulated T_min sessions
--   serving_run_id        WHICH set the dashboard is actually serving. Below the
--                         warm-up threshold that is the prior year's set, and
--                         users should not have to infer that the anchor set
--                         predates the data they are looking at (docs/04 §4).
-- -----------------------------------------------------------------------------
CREATE TABLE live_coverage_monitor (
    run_id                    bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    bar_date                  date    NOT NULL,
    window_w                  int     NOT NULL CHECK (window_w > 0),
    fbar_rolling              numeric CHECK (fbar_rolling BETWEEN 0 AND 1),
    fbar_published            numeric NOT NULL CHECK (fbar_published BETWEEN 0 AND 1),
    coverage_drift            numeric,          -- fbar_rolling - fbar_published
    n_under_tau               int,
    n_assignment_challenges   int,
    sessions_since_publication int,
    warmup_sessions_required  int     NOT NULL DEFAULT 125,   -- T_min, docs/03 §5
    is_warm                   boolean NOT NULL,
    serving_run_id            bigint  REFERENCES model_runs ON DELETE SET NULL,

    CONSTRAINT live_coverage_monitor_pk PRIMARY KEY (run_id, bar_date)
);

CREATE INDEX idx_lcm_date ON live_coverage_monitor (bar_date DESC);

COMMENT ON COLUMN live_coverage_monitor.warmup_sessions_required IS
    'T_min = 125 sessions (half a year). Below it the largest ρ² attributable to pure noise is '
    '≈ 0.15 across 4,950 pairs, so a set built on less is close to noise (docs/01 §6). This is '
    'not a workaround — the cross-year ratio measures what serving a prior-year set costs, so '
    'the warm-up behaviour is licensed by a measured quantity rather than asserted.';

-- -----------------------------------------------------------------------------
-- live_beta_drift — docs/04 §4. Display only.
-- Large divergence means the residuals being computed each session are drifting
-- from the quantity the anchor set was built on. It informs the next scheduled
-- rebuild; it does not trigger one.
-- -----------------------------------------------------------------------------
CREATE TABLE live_beta_drift (
    run_id       bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    ticker       text    NOT NULL,
    bar_date     date    NOT NULL,
    window_w     int     NOT NULL CHECK (window_w > 0),
    beta_rolling numeric NOT NULL,
    beta_frozen  numeric NOT NULL,
    beta_delta   numeric NOT NULL,               -- beta_rolling - beta_frozen

    CONSTRAINT live_beta_drift_pk PRIMARY KEY (run_id, ticker, bar_date)
);

CREATE INDEX idx_lbd_date ON live_beta_drift (bar_date DESC);

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
