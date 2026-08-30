# P15 — Rebuild the deployment, and shrink what it serves

**Opened:** 2026-08-30. **Shape:** durable planned change (WORKFLOW §2) — schema migrations,
deletions, and a change of hosting topology.

## Why

The deployment is being rebuilt from nothing on clean infrastructure. Three provider facts,
checked directly on 2026-08-30 rather than read from a document:

- **Render** holds two live services (`srv-da29ai9t0dsc738v8t20` API on the free plan,
  `srv-da29ai9t0dsc738v8t5g` static site) still wired to the predecessor repository.
- **Netlify** holds **no project at all**. `netlify.toml` describes a site that has never existed.
- **Supabase** holds two projects: `dxklhenmyzdzitgnmuwc` (Sydney, ap-southeast-2) with 365k rows
  of the current data, and `qhbfjgheeyckefcwtmcq` (**Singapore**, ap-southeast-1) which is
  **completely empty**. The Singapore project is the target — Render's instance is in Singapore,
  so the Sydney hop on every query goes away.

**Who actually reads this: one person — the author, presenting.** Others look over their shoulder.
That is not a hedge, it is the sizing input: the thing to optimise is **the latency of one page
load**, not throughput. Everything in P15 that was originally scoped for concurrency has been cut.

Measured, and each one damages exactly that:

| Problem | Measurement | What it costs when presenting |
|---|---|---|
| Free plan sleeps after ~15 min | ~50 s spin-up | Opening the link in front of a committee means a minute of nothing |
| No gzip on the API | `/api/tickers/{t}/indicators` ≈ **400 KB of JSON** | Plainly slow over the Vietnam→Singapore path |
| Database in Sydney, API in Singapore | one extra leg per query | ~450 ms per request at steady state |

And one thing that blocks the rebuild itself: **writing to Supabase takes ~10 hours**, because
`pipelines/common/upsert.py` submits through `executemany` — one round trip per row.

## The sizing that decides most of this

| Tier | Tables | Rows | Size | Reproducible? |
|---|---|---|---|---|
| 1. Source of record | `daily_bars`, `market_index_bars`, `stocks`, `trading_calendar`, `universe_*` | 123k | 32 MB | **No** — only by refetching from a provider who may answer differently |
| 2. Frozen output | `model_*` (6 tables) | 1.1k | 4 MB | **Must not be** — `docs/04` §5 forbids a request path reaching greedy |
| 3. Derived | `daily_returns`, `index_returns`, `technical_indicators_daily` | 243k | 112 MB | **Yes** — a pure function of tier 1 |

Tier 3 is 67% of the rows and 76% of the bytes and carries no information tier 1 does not already
have. Expected after P15: **159 MB → ~17 MB**.

## Decisions

| # | Decision |
|---|---|
| 1 | Target the **Singapore** Supabase project, same region as the Render instance |
| 2 | The dashboard is a **Render Static Site**. One provider, one `render.yaml`. `netlify.toml` is deleted |
| 3 | **Drop 8 tables with no writer** — `00006_research` and `00007_live_monitors` |
| 4 | The 31 indicator columns become **`double precision`** |
| 5 | `daily_returns` / `index_returns` become **views**; `technical_indicators_daily` stays a table but is **labelled a cache** |
| 6 | The API moves to **Starter**. It buys *not sleeping*, not memory — measured RSS is 65–74 MB against a 512 MB limit on both plans |

Recorded as one decision record rather than four; see `docs/decisions/`.

## Progress

### Phase A — schema ✅
- [x] A1 `00006`, `00007` → `_archive/`; 8 names out of `REQUIRED_TABLES` in `pipelines/common/db.py`
- [x] A2 `00003_returns.sql` — two tables become two views
- [x] A3 `00004_indicators.sql` + `00013`'s `ADD COLUMN` — `numeric` → `double precision`, and a table comment saying it is a cache
- [x] A4 apply 11 migrations to Supabase Singapore **through a migration runner** — `schema_migrations` holds 11 rows
- [x] A5 `scripts/db/verify_schema.sql` — counts updated and **measured**, plus a gate that also fails on a withdrawn table being present

