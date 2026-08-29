# P10 execution plan — the dashboard

> ## CLOSED — moved to `completed/` on 2026-08-29 (P12/F5)
>
> **Closed by:** 33 of 33 boxes ticked, and the screens confirmed live on 2026-08-29 — the
> deployed page renders the market overview, the sector treemap, the movers table and the
> provenance strip against real data.
>
> **Its validation row is only PARTIAL and is recorded that way in the parent, not here.**
> `vitest` now runs — 42 passed across 5 files — but the two other clauses of that row
> (mock-mode rendering with `NEXT_PUBLIC_API_BASE_URL` unset, and live mode against the P9 API)
> are still **not attempted**: no test renders a screen. The plan is closed; that check is not.

---


**Started:** 2026-08-19
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md` — this file is the executable detail of its P10 section.
Progress and Validation are maintained **here**; the parent's P10 checkboxes track completion.
**Predecessor:** `p9-read-api.md` — DONE. Eight routes added, API at 11, all verified live against
the deployed Render service (commit `0beb4e9`, pushed to `origin/main` 2026-08-19).

---

## Why

P9 stopped at the wire, by design. Eleven routes are deployed and returning live Supabase data,
and **eight of them have no consumer**: `apps/web` still holds the single `/` screen P8 shipped.
The screens the thesis argues from — the sector treemap, the ticker page, the anchor page — exist
as API responses and nothing else.

P10 builds them. It is frontend work almost exclusively: no migration, no new route, no change to
what the API returns.

### The editorial change this phase also makes

The project owner's instruction, given with a screenshot of the current provenance strip
(`Cửa sổ ước lượng · Phiên mới nhất · Số mã · k · τ · F̄(S) · Dưới τ · Độ đo · Artifact`):

> *"tôi muốn bỏ đi các thông tin như là kiểu … mô hình này chạy như nào, thuật toán rồi độ đo là
> gì … người dùng thì họ thường quan tâm tới kết quả hơn, ví dụ như thay vì viết MA20 tính như
> nào thì họ chỉ cần biết chỉ số đó là MA20 thôi."*

This is not a new principle. `docs/03-temporal-design.md` §5 already states it:

> *"the report establishes that the method works, and the dashboard then applies it to current
> data for users who do not need the methodology re-argued."*

The report is where the method is argued. The dashboard is where the results are read. P10 makes
the built artefact match the specification that was already written.

**The constraint that stops this becoming deletion:** `docs/04` §5 requires the dashboard to show
the universe as of the active run and say so, and the parent plan requires a provenance strip on
every page. The resolution is **demotion, not removal** — S1 and S2 below.

### Scope change from the parent plan

- **`/methodology` becomes `/about` ("Giới thiệu"), one screen** — S2.
- **Detail pages are query strings, not dynamic segments** — S4. The parent plan writes
  `/tickers/[ticker]` and `/anchors/[anchor]`; `output: "export"` cannot build those from client
  components, which `next.config.ts` has said since P8.
- **`/pipeline` was already removed** by P9 S1 and is not restored.

**Definition of done.** Four screens (`/`, `/tickers`, `/anchors`, `/about`) rendering live data
from the P9 API, and rendering committed fixtures with `NEXT_PUBLIC_API_BASE_URL` unset — the
documented frontend development workflow, which must not regress.

---

## Decisions taken

| # | Decision | Reasoning |
|---|---|---|
| S1 | **Provenance is one line plus a disclosure.** Always visible: `Dữ liệu đến {latest_session} · {n_tickers} mã · {k} điểm neo`. Behind `Chi tiết mô hình ▾`: `window_start`–`window_end`, `τ`, `F̄(S)`, `n_under_tau`, `similarity_measure`, `artifact_id` | `docs/04` §5 is satisfied by the first line — it names the universe and the as-of date. The remaining seven fields are the run's identity, which matters to a reviewer reproducing the result and to nobody reading a price. Deleting them would break §5 and lose the defence's evidence; leading with them costs every reader nine mathematical symbols before the first number they came for |
| S2 | **`/methodology` → `/about`, one screen.** What the system does in 3–4 sentences, the as-of date, the not-investment-advice disclaimer, and the run's parameter table | The archived `MethodologyScreen.tsx` is ~300 lines: an "It does / It does not" pair, seven limitations, two verbatim disclaimers, and two charts drawn on fabricated "Stock A/B/C" data. That page argues the method. `docs/03` §5 says the dashboard does not have to. What genuinely cannot move to the report is the disclaimer — `docs/02` §4 forbids advisory framing, and a fixed place to say so is worth one screen |
| S3 | **`/anchors` leads with results, keeps the statistics secondary.** Primary: anchored members with sector and `coverage_c`, sector composition, the anchor's own price trend. Secondary panel `Chỉ số nhóm`: `size`, `f_j`, `rho2_mean`, `rho2_min`, `marginal_gain` | This screen is the thesis's own contribution, so hiding the statistics outright would remove the evidence a defence needs. Giving them equal weight makes the screen unreadable to the audience `docs/03` §5 describes. Two tiers serves both, and neither reader has to skip the other's content |
| S4 | **Detail pages are query strings: `/tickers/?t=VCB`, `/anchors/?a=VCB`.** One route each, rendering the list when the parameter is absent | `output: "export"` cannot export a dynamic route from a client component — `generateStaticParams` is a server-side export, and every screen here is `"use client"`. The alternative (a server wrapper enumerating the 85 tickers from `list_stocks_research.txt` at build time) yields prettier URLs and a real failure mode: the committed file drifting from the active run's universe would 404 a valid ticker until someone rebuilt. **`useSearchParams` must sit inside a `<Suspense>` boundary or `next build` fails** — this is the one way S4 breaks, and it breaks at build time, which is the right time |
| S5 | **No charting library.** Continue with hand-written SVG over the existing `ChartFrame` / `ChartSvg` / `ChartAxisLabel` / `ChartLegend` / `ChartCaption` / `PriceHistoryChart` primitives | The primitives already exist and already consume the design tokens, so they theme correctly in light and dark. A library would have to be restyled onto those same tokens to look like the rest of the app — the work is not avoided, only relocated — and it would be the largest dependency in a package that currently has three |
| S6 | **Directional colour follows the Vietnamese convention: green up, red down.** `--data-pos` / `--data-neg` are reassigned | The current tokens are deliberately *not* red/green (steel blue `#1d4ed8` vs clay `#b45309`, commented "non-emotional directional pair"). That choice belonged to the Leiden screens, where the quantity being coloured was a cluster relationship with no market direction. Here the quantity is a price change read by Vietnamese users against every other board they use. Deviating would be a statement the data does not make |
| S7 | **Delete the dead Leiden CSS from `globals.css`.** Roughly 2,800 of its 3,589 lines — the `clusters-`, `cluster-detail-`, `universe-`, lead-lag and outcome blocks | The screens those rules styled were archived in P8; the rules ship to every visitor on every page load. P8 recorded the debt and assigned it here. New screens use CSS Modules, the convention P8 chose going forward |

