# P8 execution plan — publish the dashboard on Render

> ## CLOSED — moved to `completed/` on 2026-08-29 (P12/F5)
>
> **Closed by:** the blueprint is applied and both services are live —
> `anchor-model-api` and `anchor-model-web` on Render (Singapore), reading Supabase
> (ap-southeast-2) through the session pooler.
>
> **The four validation rows that stood at `not attempted` were run for real on 2026-08-28/29
> and now carry their results** — rows 8 (deployed `/health`), 9 (CORS admits the site's origin
> and no other), 10 (the deployed page's figures reconciled field-by-field against a direct
> `v_market_overview` query) and 11 (cold start). Row 11 is a **FAIL**, recorded as measured
> rather than softened; see the row for what it means and why it is a consequence of D-21's
> free-tier choice rather than a defect.
>
> Six unticked boxes remain below and are left unticked.

---


**Started:** 2026-08-18
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md` — this file is the executable detail of its P8 section.
Progress and Validation are maintained **here**; the parent's P8 checkboxes track completion.
**Predecessor:** `p7-indicators.md` — DONE, verified on Supabase (commits `86420f3`, `a0ed300`,
`4fc61c7`)

---

## Why

P0–P7 produced a complete, verified system that **nobody can reach**. Supabase holds 121,014
daily bars, 121,014 indicator rows, 85 tickers with sectors, the active run `ae2010a4ad426`
(2025, `pearson_rho2`, k=10, τ=0.10), and nine working views. The read path was proven and then
locked down: after D-20, `postgres` over `DATABASE_URL` is the only way in.

Everything still runs on one Windows laptop. The thesis needs a URL.

P8 puts the system on Render and keeps it awake. It is **not** the refresh runbook, not
Airflow, and not a data-refresh pipeline — that was the old P8, renumbered to P11 by S1 below.

### Two facts that shape the scope

1. **`services/api` has no data routes.** `create_app()` includes exactly one router, `/health`
   (`app/main.py:54`). The twelve read routes are P9.
2. **`apps/web` fetches a dead contract.** All 15 fetchers in `src/lib/api.ts` target Leiden
   endpoints (`/api/clusters/latest`, `/api/tickers/{t}/lead-lag`) that the API does not
   implement and never will. The rewrite is P10.

So "the dashboard shows data from Supabase" cannot be met by deployment alone. P8 therefore
carries a **thin vertical slice** — three real routes and one rewritten screen — chosen to
exercise the whole path (Supabase view → psycopg2 → FastAPI → CORS → browser) without absorbing
P9 and P10 wholesale.

**Definition of done.**

- FastAPI runs on Render as a Web Service, boots with `ENV=production` guards satisfied, and
  reads Supabase.
- Next.js is published as a Render Static Site and calls the deployed API.
- CORS: the API returns `access-control-allow-origin` for the static site's origin and for no
  other.
- UptimeRobot keeps the API service from spinning down; a request after 20 minutes idle is not
  a cold start.
- The deployed `/` renders **live Supabase figures** — market KPIs, top movers, and the run's
  provenance strip.

---

## Decisions taken

| # | Decision | Reasoning |
|---|---|---|
| S1 | **Renumber.** Deployment takes the P8 slot; the one-shot refresh runbook moves to **P11**, after P9 and P10 | The parent plan's phase map (line 7) and its "deployment beyond local" exclusion (line 357) both need amending. D-20's justification for migration `00011` cites "P8's runbook" and needs the same correction — the argument survives the renumber, the number does not |
| S2 | **Thin vertical slice, not full P9+P10.** Three routes: `/api/model/active`, `/api/market/overview`, `/api/market/movers`. One screen: `/` | These three cover every shape the remaining nine will need — a single-row view, an aggregate view, and a parameterised list. If they work deployed, P9 is mechanical |
| S3 | **Web ships as a Render Static Site** (`output: 'export'`), not a Web Service | Static Sites are free and **never spin down**, so the page always paints instantly and only its data can be slow; a Web Service serving the same files would make a visitor wait ~1 min for the HTML itself after an idle period. Every screen is already `"use client"`, so nothing is lost. *(An earlier draft rested this on instance-hours — see the correction below.)* |
| S4 | **`render.yaml` Blueprint**, not hand-clicked dashboard services | The same argument D-20 made for `00011` being a migration: hand-made state is not reproducible, and a thesis defence should be able to rebuild the deployment from the repository |
| S5 | **A lean API dependency manifest.** `services/api` stops installing the full `requirements.lock` | The current shim pulls vnstock, matplotlib, seaborn, wordcloud, pillow and openpyxl into a service that imports fastapi, uvicorn, pydantic-settings and psycopg2. On a free-tier build that is minutes of wasted time and real disk pressure |
| S6 | **Connect through the Supabase pooler, never the direct host** | Supabase's direct `db.<ref>.supabase.co` endpoint is IPv6-only; Render egress cannot be assumed to be. The pooler is IPv4 and is already what `.env` uses |
| S7 | **Session pooler (5432), not transaction pooler (6543)** | `app/db/connection.py` calls `conn.set_session(readonly=True)`, which issues `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`. Under transaction pooling that either errors or leaks to another client. Read-only enforcement is worth more than the pooler's connection ceiling at this traffic level |
| S8 | **Archive the dead Leiden screens now**, ahead of P10's schedule | Two of them (`/clusters/[cluster_id]`, `/tickers/[ticker]`) are dynamic routes that `output: 'export'` cannot build from client components, and the rest would publish visibly broken pages on a public URL. Move to `_archive/`, per `AGENTS.md`, rather than delete |

### Decision records this phase writes

- **D-18 — API surface** (currently OPEN). P8 lands the first three routes, so the principle
  must be recorded now: FastAPI over the views, GET-only, the `{"error": {...}}` envelope, no
  PostgREST from the browser. The full route table is completed in P9; the record says so.
- **D-21 — deployment topology.** Render Blueprint; API as Web Service, web as Static Site; the
  instance-hour arithmetic behind S3; UptimeRobot as keep-alive rather than alerting; D-20's
  standing rule that the service-role key never reaches `apps/web`.
- **D-22 — split API dependency manifest.** Records S5 and the fact that it contradicts the
  "one venv serves either role" note currently in `services/api/requirements.txt`.

---

## Progress

### P8.0 — Renumber and record — **DONE**

- [x] Amend `anchor-model-operations.md`: scope line, the *What changed and why* row, the P8
      section moved to **P11** and placed after P10, the Validation table's P8 row, and the
      "deployment beyond local" exclusion
- [x] Insert the new P8 section (deployment) into the parent plan, pointing here
- [x] Amend `D-20`'s "Why a migration rather than a fix in the dashboard" — it cited *P8's*
      runbook, which is now P11's. Its `Related:` line also called D-18 OPEN; corrected
- [x] Correct the two stale deployment claims: `services/api/README.md` said "deployed to AWS
      EC2", `apps/web/README.md` said "deployed to Vercel". Both were ClusterWeb residue. While
      there, both configuration tables were wrong by omission and were completed — the API's
      listed only `DATABASE_URL` (not `ENV`, `ALLOWED_ORIGINS`, `API_DEV_FIXTURES`, all of which
      gate startup), and the web's claimed a missing base URL "shows mock data", which is false
      for every deployed build
- [x] Write D-18, D-21, D-22 in `docs/decisions/`, and update `docs/decisions/README.md`

D-18 was the register's only OPEN entry; it is now closed. D-21 carries two items marked **to
confirm** rather than asserted — Render's free instance-hour allowance, and whether `fromService`
resolves a static site's URL — because both are provider terms and P8.4 is where they get
checked.

### P8.1 — Lean API dependency manifest (S5, D-22) — **DONE**

- [x] New `requirements-api.in` holding only the four direct API dependencies already grouped
      under the `# --- API (services/api/app) ---` header in `requirements.in:15`
