# Plan — P6 to P10: publish the 2025 anchor set as a working dashboard

**Started:** 2026-08-18
**Revised:** 2026-08-18, after review — see *What changed and why*
**Revised:** 2026-08-18 — **renumbered.** Deployment takes the P8 slot; the one-shot refresh
runbook moves to P11, after the dashboard. Reasoning in `../completed/p8-render-deployment.md` S1.
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Predecessor:** `../completed/anchor-model-migration.md` (P0–P5, finished 2026-08-17)
**Scope:** P6 database landing, P7 indicators, P8 deployment, P9 read API, P10 dashboard,
P11 refresh runbook.

Update **Progress** and **Validation** in the same commit as the code they describe.

---

## Why

P0–P5 delivered a **method that is proven but unreachable**. Ten artifacts sit in
`data/artifacts/` (five years × two measures), all passing V1–V14, reproducing bit-for-bit.
Nothing consumes any of them. The database is empty, `services/api` is `/health` only, and
`apps/web` still renders the dead Leiden contract against mocks.

The target of this pass is narrow and stated once: **the system applies the model; the report
argues for it.** Everything that exists to *prove* the method — the frequency table, the
cross-year evaluation, the dCor comparison, the near-degeneracy diagnostic — stays in
`data/research/` and goes into the written thesis. What ships is what a user actually asks:
*what is the market doing, what is this stock doing, which anchor represents it, and what does
that anchor's group look like.*

The dashboard is **static as of the last collection**. Data is fetched through today once,
processed once, and served. There is no daily orchestration and no live track this pass.

### What changed and why

The first draft of this plan was wider. Review cut it, and the cuts are the point:

| First draft | Now | Reason |
|---|---|---|
| Register both universes (100 + 85) | **85 only** (`list_stocks_research.txt`) | The other 15 have no α̂/β̂ and no anchor assignment — nothing downstream can use them. Loading them would put rows on screen the model cannot explain. |
| Mirror raw payloads too | **No `staging.ohlc_raw`** | Local-track artefact; nothing serving reads it. |
| Load the research tables | **Dropped** | Those figures are the report's argument, not the product. |
| `model/apply.py` + four live monitors | **Dropped** | No live track this pass. The `live_*` tables stay empty. |
| P8 = Airflow + three DAGs | **a one-shot refresh runbook** (renumbered to P11) | No daily collection wanted. A documented, reproducible command sequence replaces orchestration honestly. |
| — | **Sector labels for the 85** (new) | The treemap and the anchor group composition both need them, and nothing collects them today. |
| — | **Three specified screens** (new) | Market overview, ticker detail, anchor analysis. |

## Decisions taken

| # | Decision |
|---|---|
| S1 | Serving universe is the **85** research tickers, everywhere — model *and* presentation |
| S2 | Postgres: local Docker container first, promoted to Supabase as a separately-verified final step |
| S3 | Collect **2026 YTD once**, through today; static from there |
| S4 | **No khối ngoại (foreign-flow) figures** — nothing collects them and no column exists. Those KPI cards become turnover, advancers/decliners and VNINDEX change |
| S5 | Sector labels: vnstock `symbols_by_industries()` first, curated `data/reference/sector_map.csv` for whatever is missing |
| S6 | Keep **k = 10** as published in the active artifact — no retrain at k = 5 |

To be recorded as records when reached: D-13 (static dashboard), D-14 (staging local-only),
D-15 (indicator price basis), D-16 (serving universe), D-17 (sector source), D-18 (API
surface), D-19 (no foreign-flow data). Each is described under its phase.

---

## Structural rules this pass inherits

- **The universe order pins everything.** A loader that writes `model_universe` in a different
  order than `P.npy` is indexed by corrupts every read without raising.
- **One compute path, two sinks** (`pipelines/storage/ports.py`). P7 adds a dataset; it adds it
  to both implementations and to the four contract tables, or `localfs --selftest` assertion 1
  fails — which is the point of that assertion.
- **No path from the dashboard to greedy** (`docs/04` §5). `services/api` must not be able to
  import `pipelines.anchors`. With the live-apply path dropped this is easy to hold: the API
  reads stored rows only.
- **Sector labels are display and external validation only** (`docs/02` §3g). They never
  entered `P` and must not appear to. Return-derived groups lining up with sectors is
  *evidence*; feeding sectors in would make it circular.
- **Report checks honestly.** No test runner, no CI. Separate checks performed from checks not
  attempted.

---

## Progress

### P6 — Database landing — **DONE** (verified-local; Supabase promotion deferred, S2)

Full detail, live figures, and five findings (two real bugs caught by the read-back check) are
in `../completed/p6-database-landing.md`, the executable sub-plan for this phase. Summary:

- [x] **P6.0 Groundwork** — vnstock pin corrected to `==4.0.4` exact (not a range: three
      version-specific behaviors in `provider.py` were probed against 4.0.4 specifically);
      `requirements.lock` regenerated for real in a disposable Linux container; `AGENTS.md`
      corrected; `scripts/db/{compose.db.yml,apply_migrations.ps1,verify_schema.ps1}` written
      and run; `.env.example` written. Latent bug #3 struck (the code that carried it was
      archived in P2; `fetch.py` re-fetches the full window by design). Latent bug #5 folded
      into D-14 as a documented, contained divergence rather than fixed.
