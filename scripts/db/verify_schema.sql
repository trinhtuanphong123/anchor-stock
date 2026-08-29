-- scripts/db/verify_schema.sql — structural counts + view execution, run against the local
-- container by verify_schema.ps1.
--
-- The reference figures below are P15's, replacing P0's (27 tables [26 public + 1 staging],
-- 4 views, 27 PKs, 26 FKs, 65 CHECKs, 6 UNIQUEs, 63 indexes). P15 changed the shape three ways:
--
--   * 00006_research and 00007_live_monitors were withdrawn to _archive/ — eight tables that
--     held zero rows and had no writer in this repository;
--   * daily_returns and index_returns became VIEWS over daily_bars / market_index_bars, so
--     they move out of the table count and into the view count;
--   * v_active_group_health lost its seven live_coverage_monitor columns with that table.
--
-- P15's figures, MEASURED on 2026-08-30 against the Supabase project immediately after all
-- eleven migrations were applied to an empty database — not carried forward and not estimated:
--
--     17 base tables (16 public + 1 staging)   13 views
--     17 PKs   14 FKs   46 CHECKs   5 UNIQUEs   44 indexes
--
-- The counts are read from the same catalogs the queries below read, so they are directly
-- comparable. 00011 is a no-op on the local container (anon/authenticated do not exist there),
-- and it creates no objects on Supabase either, so both targets should show these numbers.

\echo '-- tables (public + staging) -- expected 16 + 1 = 17'
SELECT table_schema, count(*) AS n_tables
FROM information_schema.tables
WHERE table_schema IN ('public', 'staging') AND table_type = 'BASE TABLE'
GROUP BY table_schema
ORDER BY table_schema;

\echo '-- views -- expected 13'
SELECT count(*) AS n_views FROM information_schema.views WHERE table_schema = 'public';

\echo '-- constraints by type -- expected p=17, f=14, c=46, u=5'
SELECT contype, count(*) AS n
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname IN ('public', 'staging')
GROUP BY contype
ORDER BY contype;

\echo '-- indexes -- expected 44'
SELECT count(*) AS n_indexes
FROM pg_indexes
WHERE schemaname IN ('public', 'staging');

-- Every view must EXECUTE, not just parse. An empty base table still returns zero rows
-- successfully; a broken view (wrong column, bad join) raises here instead of at first use
-- from the API.
--
-- All thirteen are listed since P15, not the four P0 checked. The two new ones are the
-- returns views, and they are the ones most worth executing: they are the only views in this
-- schema that COMPUTE rather than project, so a mistake in the lag() partition or the float8
-- casts surfaces here rather than in a model run.
\echo '-- executing every view --'
SELECT 'daily_returns'          AS view, count(*) FROM daily_returns
UNION ALL SELECT 'index_returns',          count(*) FROM index_returns
UNION ALL SELECT 'v_active_model_run',     count(*) FROM v_active_model_run
UNION ALL SELECT 'v_active_assignment',    count(*) FROM v_active_assignment
UNION ALL SELECT 'v_active_group_health',  count(*) FROM v_active_group_health
UNION ALL SELECT 'v_active_anchors',       count(*) FROM v_active_anchors
UNION ALL SELECT 'v_latest_indicators',    count(*) FROM v_latest_indicators
UNION ALL SELECT 'v_latest_session',       count(*) FROM v_latest_session
UNION ALL SELECT 'v_market_overview',      count(*) FROM v_market_overview
UNION ALL SELECT 'v_sector_performance',   count(*) FROM v_sector_performance
UNION ALL SELECT 'v_top_movers',           count(*) FROM v_top_movers
UNION ALL SELECT 'v_index_history',        count(*) FROM v_index_history
UNION ALL SELECT 'v_anchor_group_detail',  count(*) FROM v_anchor_group_detail;

-- THE GATE. Everything above is informational; this block is the one verify_schema.ps1 reads,
-- and it must be the LAST result set in the file — the script's pass condition is that the
-- output ENDS with "(0 rows)", so a query added after this one would silently become the gate
-- and retire this one.
--
-- It asks two questions at once, deliberately, for exactly that reason. They were briefly two
-- separate blocks and the second one took the first one's place as the gate, leaving the
-- presence check printing to nobody.
--
-- 1. Every required relation is present. "Relation", not "table": daily_returns and
--    index_returns are views since P15. That needed no change here —
--    information_schema.tables lists views too, under table_type = 'VIEW', and this never
--    filtered on table_type. Said out loud because the obvious tidy-up is to add
--    `AND table_type = 'BASE TABLE'`, which would report both views missing on a database
--    that is entirely correct.
--
-- 2. Every withdrawn table is absent. A database carrying them applied the archived
--    migrations, and question 1 would pass on it without a word.
\echo '-- schema gate: required relations present, withdrawn tables absent --'
WITH required(name) AS (VALUES
    ('stocks'), ('universe_snapshots'), ('universe_members'), ('trading_calendar'),
    ('ohlc_raw'), ('daily_bars'), ('market_index_bars'),
    ('daily_returns'), ('index_returns'),
    ('technical_indicators_daily'),
    ('model_runs'), ('model_universe'), ('model_ticker_params'), ('model_anchors'),
    ('model_similarity_anchor'), ('model_similarity_full'), ('model_groups'),
    ('pipeline_runs'), ('data_quality_reports')
),
withdrawn(name) AS (VALUES
    ('stability_studies'), ('anchor_frequency'), ('cross_year_eval'), ('measure_comparison'),
    ('live_residuals'), ('live_rolling_similarity'), ('live_coverage_monitor'),
    ('live_beta_drift')
),
present(name) AS (
    SELECT table_name FROM information_schema.tables
    WHERE table_schema IN ('public', 'staging')
)
SELECT 'MISSING' AS problem, r.name AS relation
FROM required r LEFT JOIN present p ON p.name = r.name
WHERE p.name IS NULL
UNION ALL
SELECT 'WITHDRAWN BUT PRESENT', w.name
FROM withdrawn w JOIN present p ON p.name = w.name
ORDER BY 1, 2;