- [x] Compile `requirements-api.lock` **authoritatively in a disposable `python:3.13-slim` Linux
      container** (resolved 3.13.15), exactly as `requirements.lock`'s header mandates and as
      P6.0 did. **21 pins against the root lock's 54**; none of vnstock, pandas, numpy,
      matplotlib, seaborn, wordcloud, pillow, openpyxl
- [x] Repoint `services/api/requirements.txt` at the new lock; replace the shim comment with the
      D-22 reference
- [x] Add `services/api/.python-version` (3.13.13, matching the repo root) — Render's root
      directory is `services/api`, so the repo-root file is out of its view

#### One thing the first compile got wrong, and the flag that fixes it

Compiled without a constraint, the resolver took the newest release satisfying
`requirements-api.in` and produced **starlette 1.6.0 / uvicorn 0.52.3 / pydantic-settings
2.15.0** against the root lock's **1.3.1 / 0.51.0 / 2.14.2**. That is a deployment running a
different FastAPI stack than local development, with nothing anywhere to surface the difference.

Recompiled under `--constraint requirements.lock`, the lock is now a **strict subset of the root
lock, version for version** — verified mechanically: 21/21 pins present in `requirements.lock`
at identical versions, 0 mismatches. The only thing that can now drift between the two manifests
is the package *list* in `requirements-api.in`, which is four lines.