- [x] **P6.1 Reference data — 85 tickers, with sectors** — `pipelines/universe/sync.py`
      written; live sync: `stocks`=85, `universe_snapshots`={`u27ba69c4`} only,
      `universe_members`=85, sector coverage 85/85 (all from vnstock, 0 from the CSV fallback,
      0 NULL). Required a real-provider fix along the way:
      `VnstockListingSource.fetch()` called `all_symbols()`, which on the installed vnstock/KBS
      combination returns no `exchange` column at all — switched to `symbols_by_exchange()`
      filtered to `type == 'stock'` (identical row count to the old method, 1,528 both ways).
- [x] **P6.2 Mirror the market data into Postgres** — `pipelines/storage/mirror.py`, plus a
      necessary port extension (`BarSource.read_records`, since no existing method round-trips
      a full record). Live: 121,014 / 1,424 / 120,929 / 1,423 records mirrored across
      `daily_bars`/`index_bars`/`daily_returns`/`index_returns`, read == submitted, zero empty
      keys. `staging.ohlc_raw` confirmed 0 rows (D-14 held).
- [x] **P6.3 The artifact loader** — `pipelines/artifact/load.py` +
      `pipelines/artifact/activate.py`, exactly as specified (V1–V14 preflight, universe/ticker
      FK checks before any INSERT, idempotent on `artifact_id`, always loads inactive). Loaded
      and activated `ae2010a4ad426` (2025, `pearson_rho2`, `is_primary`) — the only artifact
      loaded this pass, as planned; the other nine stay on disk.
- [x] **P6.4 Collect 2026 year-to-date** — 86/86 symbols OK, 0 failures, 13,244 rows
      (`2026-01-01`→today). An overlap probe meant to run against a scratch copy instead landed
      in production due to a separate, now-flagged bug (`LocalSink`/`LocalSource`'s `root=` is
      a no-op) — turned out to be a stronger check by accident: 0 mismatches across all 86
      symbols confirmed the adjustment basis unchanged, so appending was safe. `daily_returns`
      also had to be explicitly rebuilt (bars and returns are separate write paths); boundary
      continuity at the year seam confirmed directly.
- [x] **P6.5/P6.6 Read-back verification** — `artifact/inspect.py --from-db <id>` written and
      run. Caught two real bugs before calling this phase done: `is_primary`/`is_active` swapped
      in the loader's own SQL, and `p_sha256` never threaded through the DB reconstruction. Both
      fixed, DB reloaded clean, final result: **field-for-field identical, `P` exact.**
- [x] **Supabase promotion** — **done, and verified on 2026-08-29 (P12/F5).** It happened in a
      later phase rather than in P6, which is why this box sat open: the credential S2 lacked is
      now held, Supabase carries the full schema and data, and Render reads it. The read-back was
      re-run against the real project and initially **failed** — `P` off by 4.996e-16 — which
      turned out to be `extra_float_digits = 0` on the Supavisor session truncating `float8` text
      output, not a loader bug. With `SET extra_float_digits = 3` pinned in `inspect.py`, the
      result is **field-for-field identical** against Supabase, matching the local-container
      result above. "Same migrations, same loaders, no new code" turned out to be *almost* true —
      one line of new code, in the reader.

#### What stays empty, stated plainly

`00006_research.sql` (four tables) and `00007_live_monitors.sql` (four tables) are applied and
**not populated** this pass. They are not dead schema: `docs/03` §8 and `docs/04` §3–4 specify
them, and removing them would put the schema at odds with the specification. They are reserved.

One consequence to handle in P9: `v_active_group_health` LEFT JOINs `live_coverage_monitor`, so
its monitor columns come back NULL. **The API must pass NULL through, never render it as 0** —
a zero drift figure is a claim; NULL is the truth.

#### Decisions P6 records

- **D-13 — static dashboard.** No live-apply path, no orchestration, `live_*` unpopulated.
- **D-14 — `staging.ohlc_raw` is local-track only.** Latent bug #5 (the schema-default
  `provider` column with no local counterpart) is therefore a contained, documented divergence,
  not fixed.
- **D-16 — the serving universe is the 85**, model *and* presentation. Confirmed live:
  `data/processed/` still holds all 100 tickers (the local track is the research archive), only
  the mirror and the DB are scoped to 85.
- **D-17 — sector label source**, display-only. In practice: vnstock's fine-grained
  `symbols_by_industries()` matched 85/85 with zero misses; the curated CSV fallback exists but
  was never exercised this pass. A small (~20-entry), hand-curated `industry_name → 9-bucket`
  table was still required, since vnstock's own coarse ICB hierarchy is unimplemented on the
  installed source.
- **D-19 — no foreign-flow data** this pass.

### P7 — Technical indicators

Not a side quest — this is the engine of both the market page and the ticker page.

#### P7.1 Extend the storage port

The one place P7 touches shared code, and the load-bearing part of the phase.

- [ ] `Dataset.INDICATORS_DAILY` in `storage/ports.py`
- [ ] `BarSink.write_indicators()` plus a `BarSource` read for chart ranges
- [ ] Entries in all four contract tables (`RECORD_KEYS`, `CONFLICT_KEY`, `ON_CONFLICT_KEEP`,
      `PARTITION_COL`) — conflict key `(ticker, bar_date, source)`
- [ ] The matching `INSERT ... ON CONFLICT` in `common/upsert.py`

`localfs --selftest` assertion 1 parses that SQL and asserts agreement, so a column added on
one side and forgotten on the other fails a check instead of drifting.

#### P7.2 `pipelines/indicators/`

- [ ] Compute every column `00004_indicators.sql` declares, from `daily_bars`, for the 85

