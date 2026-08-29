-- =============================================================================
-- 00003_returns.sql — log-return series, DERIVED not stored.
--
--     daily_returns   x_i(t) = ln( P_i(t) / P_i(t-1) )    per equity
--     index_returns   m(t)   = ln( I(t)   / I(t-1)   )    per index
--
-- WHY THESE ARE VIEWS (P15)
-- -------------------------
-- Both were tables until P15, holding 120,929 and 1,423 rows written by a
-- pipeline step. They are a PURE FUNCTION of daily_bars / market_index_bars:
-- one lag, one division, one logarithm, two flags. Storing the output of that
-- function alongside its input duplicates 18 MB of nothing, and — the reason
-- that actually decided it — makes a class of bug possible that a view cannot
-- have.
--
-- That bug is not hypothetical. In P6.4 the fetch succeeded and the returns
-- rebuild was MISSED, leaving a hole at the 2025/2026 boundary that only a
-- boundary check found. A derived relation cannot fall behind the table it is
-- derived from. The RUNBOOK step that had to be remembered is gone with it.
--
-- WHAT THIS COSTS, stated rather than discovered later
-- ----------------------------------------------------
-- pipelines/storage/ports.py keeps a symmetric seam: the local (parquet) and
-- Postgres backends write the SAME record dicts, and that symmetry is the
-- seam's whole value. Here it breaks — the local track still WRITES returns
-- (it is the research archive), and Postgres DERIVES them, so PostgresSink has
-- nothing to write for these two datasets.
--
-- This is not a new asymmetry, it extends an existing one. D-14 already
-- established exactly this shape for staging.ohlc_raw: local writes it, the
-- Postgres track does not, and mirror.py's fake sink ASSERTS the write is never
-- attempted. MIRRORED now excludes these two datasets on the same grounds.
--
-- THE ARITHMETIC IS float8, DELIBERATELY — AND WHAT THAT DOES NOT BUY
-- -------------------------------------------------------------------
-- pipelines/common/returns.py computes in Python float64. Postgres `numeric` is
-- arbitrary-precision decimal, so ln() and division over numeric would disagree
-- with it well above the last digit — and at the at_limit threshold a boundary
-- value could flip. Casting to float8 reproduces the same IEEE-754 division on
-- the same inputs. close/prev_close stay numeric: they are copied, not computed.
--
-- MEASURED against the 2026-08-29 database rather than asserted, because the
-- first draft of this comment claimed bit-for-bit agreement and that is FALSE:
--
--   daily_returns   120,929 rows == 120,929.  keys, prev_close, at_limit and
--                   zero_volume: 0 differences.  log_return: 543 rows (0.45%)
--                   differ, every one by exactly 1 ULP, max 1.39e-17.
--   index_returns   1,423 rows == 1,423.  keys and prev_close: 0 differences.
--                   log_return: 3 rows (0.2%) differ by 1 ULP, max 6.94e-18.
--
-- The cause was isolated, not guessed. For close=6.6, prev_close=6.54 the stored
-- value is 0x3f82b40d31e2548c and this view yields ...548b; Python on the
-- author's Windows machine returns ...548c. The inputs are identical and the
-- division is identical — the difference is `log()` in two libm builds, which
-- IEEE-754 does not require to be correctly rounded.
--
-- So this is NOT a divergence the view introduces. The table never avoided it;
-- it froze one machine's libm answer, and re-running the pipeline on Linux would
-- have shifted those same 543 rows. What changes is that the platform dependency
-- is now visible instead of latent.
--
-- Nothing the system actually uses is on that path. The dashboard never reads
-- either relation (no route selects from them). Artifacts are LOADED from disk,
-- never retrained from a request. The documented train track is the local one,
-- reading parquet written by the same Python that computed it — bit-exact and
-- untouched by this change. Only training with DATN_STORAGE=pg would read these
-- views, and that is not the documented path.
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
--
-- THE FILTER SITS INSIDE THE SUBQUERY, AND THAT IS LOAD-BEARING.
-- compute_return_rows carries prev_close forward across an unusable close
-- rather than resetting it — `if c is not None: prev_close = c` runs only for a
-- valid close, so prev_close is always the LAST VALID close, not the previous
-- session's. Filtering before the window makes lag() see only valid closes,
-- which is the same thing. Filtering after it would silently use the previous
-- ROW instead, and the two differ exactly when a bad close sits between two
-- good ones.
--
-- `close > 0` matches _as_pos_float (strictly positive; the table permits 0).
-- `close <> 'NaN'` matches its isfinite() check: numeric admits NaN, the CHECK
-- on daily_bars does not reject it, and in Postgres NaN sorts ABOVE every
-- number, so `NaN > 0` is true and the first predicate alone would let it pass.
-- -----------------------------------------------------------------------------
CREATE VIEW daily_returns AS
SELECT
    ticker,
    bar_date,
    source,
    close,
    prev_close,
    ln(close::float8 / prev_close::float8)                       AS log_return,
    -- The simple close-to-close return against the exchange band. The band and
    -- tolerance are written as the subtraction returns.py performs, not folded
    -- to 0.067, so the two read as the same expression (they are equal in
    -- float64 — checked, not assumed).
    abs(close::float8 / prev_close::float8 - 1.0)
        >= (0.07::float8 - 0.003::float8)                        AS at_limit,
    -- volume is nullable and NULL volume must not become NULL zero_volume:
    -- returns.py yields False for unknown volume rather than fabricating one.
    COALESCE(volume = 0, false)                                  AS zero_volume,
    updated_at                                                   AS computed_at