The flag is therefore not optional, and the regeneration command in `requirements-api.lock`'s
header carries it.

#### Dangling citations, fixed while here

`requirements.in` cited `docs/deployment/PYTHON_RUNTIME.md` three times and
`services/api/requirements.txt` once more, for the lock-regeneration procedure. **That file has
never existed** — it is one of the phantom paths in `docs/00-project-status.md` §5. The
citations now point at the lock headers, which actually carry the command.

### P8.2 — The three read routes (S2, D-18)

All three read **views only**, through the existing `fetch_one` / `fetch_all` / `as_float` /
`iso_date` helpers in `services/api/app/db/connection.py`. No new DB access layer, no ORM, and
no import from `pipelines.*`.

| Route | View | Shape |
|---|---|---|
| `GET /api/model/active` | `v_active_model_run` | Single object. `NoData` → 503 if the view returns zero rows (no active run) |
| `GET /api/market/overview` | `v_market_overview` | Single object. The view always returns exactly one row |
| `GET /api/market/movers?direction=up\|down&limit=10` | `v_top_movers` | List. **The view is deliberately unordered and unlimited** — ordering by `ret_1d` and applying the limit is this route's job |

- [x] `services/api/app/routes/model.py` and `services/api/app/routes/market.py`; both registered
      in `create_app()` alongside `health_router`
- [x] Validate `direction` and `limit` through FastAPI query params so a bad value yields the
      400 envelope from `_errors.py`, not a 500
- [x] **`numeric` → `float`, never `Decimal`.** psycopg2 returns `Decimal` for the scalar
      columns; `as_float` exists for exactly this. The same rule `PostgresSource` already holds
- [x] **NULL survives to the wire.** Ratios are fractions (`0.07` = +7%) per the view contract;
      formatting belongs at the display edge. A NULL indicator is not zero
- [x] `services/api/tests/test_routes.py` — same stdlib-`unittest`, dependency-free style as
      `test_runtime_guards.py`, reusing its ASGI harness pattern with a query string added

#### Four things settled in code

**`_RATIO_DIGITS = 6` everywhere a fraction is serialised.** `as_float`'s 3-decimal default is
0.1% granularity on a return — `coverage_fbar` 0.262929 would have become 0.263, and `ret_1d`
−0.032787 would have become −0.033. The default is right for prices and wrong for ratios.

**Share counts stay integers.** `sum()` over `bigint` returns `numeric`, so psycopg2 yields
`Decimal`; a local `_as_int` keeps `total_volume` exact instead of emitting `2.72811e8`.

**Ordering is explicit on both axes.** Postgres defaults `DESC` to NULLS **FIRST**, which would
have put return-less tickers at the top of the gainers table, so both directions say
`NULLS LAST`; `ticker ASC` breaks ties so the same data always yields the same response.
`direction` is a `Literal` mapped to a constant `ORDER BY` fragment — the query value is never
interpolated into SQL, and `limit` is a bound parameter.

**Emptiness is detected on the value, not the row count.** `v_market_overview`'s aggregates are
scalar subqueries, so it returns one row even against an empty `daily_bars` — with a NULL
`session_date`. Checking `fetch_one(...) is None` alone would have served a row of zeros as if
it were a quiet trading day.

Live figures, `ENV=production` against Supabase: active run `ae2010a4ad426` (2025,
`pearson_rho2`, k=10, τ=0.10, F̄=0.262929, 33 under τ); session 2026-08-18 with 85 tickers,
32 advancers / 41 decliners / 12 unchanged, turnover 8,352,129,774, VNINDEX 1732.02 (+0.264%).

