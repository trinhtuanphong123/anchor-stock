# P7 execution plan — technical indicators and the dashboard's aggregate views

> ## CLOSED — moved to `completed/` on 2026-08-29 (P12/F5)
>
> **The header below says "planning only — awaiting review before implementation". That is stale;
> P7 was implemented.** The unticked boxes below are *design specification* bullets, not a
> progress checklist, which is why they never got ticked and why ticking them now would say
> nothing.
>
> **Closed by direct verification of the deliverables on 2026-08-29**, not by trusting the
> successor plan's header: `pipelines/indicators/compute.py` and `build.py` exist;
> `_TECHNICAL_INDICATORS_SQL` is present in `pipelines/common/upsert.py`; `INDICATORS_DAILY` is
> wired through `pipelines/storage/ports.py`; `supabase/migrations/00010_dashboard_views.sql`
> exists; and the live database holds **121,014** rows in `technical_indicators_daily` against
> 121,014 in `daily_bars` — one indicator row per bar.
>
> **Never run, and not claimed:** this plan's three validation rows (`localfs --selftest`
> assertion 1, `indicators --selftest`, the four dashboard views executed with
> `v_sector_performance` reconciling against `v_market_overview`) remain `not attempted` in the
> parent's table. Implementation landing is not the same as its checks having been run.

---