FROM (
    SELECT
        ticker, bar_date, source, close, volume, updated_at,
        lag(close) OVER (PARTITION BY ticker, source ORDER BY bar_date) AS prev_close
    FROM daily_bars
    WHERE close > 0 AND close <> 'NaN'::numeric
) s
-- Drops the first session of every series, which has no prior close. NULL > 0
-- is NULL, which is not true, so this needs no explicit IS NOT NULL.
WHERE prev_close > 0;

COMMENT ON VIEW daily_returns IS
    'Log returns derived from daily_bars, not stored (P15). x_i(t) = ln(P_i(t)/P_i(t-1)) on the '
    'adjusted close, in float8 to match pipelines/common/returns.py. Agreement is exact on keys, '
    'prev_close, at_limit and zero_volume, and within 1 ULP on log_return for 0.45% of rows — a '
    'libm difference between platforms, not a difference in the formula. See the file header.';

COMMENT ON COLUMN daily_returns.at_limit IS
    'Recorded, never used to exclude. HOSE''s +/-7% band produces frequent large moves; '
    'flagging them keeps the option of a robustness check without contaminating the base run. '
    'The realized close-to-close move can sit just under the nominal band because the limit '
    'price rounds to the tick, hence the 0.003 tolerance.';

-- -----------------------------------------------------------------------------
-- index_returns — the factor series f consumed by the one-factor model.
--
-- No flags: compute_index_return_rows states why — the index has no daily band
-- and market_index_bars has no volume the flag would mean anything against.
-- -----------------------------------------------------------------------------
CREATE VIEW index_returns AS
SELECT
    index_symbol,
    bar_date,
    source,
    close,
    prev_close,
    ln(close::float8 / prev_close::float8) AS log_return,
    updated_at                             AS computed_at
FROM (
    SELECT
        index_symbol, bar_date, source, close, updated_at,
        lag(close) OVER (PARTITION BY index_symbol, source ORDER BY bar_date) AS prev_close
    FROM market_index_bars
    WHERE close > 0 AND close <> 'NaN'::numeric
) s
WHERE prev_close > 0;

COMMENT ON VIEW index_returns IS
    'The market factor f, derived from market_index_bars rather than stored (P15). '
    'm(t) = ln(I(t)/I(t-1)) in float8, matching '
    'pipelines/common/returns.py:compute_index_return_rows exactly on keys and prev_close and '
    'within 1 ULP on 3 of 1,423 rows. See the file header for the measurement.';

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