**`window_end` is 2025-12-31 and `latest_session` is 2026-08-18.** The endpoint returns both, in
one round trip, because that eight-month gap is the thing `docs/04` §5 requires on screen.

### P8.3 — Static export and the `/` rewrite (S3, S8) — **DONE**

- [x] `next.config.ts` — was empty. Now `output: 'export'` + `trailingSlash: true` so a deep
      link resolves to `<route>/index.html` on a static host
- [x] Pin Node: `engines` in `package.json` plus `apps/web/.node-version` (was unpinned anywhere
      in the repo). Built locally on Node 22.23.1
- [x] Archived to `_archive/p8-leiden-screens/`: `/clusters`, `/clusters/[cluster_id]`,
      `/tickers/[ticker]`, `/universe`, `/methodology`, `/pipeline`, the component directories
      only they used (`clusters/`, `cluster-detail/`, `ticker-detail/`, `methodology/`,
      `pipeline/`, `overview/`) and the three Leiden charts. `/` is the only route left
- [x] `AppChrome` nav reduced to the surviving route; also normalises the trailing slash that
      `trailingSlash: true` now adds to every path, which would otherwise miss the meta lookup
- [x] `lib/api.ts` trimmed to three fetchers + `/health`, `lib/mock.ts` to matching fixtures.
      `classifyRuntimeMode` / `validateApiBaseUrl` / `resolveApiConfig` / `useAsyncResource`
      kept verbatim
- [x] `src/app/page.tsx` rewritten; new `components/market/` (three components, a formatter, and
      a scoped CSS module rather than additions to the 3,589-line `globals.css`):
  - **Provenance strip** from `/api/model/active` — `window_start`, `window_end`, `n_tickers`,
    `k`, `tau`, `coverage_fbar`, plus the latest bar date. `docs/04` §5 requires this on screen,
    and the gap it exposes is real and deliberate: **anchors estimated on 2025, prices through
    2026-08.** Say it; do not hide it
  - **KPI row** from `/api/market/overview` — session date, n tickers, total turnover, total
    volume, advancers / decliners / unchanged, VNINDEX close and % change. No foreign-flow cards
    (parent plan S4, D-19)
  - **Top movers table** from `/api/market/movers` — mã, tên công ty, ngành, KL GD, GT GD, %
