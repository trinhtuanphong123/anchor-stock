# P9 execution plan — the read API

> ## CLOSED — moved to `completed/` on 2026-08-29 (P12/F5)
>
> **Closed by:** 40 of 40 boxes ticked in this file, and confirmed live on 2026-08-29 — ten
> deployed routes swept, every one HTTP 200: `/api/model/active`, `/api/tickers`,
> `/api/tickers/AAA` + `/history` + `/indicators` + `/analysis`, `/api/market/overview` +
> `/sectors` + `/movers`, `/api/anchors`. `services/api` tests stand at **165 passed**.
>
> **The one thing this plan flagged and deferred is now closed too:** P9.6 recorded connection
> pooling as "a real P10 concern" (`/api/tickers` at 3,083 ms). It was implemented, measured,
> and deployed on 2026-08-28 — steady state is now ~500 ms on that route. Detail in the parent's
> Validation table under "P9 follow-up".

---


**Started:** 2026-08-19
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md` — this file is the executable detail of its P9 section.
Progress and Validation are maintained **here**; the parent's P9 checkboxes track completion.
**Predecessor:** `p8-render-deployment.md` — DONE. Blueprint applied, both services live, `/` renders
live Supabase figures (commit `88447d1`, pushed to `origin/main` 2026-08-19).

---

## Why

P8 proved the seam. Render reaches Supabase through the session pooler, `/health` reports
`"database": "ok"`, CORS admits the static site and nothing else, and three routes render live
figures on `/`.

What is deployed is a **thin vertical slice, by design** (P8 S2). The screens the thesis actually
argues from — the sector treemap, the ticker page, the anchor page — have no data behind them,
because the routes that would feed them were never written. P9 writes them.

This phase **adds routes and nothing else**. `services/api` already holds `runtime_guards.py`,
`_errors.py`, `app/db/connection.py` and the CORS setup; all of it survived P0's trim and all of it
was exercised in production during P8. There is no infrastructure work here.

### Scope change from the parent plan

**`/api/pipeline/status` is dropped**, by explicit instruction: there is no system-status screen in
the product, so the route has no consumer.

Data freshness stays on screen regardless. `/api/model/active` already returns `latest_session`
alongside the run's `window_start` / `window_end` (`app/routes/model.py:33`), and that contrast — the
anchor set estimated on 2025 while prices run to the collection date — is what `docs/04` §5 actually
requires be visible. A status page would have been a second, weaker answer to a question already
answered.

This removes one route from D-18's table and one screen (`/pipeline`) from P10.

**P9 delivers eight routes**, taking the API from 3 to 11.

**Definition of done — met.** All eight routes deployed and returning live Supabase data (verified
over HTTP against production, not merely against Supabase directly); every one reconciled against a
direct query of its source view; `NotFound`/validation failures producing the existing envelope at
404/400 (confirmed live: `/api/tickers/ZZZZ`, `/api/anchors/ZZZZ`); NULL reaching the wire as `null`
in every route that can produce one (unit-tested; the unpublished-anchor NULL case additionally
confirmed live); and the `no path to greedy` assertion green with all five routers registered.
One finding carried forward to P10: the ticker page's four routes cost ~3.9 s combined from Render,
recorded in P9.6's Validation table rather than fixed here.

---

## Decisions taken

| # | Decision | Reasoning |
|---|---|---|
| S1 | **Drop `/api/pipeline/status`.** The route, and P10's `/pipeline` screen with it | No consumer. Freshness is already published by `/api/model/active`. Amends D-18's route table under that record rather than opening a new one — D-18 already states that P9 completes its table |
| S2 | **`log_run` / `write_dqr` stay in P11**, with a new justification | The parent plan justifies them by "what lets `/api/pipeline/status` say when the data was last refreshed". That reason dies with S1; the tables do not. With no orchestrator they are the only record that a manual refresh happened at all. P11's sentence gets rewritten, its checklist item does not |
| S3 | **`/api/anchors` reads a new view, `v_active_anchors`** (migration `00012`), not the base tables | D-18's table names `model_anchors` + `model_groups`. Those are base tables, and reading them directly makes "the API reads views" an exception-carrying claim — the precise thing D-18 rejected its alternative (b) for. The cheaper alternative, reusing `v_active_group_health`, keeps the rule but silently drops `step_k` and `marginal_gain` — the selection order and the marginal-gain curve, which `docs/02` names in the output contract and which are the greedy algorithm's most legible evidence in the whole system |
| S4 | **`/api/tickers/{t}/analysis` stays its own route** | Folding it into `/api/tickers/{t}` saves one round trip on the heaviest screen, but couples a rule engine that will change to a payload that should not, and spends an amendment to a decided route table on a latency figure nobody has measured from Render. Measure first (P9.6), decide after |
| S5 | **`/api/anchors` returns all `k_max` rows, not the published `k`** | The complete marginal-gain curve then arrives in one read and the 10-chip selector is a filter at the display edge. Same reasoning `v_top_movers` already embodies: the view publishes the facts, the caller chooses the cut |
| S6 | **The series routes duplicate `close` and `volume`** across `/history` and `/indicators` | Each response is then self-sufficient and the client never merges two arrays by date — a join that breaks exactly where one side is missing a session. The duplication is named in both docstrings so it reads as a choice, not an oversight |

---

## What is already true, and must not be re-derived

Verified during P6–P8. Not assumptions:

- **Nine views execute against live Supabase data** as `postgres`, re-checked after D-20's revoke.
- **`postgres` over `DATABASE_URL` is the only read path.** `anon` and `authenticated` hold nothing:
  schema `USAGE` false, SELECT on 0 of 35 relations, measured against a real throwaway table rather
  than inferred from the ACL.
- **The API reads views only, computes nothing, and has no import path to `pipelines.anchors`.**
  `test_routes.py:NoPathToGreedyTests` asserts the last one by inspecting `sys.modules`.
- **Two base tables are sanctioned direct reads.** `00009_views.sql`'s header says so in as many
  words: "The API and the dashboard read ONLY these views plus `daily_bars` and
  `technical_indicators_daily`." P9.3 uses that existing licence; it is not a new exception.
- **Composing two views in one statement is still "the API reads views."** `model.py` already does
  it (`v_active_model_run CROSS JOIN v_latest_session`), with the reasoning written into the SQL
  constant: a second query would double the endpoint's cost against a pooler an ocean away.
- **Ratios are fractions.** `ret_1d = 0.07` means +7%. Formatting to "%" belongs at the display edge.
- **`close` is in nghìn đồng**, so `turnover_value = close × volume` inherits that unit. Confirmed by
  the project owner during P8 and currently written down only in `p8-render-deployment.md`.
- **The active run:** `ae2010a4ad426`, `scope='year'`, `pearson_rho2`, `n_tickers=85`, **`k=10`,
  `k_max=15`**, `τ=0.10`, `F̄=0.2629`. Read from `data/artifacts/ae2010a4ad426/manifest.json`, not
  remembered.

---

## The route table after P9

| Route | Reads | Stage |
|---|---|---|
| `GET /api/model/active` | `v_active_model_run` ⋈ `v_latest_session` | *P8, done* |
| `GET /api/market/overview` | `v_market_overview` | *P8, done* |
| `GET /api/market/movers?direction=&limit=` | `v_top_movers` | *P8, done* |
| `GET /api/market/sectors` | `v_sector_performance` | P9.1 |
| `GET /api/tickers` | `v_active_assignment` ⋈ `v_latest_indicators` | P9.2 |
| `GET /api/tickers/{t}` | `v_active_assignment` ⋈ `v_latest_indicators` ⋈ `daily_bars` | P9.2 |
| `GET /api/tickers/{t}/history?from&to` | `daily_bars` | P9.3 |
| `GET /api/tickers/{t}/indicators?from&to` | `technical_indicators_daily` ⋈ `daily_bars` | P9.3 |
| `GET /api/tickers/{t}/analysis` | `v_latest_indicators` ⋈ `daily_bars` → rule engine | P9.4 |
| `GET /api/anchors` | `v_active_anchors` *(new)* | P9.5 |
| `GET /api/anchors/{anchor}` | `v_active_anchors` + `v_anchor_group_detail` | P9.5 |
| ~~`GET /api/pipeline/status`~~ | — | **dropped (S1)** |

---

## Progress

Each sub-phase is a separate working session and a separate commit. They are ordered so nothing
depends on a later one, and each leaves the deployed API in a working state.

### P9.0 — Schema and documents

No route work. First because P9.5 depends on the view, and because amending the documents is
cheapest before there is code to contradict them.

- [x] `supabase/migrations/00012_anchor_views.sql` — `v_active_anchors`: `model_anchors` joined to
      `model_groups` through `v_active_model_run`, LEFT-joined to `stocks` for display fields.
      Carries `run_id`, `step_k`, `anchor_ticker`, `position`, `marginal_gain`, `coverage_f`,
      `coverage_fbar`, `in_published_set`, `size`, `f_j`, `rho2_mean`, `rho2_min`,
      `sector_composition`, `company_name`, `sector`.
      **`model_groups` LEFT-joined**, confirmed necessary: `k_max=15`, `k=10`.
      Header follows `00009`/`00010`.
- [x] Applied to the **local container** (`datn_pg`, via `docker exec ... psql -f`, since the
      persistent container already holds `00001`–`00011` and the runner script is not
      incremental), then to **live Supabase** via the session pooler (`DATABASE_URL` from local
      `.env`, the same credential used for P6–P8 promotion)
- [x] **D-20 boundary verified on the live object, not inferred.** Against Supabase:
      `has_schema_privilege('anon','public','USAGE')` = **false**; `has_table_privilege('anon',
      'v_active_anchors','SELECT')` = **false**; same false for `authenticated`; and a full-schema
      sweep (`pg_class` × `has_table_privilege`) returns **0 of 36 relations** readable by `anon`.
      `00011` step 3's revoke of `postgres`'s default privileges holds for an object created after
      it — confirmed, not assumed.
- [x] Amend `docs/decisions/D-18-api-surface-fastapi-over-views.md` — struck `/api/pipeline/status`
      with its reason; corrected `/api/anchors` to read `v_active_anchors`
- [x] Amend `anchor-model-operations.md` — the P9 route table, the P10 screen list (dropped
      `/pipeline`), and P11's `log_run`/`write_dqr` justification (S2)
- [x] Amend `docs/01-data-pipeline.md` §1 with the turnover unit chain (nghìn đồng →
      `turnover_value` inherits it; scale-invariant for X/E/P, not for a summed dashboard figure)

### P9.1 — `/api/market/sectors`

One route over `v_sector_performance`, completing the market screen. First because it is the
smallest exercise of the new-route path, and the treemap is the last missing panel on the only
screen that currently works.

- [x] `sector`, `n_tickers`, `n_with_return`, `mean_ret_1d`, `total_turnover`, `total_volume`
- [x] **A NULL sector passes through as `null`.** Rendering it as "Khác" is P10's choice — the same
      rule P6.3 set for `stocks.sector` itself
- [x] **`n_with_return` published beside `mean_ret_1d`.** It is the mean's actual denominator
      (`avg()` skips NULLs), and this universe has sectors with two members. A two-stock average
      gets the same visual authority on a treemap as a twenty-four-stock one; the view's own comment
      says the dashboard owes the reader that caption, and the caption needs this number on the wire
- [x] Ordering is the route's job, as with movers: `total_turnover DESC NULLS LAST, sector ASC`.
      The tie-break exists so the same data always yields the same response

### P9.2 — `/api/tickers` and `/api/tickers/{t}`

- [x] **`/api/tickers`** — the searchable list of 85. `v_active_assignment` LEFT JOIN
      `v_latest_indicators`, so each row carries its latest move without the client composing two
      responses. Fields: `position`, `ticker`, `company_name`, `sector`, `industry`, `anchor_ticker`,
      `coverage_c`, `is_anchor`, `under_tau`, `bar_date`, `ret_1d`
- [x] **Ordered by `position` ASC.** The ordered universe pins every position in this system;
      serving the list in universe order rather than alphabetically keeps that visible. No
      pagination — 85 rows is the whole universe, and the screen is a search box, not a feed
- [x] **`/api/tickers/{t}`** — one statement: `v_active_assignment` ⋈ `v_latest_indicators` ⋈
      `daily_bars` at the indicator row's `(bar_date, source)`. That is the same join `v_top_movers`
      performs; doing it here rather than reading `v_top_movers` keeps the full indicator column set
- [x] Three blocks in the response: **identity** (ticker, name, sector, industry); **assignment**
      (`anchor_ticker`, `coverage_c`, `is_anchor`, `under_tau`, `alpha_hat`, `beta_hat`, `sigma_hat`,
      `r2`, `position`); **latest** (bar date, OHLC, volume, turnover, every indicator column, the
      trailing returns, `high_252d` / `low_252d` / `drawdown_from_252d_high`)
- [x] **404 when the ticker is not in the active run's universe** — `NotFound`, not an empty 200.
      D-16 makes the serving universe and the model universe the same 85, so "unknown ticker" and
      "not in this run" are currently the same condition. Say that in the docstring, so a future
      second universe does not inherit the conflation silently
- [x] Normalise the path parameter to upper case before binding

### P9.3 — `/api/tickers/{t}/history` and `/api/tickers/{t}/indicators`

Both take `from` and `to`, both read a sanctioned base table, both order `bar_date ASC`.

- [x] **`/history`** — `daily_bars`: `bar_date`, `open`, `high`, `low`, `close`, `volume`,
      `is_adjusted`. Feeds "Biến động Giá & Khối lượng"
- [x] **`/indicators`** — `technical_indicators_daily` LEFT JOIN `daily_bars` for `close` and
      `volume`. Feeds "Biểu đồ kỹ thuật tổng hợp", which needs Close, MA20, MA50, BB upper/lower,
      RSI with its 70/50/30 guides, MACD, Volume and Vol_MA20 **on one chart** — and close and
      volume are not in the indicator table
- [x] **The overlap is deliberate (S6) and named in both docstrings**
- [x] Shared parameter contract, written once: `from`/`to` optional ISO dates; default window the
      most recent 252 sessions; `from > to` → 400 through the existing `invalid_params` envelope;
      a server-side row cap so a wide range cannot return the full 1,424-session history by accident
- [x] **Unknown ticker → 404; known ticker with no rows in range → 200 with an empty array.** These
      are different facts, and a typo must not look like a quiet market
- [x] `is_adjusted` on the wire, because D-15's consequence — an adjusted chart will not match a
      broker's raw chart across an ex-date — is a caption the screen owes the reader, and the
      caption needs the flag

### P9.4 — `/api/tickers/{t}/analysis`

The only route in the system that computes anything, and the one most able to turn into a claim the
data does not support.

- [x] **A pure rule module, separate from the router**, so the rules are testable without an ASGI
      call and the router keeps its "select, serialise" shape. Input: the latest indicator row plus
      close and volume. Output: an ordered list of statements
- [x] **Each statement carries its own inputs** — `{code, text, inputs: {...}}`. The numbers the
      sentence rests on travel with the sentence, so the screen can show its evidence and a wrong
      sentence is traceable to a value rather than to prose
- [x] **Rule set**, descriptive, drawn only from columns `00004_indicators.sql` declares: price
      against SMA20/50/200; moving-average alignment; RSI band against the conventional 70/50/30
      guides; MACD histogram sign; position against the Bollinger band; latest volume against
      `volume_sma_20`; position within the 252-session range via `drawdown_from_252d_high`; and the
      trailing return ladder `ret_5d` / `ret_20d` / `ret_60d` / `ret_ytd`
- [x] **A rule whose inputs are NULL emits nothing, and the response says which rules were skipped.**
      The P6/D-13 NULL principle applied to prose: a 200-day average has no value on bar 37, and a
      sentence generated from a NULL would be the most convincing possible lie. The skipped list is
      what stops silence from being read as neutrality
- [x] **Never advisory.** `docs/02` §4: a run produces no probabilistic statement and no portfolio
      weights. Wording stays at "giá đang dưới MA20 và MA50", "khối lượng 20 phiên gần nhất cao hơn
      trung bình" — never "nên mua", never a target, never a probability. Where a conventional band
      is named, name it as a convention ("theo ngưỡng 70 thông dụng"), not as a fact about the stock
- [x] **Deterministic.** Fixed rule order, so the same indicator row always yields the same narrative
      in the same sequence — the same rule greedy follows when it breaks ties by smallest index
- [x] The response carries `bar_date` and the adjusted-price basis (D-15): a narrative about a price
      is a narrative about *which* price

### P9.5 — `/api/anchors` and `/api/anchors/{anchor}`

- [x] **`/api/anchors`** — `v_active_anchors`, all 15 rows ordered by `step_k` ASC, each carrying
      `in_published_set` (S5)
- [x] **`/api/anchors/{anchor}`** — two parts in one response: the anchor's own row from
      `v_active_anchors` (published stats plus its place in the selection order), and its members
      from `v_anchor_group_detail`, ordered `coverage_c DESC, member_ticker ASC`
- [x] `sector_composition` on the wire, **labelled as evidence, never as an input.** `docs/02` §3g:
      sectors never entered the similarity matrix or the objective, and showing that return-derived
      groups line up with sectors is external validation — feeding sectors in would make it
      circular. The API cannot enforce the labelling; the docstring is where the next reader learns
      it matters
- [x] 404 when the anchor is not an anchor of the active run
- [x] A member whose indicators have not been computed appears with NULL price columns. The view
      LEFT-joins for exactly that reason; the route must not filter those rows out

### P9.6 — Guard rails and verification

- [x] Extend `services/api/tests/test_routes.py` rather than starting a parallel style:
      standard-library `unittest`, the existing dependency-free ASGI harness, `fetch_one`/`fetch_all`
      patched in each route module's namespace. **No test opens a database.** Also added
      `test_narrative.py` for the pure rule engine (no ASGI harness needed — plain function calls)
- [x] `NoPathToGreedyTests` stays green with eleven routes registered — `python -m ruff check .`
      and `python -m unittest discover -s tests`: **142/142 pass**, `test_runtime_guards` still
      **64/64** unchanged
- [x] Live checks against **Supabase directly** (`psql`) — every route's query shape reconciled
      against real rows for all eight new routes, done incrementally per stage (P9.1–P9.5)
- [x] Pushed to `origin/main` (`88447d1..0beb4e9`, 6 commits) with explicit confirmation, Render
      auto-redeployed
- [x] Live checks against the **deployed Render API** (HTTP-level) — all 11 routes hit directly
      against production and confirmed:
      `/api/market/sectors` (9 sectors, real turnover), `/api/tickers` (85 rows), `/api/tickers/PDR`
      (three-block shape, real indicator values), `/api/tickers/ZZZZ` → 404, `/api/tickers/PDR/history`
      with an explicit `from`/`to` range, `/api/model/active`, `/api/market/movers`,
      `/api/market/overview` (unchanged from P8), `/api/anchors` (15 rows, 10 published,
      `marginal_gain` confirmed non-increasing live), `/api/anchors/VIC` (19 members = `size`),
      `/api/anchors/VCG` (unpublished: 0 members, `size` null), `/api/anchors/ZZZZ` → 404
- [x] Timed the four ticker-page routes from Render (cold, sequential):
      `/api/tickers/{t}` 872 ms, `/history` 948 ms, `/indicators` 1187 ms, `/analysis` 857 ms —
      **~3.9 s total** if the ticker page fires all four serially. `/api/tickers` (85-row list) alone
      was 3083 ms. **Decision: connection pooling is a real P10 concern, not a hypothetical one** —
      each route pays a fresh TLS handshake to the Sydney-region pooler from Singapore-region
      Render, and four sequential round trips on one page is user-visible latency. Recorded here;
      P10 should either parallelise the four fetches client-side (cheap, no API change) or revisit
      `read_cursor()` pooling (S4's deferred alternative) if parallelising isn't enough

---

## Validation

Same idiom as P0–P8. **Record what was actually run, and say plainly what was not.**

`services/api` has **no test runner wired**: `pytest` is declared in `requirements-dev.in` and used
by nothing. These files run as `python -m unittest` from `services/api`, and the completion report
must say so rather than implying a suite.

| Check | Status |
|---|---|
| `test_runtime_guards` still 64/64 — P9 adds routes, not configuration | not attempted |
| Every new route's serialisation contract, via patched fetchers | **PASS, all eight routes** — `/sectors`, `/tickers`, `/tickers/{t}`, `/history`, `/indicators`, `/analysis`, `/anchors`, `/anchors/{anchor}` |
| `Decimal` never on the wire — fixtures built with `Decimal`, asserted `float` out at a width that does not flatten a fraction | **PASS** — `obv` (large integral) and `volume` stay `int`, not float, across every route that carries one |
| **NULL serialises as `null`, never `0`** — an all-NULL fixture row per route. The single most likely way D-13 becomes a lie on screen | **PASS** — `test_no_bar_match_leaves_latest_columns_null`, series-route NULL fixtures, all-NULL narrative row, and `test_unpublished_anchor_has_null_group_fields` for the anchor curve's tail |
| Whole-number columns stay `int` — a volume fixture above 2^53 must not arrive as `1.23e9` | **PASS** — `obv=123456789012` asserted `int` across the detail, series and narrative routes |
| 400 / 404 / 503 envelopes — bad `from`/`to`; unknown ticker; unknown anchor; `NoData` | **PASS, all cases** — `from > to` → 400; unknown ticker → 404 on detail, both series routes and `/analysis`; unknown anchor → 404 (`test_unknown_anchor_is_404`); known-but-empty → 200 (empty range, no indicators yet, unpublished anchor's empty member list) |
| Narrative: closed-form fixture per rule, plus an all-NULL row asserting **zero statements and a populated skipped list** | **PASS** — `test_narrative.py`, 32 tests: all 13 rules' branches, `test_all_null_row_is_zero_statements_fully_skipped`, `test_no_statement_text_reads_as_advisory` |
| Narrative determinism — same row twice, identical ordered output | **PASS** — `test_determinism_same_row_twice_is_byte_identical` |
| No import path to `pipelines.anchors`, with all routers imported | **PASS** — `NoPathToGreedyTests` green with all five routers (model, market, tickers, anchors, health) registered |
| `00012` applies to the persistent local container and to live Supabase; `v_active_anchors` **executes** | **PASS** — `CREATE VIEW`/`COMMENT` clean on both; local container was not empty (already held `00001`–`00011`), so applied via direct `psql -f` rather than the full `apply_migrations.ps1` re-run |
| **`anon` still holds nothing after `00012`** — measured against the newly created view, the first object created after D-20's revoke | **PASS** — live Supabase: `anon` schema `USAGE` false, `SELECT` on `v_active_anchors` false for both `anon` and `authenticated`, 0 of 36 relations readable by `anon` schema-wide |
| `v_active_anchors`: 15 rows for the active run, exactly 10 with `in_published_set` true, `marginal_gain` non-increasing across `step_k` | **PASS** — verified on both the local container and live Supabase: 15 total, 10 published, `marginal_gain` strictly decreasing 5.80 → 0.99 |
| Live: each route reconciled against a direct query of its view — the P8 idiom that caught the F̄ precision bug | **PASS, all eleven routes** — P9.1–P9.5 verified against Supabase directly (`psql`); P9.6 verified the same shapes again through the deployed Render API over HTTP after push, including the unpublished-anchor case (VCG: 0 members, `size` null) and both 404 paths |
| Live: time the four ticker routes from Render. This is the measurement that decides whether connection pooling is a real P10 concern or a hypothetical one | **PASS, measured** — 872/948/1187/857 ms, ~3.9 s combined. **Connection pooling is a real P10 concern** — flagged for P10 to address (client-side parallel fetch first, `read_cursor()` pooling if that's insufficient) |
| `ruff check .` at the end of every sub-phase | **PASS**, P9.1–P9.3 — one fix needed: `Annotated[date \| None, Query(...)]` instead of `= Query(default=None)`, because ruff's bugbear B008 exemption for `fastapi.Query` does not recognise non-primitive parameter types (`date`) as exempt when passed via a default expression |

---

## Traps carried into this phase

- **Empty monitor tables are not zeros.** `v_active_group_health` LEFT-joins an empty
  `live_coverage_monitor`. P9 does not serve that view directly, but the principle governs every
  nullable column in every route added here.
- **The active run is `scope='year'`.** Anything assuming "active ⇒ `scope='live'`" is wrong.
- **The window and the prices disagree by design.** Anchors from 2025, prices through 2026-08. The
  ticker and anchor pages sit closest to that gap.
- **`index_close` must never be scaled.** An index level with no currency unit, sitting in the same
  KPI row as figures in nghìn đồng. P8 named it as the units error nobody would question.
- **No connection pooling exists.** `read_cursor()` opens a fresh psycopg2 connection per query; the
  ticker page issues four. Measured in P9.6, decided after — not designed around in advance.
- **`apps/web/tests/` does not exist** while `vitest.config.ts` points at it. `npm run test` is not a
  runnable check today. Irrelevant to P9, restated so it is not reported as passing in P10.

---

## Out of scope

- All `apps/web` work — screens, `lib/api.ts`, `lib/mock.ts`, the treemap and combined-chart
  components. **P9 stops at the wire.** P10.
- The refresh runbook, and `execute_batch` in `pipelines/common/upsert.py` — P11.
- Connection pooling, unless P9.6's measurement says otherwise.
- Airflow, scheduling, retries, backfills. D-13 stands: the dashboard is static as of the last
  collection.