The reference design's combined chart needs exactly Close, MA20, MA50, BB upper/lower, RSI with
70/50/30 guides, MACD, Volume and Vol_MA20 — all already columns in that table. `turnover_value`
(close × volume) is what replaces the dropped foreign-flow cards and also feeds the market
page's total trading value and the movers table.

**Every column is nullable by design and NULL is the honest answer during warm-up.** A 200-day
average has no value on bar 37. Do not zero-fill and do not withhold the row — the same
principle as the removal of minimum-session gates.

#### P7.3 Dashboard aggregate views

- [ ] New migration `00010_dashboard_views.sql` — keeps the "API reads only views" guard rail
      structural instead of scattering aggregate SQL through routers

| View | Feeds |
|---|---|
| `v_market_overview` | KPI row: session date, n tickers, total turnover, total volume, advancers / decliners, VNINDEX close and % change |
| `v_sector_performance` | Treemap "Diễn biến ngành": sector, mean % change, n tickers, total turnover |
| `v_top_movers` | "Top cổ phiếu tăng/giảm mạnh trong phiên": mã, tên, ngành, KL GD, GT GD, % thay đổi |
| `v_anchor_group_detail` | Anchor page: group members with sector and `coverage_c`, plus the anchor's own latest indicators |

All four start from the latest session in `daily_bars` and, where the model is involved, from
`v_active_model_run` — so "which run am I looking at" keeps exactly one answer.

#### P7.4 Verification approach

Closed-form fixtures, not a second implementation of the same formula (which would be
circular): SMA of a linear ramp, RSI of a monotone series = 100, the EMA recursion against its
own definition, the `macd == ema_12 − ema_26` identity, ATR against the true-range definition,
Bollinger width against 2σ. Plus a warm-up check asserting NULLs appear exactly where history is
insufficient, and a year-boundary check for `ret_ytd`.

#### Decision P7 records

- **D-15 — indicator price basis: adjusted**, consistent with D-6, and said on the dashboard —
  an adjusted chart will not match a broker's raw chart across an ex-date.

### P8 — Deployment to Render

Full detail is in `../completed/p8-render-deployment.md`, the executable sub-plan for this phase. Summary:
the system works and nobody can reach it. P8 puts the API on Render as a Web Service and the
dashboard alongside it as a **Static Site** (free, never sleeps, consumes no instance-hours —
the free Web Service allowance would not cover two always-on services), wires CORS between
them, and keeps the API awake with an UptimeRobot ping.

Deployment alone cannot show data, because the routes are P9 and the screens are P10. So P8
carries a **thin vertical slice** — three routes over existing views (`/api/model/active`,
`/api/market/overview`, `/api/market/movers`) and the `/` screen rewritten to render them —
chosen because those three cover every shape the remaining nine routes need.

- [ ] Lean API dependency manifest — `services/api` currently installs the whole
      `requirements.lock`, vnstock and matplotlib included, for a service that imports four
      packages
- [ ] The three routes, plus `next.config.ts` set to `output: 'export'`
- [ ] `render.yaml` Blueprint — hand-clicked services are not reproducible, the same argument
      D-20 made for `00011` being a migration
- [ ] Records **D-18** (API surface — closes the OPEN entry, since P8 lands the first routes),
      **D-21** (deployment topology), **D-22** (split dependency manifest)

Consequence worth stating here: the dead Leiden screens are archived in P8 rather than P10.
`output: 'export'` cannot build `/clusters/[cluster_id]` or `/tickers/[ticker]` from client
components, and publishing the rest would put visibly broken pages on a public URL.

### P9 — Read API

`services/api` keeps `/health`, `runtime_guards.py`, `_errors.py` and the CORS setup — the
infrastructure survived P0's trim. This phase adds routes and nothing else.

| Screen | Endpoint | Source |
|---|---|---|
| Market | `GET /api/market/overview` | `v_market_overview` |
| Market | `GET /api/market/sectors` | `v_sector_performance` |
| Market | `GET /api/market/movers?direction=&limit=10` | `v_top_movers` |
| Ticker | `GET /api/tickers` | `v_active_assignment` + `stocks` — the searchable list of 85 with sector and anchor |
| Ticker | `GET /api/tickers/{t}` | assignment + params + latest indicators + turnover/volume KPIs |
| Ticker | `GET /api/tickers/{t}/history?from&to` | `daily_bars` |
| Ticker | `GET /api/tickers/{t}/indicators?from&to` | `technical_indicators_daily` |
| Ticker | `GET /api/tickers/{t}/analysis` | rule-based narrative from the indicator row |
| Anchor | `GET /api/anchors` | `v_active_anchors` (new, `00012_anchor_views.sql`) — all `k_max` selection steps, `in_published_set` marking the published `k` |
| Anchor | `GET /api/anchors/{anchor}` | `v_active_anchors` + `v_anchor_group_detail` |
| All | `GET /api/model/active` | `v_active_model_run` — provenance |

**`/api/pipeline/status` dropped (P9 decision).** No system-status screen exists to consume it;
`/api/model/active` already publishes `latest_session` beside the run's window, which is the
freshness contrast `docs/04` §5 requires. `pipeline_runs` / `data_quality_reports` still get
written in P11 — they remain the manual runbook's own audit record, just no longer serving an
API route.

