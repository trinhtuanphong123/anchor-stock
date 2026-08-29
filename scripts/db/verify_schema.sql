-- scripts/db/verify_schema.sql — structural counts + view execution, run against the local
-- container by verify_schema.ps1. Mirrors the P0 validation report's own numbers
-- (27 tables [26 public + 1 staging], 4 views, 27 PKs, 26 FKs, 65 CHECKs, 6 UNIQUEs, 63 indexes)
-- so a drift between "what P0 verified" and "what's actually applied" is visible by eye.

\echo '-- tables (public + staging) --'
SELECT table_schema, count(*) AS n_tables
FROM information_schema.tables
WHERE table_schema IN ('public', 'staging') AND table_type = 'BASE TABLE'
GROUP BY table_schema
ORDER BY table_schema;

\echo '-- views --'
SELECT count(*) AS n_views FROM information_schema.views WHERE table_schema = 'public';

\echo '-- constraints by type --'
SELECT contype, count(*) AS n
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname IN ('public', 'staging')
GROUP BY contype
ORDER BY contype;

\echo '-- indexes (excluding those backing PK/UNIQUE constraints, counted above) --'
SELECT count(*) AS n_indexes
FROM pg_indexes
WHERE schemaname IN ('public', 'staging');

-- Every view must EXECUTE, not just parse. An empty base table still returns zero rows
-- successfully; a broken view (wrong column, bad join) raises here instead of at first use
-- from the API.
\echo '-- executing every view --'
SELECT 'v_active_model_run' AS view, count(*) FROM v_active_model_run
UNION ALL
SELECT 'v_active_assignment', count(*) FROM v_active_assignment
UNION ALL
SELECT 'v_active_group_health', count(*) FROM v_active_group_health
UNION ALL
SELECT 'v_latest_indicators', count(*) FROM v_latest_indicators;

\echo '-- REQUIRED_TABLES from pipelines/common/db.py, presence check --'
WITH required(name) AS (VALUES
    ('stocks'), ('universe_snapshots'), ('universe_members'), ('trading_calendar'),
    ('ohlc_raw'), ('daily_bars'), ('market_index_bars'),
    ('daily_returns'), ('index_returns'),
    ('technical_indicators_daily'),
    ('model_runs'), ('model_universe'), ('model_ticker_params'), ('model_anchors'),
    ('model_similarity_anchor'), ('model_similarity_full'), ('model_groups'),
    ('stability_studies'), ('anchor_frequency'), ('cross_year_eval'), ('measure_comparison'),
    ('live_residuals'), ('live_rolling_similarity'), ('live_coverage_monitor'), ('live_beta_drift'),
    ('pipeline_runs'), ('data_quality_reports')
)
SELECT r.name AS missing_table
FROM required r
LEFT JOIN information_schema.tables t
    ON t.table_name = r.name AND t.table_schema IN ('public', 'staging')
WHERE t.table_name IS NULL;
