-- =============================================================================
-- 00012_anchor_views.sql — the anchor selection surface (P9.0, D-18).
--
-- 00009 gave the API v_active_model_run, v_active_assignment and
-- v_active_group_health. None of those three carries the greedy algorithm's own
-- record of ITSELF: the order it picked anchors in, and the marginal gain each
-- one added. That record lives in model_anchors, a base table, and D-18's rule
-- is that the API reads views, not base tables — so it stays unreachable from
-- /api/anchors until this view exists.
--
-- v_active_anchors is that view: model_anchors LEFT-joined to model_groups
-- through v_active_model_run, with stocks attached for display. Selection order
-- (step_k) and the marginal-gain curve (marginal_gain, non-increasing by
-- construction) are what docs/02 names as part of the output contract, and they
-- are the most legible evidence the greedy method produces.
--
-- The LEFT JOIN to model_groups is load-bearing, not decorative. The active
-- artifact has k_max=15 and k=10 (data/artifacts/ae2010a4ad426/manifest.json):
-- model_anchors holds 15 rows, model_groups holds 10. Steps 11-15 were selected
-- but never published as a group, and an INNER JOIN would silently drop them
-- from the curve this view exists to publish.
--
-- No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- v_active_anchors — every selection step of the active run, published or not.
--
-- One row per (run, step_k). in_published_set marks step_k <= k, the boundary
-- between the published k=10 and the unpublished tail out to k_max=15 that the
-- greedy algorithm still selected and still recorded a marginal gain for.
-- group_size/f_j/rho2_mean/rho2_min/sector_composition are NULL past step_k=k,
-- because model_groups is populated only for the published anchors (00005).
--
-- That is a NULL which MEANS something: this anchor was selected but not
-- published, so it has no group. It is worth separating from the kind P15 took
-- out of v_active_group_health, which cited this one as its precedent. There,
-- seven columns were NULL on every row forever because the table behind them had
-- no writer at all. A NULL that reports a real boundary earns its column; a NULL
-- that reports "this was never built" does not.
-- -----------------------------------------------------------------------------
CREATE VIEW v_active_anchors AS
SELECT
    a.run_id,
    ma.step_k,
    ma.anchor_ticker,
    ma.position,
    ma.marginal_gain,
    ma.coverage_f,
    ma.coverage_fbar,
    ma.in_published_set,
    mg.size,
    mg.f_j,
    mg.rho2_mean,
    mg.rho2_min,
    mg.sector_composition,
    s.company_name,
    s.sector
FROM v_active_model_run a
JOIN model_anchors ma ON ma.run_id = a.run_id
LEFT JOIN model_groups mg ON mg.run_id = a.run_id AND mg.anchor_ticker = ma.anchor_ticker
LEFT JOIN stocks s ON s.ticker = ma.anchor_ticker;

COMMENT ON VIEW v_active_anchors IS
    'Active run, one row per selection step (step_k = 1..k_max), ordered by the order the greedy '
    'algorithm picked anchors in. in_published_set marks step_k <= k. Group columns are NULL past '
    'the published boundary -- that is the truth, not a join bug.';

-- =============================================================================
-- Done. No production data inserted.
--
-- Verify after apply:
--   SELECT count(*) FROM v_active_anchors;                              -- expected: k_max (15)
--   SELECT count(*) FROM v_active_anchors WHERE in_published_set;        -- expected: k (10)
--   SELECT step_k, marginal_gain FROM v_active_anchors ORDER BY step_k;  -- non-increasing
--
--   -- D-20 boundary, on the object this migration just created:
--   SELECT has_schema_privilege('anon', 'public', 'USAGE');              -- expected: false
--   SELECT has_table_privilege('anon', 'v_active_anchors', 'SELECT');    -- expected: false
-- =============================================================================