- [x] Guard rails: GET only (already in the CORS config); routers import nothing from
      `pipelines.anchors` (`NoPathToGreedyTests`, green with all five routers registered); extended
      `services/api/tests/test_routes.py` (the idiom P8 established, not `test_runtime_guards.py`)
      plus a new `test_narrative.py` for the pure rule engine — 142/142 passing, `ruff check .`
      clean. Full detail, including live HTTP verification against the deployed Render API and the
      ticker-page timing measurement, is in `../completed/p9-read-api.md`

**The narrative panel** is rule-based, computed in the API from stored indicator values — not
stored, not model-derived, and never a recommendation. `docs/02` §4 is explicit that a run
produces no probabilistic statement and no portfolio weights, so the wording stays descriptive
("giá đang dưới MA20 và MA50", "khối lượng 20 phiên gần nhất cao hơn trung bình"), never
advisory.

**Provenance must be on screen, not inferred.** `docs/04` §5 requires the dashboard to show the
universe as of the active run and say so. Here the gap is explicit and larger than a warm-up
banner: **the anchor set was estimated on 2025 while prices run to the collection date.**
`/api/model/active` returns `window_start`, `window_end`, `n_tickers`, `k`, `tau`,
`coverage_fbar` and the latest bar date; every page renders a strip saying so.

- **D-18 — API surface: FastAPI over the views**, not PostgREST direct from the browser. The
  views are the contract, and a typed server layer is where "no path to greedy" stays checkable.
  *Written in P8, which lands the first three routes; P9 completes its route table.*

### P10 — Dashboard

*Executable detail: `../completed/p10-dashboard.md`. Progress and Validation are maintained there; the
checkboxes below track completion.*

`apps/web` holds the single `/` screen P8 shipped; the Leiden screens were archived in P8. The
chart primitives (`ChartFrame`, `ChartSvg`, `ChartAxisLabel`, `ChartLegend`, `PriceHistoryChart`)
are contract-neutral and are reused; the screens and both data layers are replaced.

**Detail pages are query strings, not dynamic segments** (P10 S4): `/tickers/?t=VCB` and
`/anchors/?a=VCB`, one route each, rendering the list when the parameter is absent. `output:
"export"` cannot export a dynamic route from a client component, which `next.config.ts` has said
since P8. The route names below are written in their original `[param]` form where they describe
*content*; the URL shape is the one stated here.

**The dashboard shows results, not method** (P10 S1–S3, D-24). `docs/03` §5 already says so — the
report establishes that the method works, and the dashboard applies it for readers who do not need
it re-argued. Concretely: the provenance strip is one line (`Dữ liệu đến … · 85 mã · 10 điểm neo`)
with `k`, `τ`, `F̄(S)`, the estimation window, the measure and the artifact id behind a
disclosure; explanatory paragraphs under figures are removed; `τ` / `F̄(S)` / `ρ²` / `f_j` appear
only after a click. `docs/04` §5 is the floor this stops at, not a rule it breaks.

#### Three screens

- [x] **`/` — Tổng quan thị trường.** KPI row: Tổng số mã (85), Tổng GT giao dịch, Tổng KL giao
      dịch, số mã tăng / giảm, VNINDEX và % thay đổi *(khối ngoại removed — S4)*. Treemap
      "Diễn biến ngành" sized by turnover, coloured by % change, NULL sector → "Khác". Bảng
      "Top 10 cổ phiếu tăng/giảm mạnh trong phiên": Mã, Tên công ty, Ngành, KL GD, GT GD, %.
- [x] **`/tickers` + `/tickers/[ticker]` — Tổng quan mã chứng khoán.** Search across the 85;
      KPI row (GT GD, KL GD, % thay đổi phiên, vị trí so với đỉnh 252 phiên); "Biến động Giá &
      Khối lượng"; "Biểu đồ kỹ thuật tổng hợp"; "Phân tích kỹ thuật" narrative; **thẻ cụm neo**
      — which anchor represents this ticker, its `coverage_c`, whether it is itself an anchor,
      and a link through to that anchor's page.
- [x] **`/anchors` + `/anchors/[anchor]` — Phân tích điểm neo.** A 10-chip selector across the
      active run's published anchors. Per anchor: danh sách mã được neo (with sector and
      `coverage_c`), thành phần nhóm ngành, and the anchor's own trend from its indicators.
      Group stats (`size`, `f_j`, `rho2_mean`, `rho2_min`) go in a **secondary panel** — present
      for a reviewer, not competing with the result (P10 S3).

The sector-composition panel is the interesting one: it is the external validation `docs/02`
§3g describes. Label it as evidence, never as an input.

- [x] **`/about` — Giới thiệu**, replacing `/methodology` (P10 S2). One screen: what the system
      does in three or four sentences, the as-of date, the not-investment-advice disclaimer
      `docs/02` §4 requires a fixed place for, and the run's parameter table. Not the archived
      `MethodologyScreen`'s ~300 lines of argument, which belong to the report. **No `/pipeline`
      screen** (P9 dropped `/api/pipeline/status` for lack of a consumer, which removes its screen
      with it) — freshness is the provenance strip on every page instead, from `/api/model/active`
- [x] Extend `lib/api.ts` and `lib/mock.ts` with the eight P9 routes. *(The "664 lines of a dead
      contract" this line used to describe is gone — P8.3 already cut both files back to the three
      routes that existed then. What remains is addition, not rewriting.)* There are **no Pydantic
      response models** in `services/api`, so the types are transcribed by hand from the route dict
      literals; nothing can be generated. Standalone mock mode must keep working when
      `NEXT_PUBLIC_API_BASE_URL` is unset — it is how the frontend is developed.