### Decision records this phase writes

- **D-24 — the dashboard shows results, not method.** S1, S2 and S3 are one product decision
  applied in three places, and it will be re-litigated by anyone who reads `docs/02` and `docs/04`
  and wonders why the model's parameters are not on the front page. The record states the
  instruction, the `docs/03` §5 sentence it implements, and the `docs/04` §5 floor it stops at.

---

## What is already true, and must not be re-derived

Verified during P8–P9. Not assumptions:

- **All 11 routes are deployed and return live data**, verified over HTTP against the Render
  service, each reconciled against a direct query of its source view.
- **There are no Pydantic response models.** Every route is annotated `-> dict` and builds a dict
  literal; there is no `response_model=` anywhere in `services/api/app/`. `/openapi.json` shows an
  empty response schema for every route. **TypeScript types must be transcribed by hand from the
  route bodies** — there is nothing to generate from.
- **Ratios are fractions.** `ret_1d = 0.07` means +7%. `bb_width_20`, `dist_from_sma_200_pct` and
  `drawdown_from_252d_high` are ratios too, despite their names.
- **`close` is in nghìn đồng**, so `turnover_value` and `total_turnover` inherit that unit;
  `formatTurnoverTy` divides by 1e6 for tỷ đồng. **`index_close` carries no currency unit and must
  never pass through it.**