Two consequences A1 forced that were not in the plan, both recorded where they happened:

- **`v_active_group_health` lost seven columns.** It LEFT JOIN LATERALed onto
  `live_coverage_monitor`, so the view could not survive that table's withdrawal. The seven
  drift columns were NULL on every row forever — a permanent state dressed up by the LEFT JOIN
  as "no data yet". The group's real figures from `model_groups` remain.
- **`verify_schema.ps1` reads only the LAST result set.** Appending the withdrawn-table check
  as its own block would have silently retired the presence check. Both are now one gate block,
  and both files say why.

### Phase B — the write path ✅
- [x] B1 `pipelines/common/upsert.py` — `executemany` → `execute_values`, `page_size=500`
- [x] B2 load the data: universe sync → mirror → artifact load/activate → inspect against disk

B2 in detail: ran against the Singapore project once `DATABASE_URL`'s password (previously stale/
malformed in `.env`) was corrected. `universe.sync --sync`: 85 tickers, 85 members, all with
sector. `storage.mirror --run` landed `daily_bars` (121,014) and `market_index_bars` (1,424)
clean, then failed with `KeyError: 'ret_252d'` on `technical_indicators_daily` — the local
`data/processed/technical_indicators_daily` parquet copied in from `D:\DATN_new\data` predates the
`ret_252d` column (P13) and has no such key at all, not merely NULL in it. Recomputing instead of
mirroring closed it: `indicators.build --universe list_stocks_research.txt --storage pg` reads
prices back out of Postgres and writes fresh, `ret_252d` warm-up NULLs included (21,420/121,014,
consistent with the 252-row lookback) — 85/85 tickers, 121,014 rows. `artifact.load ae2010a4ad426`
then `artifact.activate ae2010a4ad426` landed clean; `artifact.inspect --from-db ae2010a4ad426`
reports disk and db field-for-field identical (`is_active` excepted, as expected). `v_active_model_run`
returns exactly one row, `model_runs` shows `ae2010a4ad426` both `is_active` and `is_primary`.

B1 in detail: each of the six `upsert_*` functions now has an `_..._SQL` (bare `VALUES %s`) and
an `_..._TEMPLATE` (the named-placeholder row, unchanged column order) instead of one string with
the placeholders inline. Three selftests needed matching changes, all still green:

- `pg.py --selftest` can no longer record through `cursor.executemany` (`execute_values` does its
  own mogrify/paginate dance that a fake cursor can't emulate), so the identity check now
  monkeypatches `upsert.execute_values` itself and asserts on `(sql, records, template,
  page_size)` — same invariants as before (SQL and template are upsert.py's own objects, records
  unmutated), plus a new one: `page_size == 500`.
- `localfs.py --selftest` assertion 1 now parses the `_TEMPLATE` constant for column order
  (`ON CONFLICT` / `EXCLUDED` stay in the `_SQL` constant, unchanged).
- `mirror.py`'s `MIRRORED` drops `DAILY_RETURNS`/`INDEX_RETURNS` — both are views as of A2, so
  there is nothing for the Postgres mirror to submit. `_FakeSink.write_daily_returns` /
  `write_index_returns` now raise, mirroring the existing D-14 guard on `write_raw_bars`, and a
  new selftest case (`P15: DAILY_RETURNS/INDEX_RETURNS are out of MIRRORED and the sink refuses
  them`) checks both the exclusion and the guard. `upsert_daily_returns` / `upsert_index_returns`
  stay in `upsert.py`, converted like the other four, purely for `BarSink` Protocol parity with
  `LocalSink` — nothing in the Postgres path calls them.

Verified: `pg`, `localfs`, `mirror` selftests green; `returns.build --mock`, `indicators.build
--selftest`, `common.db --check-schema-files` (the rest of CI's `pipelines` job) all still green;
`ruff check` clean on every touched file.

### Phase C — the read path ✅
- [x] C1 `GZipMiddleware`
- [x] C2 60-second in-process TTL cache + `Cache-Control`

C1: one `app.add_middleware(GZipMiddleware)` in `services/api/app/main.py`, default
`minimum_size=500`.

C2: the cache lives inside `fetch_all`/`fetch_one` in `services/api/app/db/connection.py`, keyed
on `(kind, sql, params)`, TTL 60 s via `time.monotonic()`. A hit returns a shallow copy (a caller
mutating its result — `tickers.py`'s not-found fallback does something adjacent — must never
poison the next hit). A `None` result from `fetch_one` is cached too (a real "no row" answer, not
a miss). A raised exception is never cached. Wired to `close_pool()`'s existing reset boundary
(production only calls it at shutdown; the test suite already calls it in every `setUp`/
`tearDown`, so tests got isolation for free instead of needing a second reset hook). Browser side
is a `Cache-Control: public, max-age=60` header from a small `@app.middleware("http")`, scoped to
`/api/*` GET 200s only — never `/health` (must always reflect live connectivity) and never an
error response.

Verified: 8 new tests in `test_runtime_guards.py` (`DbAndImportSafetyTests` — hit/miss, TTL
expiry, distinct params don't collide, `fetch_one(None)` is cacheable, a failed fetch is never
cached, `close_pool` clears it) and a new `services/api/tests/test_middleware.py` (5 tests: gzip
on/off by `Accept-Encoding`, `Cache-Control` present on `/api/*` 200s, absent on `/health` and on
a 503). Full `services/api` suite: 208/208 green (up from 196). `ruff check` clean.

### Phase D — deploy
- [x] D1 `render.yaml` declares both services; API on `starter`
- [x] D2 same-origin rewrite; `validateApiBaseUrl` accepts a root-relative base
- [x] D3 delete `netlify.toml`
- [~] D4 re-apply the Blueprint from this repository — **done**; deleting the two stale services from the predecessor repo is still open
- [ ] D5 delete the Sydney Supabase project — **only after Validation is green**; user has said to leave it alone for now regardless

D1–D3 in detail: `render.yaml` rewritten — `anchor-model-web` (Static Site) declared alongside
`anchor-model-api`, whose `plan` moved `free` → `starter`. Header rewritten to argue for one
provider instead of explaining why there was only one service. `netlify.toml` deleted
(`git rm`). Stale Netlify-as-current-reality claims fixed in `README.md`, `AGENTS.md`, and
`.github/workflows/ci.yml`'s "no deploy step" note; `ALLOWED_ORIGIN_REGEX`'s Netlify-preview
example in `runtime_guards.py`/its tests left alone — out of scope, and the mechanism itself is
provider-agnostic.

D2: `apps/web/src/lib/api.ts`'s `validateApiBaseUrl` now accepts a value starting with `/`,
normalized to `""` (same origin) — the empty-string branch above it is untouched, so an *unset*
value still fails closed as `api_not_configured`. `joinApiUrl("", "/api/x")` already returned
`"/api/x"` and needed no change. 4 new tests in `apps/web/tests/apiConfig.test.ts`; the one
pre-existing test asserting `/api` was *rejected* was flipped to match the new, intended
behaviour (`ok: true, baseUrl: ""`).

D4/D5 are live, destructive infrastructure actions (deleting running services, deleting a
Supabase project with 365k rows) and are **not** taken without the user driving or explicitly
confirming each one, regardless of this file's authorization — see the assistant's own safety
rules on destructive/hard-to-reverse actions.

D4 in practice: the user created the Blueprint directly through the Render dashboard rather than
via CLI. Render appended `-lrgg` to **both** service names — `anchor-model-api`/`anchor-model-web`
were already taken by another Render account — so the live hosts are
`anchor-model-api-lrgg.onrender.com` / `anchor-model-web-lrgg.onrender.com`, not the names
`render.yaml` assumed. Two values needed correcting once the real hostnames were known:
`ALLOWED_ORIGINS` on `anchor-model-api` (set in the Render dashboard, `sync: false` so not in
git) and the static site's `routes[0].destination` in `render.yaml` itself, which was hardcoded to
the un-suffixed API host. The second is now fixed in git; the first the user set directly in the
dashboard. The two stale services from the predecessor repo (`srv-da29ai9t0dsc738v8t20`,
`srv-da29ai9t0dsc738v8t5g`) have not been touched.

### Docs
- [x] `docs/RUNBOOK.md` — drop the returns build step, drop the ten-hour warning, replace "applied by hand"
- [x] `render.yaml` header — it currently argues for one service
- [x] one decision record for the whole reshape

`docs/RUNBOOK.md`: §1 rewritten around the real `apply_migration` sequence (11 files,
`schema_migrations` now 11 rows); §3.1's counts updated to P15's (17 tables, 13 views, etc.);
§3.4 (Returns) replaced with a withdrawal stub explaining the tables are now views, numbering
left as a gap rather than renumbered (two other docs cite `§3.5`/`§3.6` by number); §3.5's
ten-hour `executemany` warning rewritten now that B1 landed; Known gaps §5 lost the two entries
this closed. `docs/plans/completed/p13-market-home-redesign.md` got a short closing note where it
had flagged `execute_values` as "the obvious follow-up... not done" — now done.

One decision record, [D-31](../../decisions/D-31-single-provider-and-derived-storage.md),
bundles all three: the provider consolidation (supersedes D-30), the data-tier reshape (views,
dropped tables, `double precision`), and the baseline-migration-edited-in-place justification.
`docs/decisions/README.md` updated.

## Validation

Nothing below is reported as passing until it has actually run.

| # | Check | How | Status |
|---|---|---|---|
| 1 | CI's four jobs green | `.github/workflows/ci.yml` | **PASSED locally** — every command each job runs was executed directly (not yet through GitHub Actions itself): `ruff check .` + `check_locks.py`; `unittest discover` on `services/api/tests` (208/208); `next lint` + `npm run test` (61/61) + `next build` on `apps/web`; all 18 `pipelines` self-checks |
| 2 | The storage seam's selftests still pin `execute_values` | `storage.pg`, `storage.localfs`, `storage.mirror` — `--selftest` | **PASSED** — 11/12/6 checks, plus `returns.build --mock`, `indicators.build --selftest`, `common.db --check-schema-files` (rest of CI's `pipelines` job) |
| 3 | **The returns views match the old tables row for row** | cross-check against the Sydney database: `log_return`, `at_limit`, `zero_volume`, and a count of **120,929** | **PASSED with one qualification** — see below |
| 4 | The schema has the right shape | `verify_schema.ps1` — 17 tables, 13 views, every view **executed** rather than merely parsed | **PASSED on Supabase** — 17 / 13, all 13 views executed. Not yet run against the local container |
| 5 | The migrations are recorded | `schema_migrations` holds **11** rows | **PASSED** — 11 rows |
| 5b | The D-20 boundary holds on the new project | `has_schema_privilege('anon','public','USAGE')` and anon-readable relation count | **PASSED** — `false` and `0` |
| 6 | The artifact matches disk | `artifact.inspect --from-db ae2010a4ad426` — field for field, `P` exact | **PASSED** |
| 7 | `v_active_model_run` returns **exactly one** row | direct SQL | **PASSED** — 1 row, `ae2010a4ad426` `is_active`/`is_primary` both true |
| 8 | Batched writes are genuinely faster | time `mirror --run`; record the number | **PASSED** — `indicators.build --storage pg` (85 tickers, 121,014 rows via `execute_values`) ran end-to-end in **~5.5 minutes** (02:10:58–02:16:31), against the ~10 hour projection for `executemany` |
| 9 | The API is alive | `curl https://<api>/health` → `"database": "ok"` | **PASSED** — `anchor-model-api-lrgg.onrender.com/health` → `{"status":"ok","database":"ok",...}` |
| 10 | The three P13 routes answer | `/api/market/index-history?range=1m`, `/movers?horizon=1y`, `/liquidity?limit=5` | **PASSED** — all three answered with real rows; `movers` showed non-null `ret_252d` (e.g. `2.448276`), confirming the B2 backfill landed |
| 11 | The same-origin rewrite works | DevTools: the request goes to the site's own origin, with **no** preflight OPTIONS | **PASSED** — `anchor-model-web-lrgg.onrender.com/api/market/liquidity?limit=1` returned 200 with real data through the static site's rewrite, once `render.yaml`'s `destination` was corrected from the assumed `anchor-model-api.onrender.com` to the actual assigned `anchor-model-api-lrgg.onrender.com` (Render appended `-lrgg` to both service names — the bare names were already taken) |
| 12 | gzip is on | `content-encoding: gzip` on `/indicators`; sizes before and after | **PASSED** — `Accept-Encoding: gzip` → `Content-Encoding: gzip` present; `Accept-Encoding: identity` → absent, correctly negotiated. `Cache-Control: public, max-age=60` present on both; absent on `/health` |
| 13 | **No cold start** | leave it 30 minutes and open it again — Starter must not sleep. The row that matters most for a defence | not attempted — needs a genuine 30-minute idle gap with no traffic, which this session's repeated polling hasn't produced |
| 14 | The page's figures reconcile | `/` against a direct query of `v_market_overview`; `v_sector_performance` must sum to it | **PASSED** — `/api/market/overview` field-for-field equal to `v_market_overview` (turnover 8,352,129,774; volume 272,811,000; 85 tickers; advancers/decliners/unchanged 32/41/12); `sum(v_sector_performance)` reconciles exactly to the same three totals |

### Row 3, in full — the qualification matters more than the pass

Run against the Sydney database, which holds both `daily_bars` and the old `daily_returns` table:

|  | `daily_returns` | `index_returns` |
|---|---|---|
| row count | 120,929 == 120,929 | 1,423 == 1,423 |
| key mismatches | 0 | 0 |
| `prev_close` differences | 0 | 0 |
| `at_limit` / `zero_volume` differences | 0 / 0 | n/a |
| `log_return` not bit-equal | **543 (0.45%)**, max 1.39e-17 | **3 (0.2%)**, max 6.94e-18 |

Every difference is exactly 1 ULP, and the cause was isolated rather than guessed. For
`close=6.6, prev_close=6.54` the stored value is `0x3f82b40d31e2548c`, the view gives `...548b`,
and Python on the author's Windows machine gives `...548c`. The inputs and the division are
identical; `log()` differs between libm builds, which IEEE-754 permits.

**So the view did not introduce a divergence — the table concealed one.** It froze one machine's
libm answer, and re-running the pipeline on Linux would have moved those same 543 rows. Nothing
the system uses is on that path: no route reads either relation, artifacts are loaded from disk
rather than retrained, and the documented train track reads parquet written by the same Python
that computed it.

**The first draft of `00003`'s header claimed bit-for-bit agreement. That claim was false and has
been replaced by this measurement** — the reason the check was run before anything depended on it.

### `prev_close` was nearly wrong, and the zero in that row is the evidence

The plan's draft SQL read `lag(close)` over unfiltered rows. `compute_return_rows` carries
`prev_close` forward across an unusable close (`if c is not None: prev_close = c`), so it is the
last **valid** close, not the previous **row's**. The filter therefore has to sit inside the
subquery, before the window. The two forms differ exactly when a bad close sits between two good
ones — and `prev_close differences: 0` is what says the fix landed.

## Known risks

**A rewrite to an external host on Render Static is not verified here.** D2 keeps `ALLOWED_ORIGINS`
configured as the fallback, and row 11 is where the rewrite is proved or disproved.

**`execute_values` changes the shape of the SQL** — named placeholders become a `VALUES %s`
template. `storage/pg.py --selftest` compares the SQL object by **identity**, so it catches a
copied-and-edited constant but not a logic error inside the template. Row 3 is what catches that,
and it must run **before the Sydney project is deleted**.

**Editing the baseline migrations in place is a door that opens once.** It is defensible only
because `supabase_migrations.schema_migrations` is empty on both projects — there is no recorded
history to preserve. Once A4 has run, every further change is a new migration.