- [x] Archive the clusters / lead-lag / outcomes screens and their components — *done in P8, moved
      to `_archive/p8-leiden-screens/`*
- [x] New charts: treemap, combined multi-series indicator chart with RSI guides, price+volume
      composite. No charting library (P10 S5): the existing SVG primitives already consume the
      design tokens, so a library would have to be restyled onto them anyway
- [x] Compact provenance strip on every page (P10 S1)
- [x] Delete the ~2,800 dead Leiden lines from `globals.css`, the debt P8 recorded for this phase
      (P10 S7), and create `apps/web/tests/` — `vitest.config.ts` points at a directory that does
      not exist, so `npm run test` runs zero tests and must not be reported as a passing check
      until it does

### P11 — One-shot refresh runbook

*Was P8. Renumbered — see the Revised line at the top; the scope below is unchanged.*

Airflow is dropped. What replaces it is not nothing: it is a **documented, reproducible command
sequence** taking the repository from an empty database to a fully populated one, so the state
on screen can be rebuilt rather than only trusted.

- [x] `docs/RUNBOOK.md` — **written 2026-08-29 (P12/F5).** The ordered PowerShell sequence in the
      specified order, each step naming its check. Every command in it was verified to exist with
      the flags it is written with, by running `--help` against the module; every file, script and
      function it cites was verified present. It also records two things the plan did not
      anticipate: the Supabase project's schema is tracked by **no** migration runner
      (`supabase_migrations.schema_migrations` is empty while the schema and data exist), so only
      the local-container path is scripted; and the file has **never been run top to bottom** —
      see the validation row below, which stays open.
- [ ] **NOT DONE — stated, not pending.** Confirm `common/logging.py:log_run` and
      `common/quality.py:write_dqr` record the manual runs. Both functions exist with the
      signatures this plan assumes, but whether every step in the chain actually calls them was
      not checked. With no orchestrator and no `/api/pipeline/status` route (dropped in P9),
      these two tables are the only record that a refresh happened at all, so this is worth
      closing — it just has not been.
- [ ] **NOT DONE — stated, not pending, and deliberately.** `psycopg2.extras.execute_batch` in
      `pipelines/common/upsert.py`, carried here from `../completed/p7-indicators.md`. Checked
      2026-08-29: the module still submits every batch with `executemany`, which its own docstring
      documents as the chosen mechanism, and it is *correct* — 121,014 daily bars and 121,014
      indicator rows landed through it. The cost is speed, not correctness, and the estimate of
      "18 hours against minutes" is this plan's own and has never been measured here. Changing the
      write path is not something to do without being able to run the full chain against a
      database, which is the check above that is also still open.

`log_run`'s `dag_id` / `dag_run_id` / `task_id` stay NULL, which is correct for a manual run;
the columns exist for exactly that distinction.

**Not planned:** scheduling, retries, backfill windows, sensors. If a daily refresh is wanted
later, the callables are already the right shape and this runbook is the specification of the
chain.

---

## Validation

Same idiom as P0–P5: `main()` / `--selftest` / `--mock` per module, plus DB checks against a
throwaway container. **Record what was actually run, and say plainly what was not.**