- **`advancers + decliners + unchanged ≠ n_tickers`.** A ticker with a null `ret_1d` is in none of
  the three; `n_with_return` is the real denominator.
- **`/api/anchors` returns all 15 selection steps**, not the published 10. `in_published_set` marks
  the cut. Steps past it have null `size` / `f_j` / `rho2_*` and no members — that is the truth,
  not a join failure.
- **The active run:** `ae2010a4ad426`, `scope='year'`, `pearson_rho2`, `n_tickers=85`, `k=10`,
  `k_max=15`, `τ=0.10`, `F̄=0.2629`.
- **`k=10` is provisional and the Δ curve has no elbow** (D-2, updated at P5: still ≈0.97–1.02 at
  k=15). No screen may imply 10 was read off a knee.
- **`apps/web/tests/` does not exist** while `vitest.config.ts` points at it, so `npm run test`
  runs zero tests today. P9 restated this specifically so P10 would not report it as passing.

### Found while transcribing the types: `sector_composition` is empty

`/api/anchors/{a}` publishes `sector_composition`, and the parent plan calls the panel built from
it "the interesting one — the external validation `docs/02` §3g describes." **The field is `{}` for
all ten published groups** in the active artifact `ae2010a4ad426`, checked directly in its
`manifest.json`, not inferred.

That is deliberate, not a loading defect. `pipelines/artifact/schema.py:186` says so:

> *"`sector_composition` defaults to `{}`: no sector data is collected locally, and `docs/02` §3g
> makes sector composition external validation only — it never enters `P` or the objective, so an
> empty dict here is a deferred field, not a placeholder standing in for something the model
> needed."*

**Consequence for P10.6:** the panel cannot be rendered from `sector_composition`. It is instead
aggregated **client-side from `members[].sector`**, which the same response already populates
(`stocks.sector`, 85/85 resolved from vnstock at P6.1). This is a display-edge aggregation of data
the API already sends, not a computation moved into the frontend, and it stays external validation
for exactly the reason the docstring gives — the sector labels come from `stocks` and never touched
the similarity matrix.

The `sector_composition` field is still typed and still read, so that a future run which populates
it is preferred over the derived value rather than ignored.

---

## The editorial rule

Applies to every user-visible string in `apps/web`. Written out because it is the instruction this
phase exists to carry out, and it is the kind of rule that erodes silently.

1. **A label names an indicator; it does not define it.** `MA20` — not *"đường trung bình động 20
   phiên, tính bằng trung bình cộng giá đóng cửa 20 phiên gần nhất"*.
