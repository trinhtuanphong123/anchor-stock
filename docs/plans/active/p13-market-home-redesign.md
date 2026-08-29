# P13 execution plan — the market home redesign

**Started:** 2026-08-29
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md`
**Predecessor:** P11's dashboard redesign, whose Strata palette this supersedes.

> **Written after the fact, and saying so.** `CLAUDE.md` requires this file to exist *before*
> mutating. It did not: the work began as a UI request and only became a durable change once the
> schema and two pipeline modules were in scope. The Progress table below is a record of what was
> actually done, not a forecast, and the two aborted attempts in §Backfill are in it for the same
> reason.

---

## Why

The owner asked for a professional market-overview home page in TradingView's idiom — its layout,
palette, line and hover behaviour — carrying four things: a VNINDEX time-series chart, a sector
treemap, a top-movers ranking at 1D/5D/1M/3M/1Y, and a session liquidity ranking.

Three of those had no data path.

| Panel | Before | Gap |
|---|---|---|
| VNINDEX chart | — | No route served `market_index_bars` at all |
| Movers 1M / 3M | `/movers` returned `ret_1d`, `ret_5d`, `ret_20d` | `ret_60d` existed in the table but not in the view or the route |
| Movers **1Y** | — | **No 252-session return existed anywhere in the schema** |
| Liquidity | — | `v_top_movers` already carried `turnover_value`; only an ordering was missing |
| Sector treemap | Worked (P10) | Restyle only |

Two constraints were settled with the owner before any code was written, and both bind what the
screen may claim:

1. **1Y is a real 252-session return**, not `ret_ytd` relabelled. Chosen over the cheap option
   because on 29 August "YTD" is eight months, and a column headed 1Y that means eight months is
   the kind of quiet mislabel this project's whole documentation posture exists to prevent.
2. **The index chart has no 1D range.** The pipeline collects daily bars and nothing finer, so
   there is no intraday series in this system. The ranges are 1M/3M/6M/YTD/1Y/ALL and the panel
   footnote says one point is one session. A "1D" tab drawn from daily bars would be a label
   making a claim the data cannot support.

**Deployment shape is unchanged and needs no change.** `apps/web` is `output: "export"` and every
screen is client-rendered against the API at runtime, so Render's Static Site is correct — it
neither spins down nor draws on the 750-hour instance budget that cannot fit two always-on web
services. This was checked against the live services, not assumed.

---

## Progress

### Schema — `supabase/migrations/00013_market_home_views.sql`

- [x] `technical_indicators_daily.ret_252d` added, nullable, no CHECK — matching `ret_1d..ret_ytd`
- [x] `v_index_history` — the active run's index series, unranged and unlimited, symbol resolved
      through `v_active_model_run` so no market-specific string enters the view
- [x] `v_latest_indicators` recreated with `ret_252d` beside the other trailing returns
- [x] `v_top_movers` recreated with `ret_60d` **and** `ret_252d` (60d existed in the table but was
      never exposed, so 3M would have been unrankable)
- [x] `v_anchor_group_detail` recreated unchanged — dropped only to free its dependency
- [x] Applied to Supabase. **Applied with raw SQL, deliberately**: this project has no
      `supabase_migrations.schema_migrations` table (00001–00012 were applied by `psql`), and using
      Supabase's `apply_migration` would have created that table containing only this one file —
      a migration history that lies about where it starts.

### Pipeline

- [x] `pipelines/storage/ports.py` — `ret_252d` in `INDICATOR_COLS` (and therefore in `RECORD_KEYS`)
- [x] `pipelines/indicators/build.py` — `trailing_return(close, 252)` and `FIRST_VALID["ret_252d"] = 252`
- [x] `pipelines/common/upsert.py` — `ret_252d` in the INSERT list, the VALUES list and the
      `DO UPDATE SET`. **This was missed on the first pass and is the whole of §Backfill below.**

### API — `services/api/app/routes/market.py`

- [x] `/api/market/movers` gains `horizon=1d|5d|1m|3m|1y`, filtering and ordering on the **same**
      column, and returns all five returns on every row
- [x] `/api/market/liquidity?limit=` — the same view ordered by `turnover_value`
- [x] `/api/market/index-history?range=` — session-count windows for the fixed ranges, a
      `date_trunc` anchored to the **latest session** for YTD, no window for ALL
- [x] 33 new assertions in `services/api/tests/test_routes.py`

### Frontend — `apps/web`

- [x] Palette swapped Strata → **Terminal**: TradingView's `#131722 / #1e222d / #2a2e39 / #d1d4dc`
      neutrals and its `#089981 / #f23645` directional pair, with every alias NAME kept — which is
      exactly what P11 predicted would make the next swap a ramp edit
- [x] **Two tokens per direction.** `--data-pos/-neg` are the text step; `--data-pos-mark/-neg-mark`
      are TradingView's own colours for strokes, fills and tiles. Measured: `#089981` is 3.57:1 on
      white and fails AA on the 13px mono cells the movers table puts it on in nearly every row
- [x] Roboto 400/500 via `next/font`, and the type scale rewritten so no role asks for 600 — an
      unloaded weight would be synthesised into a faux-bold rather than refused
- [x] `MarketBar` replaces `KpiRow` (deleted): a symbol header with a proportional breadth rule,
      not six equal cards in which the index level and the ticker count weigh the same
- [x] `IndexChart` — area fill closing to the range's **opening level** (marked by a dotted rule),
      right-hand price scale, last-price chip, crosshair reusing `components/charts/ChartHover`
      unchanged, so keyboard parity comes with it