| Phase | Check | Status |
|---|---|---|
| P6.0 | `pip install -r requirements.lock` in a clean venv resolves and imports the vnstock the code actually uses | **PASS** — regenerated for real in a disposable container; `vnstock==4.0.4` exact |
| P6.1 | migrations apply to an empty container (repeat the P0 procedure); `stocks` holds exactly 85; `universe_members` order matches `list_stocks_research.txt` position for position | **PASS** — 27 tables/4 views/65 CHECKs/26 FKs/27 PKs/6 UNIQUEs/63 indexes, matching P0 exactly; `stocks`=85, members position-for-position |
| P6.1 | sector coverage reported as a count, not assumed: how many of 85 from vnstock, how many from the CSV, how many NULL | **PASS** — 85/85 vnstock, 0/85 CSV fallback, 0 NULL |
| P6.1 | `trading_calendar` — `session_seq` dense and gapless, the iff-CHECK holds on every row | **PASS** — 1,424 rows, dense 1..1,424 |
| P6.2 | `mirror --selftest`; row counts equal local↔pg per dataset; a sampled field-for-field compare returns `float`, never `Decimal`; `staging.ohlc_raw` confirmed empty | **PASS** — 5/5 selftest; live 121,014/1,424/120,929/1,423 read==submitted; raw = 0 rows |
| P6.3 | `artifact.load --selftest` — an invalid artifact rejected **before** any INSERT; re-loading a no-op; an unregistered `universe_version` refused by name | **PASS** — 6/6, including a real bug the selftest itself needed a fix to catch (see P6 sub-plan Findings) |
| P6.3 | 2025 Pearson loaded and active; `model_universe` order matches `P.npy` indexing; `v_active_model_run` returns exactly one row | **PASS** — `ae2010a4ad426` loaded (85/15/850/10), activated, `v_active_model_run` returns exactly 1 row |
| P6.4 | 2026 YTD fetched: per-symbol success ratio reported, `fetch_*.json` written, returns rebuilt with no gap at the 2025/2026 boundary | **PASS** — 86/86 OK, 13,244 rows; `daily_returns` rebuild was initially missed, caught and fixed; boundary confirmed gapless |
| P6.5 | `inspect --from-db` — field-for-field equality with disk, `P` exact | **PASS, after fixing two real bugs it found** — `is_primary`/`is_active` swapped in the loader SQL, `p_sha256` never threaded through the DB read. Now field-for-field identical, `P` exact |
| P6.5 | Supabase promotion: the same checks re-run against the real project | **PASS, 2026-08-29 — and it found a real bug on the first run.** `inspect --from-db ae2010a4ad426` against Supabase initially FAILED: `P: not exactly equal, max abs diff = 4.996e-16`. Diagnosed rather than tolerated: psycopg2 receives `float8` as *text*, and the Supavisor session reports `extra_float_digits = 0` (PostgreSQL 12+ defaults to 1), which prints 15 significant digits and drops the last bits. Re-reading the same rows at 1, 2 and 3 each returned `P` **bit-for-bit identical**, identifying formatting rather than data as the cause — the local container passed precisely because its default is 1. `inspect.py` now pins `SET extra_float_digits = 3` before reading, and the check reports **field-for-field identical** |
| P7 | `localfs --selftest` assertion 1 green after the SQL / `RECORD_KEYS` change — the one that catches a forgotten column | **PASS, 2026-08-29** — `localfs selftest: 12 passed, 0 failed`, including "read_records returns exactly RECORD_KEYS[dataset], in order" |
| P7 | `indicators --selftest` — closed-form fixtures; NULLs exactly where history is short; `macd == ema_12 − ema_26` on real data | **PASS, 2026-08-29** — `indicators selftest: 17 passed, 0 failed`, including "every column is NULL below its warm-up index and non-NULL at it" and "no record holds NaN or inf" |
| P7 | the four dashboard views execute (not merely parse) against loaded data; `v_sector_performance` totals reconcile with `v_market_overview` | **PASS, 2026-08-29 — and all ten views, not four.** Every `v_*` view was EXECUTED against live Supabase and returned rows: `v_active_anchors` 15, `v_active_assignment` 85, `v_active_group_health` 10, `v_active_model_run` 1, `v_anchor_group_detail` 85, `v_latest_indicators` 85, `v_latest_session` 1, `v_market_overview` 1, `v_sector_performance` 9, `v_top_movers` 85. Reconciliation exact across the 9 sectors: `total_turnover` 8352129774.00000004, `total_volume` 272811000, `n_tickers` 85, `n_with_return` 85 — each equal to `v_market_overview` to the last digit |
| P8 | deployed `/health` reports `"database": "ok"` — Render actually reached Supabase through the pooler | **PASS** — 2026-08-28 18:54 UTC, live URL, `"database":"ok"`. Detail: `../completed/p8-render-deployment.md` row 8 |
| P8 | deployed `/` renders live figures that reconcile against a direct query of `v_market_overview`; CORS admits the static site's origin and no other; no cold start after 20 minutes idle | **PARTIAL — two of three PASS, one FAIL.** Figures reconciled field by field against a direct `v_market_overview` read (session, ticker count, 32/41/12, turnover, volume, VNINDEX close and change — all exact). CORS: the site's origin gets `access-control-allow-origin`, an unrelated origin gets **no such header**, preflight clean. **Cold start FAILS**, and it is the free tier, not a defect — see `../completed/p8-render-deployment.md` row 11 |
| P8 | full detail — 13 checks — in `../completed/p8-render-deployment.md` | **DONE, and that plan is now closed** into `plans/completed/`. Rows 1–10 and 12–14 PASS; row 11 (cold start) FAIL, measured |
| P11 | the runbook executed start to finish against a **fresh empty container**, and the result compared to the incrementally-built database — this is what makes the state reproducible rather than merely present | **still `not attempted`** — but the runbook it refers to now exists (`docs/RUNBOOK.md`, 2026-08-29). Its individual steps have all been run, phase by phase; the *chain* has not been run as one sequence against an empty database, and the file says so in its own opening paragraph rather than implying otherwise. Until this row turns, "reproducible" is a claim about plausibility |
| P9 | `test_runtime_guards` still 64/64; route checks (142 tests total, incl. `test_narrative.py`); `services/api` has no import path to `pipelines.anchors`, asserted; NULL columns serialise as null, never 0; all 11 routes verified live against Supabase directly and again over HTTP against the deployed Render API after push | **PASS** — full detail in `../completed/p9-read-api.md` |
| P10 | `vitest` (config exists at `apps/web/vitest.config.ts`); standalone mock mode renders all three screens with `NEXT_PUBLIC_API_BASE_URL` unset; live mode against the P9 API | **PARTIAL, run 2026-08-29.** `npm --prefix apps/web run test` → **42 passed / 5 files** on `p12-method-review-followups` (`apiConfig` 10, `treemap` 9, `coverageAdjusted` 8, `chartHover` 5, `format` 10); the count is 38 on `main`, the four extra being F1's. The other two clauses — mock-mode rendering with the base URL unset, and live mode — are **still not attempted**; no test renders a screen |
| all | `ruff check .`, import sweep, `compileall`, storage selftests, `artifact.inspect --selftest`, re-run at the end of every phase | **PASS, 2026-08-29, all five.** `ruff check .` "All checks passed!"; `compileall` clean over `pipelines` and `services`; import sweep — no `pipelines*` module in `sys.modules` after importing `app.main` (D-18); `mirror --selftest` 5/0, `pg --selftest` 11/0, `localfs --selftest` 12/0; `artifact.inspect --selftest` 16/0 |
| P9 follow-up | **The connection pooling P9.6 flagged and P10 deferred — now implemented and measured against real Supabase** (`services/api/app/db/connection.py`) | **PASS, measured.** 9 page loads × 4 concurrent requests, ap-southeast-2 pooler, ~955 ms per handshake. No pool (what `main` serves today): **36 handshakes**, cold load 1,330 ms, later loads 1,338 ms. With the pool: **4 handshakes**, cold load 1,652 ms, later loads **482 ms** — steady state **−64 %**, repaid on the second page load. Plus 9 live checks on real backends: retention, read-only still enforced on a *reused* connection (`CREATE TEMP TABLE` refused), and `fetch_all` surviving a real `pg_terminate_backend` |
| P9 follow-up | **The same pool re-verified against a healthy Supabase after the earlier connection trouble, and hardened for the Render↔Supabase path** | **PASS, re-measured 2026-08-29.** Same 9×4 shape, same pooler: unpooled **36 handshakes**, steady 1,587–1,675 ms; pooled **4 handshakes**, steady **573–577 ms** (−65 %), first load +~130 ms. End to end over real HTTP against a local uvicorn on the real database: `/api/model/active` 1,426 ms then 457/456/457/470 ms; the four-request ticker screen 1,719 ms then **923 ms**; `/health` still `"database": "ok"`. Three deployment gaps found and fixed — see below |
| P9 follow-up | **F4 — the read-only write barrier, finished and measured** | **PASS.** The connection-layer half shipped with the pool (`set_session` failures are fatal in production). Two things were still wrong and are fixed here: the production check read `config.settings`, the import-time snapshot that `app/config.py` itself says must not drive the guards, so a process importing under development and later running with `ENV=production` silently got a warning instead of a refusal (`test_72`); and `render.yaml`'s stated reason for requiring port 5432 does not reproduce. Verified against real Supabase in production mode: `transaction_read_only = on`, write refused on a **reused** pooled connection, and an unestablished barrier refuses to serve |