- [x] `next build` emits `apps/web/out/` (already covered by the repo's `out/` gitignore rule)

**Not in P8:** the sector treemap (needs `/api/market/sectors`, a P9 route), `/tickers`,
`/anchors`, the combined indicator chart, and the rewritten `/methodology` and `/pipeline`.

**Carried to P10, deliberately not touched here:** roughly 2,000 of `globals.css`'s 3,589 lines
are now dead — the `clusters-`, `cluster-detail-`, `universe-`, lead-lag and outcome blocks
belong to screens that no longer exist, and they ship to the browser on every page load. The new
screen uses a scoped module precisely so this could be left alone: bulk-deleting CSS while
also rewriting the data layer and the deployment would have made a build failure hard to
attribute. It is a size problem, not a correctness one.

#### Three things this phase surfaced

**`PriceHistoryChart` was not data-agnostic, despite its own docstring.** It imported `OhlcvBar`
from `@/lib/api`, so rewriting the API contract broke a presentational primitive for reasons
having nothing to do with charts — the build caught it. It now declares the three fields it
actually reads (`date`, `close`, `volume`) as a local `PriceBar`. TypeScript is structural, so
P9's richer history row satisfies it without a cast.

**Display precision can undo wire precision.** P8.2 was careful to serialise ratios at six
decimals; the first render then put F̄(S) on screen as `0,26` through a two-decimal formatter.
Across the five research years F̄ spans ~0.2235–0.2632, so two decimals cannot distinguish two
different years' runs. `formatDecimal` now takes an explicit width and the coverage figure uses
four. Caught by looking at the rendered page, not by any test.

**The turnover unit was undeclared. It is now confirmed: `close` is in nghìn đồng.**
`turnover_value` is `close * volume` (`00004_indicators.sql:54`), so it inherits that unit —
nghìn đồng, not đồng. Nothing in the schema or the specs says so; the first pass therefore
refused to guess and labelled the card *"theo đơn vị nguồn"*, which was literally true and
useless. **The project owner confirmed the unit**, and the display now converts:

| Field | Stored unit | Displayed as |
|---|---|---|
| `total_turnover`, `turnover_value` | nghìn đồng | **tỷ đồng** (÷ 1e6) |
| `close_price` | nghìn đồng | nghìn đồng, labelled |
| `volume`, `total_volume` | cổ phiếu | cổ phiếu |
| `index_close` | **index points** | unchanged — **must never be scaled** |

The conversion lives in one function, `formatTurnoverTy` in `components/market/format.ts`, with
the whole unit chain written into its docstring, so there is exactly one place it can be wrong.
`index_close` is the trap worth naming: it sits in the same KPI row and is the most recognisable
number on the page, but it is an index level with no currency unit, and running it through the
same helper would be a units error nobody would question.

Live check after the change: 8.352.129.774 nghìn đồng → **8.352,13 tỷ đồng**; PLX 203,07 tỷ;
GAS 303,60 tỷ; VNINDEX still 1.732,02. Magnitudes are plausible for 85 HOSE names.

**This fact belongs in `docs/01-data-pipeline.md`** — it is a property of the price series, not
of the dashboard, and the next reader of `turnover_value` will ask the same question. Not done
here; P9's ticker routes are the natural point.

### P8.4 — Render blueprint and first deploy (S4, D-21) — **blueprint written; deploy is the account holder's step**

- [x] `render.yaml` written at the repository root, declaring two services
- [ ] Apply the blueprint on Render and complete the two-pass deploy (needs the Render account)

#### Both "verify before assuming" items came back — and one changed the design

Render's own documentation was read while writing the blueprint rather than inferred from
memory:

**The instance-hour figures are confirmed, but they are not the argument — correction.** 750
free instance hours per workspace per month; free Web Services spin down after 15 minutes idle;
Static Sites neither spin down nor consume those hours. All accurate. But an earlier draft of
S3 and D-21 concluded from them that "two always-on Web Services cannot fit, therefore the
static site", and **that conclusion did not apply to this project**: the dashboard is not run
continuously. It is switched on and pinged when it needs to be reachable, and otherwise left to
spin down, so the ceiling was never binding.

S3 stands on the cold-start argument instead, which is the real user-visible difference. The
hours remain worth knowing only if this ever becomes always-on — one awake service (~730 h)
fits, two do not.

**`fromService` cannot close the CORS/API-URL loop.** Its supported properties are `host`,
`port`, `hostport`, `connectionString`, `connectionPoolString`, `user`, `password`, `database`
— none yields a `https://…` origin for a web or static service (`connectionString` is a
database URL). A bare `host` fails `runtime_guards._normalize_origin`, which requires a scheme.
So the two-pass deploy is **the** method, not a fallback, and it is written into `render.yaml`
as an ordered procedure with the reason attached.

**`region: singapore`** — the Supabase project is `aws-0-ap-southeast-2` (Sydney) and Render has
no Australian region. Of `oregon` (default), `ohio`, `virginia`, `frankfurt`, `singapore`,
Singapore is nearest to both the database and the readers; the default would have sent every
query across the Pacific twice.

**Expect the first pass to fail.** The API cannot boot until `ALLOWED_ORIGINS` names the site,
and the site does not exist until the blueprint is applied. That failure is the production guard
working, not a misconfiguration.

Reference — the two services as declared:

| | API | Web |
|---|---|---|
| Type | `web` (Python) | `static` |
| Root directory | `services/api` | `apps/web` |
| Build | `pip install -r requirements.txt` | `npm ci && npm run build` |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | — |
| Publish | — | `out` |
| Health check | `/health` | — |
| Region | closest to Supabase `ap-southeast-2` (Sydney) that the free plan offers — **verify availability before assuming Singapore** | — |

  The start command carries a hard constraint: `main.py` imports `from app.health import …`,
  not `from services.api.app…`, so **cwd must be `services/api`**. The root-directory setting is
  what supplies that; changing it breaks the import with no other symptom.

- [ ] Environment variables:

| Variable | Service | Value | Notes |
|---|---|---|---|
| `ENV` | API | `production` | Arms every guard in `runtime_guards.py` |
| `DATABASE_URL` | API | Supabase **session pooler**, port 5432 | **Secret. `sync: false` in the blueprint — never committed.** Contains the `postgres` password |
| `ALLOWED_ORIGINS` | API | the static site's origin | Comma-separated. `resolve_runtime` refuses to boot in production if this is empty |
| `API_DEV_FIXTURES` | API | unset | Any truthy value is a fatal startup error in production — this is intended |
| `NEXT_PUBLIC_API_BASE_URL` | Web | the API service's URL | **Build-time.** Next inlines it into the bundle; setting it after the build does nothing |

- [ ] Resolve the circular reference between the last two rows. Preferred: `fromService`
      property references in the blueprint so Render resolves both hostnames itself. **Verify
      `fromService` supports a static site's URL**; if it does not, fall back to a documented
      two-pass deploy (API first → note its URL → configure and deploy the site → set
      `ALLOWED_ORIGINS` → redeploy the API) and record that in D-21, not in a comment
- [ ] First deploy; capture both build logs

### P8.6 — What the public repository carries (D-23) — **DONE**

Added after the first review: P8 is the first phase whose output leaves this machine, and the
GitHub repository is public.

- [x] `docs/` and `_archive/` gitignored; `git rm -r --cached` on both, since they were tracked
      (`_archive/` was already ignored **by rule** — `git mv` into an ignored directory still
      stages the move, so 59 files sat in the index regardless)
- [x] `pipelines/`, `supabase/migrations/`, `services/api/`, `apps/web/`, `scripts/` and
      `data/artifacts/` + `data/research/` stay published — deleting the model, the schema and
      the study's results from version control to tidy a deployment would be the wrong trade,
      and `AGENTS.md` requires those artifacts be "citable and reproducible from the repo alone"
- [x] `AGENTS.md` carries a note that `docs/` is unpublished and that the `docs/` citations
      throughout the tracked files will not resolve in a public clone — left in place
      deliberately, because a reference a reader cannot follow beats a claim with no reason
- [x] Publishable tree scanned for secrets: the Supabase project ref appears **nowhere**; every
      connection-string hit is a fake test fixture or the local container password

Worth recording plainly: **removing files does not help Render.** It clones the whole repo and
runs only the declared build commands inside the declared root directories, so `docs/` and
`_archive/` cost nothing there. The change is justified by the repository being public, and by
nothing else.

### P8.5 — Uptime monitoring and end-to-end verification

- [ ] UptimeRobot HTTP(s) monitor on `https://<api>.onrender.com/health`, 5-minute interval
      (Render free spins down after ~15 minutes idle; UptimeRobot free floors at 5 minutes)
- [ ] No monitor on the static site — it never sleeps, so the page always paints and only its
      data can be waiting

**The ping is switched on when the system needs to be reachable, not left running by default.**
This is a thesis artefact, not a service with users: between demonstrations the API is allowed
to spin down, and the first request after that pays a spin-up of roughly a minute. Enabling the
monitor ahead of a demonstration is what removes that wait. Nothing about the deployment assumes
continuous operation, and D-21 records why the instance-hour ceiling is therefore not the
argument for anything here.

---

## Validation

Same idiom as P0–P7. `not attempted` until actually run — and per `docs/WORKFLOW.md`, "the check
is X, and X is not runnable yet" is an acceptable answer.

| # | Check | Status |
|---|---|---|
| 1 | `requirements-api.lock` compiled in a `python:3.13-slim` container; a clean venv from it imports `app.main` with no vnstock/matplotlib present | **PASS** — 22 packages installed (21 pins + pip); `app.main` imports, `Anchor Model API 0.2.0`; all eight heavy packages report unimportable. Also served for real: `uvicorn app.main:app` → `GET /health` 200 with the documented four-key body, and CORS returned `access-control-allow-origin` for `http://localhost:3000` and **nothing** for an unrelated origin |
| 2 | `test_runtime_guards` still passes at its existing count after the route additions | **PASS** — 64/64, unchanged. Plus `test_routes.py` 12/12 new |
| 3 | Locally, `ENV=production` + real `DATABASE_URL` + `ALLOWED_ORIGINS`: the app boots, and all three routes return non-empty live data | **PASS** — all three 200 with live figures. Movers reconciled against an **independent** `ORDER BY ret_1d ASC, ticker ASC` query: DXG −0.039130, TCH −0.032787, DIG −0.031963, same three in the same order |
| 4 | Locally, `ENV=production` with `ALLOWED_ORIGINS` blank: startup **fails** with `RuntimeConfigError` — the guard is proven armed, not assumed | **PASS** — and extended to all three guards: blank `ALLOWED_ORIGINS`, blank `DATABASE_URL`, and `API_DEV_FIXTURES=true` each refuse to construct the app |
| 5 | Every numeric field in the three responses serialises as a JSON number, never a `Decimal` string; NULL indicator fields serialise as `null`, never `0` | **PASS** — asserted at 6-decimal width (the 3-decimal default would round `coverage_fbar` 0.262929 → 0.263); `total_volume` stays `int`; a NULL index half and a NULL `ret_5d` both serialise `null` |
| 6 | `/api/market/movers?direction=down&limit=10` returns rows sorted ascending by `ret_1d`; `direction=sideways` returns the 400 envelope | **PASS** — `direction=sideways`, `limit=0`, `limit=101`, `limit=abc` all return 400 `invalid_params`, and the invalid direction is proven never to reach the SQL string |
| 7 | `npm run build` emits `apps/web/out/` with the surviving routes prerendered; no dynamic-route export error | **PASS** — `/` and `/_not-found` exported, 108 kB first load; `next lint` clean. Went further than the check asked: served `out/` locally against the API running with `ENV=production` against **live Supabase**, and the page rendered real figures (F̄ 0,2629, session 18/08/2026, VNINDEX 1.732,02 +0,26%). CORS returned `access-control-allow-origin` for the site's origin and nothing for an unrelated one. The direction toggle refetched and returned DXG −3,91% / TCH / DIG — the same three, in the same order, as the independent SQL check |
| 8 | Deployed: `GET /health` returns `{"database": "ok"}` — proving Render reached Supabase through the pooler | **PASS** — run 2026-08-28 18:54 UTC against `https://anchor-model-api.onrender.com/health`: `{"status":"ok","service":"clusterweb-api","database":"ok","time":"2026-08-28T18:54:31Z"}`. Render (Singapore) reaches the Supabase session pooler (ap-southeast-2) |
| 9 | Deployed: a request with `Origin: <static site>` returns `access-control-allow-origin`; the same request with an unrelated Origin does **not** | **PASS** — `GET /api/model/active` with `Origin: https://anchor-model-web.onrender.com` → 200 + `access-control-allow-origin: https://anchor-model-web.onrender.com`; the identical request with `Origin: https://evil.example.com` → 200 with **no** `access-control-allow-origin` header at all, so a browser blocks the read. Preflight also checked: `OPTIONS` from the site's origin returns `allow-methods: GET`, `allow-origin: <site>`, `max-age: 600`, and no `allow-credentials` |
| 10 | Deployed `/` shows the live session date and figures reconciling against a direct query of `v_market_overview` — the numbers on screen are checked, not trusted | **PASS** — the deployed page was loaded in a browser and every headline figure reconciled against a direct read-only `SELECT * FROM v_market_overview`, field by field: session 18/08/2026 = `session_date 2026-08-18`; 85 = `n_tickers`; 32/41/12 = `advancers/decliners/unchanged`; 8.352,13 tỷ = `total_turnover 8352129774`; 272.811.000 = `total_volume`; VNINDEX 1.732,02 +0,26 % = `index_close 1732.02`, `index_ret_1d 0.0026397137994512`. The API layer between them was checked too and returns the same values |
| 11 | 20 minutes idle, then a request: served without a cold-start delay | **FAIL, measured twice — and it cannot pass on this plan.** Run deliberately on 2026-08-28: last request 18:55:22 UTC, then no contact with the API for 21 minutes. Render's own log shows the instance spinning itself down at **19:09:54** — 14 min 32 s of idleness, matching the free tier's ~15-minute policy. The request at 19:16:23 then took **25,250 ms**; the one right after it took 1,012 ms. An independent measurement earlier the same day gave **34,259 ms** after a comparable gap (log empty 17:20–17:47). **This is D-21's free-tier choice showing its price, not a defect**: a free Render web service stops its process when idle, so a cold start is the specified behaviour and no code change can remove it. Connection pooling does not help here either and never claimed to — a freshly started process has an empty pool by construction. The check is left as FAIL rather than reworded, because the deployment genuinely does not do what the row asked |
| 12 | `render.yaml` contains no password, key, or connection string; `git log -p` on it confirms none was ever committed | **PASS** — scanned for connection strings, `password:`/`password=`, JWT-shaped tokens, `service_role`, a Supabase host, and any 32+ char token. One hit, inspected and dismissed: the literal placeholder `db.<ref>.supabase.co` inside an explanatory comment. History is empty of secrets because the file is new and untracked |
| 13 | `ruff check .`, import sweep, `compileall`, storage selftests re-run at phase end | **PASS** — repo-wide `ruff check .` "All checks passed!"; `compileall` clean over `pipelines` and `services`; `pipelines.storage.localfs --selftest` 12 passed / 0 failed. Web side: `next build` and `next lint` both clean |
| 14 | `services/api` has no import path to `pipelines.anchors` — asserted, not trusted (D-18, `docs/04` §5) | **PASS** — `test_routes.py::NoPathToGreedyTests`: no `pipelines*` module in `sys.modules` after importing `app.main` |

---

## Traps worth naming before starting

- **`NEXT_PUBLIC_API_BASE_URL` is baked in at build time.** It is read as a literal
  `process.env.…` member expression in `ambientEnv()` so Next can inline it. Setting it in
  Render's dashboard after a successful build changes nothing until a rebuild.
- **A deployed build never falls back to mocks.** `next build` sets `NODE_ENV=production`, so
  `classifyRuntimeMode` returns `production-like`, and `resolveApiConfig` returns
  `{kind: "error", code: "api_not_configured"}` rather than mock data when the base URL is
  blank. Fail-closed is correct — but it means a misconfigured deploy is a visibly broken site,
  not a silently fake one.
- **`VERCEL_ENV` is read first.** On Render it is absent so the `NODE_ENV` branch governs, which
  is the right outcome, but the Vercel coupling in `lib/api.ts` is now misleading and should be
  renamed or commented while that file is being trimmed anyway.
- **The Supabase direct connection is IPv6-only.** Use the pooler hostname (S6). A
  `DATABASE_URL` copied from the wrong panel in Supabase's UI fails at connect time with a
  network error that looks nothing like a configuration mistake.
- **Transaction pooling breaks `set_session(readonly=True)`** (S7). Port 6543 is not a drop-in
  substitute for 5432 here.
- **`/health` returns HTTP 200 even when the database is unreachable** — `database` flips to
  `"error"` in the body. A Render health check on it therefore monitors liveness only. Keep it
  that way: a health check that fails on a Supabase blip would restart-loop the service.
- **No connection pooling exists.** `read_cursor()` opens a fresh psycopg2 connection per query.
  P7 measured ~175 ms per statement to the Sydney pooler from this machine; from Render the RTT
  will differ but the TLS handshake per query stays. Three panels on `/` means three requests,
  each paying it. Acceptable at this traffic; revisit in P9 when there are twelve routes.
- **`v_top_movers` is unordered and unlimited by design.** A route that forwards it verbatim
  ships 85 rows in arbitrary order and looks like a view bug.
- **`apps/web/tests/` does not exist** while `vitest.config.ts` points at it. `npm run test` is
  not a runnable check today; do not report it as passing.

---

## Deferred / Out of scope

- The remaining nine P9 routes, `/tickers`, `/anchors`, the treemap, the combined indicator
  chart, and the rewritten `/methodology` and `/pipeline` — P9 and P10.
- **The refresh runbook, now P11.** Also carried there, from `p7-indicators.md`:
  `psycopg2.extras.execute_batch` in `pipelines/common/upsert.py`, which is the difference
  between 18 hours and minutes when the pipeline runs over a real network.
- Airflow, scheduling, retries, backfills, and any daily refresh. D-13 stands: the dashboard is
  static as of the last collection.
- A custom domain, CDN configuration, and TLS beyond what Render provides by default.
- Converting the `--selftest` bodies into `pytest` files; there is still no CI.
