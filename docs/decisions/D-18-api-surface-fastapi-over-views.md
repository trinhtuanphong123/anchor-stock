# D-18 — The API is FastAPI over the views, not PostgREST and not ad-hoc SQL

**Status:** Decided, 2026-08-18. Opened as a placeholder in the P6–P10 plan; closed in P8, which
lands the first three routes. P9 completes the route table under this record rather than
reopening it.
**Affects:** `services/api/app/routes/`; what `apps/web` may call; the guard rail in `docs/04` §5.
No schema changes.
**Related:** [[D-20]] (who may reach the database — this record is what the API *serves*, on top
of that), [[D-13]] (static dashboard), [[D-21]] (where it runs).

## Context

The register carried D-18 as OPEN with the note "belongs to P9". P8 overtook that: deploying
something that shows real data means landing three routes now, and a route surface chosen
route-by-route while building is a surface nobody decided.

Two things had already narrowed the question without settling it.

`docs/04` §5 requires that no request can reach the greedy algorithm — the anchor selection runs
in `pipelines/` and its outputs are frozen. And D-20 revoked every grant held by `anon` and
`authenticated`, leaving `postgres` over `DATABASE_URL` as the only path to the data.

Nine views already exist and are verified executing against live Supabase data:
`v_active_model_run`, `v_active_assignment`, `v_active_group_health`, `v_latest_indicators`
(`00009_views.sql`), and `v_latest_session`, `v_market_overview`, `v_sector_performance`,
`v_top_movers`, `v_anchor_group_detail` (`00010_dashboard_views.sql`).

## Alternatives

**(a) PostgREST direct from the browser.** Supabase ships it; it is the idiomatic answer and
needs no server code at all. Rejected, and D-20 already made it impossible: the roles a browser
could authenticate as hold nothing. Reinstating them to enable this would undo that decision.
The deeper objection is that PostgREST exposes a *schema*, not a chosen surface — keeping
`model_ticker_params` and `model_similarity_full` out of reach would become a per-object
exercise repeated every time an object is added.

**(b) FastAPI over ad-hoc SQL** — routers querying base tables directly, each writing its own
joins and aggregates. Rejected. It scatters aggregate SQL across routers, where two routes
computing "the latest session" can drift apart silently, and it makes "the API reads views" an
unenforceable claim rather than something visible in a file.

**(c) FastAPI over the views.** Chosen.

## Decision

**Every route reads a view.** The views are the contract; a route selects, orders, limits and
serialises, and does not compute. Where a figure is genuinely presentational — sorting movers by
`ret_1d`, taking the top ten — that belongs in the route, because `v_top_movers` is deliberately
unordered and unlimited so that the direction and the cut are the caller's choice rather than
baked into SQL.

**GET only.** Already enforced in `create_app()`'s CORS middleware (`allow_methods=["GET"]`).
The serving plane is read-only; D-13 removed the live-apply path, so there is nothing to write.

**One error envelope**, `{"error": {"code": ..., "message": ...}}`, from
`app/routes/_errors.py`: 400 on request validation, 404 on `NotFound`, 503 on
`DatabaseUnavailable` and `NoData`, 500 otherwise. No route invents its own shape.

**No import path from `services/api` to `pipelines.anchors`.** This is what makes `docs/04` §5
checkable by inspection rather than by trust. `services/api` keeps its own
`app/db/connection.py` and does not reuse `pipelines/storage/` for exactly this reason.

**Floats cross the seam, never `Decimal`.** psycopg2 returns `Decimal` for `numeric` columns;
`as_float` converts in one place. This is the same rule `PostgresSource` already holds at the
storage port.

**NULL is passed through, never rendered as zero.** `v_active_group_health` LEFT JOINs the
deliberately-empty `live_coverage_monitor`, and every indicator column is nullable during
warm-up. A zero drift figure is a claim; NULL is the truth. Ratios stay fractions (`0.07` =
+7%); formatting to a percent sign happens at the display edge.

### The route table

P8 lands three, chosen because they cover every shape the rest need — a single-row view, an
aggregate view, and a parameterised list:

| Route | View |
|---|---|
| `GET /api/model/active` | `v_active_model_run` |
| `GET /api/market/overview` | `v_market_overview` |
| `GET /api/market/movers?direction=&limit=` | `v_top_movers` |

P9 adds `/api/market/sectors`, `/api/tickers`, `/api/tickers/{t}`, `/api/tickers/{t}/history`,
`/api/tickers/{t}/indicators`, `/api/tickers/{t}/analysis`, `/api/anchors`, and
`/api/anchors/{anchor}`, under this record.

**`/api/pipeline/status` is struck**, decided in P9 rather than built. There is no system-status
screen in the product, so the route had no consumer. Data freshness stays on screen regardless:
`/api/model/active` already returns `latest_session` beside the run's `window_start`/
`window_end`, which is the contrast `docs/04` §5 actually requires be visible — a status page
would have been a second, weaker answer to a question already answered. `pipeline_runs` and
`data_quality_reports` are unaffected; P11 still writes to them as the manual runbook's own audit
record.

**`/api/anchors` reads `v_active_anchors`** (`00012_anchor_views.sql`, P9.0), not `model_anchors`
and `model_groups` directly as an earlier draft of this table had it. Those are base tables, and
reading them from a route would have made "the API reads views" an exception-carrying claim —
the same objection alternative (b) was rejected for. The view is `model_anchors` LEFT-joined to
`model_groups` (LEFT, because the active run has `k_max=15` published anchors but only `k=10`
groups) through `v_active_model_run`, carrying `step_k` and `marginal_gain` — the selection order
and the marginal-gain curve, which `docs/02` names as part of the output contract.

Two more need their boundaries stated here rather than argued again later.
`/api/tickers/{t}/analysis` is a **rule-based narrative computed from stored indicator values** —
not stored, not model-derived, and never advisory. `docs/02` §4 is explicit that a run produces
no probabilistic statement and no portfolio weights, so the wording stays descriptive. And
`/api/model/active` is not optional decoration: `docs/04` §5 requires the active run's window to
be on screen, because the anchors were estimated on 2025 while prices run to the collection
date.

## Verified

At the time of writing, nothing — the routes are being built under this record, not documented
after the fact. What the record rests on is verified: all nine views execute against live
Supabase data as `postgres` (P7 verification, re-run after D-20's revoke), and `create_app()`
already restricts methods to GET and registers the error envelope.

P8's Validation table carries the checks that close this: `Decimal` never on the wire, NULL
never as `0`, and a bad `direction` returning the 400 envelope rather than a 500.