**Started:** 2026-08-18 (planning only — awaiting review before implementation)
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md` — this file is the executable detail of its P7 section.
Progress and Validation are maintained **here**; the parent's P7 checkboxes track completion.
**Predecessor:** `p6-database-landing.md` — DONE, verified-local (commit `d0edf93`)

---

## Why

P6 put the model in the database: 85 tickers, 121,014 daily bars, 120,929 returns, one active
`model_run` (`ae2010a4ad426`), all field-for-field verified. What is *not* there is anything a
user would actually look at. Both reference screens depend on numbers no table currently holds —
the market page needs per-sector daily change and a top-movers table, the ticker page needs a
full technical chart (MA20/MA50/Bollinger/RSI/MACD/volume).

`technical_indicators_daily` (migration `00004`) has held all ~30 columns since P0.5 and has
never had a producer. P7 writes that producer, and adds the four aggregate views the API (P9)
will read.

**Definition of done.** `technical_indicators_daily` populated for all 85 tickers across the full
available history (2020-12-01 → 2026-08-18, ~1,424 sessions each), NULL exactly where history is
insufficient and nowhere else; four new dashboard views executing against real data; every
indicator verified against a closed-form fixture rather than against another implementation of
itself.

## Decisions taken

| # | Decision |
|---|---|
| S1 | **Hand-rolled numpy/pandas**, no `pandas-ta`. It is installed but undeclared (exactly pyarrow's status before D-3), and adopting it would make the library's smoothing defaults an unwritten spec. More importantly it would make verification circular — checking pandas-ta with pandas-ta proves nothing. No cross-check against it either. |
| S2 | **Every ratio column stores a fraction**, not a percent: `0.07` means +7%. One rule for `ret_*`, `dist_from_sma_200_pct`, `drawdown_from_252d_high`, `bb_width_20`. The `_pct` suffix on one DDL column is legacy and does **not** change its unit — stated in the module docstring. Matches `daily_returns.log_return` sitting beside it in the same database. Formatting to "%" happens at the display edge (P9/P10). |
| S3 | **Sector daily change is the equal-weighted mean** of member `ret_1d` — "the average stock in this sector today". Treemap tile *size* still comes from summed turnover. No market-cap data exists, so a cap-weighted alternative is not available. |

### One thing to fix first

The parent plan says P6 records decisions **D-13, D-14, D-16, D-17, D-19**. It did not —
`docs/decisions/` still stops at D-12, and the register table in its `README.md` ends there too.
P6 was reported done without them. **P7.0 writes those five records plus D-15**, from reasoning
already captured in the two plan files, so the register stops lying about what has been decided.
This is P6 residue, not P7 scope, but it is cheap and belongs before new decisions pile on top.

---

## Progress

### P7.0 — Close the decision-record gap

- [ ] Write six records and update the register table in `docs/decisions/README.md`

| # | Decision | Source |
|---|---|---|
| D-13 | Static dashboard — no live-apply path, no orchestration, `live_*` unpopulated | parent plan |
| D-14 | `staging.ohlc_raw` is local-track only; latent bug #5 is a contained, documented divergence | P6 |
| D-15 | **Indicator price basis: adjusted close** (consistent with D-6), stated on the dashboard because an adjusted chart will not match a broker's raw chart across an ex-date | P7 |
| D-16 | The serving universe is the 85, model *and* presentation | P6 |
| D-17 | Sector label source: vnstock `symbols_by_industries()` + a curated ~20-entry industry→bucket table; display/validation only | P6 |
| D-19 | No foreign-flow (khối ngoại) data this pass | parent plan |

D-18 (API surface) belongs to P9 and stays unwritten here.

### P7.1 — Extend the storage port

The one place P7 touches shared code, and the part most able to fail silently.

`pipelines/storage/ports.py`:

- [ ] `Dataset.INDICATORS_DAILY = "technical_indicators_daily"` — the enum value *is* the table
      name for non-raw datasets (`Dataset.table` returns `self.value`), so no other wiring needed
- [ ] `RECORD_KEYS[INDICATORS_DAILY]` — **34 columns in exact DDL order**: `ticker, bar_date,
      source`, the 30 indicator columns, `computed_at`
- [ ] `CONFLICT_KEY` = `("ticker", "bar_date", "source")`
- [ ] `ON_CONFLICT_KEEP` = `frozenset()` — every column is recomputed on a re-run, `computed_at`
      included. Nothing here has `ingested_at`'s "keep the first arrival" semantics
- [ ] `PARTITION_COL` = `"ticker"`
- [ ] **`FLOAT_COLS` += all 30 numeric indicator columns.** This is the trap:
      `localfs._arrow_schema` falls through to `pa.string()` for any name it does not recognise,
      so omitting them writes every indicator to parquet **as a string**, silently, with no
      error. The same set drives `_validate_records`'s finite check, so adding them
      simultaneously buys NaN/inf rejection.

- [ ] `BarSink` Protocol gains `write_indicators(records) -> int`; `LocalSink` delegates to the
      existing `_write_typed`, `PostgresSink` to a new `upsert_technical_indicators`
- [ ] `pipelines/common/upsert.py` gains `_TECHNICAL_INDICATORS_SQL` + its function. The
      `%(name)s` placeholder order **must** equal `RECORD_KEYS` exactly and the `ON CONFLICT`
      tuple must equal `CONFLICT_KEY` — `localfs --selftest` assertion 1 parses this SQL and
      asserts both, so a mismatch fails a check instead of drifting. Add the mapping entry to
      that assertion's `sqls` dict.
- [ ] `pipelines/storage/mirror.py`: `MIRRORED += (INDICATORS_DAILY,)` and the matching
      `_SINK_METHOD` entry

**`read_records` needs no change at all** — P6.4 built it generically from `RECORD_KEYS`, so the
new dataset is readable from both backends the moment the contract tables know about it. That is
the P6 port investment paying off, and it is also what P7.2 reads bars *through*: the older
`daily_bars()` returns only `(date, close, volume)`, and ATR and Stochastic need high/low.

### P7.2 — `pipelines/indicators/`

Two modules, matching the repo's existing split between pure computation and I/O:

- [ ] **`compute.py`** — pure functions over numpy arrays, no I/O, no storage imports: `sma`,
      `ema`, `wilder`, `rsi`, `stochastic`, `atr`, `bollinger`, `obv`, `realized_vol`,
      `trailing_return`, `ytd_return`, `rolling_max`/`rolling_min`. Internally these produce
      `np.nan` for warm-up.
- [ ] **`build.py`** — orchestration, mirroring `pipelines/common/returns.py:compute_return_rows`'s
      shape: `compute_indicator_rows(bars) -> list[dict]`, then
      `run_build_indicators(tickers, *, reader, writer, source) -> BuildIndicatorsResult` shaped
      like `returns/build.py:BuildReturnsResult`. CLI with `--selftest`, `--mock`, `--tickers`,
      `--storage`.

**`np.nan → None` conversion happens once, at the record-building boundary in `build.py`.** Not
optional and not stylistic: `_validate_records` raises on any non-finite value in a `FLOAT_COLS`
column, so a NaN that survives to the sink is a hard stop. Warm-up must be `None`.

#### The exact definitions — the part that most needs review

Ambiguity here is the main risk in P7: "RSI" names a family, not a formula. Every column is
pinned below. Index `i` is 0-based over each ticker's ascending session series; "first valid" is
the smallest `i` producing a non-NULL value. Everything before it is `None`.

**Trend**

| Column | Definition | First valid |
|---|---|---|
| `sma_20/50/200` | mean of `close[i-n+1 … i]` | `i ≥ n-1` |
| `ema_12/26` | α = 2/(n+1); seeded with the SMA of the first `n` closes at `i = n-1`, then `ema = α·close + (1-α)·ema_prev` | `i ≥ n-1` |

**Momentum**

| Column | Definition | First valid |
|---|---|---|
| `macd` | `ema_12 - ema_26` | `i ≥ 25` |
| `macd_signal` | 9-period EMA of `macd`, α = 2/10, seeded with the mean of the first 9 macd values | `i ≥ 33` |
| `macd_hist` | `macd - macd_signal` | `i ≥ 33` |
| `rsi_14` | **Wilder.** First `avg_gain`/`avg_loss` = simple mean of the first 14 up/down close changes at `i = 14`; thereafter `avg = (avg_prev·13 + current)/14`. `RSI = 100 - 100/(1 + avg_gain/avg_loss)` | `i ≥ 14` |
| | **Edge:** `avg_loss == 0` → **exactly `100.0`**, never a division producing `inf`/NaN | |
| `stoch_k_14` | `100 · (close - min(low[i-13…i])) / (max(high[i-13…i]) - min(low[i-13…i]))` | `i ≥ 13` |
| | **Edge:** denominator `== 0` (flat 14-session range) → **exactly `50.0`** | |
| `stoch_d_14` | 3-period SMA of `stoch_k_14` | `i ≥ 15` |

**Volatility**

| Column | Definition | First valid |
|---|---|---|
| `atr_14` | **Wilder.** `TR = max(high-low, abs(high-close_prev), abs(low-close_prev))`, defined from `i ≥ 1`. First ATR = mean of `TR[1…14]` at `i = 14`; Wilder smoothing thereafter | `i ≥ 14` |
| `bb_mid_20` | `= sma_20` | `i ≥ 19` |
| `bb_upper_20` / `bb_lower_20` | `mid ± 2σ`, σ = **population** std (`ddof=0`) of `close[i-19…i]` | `i ≥ 19` |
| `bb_width_20` | `(upper - lower) / mid` = `4σ/mid`, a fraction | `i ≥ 19`, `mid > 0` else `None` |
| `realized_vol_20d/60d` | `std(log_return[i-n+1…i], ddof=1) · √252`, log returns from close | `i ≥ n` |

**Volume**

| Column | Definition | First valid |
|---|---|---|
| `obv` | cumulative `+volume` when `close > close_prev`, `-volume` when `<`, `0` when equal; running total starts at 0 | `i ≥ 1` (no prior close at `i=0`) |
| `volume_sma_20` | mean of `volume[i-19…i]` | `i ≥ 19` |
| `turnover_value` | `close · volume` | `i ≥ 0` |

**Returns — fractions (S2)**

| Column | Definition | First valid |
|---|---|---|
| `ret_1d/5d/20d/60d` | `close[i] / close[i-n] - 1` | `i ≥ n` |
| `ret_ytd` | `close[i] / (last close of the previous calendar year) - 1` | `None` when the loaded history holds no prior-year session |

`ret_1d` is a **simple** return, deliberately unlike `daily_returns.log_return` beside it in the
database: this one is for display, and a screen reading "+7.00%" must be the simple figure.

**Position within the recent range**

| Column | Definition | First valid |
|---|---|---|
| `dist_from_sma_200_pct` | `close / sma_200 - 1` — a fraction despite the suffix (S2) | `i ≥ 199` |
| `high_252d` / `low_252d` | `max(high[i-251…i])` / `min(low[i-251…i])` — true intraday extremes | `i ≥ 251` |
| `drawdown_from_252d_high` | `close / high_252d - 1`, so `≤ 0` | `i ≥ 251` |

Intraday `high`/`low` are safe to depend on: **all 139,477 collected bars have non-null
open/high/low/close/volume** (verified directly across all 100 shards during planning), so
neither ATR, Stochastic, nor the 252-day extremes will propagate NULLs from missing inputs. If
that ever stops holding, the rule is a NULL window → NULL indicator, never a substituted close.

### P7.3 — Dashboard aggregate views

- [ ] New migration `supabase/migrations/00010_dashboard_views.sql`

Keeps P9's "the API reads views, not ad-hoc SQL" guard rail structural rather than scattering
aggregation through routers.

| View | Feeds | Shape |
|---|---|---|
| `v_market_overview` | KPI row, image 1 | one row: session date, n_tickers, total turnover, total volume, advancers / decliners / unchanged, VNINDEX close and its `ret_1d` |
| `v_sector_performance` | "Diễn biến ngành" treemap | per sector: n_tickers, **equal-weighted mean `ret_1d`** (S3), summed turnover for tile size |
| `v_top_movers` | "Top 10 cổ phiếu…" table | per ticker: mã, tên, ngành, KL GD, GT GD, `ret_1d` — **unordered and unlimited**; the API applies direction and limit |
| `v_anchor_group_detail` | `/anchors/[anchor]` page | per (anchor, member): member ticker, sector, `coverage_c`, `is_anchor`, plus the member's latest `ret_1d` |

All four resolve "today" as `(SELECT max(bar_date) FROM daily_bars)` — a view takes no
parameters, and the alternative (a hard-coded date) would go stale silently. The three
model-aware ones join through `v_active_model_run` so "which run am I looking at" keeps one
answer, and `v_top_movers` builds on the existing `v_latest_indicators` (migration `00009`)
rather than re-deriving "latest row per ticker".

A NULL `sector` stays NULL in the view. `"Khác"` remains a rendering choice at the edge — the
same rule P6.3 set for `stocks.sector` itself.

### P7.4 — Verification approach

Closed-form fixtures, never a second implementation of the same formula. Each is a series whose
correct answer is known by construction:

| Check | Fixture |
|---|---|
| SMA | linear ramp `close[i] = a + b·i` → `sma_n[i] = close[i] - b·(n-1)/2`, exactly |
| EMA | short series checked against the explicit recursion, term by term |
| MACD identity | `macd == ema_12 - ema_26` — asserted on **real data**, all 85 tickers, every row |
| RSI | strictly increasing series → exactly `100.0`; strictly decreasing → exactly `0.0` |
| RSI edge | a series with zero losses must give `100.0`, not `inf`/NaN |
| ATR | series engineered with constant true range → ATR equals that constant |
| Bollinger | constant series → `σ = 0`, `upper == lower == mid`, `bb_width == 0` |
| Stochastic | `close == max(high)` over the window → `k = 100`; `close == min(low)` → `k = 0`; flat range → `50.0` |
| OBV | alternating up/down series → hand-computed running total |
| Warm-up | every column NULL at `i < first_valid` and non-NULL at `i == first_valid` — the definition tables above, asserted mechanically |
| `ret_ytd` | a two-year synthetic series across a year boundary |
| No NaN escapes | assert no record reaching the sink holds a non-finite value (belt-and-braces over `_validate_records`) |

---

## Validation

Repo idiom: `main()` / `--selftest` / `--mock` per module, plus checks against the live
container. **Record what was actually run, and say plainly what was not.**

| # | Check | Status |
|---|---|---|
| 1 | `python -m pipelines.storage.localfs --selftest` — **assertion 1 is the one that matters**: it parses `upsert.py`'s new SQL and asserts placeholder order == `RECORD_KEYS` and conflict tuple == `CONFLICT_KEY` | not attempted |
| 2 | `python -m pipelines.storage.pg --selftest` — `read_records` still contract-clean with the new dataset present | not attempted |
| 3 | `python -m pipelines.storage.mirror --selftest` — five datasets now, routing still correct | not attempted |
| 4 | `python -m pipelines.indicators.build --selftest` — the whole P7.4 fixture table | not attempted |
| 5 | Live compute for all 85 over full history; report rows written and, per column, the NULL count and first non-NULL index — compared against the "first valid" column of the definition tables, not eyeballed | not attempted |
| 6 | Parquet dtype check: read one shard back and assert every indicator column is `float64`, **not** `string` — the `FLOAT_COLS` trap, caught explicitly rather than trusted | not attempted |
| 7 | `macd == ema_12 - ema_26` on every written row, real data | not attempted |
| 8 | Mirror to Postgres; row counts equal local↔pg; a sampled `read_records` returns `float`, never `Decimal` | not attempted |
| 9 | `00010` applies to the live container; all four views **execute** (not merely parse) | not attempted |
| 10 | `v_sector_performance` reconciles with `v_market_overview`: summed per-sector `n_tickers` == 85, summed turnover == the overview's total | not attempted |
| 11 | `v_top_movers` sanity: the top row's `ret_1d` matches that ticker's `technical_indicators_daily` row for the same date | not attempted |
| 12 | Regression sweep: `ruff check .`, import sweep, `compileall`, `artifact.inspect --selftest`, `artifact.load --selftest`, `test_runtime_guards` | not attempted |

---

## Traps

- **`FLOAT_COLS` is load-bearing and fails silently.** Omit a column and it becomes a parquet
  string with no error at write time and no error at read time — it surfaces much later as a
  chart that will not plot. Check 6 exists solely for this.
- **NaN must become `None` before the sink**, in one place. `_validate_records` will raise
  otherwise, which is the good outcome; the bad one is scattering the conversion across thirty
  call sites.
- **Two sectors have only two tickers each** (Công nghệ = CMG, FPT; Công nghiệp = PTB, GEX, from
  P6's live distribution). An equal-weighted "sector performance" over two names is an average of
  two stocks, and the treemap will show it with the same visual authority as the 24-ticker Bất
  động sản tile. Worth a caveat on screen in P10.
- **The views return zero rows until P7.2 has actually run.** `v_market_overview` and friends
  join `technical_indicators_daily`; applying `00010` before computing indicators produces an
  empty dashboard that looks like a bug and is not one.
- **`bb_width_20` and `dist_from_sma_200_pct` divide.** Both need an explicit `mid > 0` /
  `sma_200 > 0` guard returning `None`, not an `inf` that `_validate_records` will reject at the
  end of a long compute.
- **Re-running is safe by construction** — the conflict key is `(ticker, bar_date, source)` and
  every column is in the `DO UPDATE SET`. A recompute overwrites cleanly. No stale-shard problem
  exists here because the dataset is new, but a future `RECORD_KEYS` addition would reintroduce
  P3's `LocalSink._merge` `KeyError` trap.

---

## Progress — **DONE**, verified local + local Postgres container

Executed 2026-08-18, in the order below. Supabase promotion deliberately skipped (see
"Deferred", last section) — everything else in the plan is built and checked.

### P7.0 — Decision records — **DONE**

Six records written from the reasoning already captured in the two plan files, plus the register:

| Record | File |
|---|---|
| D-13 static dashboard | `docs/decisions/D-13-static-dashboard.md` |
| D-14 `staging.ohlc_raw` local-only | `docs/decisions/D-14-staging-raw-local-only.md` |
| D-15 indicator price basis: adjusted | `docs/decisions/D-15-indicator-price-basis.md` |
| D-16 one serving universe | `docs/decisions/D-16-serving-universe.md` |
| D-17 sector label source | `docs/decisions/D-17-sector-label-source.md` |
| D-19 no foreign-flow data | `docs/decisions/D-19-no-foreign-flow-data.md` |

`docs/decisions/README.md` gains all six rows plus a D-18 **OPEN** row (P9), and a short note
saying these were written a phase late and why.

D-16 was written slightly wider than the plan sketched it: it records *"there is one serving
universe and it is the model's"* as the decision, and *which* tickers are in it as explicitly
**not** decided — see "Universe rebalancing" below.

### P7.1 — Storage port — **DONE**

| File | Change |
|---|---|
| `pipelines/storage/ports.py` | `Dataset.INDICATORS_DAILY`; new exported `INDICATOR_COLS` (the 30 numeric columns in DDL order); `RECORD_KEYS` entry built from it (34 columns); `CONFLICT_KEY`; `ON_CONFLICT_KEEP = frozenset()`; `PARTITION_COL`; `FLOAT_COLS` extended by splatting `INDICATOR_COLS`; `BarSink.write_indicators` |
| `pipelines/common/upsert.py` | `_TECHNICAL_INDICATORS_SQL` + `upsert_technical_indicators`, generated *from* `RECORD_KEYS` so placeholder order could not drift by hand |
| `pipelines/storage/pg.py` | `PostgresSink.write_indicators` delegates verbatim; the empty-input selftest now covers it |
| `pipelines/storage/localfs.py` | `LocalSink.write_indicators` delegates to `_write_typed`; **assertion 1's `sqls` dict gains the new dataset** |
| `pipelines/storage/mirror.py` | `MIRRORED += INDICATORS_DAILY` (last, because it derives from `daily_bars`), `_SINK_METHOD`, fake sink, routing check |

`read_records` needed no change, exactly as the plan predicted.

**The `FLOAT_COLS` trap is handled by construction, not by discipline.** Rather than typing
thirty column names twice, `INDICATOR_COLS` is defined once and both `RECORD_KEYS` and
`FLOAT_COLS` derive from it, so the two cannot disagree. Validation 6 still checks the outcome
independently rather than trusting the construction.

### P7.2 — `pipelines/indicators/` — **DONE**

`compute.py` (pure numpy, no storage import) and `build.py` (records, runner, CLI, 17-check
selftest). Every formula in the plan's definition table is implemented as specified, including
all four edge cases: `avg_loss == 0` gives exactly `100.0`, a flat stochastic range gives exactly
`50.0`, and `mid <= 0` / `sma_200 <= 0` give `None`.

Two things the plan left implicit and this pass pinned:

- **`FIRST_VALID`** — the plan's "first valid" column, lifted into a module constant in
  `build.py` and asserted mechanically by `first_valid_report()`, in the selftest *and* on live
  data. An off-by-one warm-up is invisible in a chart and permanent in a database.
- **`_signal()`** seeds the MACD signal EMA over the *valid* stretch of the MACD line. Seeding
  over the whole array feeds it 25 NaNs and makes `macd_signal` NaN forever, silently.

`compute_indicator_rows` cross-checks its own column set against `ports.INDICATOR_COLS` and
raises on drift, so adding a column to the DDL without adding a formula fails loudly.

### P7.3 — Dashboard views — **DONE**

`supabase/migrations/00010_dashboard_views.sql` — **five** views, not four. `v_latest_session`
was factored out so `(SELECT max(bar_date) FROM daily_bars)` has one definition rather than four
copies that could drift apart.

`v_market_overview` also publishes **`n_with_return`**, and `v_sector_performance` publishes
`n_tickers` *and* `n_with_return`, because `avg()` skips NULLs and the mean's real denominator
should not have to be inferred. That is also the number P10's two-ticker-sector caveat needs.

The index columns in `v_market_overview` resolve their symbol through `v_active_model_run`, so no
`'VNINDEX'` literal appears anywhere; with no active run they are NULL and the rest of the row
still returns.

## Validation

| # | Check | Result |
|---|---|---|
| 1 | `python -m pipelines.storage.localfs --selftest` | **PASS** — 12/12. Assertion 1 parses the new SQL: placeholder order == `RECORD_KEYS`, conflict tuple == `CONFLICT_KEY`, omitted-column set == `ON_CONFLICT_KEEP` (empty) |
| 2 | `python -m pipelines.storage.pg --selftest` | **PASS** — 11/11 |
| 3 | `python -m pipelines.storage.mirror --selftest` | **PASS** — 5/5, five datasets, routing correct |
| 4 | `python -m pipelines.indicators.build --selftest` | **PASS** — 17/17: every fixture in the P7.4 table plus the parquet round-trip |
| 5 | Live compute, 85 tickers, full history | **PASS** — 121,014 rows (equal to `daily_bars`), 2020-12-01 to 2026-08-18. Every column's NULL count is **exactly 85 x its `FIRST_VALID`** (`sma_200` 16,915 = 85x199; `high_252d` 21,335 = 85x251; `turnover_value` 0). `first_valid_report` reported **0 warm-up mismatches** across all 85 tickers |
| 6 | Parquet dtypes | **PASS** — 85 shards x 30 columns, all `double`. Checked, not trusted |
| 7 | `macd == ema_12 - ema_26` | **PASS** — 118,889 rows, 0 violations. `macd_hist == macd - macd_signal` also holds on every row |
| 8 | Mirror to Postgres, local vs pg | **PASS** — 121,014 read, 121,014 submitted, 0 empty keys. Sampled 8 tickers: 0 `Decimal` leaks, 0 NULL-pattern mismatches, **max abs(pg - local) = 0.0** across every indicator value |
| 9 | `00010` applies; all views **execute** | **PASS** — 5 views created on the live container; all five queried and returning rows |
| 10 | `v_sector_performance` reconciles with `v_market_overview` | **PASS** — sum of `n_tickers` = 85; sum of `total_turnover` = 8,352,129,774.00000004, matching the overview digit for digit; 9 sectors, no NULL group |
| 11 | `v_top_movers` sanity | **PASS** — 85 rows, one distinct `bar_date`; the top row (PLX, +6.90%) equals its own `technical_indicators_daily` row |
| 12 | Regression sweep | **PASS** — `ruff check .` clean; 50/50 modules import; `compileall` clean; `artifact.inspect` 16/16, `artifact.load` 6/6; `test_runtime_guards` 64/64 |

### One check worth more than the twelve

`ret_1d` was cross-checked against `daily_returns`, which a *different module*
(`pipelines.common.returns`) computed from the same closes:

```
max |ret_1d - (close/prev_close - 1)|  = 3.34e-16   over 120,929 rows
max |ret_1d - (exp(log_return) - 1)|   = 6.0e-17    over 120,929 rows
```

Machine precision. This is the one verification in P7 that is not a fixture — an independent
implementation agreeing to the last representable bit — and it is what pins the adjusted-close
chain end to end (D-15).

## Universe rebalancing — what this phase deliberately did NOT fix

The uneven sector distribution is real and is confirmed on the live data:

| Sector | n |
|---|---|
| Bat dong san va Xay dung | 24 |
| Tai chinh | 19 |
| Nguyen vat lieu / Dich vu | 11 each |
| Hang tieu dung | 6 |
| Nong nghiep / Nang luong | 5 each |
| **Cong nghe / Cong nghiep** | **2 each** |

**P7 does not rebalance the list, and does not need to be revisited when someone does.** Nothing
built in this phase knows the number 85, any ticker symbol, or any sector name:

- the CLI resolves tickers through `resolve_universe` / `--universe`, the same path every other
  stage uses;
- `00010_dashboard_views.sql` contains **no ticker, no count, no sector literal, and no date** —
  every aggregate is computed from whatever rows exist, and "today" is
  `(SELECT max(bar_date) FROM daily_bars)`;
- `v_sector_performance` groups by whatever `stocks.sector` holds, so new sectors appear on the
  treemap with no migration.

Replacing `list_stocks_research.txt` and re-running the pipeline is therefore a **data change**.
It produces a new `universe_version` (a content hash) and hence a new artifact, which is correct:
a different universe is a different study, and D-12's coverage derivation has to be re-run
against the new list. The re-run sequence is P8's runbook; P7's own contribution to it is one
command, `python -m pipelines.indicators.build --universe <file>`.

What P7 *does* contribute to the problem is the number needed to caveat it honestly:
`v_sector_performance.n_with_return` puts "this average is two stocks" on the record, for P10 to
put on screen.

## Supabase promotion — **DONE**, 2026-08-18

Promoted after the local verification above, once `DATABASE_URL` was filled in. Region
**ap-southeast-2 (Sydney)**, PostgreSQL 17.6, session pooler on 5432.

### How, and why not the pipeline

Measured round-trip to the pooler: **~175 ms per statement**. `pipelines/common/upsert.py` uses
`cur.executemany`, which psycopg2 sends as one round-trip per row — so mirroring 368k rows
through the pipeline would have taken **~18 hours**. The transfer was done with
`pg_dump --data-only | psql` instead (both inside the `datn_pg` container, so only the COPY
stream crosses the network), table by table in explicit parent-before-child order:

    stocks -> universe_snapshots -> universe_members -> trading_calendar
    -> market_index_bars -> index_returns -> daily_bars -> daily_returns
    -> technical_indicators_daily
    -> model_runs -> model_universe -> model_ticker_params -> model_groups
    -> model_anchors -> model_similarity_full -> model_similarity_anchor

Explicit order because `pg_dump --data-only` sorts by table name, not by FK dependency, so a
whole-database dump violates `stocks <- daily_bars` on restore.

**This is a one-off, not the documented path.** P8's runbook should still specify the pipeline
(`mirror --run`, `indicators.build --storage pg`) — it is what proves the two-track promise that
flipping the sink is the only difference. Making that path usable over a real network needs
`psycopg2.extras.execute_batch` in `pipelines/common/upsert.py`: a contained change to the five
helpers, and the difference between 18 hours and minutes. **Carry it into P8.**

### Verification on Supabase — not inferred from the local run

| Check | Result |
|---|---|
| 10 migrations, `ON_ERROR_STOP=1` | **PASS** — applied to an empty `public` schema (0 tables before); only notice was `pgcrypto` already present |
| Row counts, 16 tables | **PASS** — every table equals local exactly (121,014 / 120,929 / 121,014 / 1,424 / ...) |
| `staging.ohlc_raw` | **PASS** — 0 rows; D-14 held across the promotion |
| All 9 views execute | **PASS** — 1 / 85 / 10 / 85 / 1 / 1 / 9 / 85 / 85 rows |
| Check 7, macd identity | **PASS** — 118,889 rows, 0 violations |
| Check 8, `read_records` types | **PASS** — 1,424 records for VCB, key order == `RECORD_KEYS`, 0 `Decimal` leaks, 0 non-float values |
| Check 10, sector vs overview | **PASS** — n_sum 85 = 85; turnover 8,352,129,774.00000004 both sides, digit for digit |
| Check 11, top movers | **PASS** — PLX +6.9014% equals its own `technical_indicators_daily` row |
| Warm-up NULL counts | **PASS** — 30 columns, all exactly 85 x `FIRST_VALID`, 0 mismatches |
| `ret_1d` vs `daily_returns` | **PASS** — 3.34e-16 and 6.0e-17 over 120,929 rows, same as local |

Database size **105 MB of the 500 MB free tier** — `technical_indicators_daily` 55 MB,
`daily_bars` 20 MB, `daily_returns` 18 MB. Headroom is fine; a second measure or a wider
universe would need re-checking.

### One finding the promotion surfaced — needs a decision in P9

**Every table is world-readable through the Supabase REST API.** Verified, not assumed:

- RLS is enabled on **0 of 26** tables. Our migrations are plain SQL and never enable it.
- The `anon` role has `SELECT` on **35 relations** (all 26 tables plus all 9 views), via
  Supabase's default grants on `public`.
- `public` is an API-exposed schema, so PostgREST serves exactly those.

The `anon` key is public by design — it ships in the browser bundle — so this means
`model_ticker_params`, `model_similarity_full` and every other artifact table can be read by
anyone with the project URL. The price data is not secret; **the frozen parameter set being
public is a choice, and right now it is an accidental one.**

**Resolved the same day as [[D-20]], by explicit instruction: revoke.**
`supabase/migrations/00011_revoke_api_roles.sql` takes every privilege, the schema `USAGE`, and
the default privileges for future objects away from `anon` and `authenticated`; `services/api`
will connect as `postgres`. The migration is a guarded no-op on the local container, so
`apply_migrations.ps1` is unaffected.

Two things that pass reads badly and are recorded in D-20 rather than in this plan: revoking the
role's own schema `USAGE` does **not** remove it (the grant is inherited from `PUBLIC`, and the
first pass measured usage still `true` with table privileges already at 0), and
`ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin` is denied to `postgres` on hosted Supabase.

Verified after the revoke: both roles at schema usage `false` and 0 of 35 relations for SELECT/
INSERT/UPDATE/DELETE/TRUNCATE; a table created as `postgres` *after* the migration is unreachable
by them (tested with a real throwaway table, not inferred from the ACL); and all 12 P7 checks
still pass unchanged. D-18 stays OPEN for the API's route surface.

## Deferred

- **The `LocalSink(root=...)` no-op** found in P6.1 is still a no-op, so
  `pipelines.indicators.build` routes its selftest temp directory through `$DATN_DATA_ROOT` like
  every other module rather than through the constructor argument. Pre-existing, out of scope,
  already tracked.

## Out of scope for P7

The runbook (P8), API routes (P9), dashboard screens (P10). Foreign-flow data (D-19). Any
indicator not already declared in `00004`. `docs/01`–`04`
remain the specification, and where code disagrees the spec wins.