**The `render.yaml` claim behind F4, measured.** That file said the transaction pooler (6543)
makes `set_session(readonly=True)` "error or leak to another client". Against this project on
2026-08-29 it does neither: the call succeeded, and across 20 transactions on one client
connection served by **8 distinct backends**, `transaction_read_only` read `on` every time —
Supavisor replays the session parameter onto whichever backend it assigns. So no boot-time guard
rejecting port 6543 was added: refusing to start for a reason that does not reproduce is the same
error in the other direction. The comment is corrected in place rather than deleted, and 5432 is
still required on the reason that survives measurement — under session pooling the characteristic
belongs to a session this process owns, under transaction pooling it belongs to undocumented
proxy behaviour, and since D-20 it is the only thing between a read path and a read-write
`postgres` session.

**A side confirmation nothing had planned for.** Measuring the cold start caught Render's log of a
real spin-down: `Shutting down` → `Waiting for application shutdown.` → `Application shutdown
complete.` → `Finished server process [46]`, at 19:09:54 UTC on 2026-08-28. That is the FastAPI
lifespan running on a genuine instance stop, which is the path `close_pool()` is wired into (F2,
D5). Until then it had only been exercised against fakes (`test_66` drives the ASGI lifespan
protocol). The shutdown completed cleanly, with no error logged between the two lines.

**Worth knowing for diagnosis:** if the barrier ever genuinely cannot be established, every data
route answers 503 while `/health` still reports `"database": "ok"` — `db/ping.py` opens its own
connection and never issues the statement. That asymmetry is recorded in `render.yaml` beside the
variable it would be diagnosed from.

**Three gaps this re-verification found, all specific to running the pool between Render and
Supabase rather than to pooling as such.** Each was reproduced against the real database before
it was fixed, and each has a test that fails when the fix is removed.

1. *A dead connection took its siblings' turn.* `_execute` retries once. Every pooled connection
   is opened to the same pooler at the same moment, so whatever kills one has very likely killed
   the rest — and the ticker screen fires four requests at once. Measured: after
   `pg_terminate_backend` on all four pooled connections, a four-way page load returned
   **two 503s and two successes**. The first connection proved dead now retires the idle set, and
   the same load returns **4/4 in 1,371 ms**. (`test_70`)
2. *No TCP keepalives.* When the peer's RST arrives, a dead pooled connection surfaces at once
   and the retry serves the request. When nothing arrives — an idle flow dropped by a middlebox
   between Render's Singapore egress and Supabase's Sydney pooler, which is the ordinary failure
   mode on a public-internet path — `execute` blocks on kernel retransmission (~15 min on Linux)
   holding a Uvicorn threadpool slot. `connect_timeout` is already spent and the server's
   `statement_timeout` never starts, because the server never receives the query. Keepalives are
   the only guard that applies; verified on the wire (`keepalives=1, idle=30, interval=10,
   count=3` present in `get_dsn_parameters()` of a live connection). (`test_69`)
3. *A dropped socket was reported as a read-only failure.* A connection dying between the
   handshake and `set_session` produced a 503 logged as "could not set the connection read-only",
   pointing a reader at the write barrier for what is a network event, and skipping the retry
   that would have served the request. Connection-level errors now pass through to the retry;
   `test_59` still holds, so fail-closed on a genuine read-only failure is unchanged. (`test_71`)

**Deployment facts established rather than assumed.**

* The deployed `DATABASE_URL` really is on the **session** pooler (5432), not the transaction
  pooler (6543) that `render.yaml` warns about. Verified indirectly but decisively: under load
  from the deployed API, `pg_stat_activity` shows backends whose `backend_start` is *now* and
  which disappear again — one client connection to one backend, which is session-mode behaviour.
  Transaction mode would show a small set of long-lived shared backends. This matters because F2
  makes a `set_session` failure fatal in production: on 6543 the API would answer 503 to
  everything, where before it degraded silently to a read-write superuser session.