2. **No explanatory paragraph under a figure.** Specifically deleted: `ProvenanceStrip.gapNotice`
   (four lines on why the estimation window trails the latest session and how adjusted prices
   differ from a broker's), the six `.kpiHint` lines in `KpiRow.tsx`, the `.caption` under
   `MoversTable`, and the methodology sentence in `layout.tsx`'s `metadata.description`.
3. **Facts load-bearing for correctness become tooltips or units, never prose.** `n_with_return`
   still has to be reachable, because the three breadth counts are not a partition — it belongs in
   a `title=`, not a sentence. Units sit against their number.
4. **Mathematical notation appears only after a click.** `τ`, `F̄(S)`, `ρ²`, `f_j` are not in the
   always-visible layer of any result screen.
5. **Two existing rules are not relaxed by any of the above** — this is where tidying turns into a
   defect:
   - **`null` is not `0`.** Every formatter maps null to `—`. `0` asserts a measurement was made
     and came out zero; `null` says nothing was measured. D-13 calls this "the single most likely
     way this decision turns into a lie on screen."
   - **Units.** `formatTurnoverTy` applies to `turnover_value` and `total_turnover` only.

---

## The screens after P10

| Route | Screen | Reads |
|---|---|---|
| `/` | Tổng quan thị trường | `/api/market/overview`, `/api/market/sectors`, `/api/market/movers` |
| `/tickers/` | Danh sách mã | `/api/tickers` |
| `/tickers/?t=X` | Chi tiết mã | `/api/tickers/X` + `/history` + `/indicators` + `/analysis` |
| `/anchors/` | Danh sách điểm neo | `/api/anchors` |
| `/anchors/?a=X` | Chi tiết nhóm neo | `/api/anchors/X`, `/api/tickers/X/indicators` |
| `/about/` | Giới thiệu | `/api/model/active` |
| ~~`/methodology`~~ | — | **replaced by `/about` (S2)** |
| ~~`/pipeline`~~ | — | **dropped in P9 (S1 there)** |

Compact provenance (S1) sits at the foot of every page, from `/api/model/active`.

---

## Progress

Each sub-phase is a separate working session and a separate commit, ordered so nothing depends on
a later one.

### P10.0 — Plan, documents, shell — **DONE**
- [x] This file
- [x] Amend the `### P10 — Dashboard` section of `anchor-model-operations.md`: `/methodology` →
      `/about`, query-string detail URLs, compact provenance
- [x] `docs/decisions/D-24-dashboard-shows-results-not-method.md`, registered in
      `docs/decisions/README.md`
- [x] `AppChrome.tsx` — four nav items and their `PAGE_META`; drop the docstring's `/pipeline`
      reference, dropped in P9

#### Two stale claims corrected in the parent while passing through

- **"Rewrite `lib/api.ts` (664 lines of a dead contract) and `lib/mock.ts` (317 lines)."** Both
  files were already cut back to the three live routes in P8.3. `api.ts` is 382 lines of a
  *current* contract; the work here is addition, not rewriting.
- **"Archive the clusters / lead-lag / outcomes screens and their components."** Done in P8; ticked
  rather than left as pending work this phase would appear to owe.

Also added to the parent's checklist, because P8 recorded them for this phase and the parent never
listed them: the dead-CSS deletion, and creating `apps/web/tests/` so `npm run test` stops being a
check that silently passes on zero tests.

### P10.1 — The data layer — **DONE**
- [x] `src/lib/api.ts` — eight response type blocks and eight fetchers, transcribed by hand from
      the route dict literals. Unit notes (fraction / price / index level) at the type
- [x] `src/hooks/dashboard.ts` — eight hooks in the existing `useAsyncResource` shape
- [x] `src/lib/mock.ts` — eight fixtures, adversarial in the manner of the existing four
- [x] `npx tsc --noEmit` clean

#### Three things settled here

- **`IndicatorFields` is declared once and extended twice.** `/api/tickers/{t}`'s `latest` block
  and every row of `/indicators` carry the same 29 columns — the series route duplicates them on
  purpose so each response is self-sufficient. Writing the interface twice would have been 60 lines
  of drift waiting to happen; `TickerLatest` and `IndicatorPoint` extend the shared base and add
  only what differs (OHLC on one, nothing on the other).
- **The series fixtures are generated, not authored.** A seeded LCG builds a 252-session price path
  and computes the real indicator definitions over it (EMA carried forward, RSI over a 14-session
  gain/loss ratio, Bollinger from a 20-session standard deviation). A hand-written 20-point fixture
  would have hidden every defect that only appears at real density — and would have had `sma_200`
  populated everywhere, when in truth it is null for the first 199 points of any window.
- **Fixtures keep the adversarial cases**: a ticker with no bar at all (`bar_date: null`), four
  tickers with no sector, a sector whose `mean_ret_1d` is null because none of its members has a
  return today, five anchors past the published boundary with null group statistics, and a member
  with a null `ret_5d`.

### P10.2 — Provenance and the prose removal — **DONE**
- [x] Rewrite `ProvenanceStrip.tsx` per S1, and **move it into the shell**. It now lives at
      `components/ProvenanceStrip.tsx` and is rendered once by `AppChrome` at the foot of every
      page, rather than by each screen — "on every page" met in four places is a requirement that
      will eventually be met in three
- [x] Delete `gapNotice`, the six `kpiHint`s, the movers caption; move `n_with_return` and the
      stale-bar ⚠ into `title=`
- [x] Rewrite `metadata.description`
- [x] Vietnamese-ise `states/*` and `charts/*`, still English from the Leiden era

#### Two defects found while doing this

- **`text-transform: uppercase` was corrupting `τ`.** The label read `Dưới τ` in the source and
  `DƯỚI Τ` on screen — capital tau, which is visually a Latin T, and is exactly what the strip in
  the owner's screenshot showed. A label that silently renames the symbol it names is worse than a
  long label. `.defTerm` and the provenance `.label` no longer uppercase; every other label class
  still does, because none of them carries Greek.
- **`PriceHistoryChart` labelled prices "VND".** They are in **nghìn đồng** — the `daily_bars`
  convention this repo has written down twice. The axis, the legend and the endpoint label all
  said VND, which is wrong by a factor of a thousand on the one chart a reader checks against
  their broker. Fixed with the rest of that file's Vietnamese pass.

### P10.3 — `/` and the treemap — **DONE**
- [x] `src/components/charts/treemap.ts` — a pure squarify function, no React, no DOM
- [x] `SectorTreemap.tsx` — area by `total_turnover`, colour by `mean_ret_1d`, null sector → "Khác",
      null `mean_ret_1d` → neutral, never the colour of 0%
- [x] `KpiRow` / `MoversTable` retouched per P10.2
- [x] Verified in the browser against the fixtures: 7 tiles, total area exactly 640×300, no
      overlapping pair, and the null-sector tile painted `--data-neutral` with `—` rather than 0%

#### `components/ui.module.css`, added here

P10 adds three screens to a codebase whose only screen kept its table, KPI card and pill toggle in
its own module. Three more copies of those would have drifted. The shared primitives moved to
`components/ui.module.css`, which several components import; `market/Market.module.css` now holds
the treemap and nothing else. No rule is duplicated between them.

### P10.4 — `/tickers/` — **DONE**
- [x] One fetch, client-side filter over 85 rows
- [x] `<Suspense>` around the `useSearchParams` read
- [x] Anchor badge, and an `under_tau` marker with the threshold explained in its `title`

### P10.5 — `/tickers/?t=X` — **DONE**
- [x] Four hooks in one component — concurrent `useEffect`s, never chained
- [x] KPI row; price+volume; the combined four-pane technical chart; the narrative; the anchor card

The combined chart draws every series as contiguous runs of finite points, broken at each null.
`sma_200` is null for the first 199 sessions of a 252-session window and `rsi_14` for the first 14;
joining across those gaps would draw a line the data does not contain, and substituting 0 would
draw a crash that never happened. Each pane scales to its own finite values, and a pane with
nothing finite renders its frame and nothing else.

### P10.6 — `/anchors/` and `/anchors/?a=X` — **DONE**
- [x] Ten chips filtered from the fifteen returned steps; the five unpublished steps kept in a
      disclosure rather than dropped, so k=10 can be compared against what k=15 would have been
- [x] Members, sector composition (labelled as external evidence), the anchor's own figures
- [x] Secondary `Chỉ số nhóm` panel (S3); unpublished steps render as "chosen at step N, outside
      the published 10", never as a group of size 0

Sector composition is derived from `members[].sector` for the reason recorded above — the API's
`sector_composition` is `{}` for every group of the active artifact.

### P10.7 — Cleanup and the first tests — **DONE**
- [x] Deleted the dead CSS (S7): `globals.css` 3,595 → 707 lines. Sections 20–24 styled the Leiden
      screens P8 archived. Verified unused first — no class defined below the old line 760 was
      referenced by any `className` in `apps/web/src`, as a literal or inside a template literal
- [x] Created `apps/web/tests/` — 29 tests over `format.ts`, `treemap.ts` and the runtime-mode
      resolver. `npm run test` is a real check for the first time
- [x] Deleted the orphaned `HealthStatus.tsx` and the `.status-card*` / `.status-badge*` /
      `.status-row__*` rules that styled only it. A backend health card has no place on a results
      dashboard, and P9 already dropped the screen that would have hosted one. `fetchHealth` stays
      in `lib/api.ts`: `/health` is a real route and this file covers all of them
- [x] `.gitignore`: `*.tsbuildinfo` and `.claude/`

### P10.8 — Verification — **DONE**
- [x] `npm run build` — static export succeeds, 4 routes prerendered
- [x] `npm run lint` — clean
- [x] `npm run test` — 29 passing; `services/api` 146 passing, `ruff` clean
- [x] Mock mode across all four screens
- [x] **Deployed and verified live** on `https://anchor-model-web.onrender.com` against the
      Render API and Supabase

#### Three defects found only by deploying

None of these could have been caught by the fixtures, because the fixtures were written by the
same hand as the code and agreed with it.

1. **`narrative.py` — "Giá tăng 17.92% trong từ đầu năm (YTD)."** Fixed in `3b8a898`; detail
   below.
2. **Chart captions printed the raw ISO date** — `DỮ LIỆU ĐẾN 2026-08-18` beside a KPI reading
   `18/08/2026`. `asOf` was passed straight from the response instead of through `formatDate`.
   Fixed in `9ca4151`.
3. **Chart axis labels did the same** — the range line and both x-axis endpoints. Fixed in
   `9434c35`.

All three are the same defect: a date or a phrase reaching the screen without passing through the
one function that formats it. The fixtures used ISO strings throughout and looked correct.

---

## Validation

Run on 2026-08-19 against the committed fixtures. **Everything below marked PASS was executed; the
one row that was not is marked and says why.** No live-API row is claimed.

| Check | Status |
|---|---|
| `npm run build` — static export succeeds (where a missing Suspense boundary surfaces) | **PASS** — 4 routes prerendered (`/`, `/about`, `/anchors`, `/tickers`), export 2/2, 103 kB shared JS |
| `npx tsc --noEmit` | **PASS** — clean |
| `npm run lint` | **PASS** — no warnings or errors. One `react-hooks/exhaustive-deps` warning was found and **fixed** rather than suppressed: `TickerList` derived `rows` outside its `useMemo`, giving the array a new identity every render and defeating the memo |
| `npm run test` — a suite that exists and covers the pure functions | **PASS — 29 tests, 3 files.** Before this phase the directory `vitest.config.ts` pointed at did not exist, so the command ran zero tests and exited 0. It is a real check now, not a green tick over nothing |
| Mock mode: `NEXT_PUBLIC_API_BASE_URL` unset renders all four screens | **PASS** — `/`, `/tickers`, `/tickers/?t=VIC`, `/anchors/?a=VIC`, `/about` all rendered and read in the browser |
| Treemap tiles the rectangle | **PASS, measured in the DOM** — 7 tiles, total area 192000.0000 against an expected 640×300 = 192000, no overlapping pair. Also asserted in `tests/treemap.test.ts` |
| No `0` rendered where the API sent `null` | **PASS** — checked on the fixtures built to carry nulls: the null-sector treemap tile shows `—` and `--data-neutral`; ticker `T40` (no bar) shows `—` for its 1-session return; member `M03` shows `—` for `ret_5d`; unpublished anchors render as "outside the published 10" rather than size 0. `tests/format.test.ts` asserts the rule across every formatter |
| `index_close` does not pass through `formatTurnoverTy` | **PASS** — `tests/format.test.ts` pins both halves: the conversion is right for turnover (8,352,129,774 nghìn đ → "8.352,13" tỷ đ) and would visibly destroy an index level (1732.02 → "0,00"), which is the failure it exists to prevent |
| A gap mid-series breaks the line instead of being joined across or filled with 0 | **PASS, measured in the DOM.** The fixture carries a deliberate two-session hole at the middle of the 252-session window; every one of the combined chart's nine series renders exactly 2 subpaths, and the price chart 2 polylines of 126 + 124 points. Added after noticing the first fixture only had *leading* nulls — a gap at the start of a series is the case every renderer gets right by accident |
| Both themes resolve, and the new directional palette holds in each | **PASS, measured** — dark: bg `#0f172a`, pos `#4ade80`, neg `#f87171`; light: bg `#f8fafc`, pos `#15803d`, neg `#b91c1c`. Both pairs clear WCAG AA against their own canvas. The treemap's `color-mix` alpha ramp resolves in both |
| Built CSS contains no dead Leiden rule | **PASS** — grepped the two emitted bundles (13.7 kB + 22.2 kB): `.app-chrome` present, `--data-pos` present for both themes, zero matches for `.clusters-` / `.cluster-detail-` / `.universe-page` / `.ticker-detail-page` |
| Live API reachable and serving Supabase | **PASS** — `https://anchor-model-api.onrender.com/health` returns `"database": "ok"`. Site: `https://anchor-model-web.onrender.com` |
| Live: every route reconciled against `curl` | **PASS — four independent cross-route reconciliations**, listed below. This is the strongest check in the phase: each figure is confirmed against a *different* route that must agree with it |
| Live: the ticker page issues four **concurrent** requests, not four sequential ones | **PASS, measured in the browser's Resource Timing.** The four calls overlap — each ~1.0–1.1 s, wall clock ~1.1 s, against the 3.9 s a sequential chain would cost. The P10.5 design claim is confirmed against the real API, not argued |
| Live mode: each **screen** rendered against the live API | **PASS — deployed and verified.** Pushed `3b8a898`; Render rebuilt the static site in ~60 s and redeployed the API. All four screens read in the browser on `https://anchor-model-web.onrender.com` against live Supabase data. Every KPI checked against the `curl` figures above: close 200,00 / +1,01% / 860,38 tỷ đ / 4.301.900 cp / −17,36% for VIC, and 8.352,13 tỷ đ / 1.732,02 / 32-41-12 on the market screen |

**A note on why this could not be done from localhost.** The API returns
`access-control-allow-origin` only for `https://anchor-model-web.onrender.com`; from
`http://localhost:3000` it answers 200 with no CORS header and the browser discards the body. The
four requests were confirmed to fire — correct URLs, concurrent — and were then correctly refused.
That is P8's boundary working as designed. Verifying the screens live therefore *required*
deploying, which is what settled the order of operations here.

### The four live reconciliations

Each figure is checked against a route that computes it independently:

| Reconciliation | Result |
|---|---|
| `Σ sectors[].total_turnover` vs `market/overview.total_turnover` | **8,352,129,774 = 8,352,129,774**, exact. Nine sectors, `Σ n_tickers` = 85 |
| `Σ anchors[].size` over the published 10 vs the universe | **85** — the groups partition the universe exactly |
| `anchors[step_k=10].coverage_fbar` vs `model/active.coverage_fbar` | **0.262929 = 0.262929** — the greedy curve's last published step is the run's headline coverage |
| `Σ members[].coverage_c` for VIC vs that group's `f_j` | **2.662457 vs 2.662459** — agreement to the rounding of 19 six-decimal values, which is `f_j`'s definition |
| `count(under_tau)` over `/api/tickers` vs `model/active.n_under_tau` | **33 = 33**. Anchors flagged: **10 = k** |
| Unpublished anchors (`step_k` 11–15: VCG, FRT, HDB, BWE, VNM) | `size` / `f_j` / `rho2_*` / `sector_composition` all **null**, member list empty — the NULL tail P10.6 renders as "outside the published 10", confirmed live |

### `sector_composition` is empty on the live database too

Confirmed against Supabase, not only against the artifact on disk: `{}` for all ten published
groups. The client-side derivation from `members[].sector` is therefore necessary, not a local
workaround. For VIC it yields Tài chính 10 / Bất động sản và Xây dựng 4 / Dịch vụ 3 / Hàng tiêu
dùng 2 — a genuinely mixed group, which is what the external-validation panel is for.

### One live defect found, in the API not the dashboard — **FIXED** (`3b8a898`)

`GET /api/tickers/VIC/analysis` emitted:

> *"Giá tăng 17.92% trong **từ đầu năm** (YTD)."*

`_trailing_return` formatted every sentence as `"Giá {direction} {pct}% trong {label}."` and
prepended `trong ` to a label that was already a complete adverbial phrase. Correct for the three
session windows, ungrammatical for `ret_ytd` — one malformed sentence out of the thirteen on every
ticker page, in production.

The label now carries its own preposition (`"trong 5 phiên gần nhất"`, `"từ đầu năm (YTD)"`), so
adding a fourth window cannot reopen the question. A return of exactly zero also drops the
percentage: *"Giá không đổi trong 5 phiên gần nhất"* rather than *"Giá không đổi 0.00% trong…"*,
which stated the same fact twice.

**Why it survived a 142-test suite.** The three tests covering these sentences asserted substrings
— `"tăng"`, `"giảm"`, `"không đổi"` — and a substring check cannot see grammar; all three passed on
the broken sentence. The replacements pin whole sentences, and one scans every statement for
`"trong trong"` / `"trong từ"` so the family is guarded rather than the single label that happened
to be wrong. 146 passed, `ruff` clean.

---

## Traps carried into this phase

- **`docs/product/` and `docs/ARCHITECTURE.md` do not exist**, though `CLAUDE.md` cites both — the
  same defect class D-23 recorded once for `docs/deployment/PYTHON_RUNTIME.md`. The screen
  specification is the ~25-line P10 section of `anchor-model-operations.md`. There is no product
  document to arbitrate a screen question.
- **`sector_composition` is external validation, not an input.** Sector never entered the
  similarity matrix or the objective. Labelling it as an input on screen turns the one independent
  check this system has into a circular argument.
- **The breadth counts are not a partition.** Never a pie chart summing to 85.
- **`/api/tickers` measured 3,083 ms from Render.** `/tickers/` will have a visible wait. Fixing
  that is the deferred pooling work, not P10 — but the loading state has to be honest and decent.
- **A production-like build never serves mock data.** `next build` sets `NODE_ENV=production`, so a
  missing `NEXT_PUBLIC_API_BASE_URL` renders `api_not_configured` on every panel. Mock mode is a
  `npm run dev` fact only.

---

## Out of scope

- **Connection pooling / `read_cursor()`.** Deferred to its own phase by the project owner. One
  note so that phase is not mis-scoped: P9.6's ~3.9 s figure is the **sequential** cost. With
  `useAsyncResource`, four hooks in one component issue four independent `useEffect`s, so the
  ticker detail screen costs about the slowest route (~1.2 s) rather than the sum — provided P10.5
  does not chain them, which is why that is written as a checklist item rather than left to taste.
  What remains genuinely pooling-shaped is `/api/tickers` at 3,083 ms and cold starts.
- **Shortening the indicator labels inside `services/api/app/narrative.py`.** The generated
  sentence currently reads *"…đường trung bình 20 phiên (MA20)…"* where the editorial rule would
  prefer *"…MA20…"*. It is a backend change with a test alongside it, and the narrative states
  facts about numbers rather than defining indicators — so it does not actually violate the rule.
  Left for a later decision.
- **Rolling ρ²_W, coverage drift, assignment challenges, beta drift.** The `live_*` tables are
  empty by D-13 and no endpoint exists.
- **Khối ngoại.** Never collected (D-19).