- [x] `MoversTable` — five horizon tabs, direction segment, inline magnitude bar on the **ranked**
      column only, and the ranked column marked structurally rather than by colour
- [x] `LiquidityTable` — share and cumulative share of session turnover; bar is neutral, because
      money traded has no direction and green would have read as "up"
- [x] `SectorTreemap` — viewBox is now the **measured** box, so the map fills its panel at any
      width instead of leaving 90px of dead space beside a taller chart
- [x] 15 new assertions in `apps/web/tests/marketHome.test.ts`

---

## Backfill — two failed attempts, and why they are recorded

The column was added, the formula wired, and `python -m pipelines.indicators.build --storage pg`
run. It wrote nothing useful, twice, for two different reasons.

**Attempt 1 — silent column drop.** `_TECHNICAL_INDICATORS_SQL` in `pipelines/common/upsert.py`
names its 34 columns literally. `ret_252d` was in `INDICATOR_COLS` and in the computed record, and
absent from that SQL, so every row was upserted with its other 30 indicators refreshed and the new
column untouched. `computed_at` advanced; `ret_252d` stayed NULL across 121,014 rows.

`pipelines/storage/localfs.py --selftest` catches this — it compares the SQL's `%(placeholder)s`
set against `RECORD_KEYS` and fails loudly. **It was not run.** `pipelines/indicators/build.py
--selftest` was, and passed, because the record contract is not what that file checks. The guard
worked; the process did not. Both selftests belong in the loop for any change that adds a column.

**Attempt 2 — `executemany`.** With the SQL fixed, the same command took **~7 minutes per ticker**:
psycopg2's `executemany` issues one round trip per row, and 1,424 rows per ticker over a session
pooler to `ap-southeast-2` is 1,424 round trips. Eighty-five tickers projected to roughly ten hours.

**What was done instead.** A one-off script computed `ret_252d` with
`pipelines.indicators.compute.trailing_return` — the same pinned function, imported, not
reimplemented — and wrote that single column with `psycopg2.extras.execute_values`. **42 seconds.**
The formula stayed in its one module; only the transport changed. The script is deliberately not in
the repository: the supported way to recompute indicators is `pipelines.indicators.build`, and a
second faster partial path in `scripts/` would invite use for a job it does not do.

**This leaves a real, unfixed problem.** `pipelines.indicators.build --storage pg` cannot complete a
full-universe rebuild against Supabase in reasonable time. `docs/RUNBOOK.md` §3.5 presents it as a
routine step and it is not one. Switching `upsert.py` to `execute_batch` / `execute_values` would
fix it for every dataset at once and is the obvious follow-up; it is **out of P13's scope** and is
recorded here rather than done quietly as part of a UI change.

**Closed, P15/B1 (2026-08-30).** `pipelines/common/upsert.py`'s six `upsert_*` functions now
submit through `psycopg2.extras.execute_values` (`page_size=500`) instead of `executemany`.
`docs/RUNBOOK.md` §3.5 no longer carries the routine-step warning this paragraph flagged.

---

## Validation

Separated into checks actually performed and checks not attempted, per `CLAUDE.md` §"Rule 5".

### Performed

| Check | Command | Result |
|---|---|---|
| Indicator formulas | `python -m pipelines.indicators.build --selftest` | 17 passed, 0 failed |
| Storage record contract | `python -m pipelines.storage.localfs --selftest` | 12 passed, 0 failed |
| Guard actually fires | column + placeholder removed by hand, selftest re-run | FAILS as designed, naming `ret_252d` |
| API contract | `python -m pytest services/api/tests -q` | 183 passed, 14 subtests |
| Web unit | `npm --prefix apps/web run test` | 57 passed (6 files) |
| Static export | `npm --prefix apps/web run build` | 5 routes exported, lint + types clean |
| `ret_252d` vs independent SQL | `lag(close, 252)` window function over `daily_bars`, full join | **0 null-disagreements**, max abs diff **1.8e-15** across 99,594 values / 85 tickers |
| Live routes | local uvicorn against Supabase | `/index-history?range=3m` → 60 bars; `/movers?horizon=1y` → VIC +244.83%; `/liquidity` → VIC 860.38 tỷ |
| Screen, light + dark | dev server at 1280px, both themes | Panels, chart, crosshair, horizon switch (network shows `horizon=1y`), treemap fill — all correct |
| Dark tokens | computed styles read from the live document | `#131722 / #1e222d / #2a2e39 / #d1d4dc / #5b8dff / #2dbd96 / #ff6b6b` |

### Not attempted

- **Deployed verification.** Nothing has been pushed; both Render services still run the previous
  commit. The API changes are what the new screen needs, so the site will show errors on three
  panels until the API redeploys — the two must go out together.
- **Cross-browser and mobile.** Checked at 1280px in the preview browser only. The `.split` collapses
  to one column at ≤1080px by media query, and that breakpoint has not been looked at.
- **Contrast audit of the whole app.** The Terminal tokens were measured for the pairs this screen
  uses. `/anchors`, `/tickers` and `/about` inherit the new palette and were **not** re-checked;
  they use the same aliases, so nothing should have broken, but "should" is the operative word.
- **`ret_252d` in the local track.** Only Supabase was backfilled. `data/processed/` still holds
  indicator parquet without the column; `pipelines.storage.mirror` would carry it over, and has not
  been run.