* The Supabase pooler does **not** reap idle connections quickly. Measured directly: connections
  left idle for 60 / 180 / 300 / 600 / 900 / 1,500 s all served the next query normally, in
  267-331 ms, and `idle_session_timeout` is `0` server-side. So staleness comes from the network
  path, not from a pooler timeout — which is why the fix is keepalives plus sibling retirement,
  not a recycle age.
* Headroom is not a concern: `max_connections` is 60 with a baseline of ~11 in use;
  `_POOL_MAX` is 8.
* Live baseline of the **deployed** service before this change, for comparison after it ships:
  cold start 34.3 s, then `/health` ~1,000 ms, `/api/model/active` ~950 ms, `/api/tickers`
  ~1,085 ms.

**Measured on the deployed instance after shipping** (commit `cdc0892`, live 2026-08-28 18:05 UTC;
client in Vietnam, so both columns carry the same client→Singapore leg and only the
Singapore→Sydney database leg changed):

| route | before (`main`, per-request connect) | after (pooled) |
|---|---:|---:|
| `/api/model/active` | ~950 ms | **449 ms** median (min 440) |
| `/api/tickers` — the route P10 named at 3,083 ms | ~1,085 ms | **501 ms** median (min 482) |
| ticker screen, 4 requests in parallel | — | 1,180 ms then **827 / 732 ms** |
| `/health` | ~1,000 ms | 909 ms — unchanged by design, it keeps its own connection |

Render's app log for the window shows 200 on every route, no 503, and no read-only warning.

**Noted while reading those logs, not acted on:** Render polls `/health` every ~5 s for as long as
the instance is awake (two pollers, ~24 requests/min), and `db/ping.py` opens a fresh connection
to Sydney for each one. It is bounded — the log is empty for 17:20–17:47 UTC, confirming the free
instance spins down and the polling stops with it — and Q2 deliberately kept `/health` off the
pool so it can answer when the pool is exhausted. But that cadence was not known when Q2 was
decided, and it is the largest remaining source of handshakes in this deployment.

**Still not attempted.** Cold process start is unchanged by any of this: a freshly woken instance
has an empty pool by construction, and the wake itself measured 34.3 s.

**Two corrections this measurement forced, recorded because both were assumptions until they were
run.** First, `psycopg2.pool.ThreadedConnectionPool` was the obvious implementation and is the
wrong one here: `getconn` holds a single lock across `psycopg2.connect()`, so concurrent
handshakes serialise, and the cold page load measured **8,647 ms against 1,330 ms unpooled** — a
five-fold regression on exactly the load a reader of a spun-down free instance sees. The pool is
therefore hand-written, with all network work outside its lock. Second, the pooled cold load is
still ~320 ms slower than unpooled, and that is *not* serialisation: it is the `rollback()`
needed to return a connection reusable, which closing one does not need. `autocommit` removes it
(measured: 161 ms steady, cold load faster than unpooled) and is deliberately left as a separate
decision, since it drops the shared snapshot across the two queries `anchor_detail` issues.

**Not covered by the above:** cold *process* start. A freshly woken Render instance has an empty
pool by construction, so the pool cannot help the first request after a spin-down — only the
requests after it.

**Stated plainly:** there is still no CI and no test runner wired for the Python side. `pytest`
is declared in `requirements-dev.in` and used by nothing. Converting the `--selftest` bodies
into `test_*.py` is mechanical and deliberately out of scope.

---

## Traps worth naming before starting

- **Re-running a build after a `RECORD_KEYS` change is not automatically safe.** P3 hit this:
  `LocalSink._merge` builds each row from `RECORD_KEYS[dataset]`, so a shard predating a new
  column raises `KeyError` at write time. P7 adds a dataset — check for stale shards.
- **pyarrow partition inference.** `pq.read_table` on `ticker=VCB/data.parquet` synthesises a
  dictionary-encoded `ticker` column that collides with the real one. `localfs._read_parquet`
  wraps `ParquetFile(path).read()` for that reason; the "simplification" back is silent.
- **`numeric` round-trip.** `P` is `float8[]` and exact. The scalar columns are `numeric` and
  psycopg2 returns `Decimal`. The port contract says floats cross the seam, never `Decimal` —
  the conversion runs in one place, toward float, as `PostgresSource` already does.
- **Empty monitor tables are not zeros.** `v_active_group_health` LEFT JOINs an empty
  `live_coverage_monitor`; NULL must survive all the way to the screen.
- **The active run is `scope='year'`.** Deliberate, and the schema permits it. Anything assuming
  "active ⇒ `scope='live'`" is wrong.
- **The window and the prices disagree by design.** Anchors from 2025, prices through 2026-08.
  Not a bug to hide — a fact to display.

## Out of scope this pass

Tuning the model — D-2's `k` and `τ` stay provisional; P5 established there is no elbow to
read, and choosing final values is a report-writing decision. Also out: the live track and the
monthly rebuild, orchestration, foreign-flow data, loading the research tables or the nine
non-active artifacts, and deleting `_archive/`. `docs/01`–`04` remain the specification, and
where code disagrees the spec wins.

*Deployment was on this list and no longer is.* It became P8 — see the Revised line at the top.
What stays out is everything past a single hosted deployment: custom domains, CDN
configuration, staging environments, and any orchestration of the refresh.
