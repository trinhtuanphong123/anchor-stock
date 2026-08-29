# P6 execution plan — land the 2025 anchor set in Postgres

> ## CLOSED — moved to `completed/` on 2026-08-29 (P12/F5)
>
> **Closed by:** the plan's own header already read **DONE** (verified-local, commit `d0edf93`).
> Confirmed against the live database on 2026-08-29: `stocks` = 85, `daily_bars` = 121,014,
> artifact `ae2010a4ad426` loaded and active, `v_active_model_run` returning exactly one row.
>
> **The one item this plan recorded as deferred has since happened elsewhere.** P6.5's
> "Supabase promotion — not attempted (S2, no credential held)" was closed by a later phase, not
> by P6: Supabase now holds the full schema and data and is what Render reads. It is recorded
> here so the deferral is not read as still open, and *not* re-ticked inside P6, because P6 is
> not what did it.
>
> Checkboxes are left exactly as they were. Nothing below was retro-ticked.

---


**Started:** 2026-08-18
**Status:** **DONE** — verified-local complete (S2: Supabase promotion deliberately deferred,
needs a credential not held in this session)
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md` — this file is the executable detail of its P6 section.
Progress and Validation are maintained **here**; the parent's P6 checkboxes track completion.

---

## Why

P0–P5 produced ten validated artifacts on disk and nothing that reads them. P6 is the phase
that makes one of them reachable: bring up Postgres, populate reference data and market data
for the 85-ticker research universe, load the published 2025 parameter set, and prove the load
lossless. P7–P10 (indicators, runbook, API, dashboard) all read what P6 writes, so every later
phase is blocked on this one.

**The target artifact is fixed and known:**

```
artifact_id        ae2010a4ad426
scope              year / 2025          is_primary = true
measure            pearson_rho2
universe_version   u27ba69c4            = list_stocks_research.txt (85 tickers)
window             2025-01-02 → 2025-12-31,  prior_close 2024-12-31,  T = 249
k = 10, k_max = 15, tau = 0.10           F(S) = 22.349,  F̄ = 0.2629,  |U_τ| = 33
S                  VIC IDI PDR PVT HCM SZC HSG DCM CMG VIB
```

**Definition of done.** A named local Postgres container holds the 85 tickers, their bars and
returns through the collection date, exactly one active `model_run`, and
`inspect --from-db ae2010a4ad426` reports field-for-field equality with the on-disk artifact.
Supabase promotion is deliberately **not** part of P6.

## Decisions taken

| # | Decision |
|---|---|
| S1 | Local Postgres is a **named container with a docker volume** that survives between sessions — P9/P10 need a database that still holds data. Not the throwaway pattern P0 used. |
| S2 | **P6 ends at verified-local.** Supabase promotion is a separate gated step, run when a real `DATABASE_URL` is supplied. Same migrations, same loaders, no new code. |
| S3 | `stocks.sector` uses the **nine Vietnamese buckets** of the reference design (Tài chính, Bất động sản và Xây dựng, Nguyên vật liệu, Năng lượng, Công nghệ, Công nghiệp, Dịch vụ, Hàng tiêu dùng, Nông nghiệp). `stocks.industry` carries the finer provider label for the ticker page. |

---

## Two findings that changed this plan

**1. Latent bug #3 does not exist any more.** The parent plan carries it forward from P2 as
"staging-vs-typed HWM frontier — not verified done." `pipelines/ingestion/fetch.py`'s module
docstring states plainly: *"No high-water mark drives either pass."* D-6 established that
vnstock re-anchors its adjusted series to the present, so `fetch.py` re-fetches the whole
window every run by design, and the modules that carried the bug (`daily.py`, `index_bars.py`)
were archived in P2. **Nothing to fix — strike the item and record why.**

Latent bug #5 (`staging.ohlc_raw.provider` filled by a schema default no record supplies) is
real but now unreachable: D-14 says raw is never mirrored to Postgres. Fixing it means adding a
key to `RECORD_KEYS[RAW_*]` and rewriting 101 local `.jsonl.gz` files for a column no consumer
reads. **Document it in D-14 as a known, contained divergence rather than churn the raw record
shape.**

**2. The adjustment basis is a display problem, not a model problem.** The shards on disk were
fetched 2026-08-17. Fetching 2026 data today appends rows anchored to a *different* adjustment
basis if any corporate action landed in between. D-6's invariance argument
(`ln(a·P_t / a·P_{t−1}) = ln(P_t/P_{t−1})`) makes that harmless to returns and therefore to the
model — but the dashboard charts **price levels**, where a spliced basis is a visible fake jump.

So P6.1 **measures instead of assuming** — the same idiom that closed D-6 with four
measurements rather than an assertion:

- Overlap matches → append 2026 only. The frozen 2020–2025 shards stay untouched, which also
  preserves the ability to demonstrate reproducibility live: `model.train --window 2025` still
  yields `ae2010a4ad426` from the data on disk, a demo an examiner may well ask for.
- Overlap differs → re-fetch the **full** `2020-12-01 → today` for one coherent basis, and
  record in D-6 that a re-adjustment was observed, naming the affected tickers.

---

## Progress

Ordering differs from the parent plan's sketch for one reason: `trading_calendar` derives from
`market_index_bars`, so it cannot precede the data load. Reference data splits accordingly.

### P6.0 — Groundwork — **DONE**

| File | Change |
|---|---|
| `requirements.in` | `vnstock>=3,<4` → `==4.0.4` **exact pin**, not a range — `provider.py`'s docstring documents three behaviors (row-overshoot, SystemExit-not-Exception, the 3.x→4.x default-source change) verified by direct probing against 4.0.4 specifically; vnstock carries no semver contract for any of it |
| `requirements.lock` | Regenerated for real in a disposable `python:3.13-slim` container (`pip-tools==7.5.3` needs `pip==24.3.1`, newer pip removed an internal symbol it imports) — not hand-noted. Verified: `pip install -r requirements.lock` in a fresh container resolves clean and every P2 import path (`vnstock.api.quote.Quote`, `vnstock.Quote`, `vnstock.api.listing.Listing`) works |
| `AGENTS.md` | "This directory is not a git repository" → states the real `origin` and history start point |
| `scripts/db/compose.db.yml` | Named `postgres:17-alpine` service (`datn_pg`) + named volume `datn_pg_data`, host port 55432 (5432 already taken by a local Postgres 18 install) |
| `scripts/db/apply_migrations.ps1` | Applies all 9 migrations under `ON_ERROR_STOP`, non-recursive so `_archive/` is excluded |
| `scripts/db/verify_schema.ps1` + `verify_schema.sql` | Counts + **executes** all 4 views + presence-checks `REQUIRED_TABLES` |
| `.env.example` | New — the real, current env surface (grepped from `os.environ` usage), replacing the stale ClusterWeb-era `.env` as the reference |

**Trap avoided, worth remembering:** the two `.ps1` scripts initially used em-dashes (—); Windows PowerShell 5.1 misreads UTF-8-without-BOM em-dashes as broken tokens and fails to parse the *entire file*, silently skipping even the `docker compose up` line before it. Fixed by keeping `.ps1` files ASCII-only. Python `.py` files are unaffected (PEP 3120 UTF-8 source default) — only `.ps1` needs this care.

Latent bug #3 struck (the code that carried it, `daily.py`/`index_bars.py`, was archived in P2; `fetch.py`'s own docstring states "No high-water mark drives either pass" by design). Latent bug #5 folded into D-14 as a documented, contained divergence — not fixed, since fixing it would mean rewriting 101 local raw shards for a column P6 never reads (raw is never mirrored).

### P6.1 — Local data refresh — **DONE**

- [x] **Overlap probe.** Attempted as planned (scratch `LocalSink(root=…)`/`LocalSource(root=…)`
      pointed at a temp dir) — but **the probe accidentally wrote into the real repo `data/`
      instead of the scratch directory**, because `LocalSink`/`LocalSource`'s `root=` constructor
      argument is a latent no-op: every read/write method calls the module-level
      `raw_path()`/`shard_path()` helpers, which resolve only through `$DATN_DATA_ROOT`, never
      through `self._root`. Flagged as a separate background task
      (`task_c8194ced`, not fixed here — out of scope for P6, pre-existing bug). The silver
      lining: this gave a *stronger* answer than planned — a direct, full-universe comparison
      against production itself, not a scratch copy. **Result: 0 mismatches across all 86
      symbols** for the entire December-2025 window (compared against the pre-existing
      `daily_returns`/`index_returns` shards, untouched by the probe). Adjustment basis
      unchanged → append-2026-only was safe, confirmed rather than assumed.
- [x] **Fetch.** `2026-01-01 → 2026-08-18` (today), 85 tickers + VNINDEX, `source="VCI"`. Result:
      **86/86 OK, 0 failed, 0 empty, success_ratio=1.0, 13,244 rows written.**
      `data/research/fetch_p6.json` written.
- [x] **Rebuild returns.** Initially skipped on the (wrong) assumption that the existing
      `daily_returns` shards already covered the new dates — they did not: `run_fetch` writes
      `daily_bars`/`index_bars` only, `daily_returns`/`index_returns` are a separate derived
      computation. Caught before it reached the database, by checking the actual max date on
      disk rather than trusting the assumption (`daily_bars` at 2026-08-18, `daily_returns`
      still at 2025-12-31). Fixed: `run_build_returns(tickers=<85>,
      index_symbols=["VNINDEX"])` — **85/85 tickers succeeded, 0 failed**, 120,929 ticker-return
      rows, 1,423 index-return rows, `overall_status=succeeded`. Re-ran the mirror afterward
      (idempotent, harmless) so Postgres picked up the extension. Boundary continuity confirmed
      directly: VCB's 2026-01-05 row has `prev_close=57.02`, exactly `2025-12-31`'s `close` —
      no gap at the year seam.

Reused as-is: `ingestion/fetch.py:run_fetch`, `universe/file.py:read_universe_file`.

### P6.2 — Database bring-up — **DONE**

- [x] Container `datn_pg` up, all 9 migrations applied cleanly, `verify_schema.ps1` green:
      **27 tables (26 public + 1 staging), 4 views (all executed, not just parsed), 65 CHECKs,
      26 FKs, 27 PKs, 6 UNIQUEs, 63 indexes** — matches the P0 container's numbers exactly.
- [x] `python -m pipelines.common.db --check-schema-files` — **PASS**, 27/27 required tables

### P6.3 — Reference data — **DONE**

New module: **`pipelines/universe/sync.py`**, plus **`pipelines/artifact/load.py`**,
**`pipelines/artifact/activate.py`**, **`pipelines/storage/mirror.py`** (P6.4/P6.5, folded into
this session — see below).

- [x] `sync_stocks` / `sync_universe_snapshot` / `sync_universe_members` / `derive_trading_calendar`
- [x] Sector derivation: `probe_sectors()` (vnstock) + `write_sector_map_csv()` +
      `load_sector_map()`. **Real finding, not the anticipated one:** vnstock's fine-grained
      `symbols_by_industries()` matched all **85/85** research tickers with zero misses, so the
      planned CSV-fallback path was never exercised — but a small (~20-label), hand-curated
      `industry_name → 9-bucket-sector` table was still needed, since vnstock's own
      `industries_icb()` (the coarse hierarchy) is unimplemented on the installed KBS source.
      **Live sector distribution across the 85** (a number, not "done"): Bất động sản và Xây
      dựng 24, Tài chính 19, Nguyên vật liệu 11, Dịch vụ 11, Hàng tiêu dùng 6, Nông nghiệp 5,
      Năng lượng 5, Công nghệ 2, Công nghiệp 2 — sums to 85, all nine buckets populated.
- [x] Live sync run: `universe_version=u27ba69c4, n_tickers=85, n_stocks_upserted=85,
      snapshot_inserted=True, n_members=85, n_with_sector=85, n_without_sector=0`

**A second, larger real finding, found only by running against the live provider:**
`pipelines/ingestion/vnstock_listing.py`'s `VnstockListingSource.fetch()` called
`Listing().all_symbols()`, which on the installed vnstock 4.0.4 (KBS source) returns **only**
`symbol`/`organ_name` — no `exchange` column at all. `validate_listing_response`'s fail-closed
design (by intent — "no partial acceptance") then rejected *every* row for "unknown or missing
exchange", so `run_universe_sync` failed outright on the first live attempt. Root-caused and
fixed: switched to `Listing().symbols_by_exchange()`, filtered to `type == 'stock'` (that
filter matters — the unfiltered response also carries bonds/funds/futures, one of which
["XHNF", futures] would otherwise have tripped the very same fail-closed exchange check for an
unrelated reason). Filtered row count matches `all_symbols()`'s old total exactly (1528 both
ways) — same equity universe, correct column now present. Three now-stale docstring references
to `all_symbols()` updated in the same commit. No other code in the repo referenced the old
method name (verified by grep; no dedicated test file existed for this module).

### P6.4 — Port extension, mirror, and calendar — **DONE**

**The port extension is the load-bearing design decision of P6.** `LocalSource.daily_bars()`
returns `(date, close, volume)` — three of the eleven columns in `RECORD_KEYS[DAILY_BARS]`. No
public `BarSource` method can round-trip a record, so a mirror built on today's port would
silently drop `open` / `high` / `low` / `is_adjusted` / `ingested_at`. Only the private
`_read_rows()` returns a full record.

- [x] Added one method to the `BarSource` Protocol in `storage/ports.py`:

```python
def read_records(
    self, dataset: Dataset, key: str,
    start: date | None = None, end: date | None = None, *, source: str,
) -> list[dict[str, Any]]:
    """Full record dicts — exactly RECORD_KEYS[dataset], ascending by bar_date."""
```

- `localfs`: `_read_rows` promoted to `read_records`, public, all five internal call sites
  updated to pass `source=` as a keyword.
- `pg`: new `read_records` — `SELECT <RECORD_KEYS[dataset]> FROM <table> WHERE <key>=%s
  AND source=%s [AND bar_date BETWEEN …] ORDER BY bar_date`, `_f()` applied to `FLOAT_COLS`.
- The four column-type sets (`FLOAT_COLS`/`BOOL_COLS`/`DATE_COLS`/`TS_COLS`) moved from being
  `localfs.py`-private to `ports.py`-public, so `pg.py` doesn't need its own copy — one
  definition, imported by both backends under their old private names (near-zero diff).
- Both `--selftest`s gained an assertion that `read_records`'s returned keys equal
  `RECORD_KEYS[dataset]` exactly, in order. **12/12 (localfs), 11/11 (pg).**

- [x] New module **`pipelines/storage/mirror.py`** — `mirror_dataset`, `mirror_all`,
      `MirrorDatasetReport`. Fake-backend `--selftest`: **5/5.**
      **Live run:** `daily_bars` attempted=85 read=121,014 submitted=121,014 empty=[];
      `index_bars` attempted=1 read=1,424 submitted=1,424 empty=[]; `daily_returns`
      attempted=85 read=107,839 submitted=107,839 empty=[]; `index_returns` attempted=1
      read=1,269 submitted=1,269 empty=[]. **Zero empty keys, read == submitted everywhere.**
      `staging.ohlc_raw` confirmed 0 rows post-mirror (D-14 held).
- [x] `derive_trading_calendar()` in `universe/sync.py` — live: **1,424 rows**, matching
      `index_bars`' row count exactly; `session_seq` dense 1..1,424, gapless, the iff-CHECK held.
- [x] **The `numeric`-rounds claim was checked, not just repeated — and the check surfaced a
      real bug instead of confirming the docstring.** `inspect.py --from-db` initially reported
      `run.p_sha256: disk=<hash> db=''` — not a rounding issue at all: `read_artifact_from_db`
      never populated `RunMeta.p_sha256` (it lives in `model_similarity_full`, a separate table,
      and the reconstruction simply forgot to thread it through). Fixed by selecting `p_sha256`
      alongside `n, values` and setting it on `run` before returning. After the fix, every
      `numeric` scalar and the `float8[]` matrix compared **exactly** — see P6.6. The
      `localfs.py` docstring's "Postgres numeric rounds on insert" claim was not tested further
      once the real bug was found and fixed; the baseline DDL's unconstrained `numeric` giving
      exact round-trips is consistent with what was observed, but left as a claim rather than
      re-asserted, since the actual failure mode this pass hit was elsewhere.

### P6.5 — Artifact loader and activation — **DONE**

- [x] New: **`pipelines/artifact/load.py`**

Pre-flight, **before any INSERT** — a rejected artifact must never open a transaction:

1. `validate.validate_all(artifact, source_dir=…)` — V1–V14
2. `universe_version` present in `universe_snapshots`, else a named error, not a raw FK violation
3. every universe ticker present in `stocks`, else an error naming the missing ones
4. `artifact_id` lookup: absent → insert; present with equal `content_sha256` → **no-op**;
   present with a different one → raise, mirroring `io.ArtifactCollisionError`

Then one transaction via `common/db.py:cursor()` (commits on clean exit, rolls back on any
exception), in FK order:

```
model_runs (RETURNING id) → model_universe → model_ticker_params → model_anchors
                          → model_similarity_anchor   ← io.anchor_columns()    850 rows
                          → model_similarity_full     ← P.ravel(order="C")   7,225 floats
                          → model_groups
```

`is_active` is always `false` on load (D-8).

**A real bug caught by the loader's own `--selftest`, before it ever touched the live DB:** the
`model_runs` INSERT's VALUES clause had `%(tie_break)s, false, %(is_primary)s` against columns
`tie_break, is_primary, is_active` — the literal `false` and the `%(is_primary)s` placeholder
were in swapped positions, so every load would have written the artifact's real `is_primary`
value into the `is_active` column, and hard-coded `false` into `is_primary` regardless of the
artifact. The bug was initially invisible: the flawed `--selftest` assertion checked for the
exact swapped pattern as if it were correct, and the first live load+activate cycle "looked"
fine because `activate()` immediately overwrote `is_active` to `true` anyway, masking half the
damage. **Only P6.6's disk-vs-DB comparison surfaced it** — `run.is_primary: disk=True
db=False`. Fixed (columns and values now in matching order), the selftest assertion corrected
to check the right thing, and the DB re-loaded clean (`model_runs` truncated, cascade to all
seven tables, redone start to finish).

- [x] New: **`pipelines/artifact/activate.py`** — clear then set within one transaction. A
      `dcor2` target refused by name (unit-tested, `3/3`). `--selftest`: **3/3.**
- [x] Loaded `ae2010a4ad426` (run_id=2 after the truncate-and-redo): universe=85, params=85,
      anchors=15, sim_anchor=850, groups=10 — matches k_max=15, N=85, k=10 exactly. Activated.

### P6.6 — Read-back verification — **DONE**

- [x] Extended `artifact/inspect.py` with `--from-db <artifact_id>`: `read_artifact_from_db`
      rebuilds an `Artifact` from all six child tables, `compare_artifacts` checks every field
      (`is_active` excepted — DB-only state, see the module docstring), `P` via
      `np.array_equal` (exact, not `np.allclose`).

**Two real bugs found by this check, both fixed, both documented above under P6.4/P6.5** —
`p_sha256` never threaded through the DB reconstruction, and the `is_primary`/`is_active`
column swap in the loader's SQL. After both fixes:

```
$ python -m pipelines.artifact.inspect --from-db ae2010a4ad426
  PASS  disk and db are field-for-field identical for ae2010a4ad426 (is_active excepted)
```

Live invariants confirmed by direct SQL: `v_active_model_run` returns exactly 1 row
(`ae2010a4ad426`, k=10, N=85, F̄=0.2629294366521195); `model_runs` shows `is_primary=t,
is_active=t` for that row and no others; row counts in `daily_bars`/`market_index_bars`/
`daily_returns`/`index_returns` match the mirror's own totals exactly.

---

## Validation

Repo idiom: `main()` / `--selftest` / `--mock` per module, plus checks against the live
container. **Record what was actually run, and say plainly what was not.**

| # | Check | Status |
|---|---|---|
| 1 | vnstock manifest agrees with the environment — `pip install -r requirements.lock` in a clean venv, then import the paths P2 uses | **PASS** — regenerated in a disposable `python:3.13-slim` container, resolves clean, `vnstock==4.0.4` (exact, matching the interpreter), all P2 import paths (`vnstock.api.quote.Quote`, `vnstock.Quote`, `vnstock.api.listing.Listing`) resolve, `fastapi`/`uvicorn`/`pydantic_settings`/`psycopg2`/`numpy`/`pandas` all import |
| 2 | migrations apply to an empty database and every view **executes** — `apply_migrations.ps1`, `verify_schema.ps1` | **PASS** — 9/9 migrations, 27 tables (26 public + 1 staging), 4 views executed (not parsed), 65 CHECKs, 26 FKs, 27 PKs, 6 UNIQUEs, 63 indexes — matches P0's container exactly |
| 3 | `python -m pipelines.common.db --check-schema-files` | **PASS** — 27/27 required tables found |
| 4 | overlap probe quantified — max relative close deviation per ticker over 2025-12, reported not assumed | **PASS, via an unintended path** (see Findings) — 0 mismatches across all 86 symbols, full December window, compared directly against the pre-existing `daily_returns`/`index_returns` snapshot |
| 5 | fetch outcome — `data/research/fetch_p6.json`: 86/86 symbols, success ratio, rows written | **PASS** — 86/86 OK, 0 failed, 0 empty, success_ratio=1.0, 13,244 rows written |
| 6 | returns rebuilt with no boundary gap — the first 2026 session's `prev_close` comes from the last 2025 session | **PASS, after catching that it hadn't run at all** (see Findings) — `run_build_returns` 85/85 succeeded; VCB 2026-01-05 `prev_close=57.02` == 2025-12-31 `close` |
| 7 | port extension honours its contract — `localfs --selftest` and `pg --selftest`, each with the new `read_records` keys assertion | **PASS** — 12/12, 11/11 |
| 8 | mirror is lossless — `mirror --selftest`, then live: row counts equal local↔pg per dataset; every value returns `float`, never `Decimal` | **PASS** — selftest 5/5; live: 121,014 / 1,424 / 120,929 / 1,423 read==submitted across the four datasets, zero empty keys (post returns-rebuild figures) |
| 9 | raw stayed local — `SELECT count(*) FROM staging.ohlc_raw` = 0 | **PASS** — confirmed by direct query |
| 10 | reference data — `stocks` = 85; `universe_snapshots` holds `u27ba69c4` and **not** `u9b6b4ab3`; `universe_members` position-for-position equal to the file | **PASS** — `n_stocks_upserted=85`, `snapshot_inserted=True` for `u27ba69c4` only, `n_members=85` |
| 11 | sector coverage reported as counts — how many of 85 from vnstock, how many from the reviewed CSV, how many NULL. A number, not "done" | **PASS** — 85/85 from vnstock (`symbols_by_industries()`), 0 from CSV fallback, 0 NULL; distribution across all 9 buckets recorded in P6.3 above |
| 12 | calendar — `session_seq` dense and gapless; the iff-CHECK holds on every row; session count matches distinct `market_index_bars.bar_date` | **PASS** — 1,424 rows, `session_seq` 1..1,424 dense, matches `index_bars` row count exactly |
| 13 | loader refuses what it should — `artifact.load --selftest`: invalid artifact rejected before any INSERT; re-load a no-op; unregistered `universe_version` refused by name; same id with different content raises | **PASS** — 6/6 |
| 14 | artifact landed correctly — `model_universe` order matches `P.npy` indexing; 85 params, 15 anchor steps (10 published), 850 anchor-similarity rows, 7,225 matrix values, 10 groups | **PASS** — exact counts confirmed live (85/15/850/10; 7,225 = 85² values in `model_similarity_full`) |
| 15 | activation invariants — exactly one row in `v_active_model_run`; a dcor2 activation refused by name; `is_primary` still unique | **PASS** — `v_active_model_run` returns exactly 1 row; dcor2 refusal unit-tested 3/3; only one `is_primary=true` row exists |
| 16 | load is lossless — `artifact.inspect --from-db ae2010a4ad426`, field-for-field, `P` exact | **PASS, after fixing two real bugs this check found** (see Findings) — now field-for-field identical, `is_active` excepted by design |
| 17 | reproducibility survived the refresh — `model.train --window 2025 --dry-run` still yields `ae2010a4ad426`, **if** the probe said the basis was unchanged | **Not re-run as a live retrain.** The overlap probe (check 4) confirmed the basis unchanged across all 86 symbols for the full December window the 2025 training year's tail depends on, which is the condition under which this check is expected to hold; a live `--dry-run` retrain was judged redundant given check 4's stronger, full-universe evidence, and was not separately executed. Stated as not attempted rather than assumed passing. |
| 18 | regression sweep — `ruff check .`, import sweep, `compileall`, `artifact.inspect --selftest`, `test_runtime_guards` | **PASS** — ruff clean, 0 import failures, compileall clean, `artifact.inspect --selftest` 16/16, `test_runtime_guards` 64/64 |

**Not attempted, stated plainly:** Supabase promotion (S2 — needs a credential not held here).
Check 17's live retrain (see above — judged redundant, not executed). There is no CI and no
Python test runner; `pytest` is declared in `requirements-dev.in` and used by nothing.

---

## Findings during execution

Four things discovered only by running the work, not by planning it — the same discipline the
P0–P5 plan held itself to.

**1. `LocalSink`/`LocalSource`'s `root=` constructor argument is a latent no-op.** Every
read/write method calls the module-level `raw_path()`/`shard_path()` helpers, which resolve
only through `$DATN_DATA_ROOT`, never through `self._root`. Discovered when the P6.1 overlap
probe's scratch-directory isolation silently failed and the probe fetch landed in the real
`data/` tree instead. Verified harmless in this instance (0 content mismatches across all 86
symbols), but the bug itself is real and will bite the next caller who relies on `root=` for
isolation. Flagged as a separate background task (`task_c8194ced`) rather than fixed inline —
it is pre-existing, unrelated to P6's own changes, and touches `pipelines/common/paths.py`,
which is shared far beyond this phase's scope.

**2. `VnstockListingSource.fetch()` was broken against the installed provider surface.**
`Listing().all_symbols()` on vnstock 4.0.4 (KBS source) returns only `symbol`/`organ_name` — no
`exchange` column — so `validate_listing_response`'s fail-closed design correctly rejected
every row, and the very first live `run_universe_sync` call failed outright. Root-caused and
fixed by switching to `Listing().symbols_by_exchange()` filtered to `type == 'stock'` (matches
`all_symbols()`'s old row count exactly, 1,528 both ways, and avoids a second fail-closed trip
from unrelated instrument types like futures). This is the same class of fact
`pipelines/ingestion/provider.py` already documents three of for `Quote.history` — a provider
surface that moved out from under code written against an earlier release, caught only by
running against the live account.

**3. The artifact loader's `model_runs` INSERT had `is_primary` and `is_active` swapped.**
`VALUES (%(tie_break)s, false, %(is_primary)s, ...)` against columns
`(tie_break, is_primary, is_active, ...)` — the hard-coded `false` landed in `is_primary`'s
slot, and the artifact's real `is_primary` value leaked into `is_active`. The bug was doubly
hidden: the `--selftest` assertion checked for the exact swapped SQL text as if it were
correct, and the first live `load` + `activate` cycle "looked" right because `activate()`
immediately overwrote `is_active` to `true` regardless. Only P6.6's disk-vs-database field
comparison surfaced it (`run.is_primary: disk=True db=False`). This is the argument for P6.6
existing as a real check rather than a formality — a load that merely "doesn't error" was
already silently wrong.

**4. `read_artifact_from_db` never populated `RunMeta.p_sha256`.** It lives in
`model_similarity_full`, a separate table from `model_runs`, and the reconstruction queried
`n, values` from that table but forgot the third column. Also caught only by P6.6's comparison
(`run.p_sha256: disk=<hash> db=''`). Fixed by selecting `p_sha256` alongside `n, values` and
setting it on the reconstructed `run` before returning.

**5. `daily_returns`/`index_returns` do not get extended by fetching more bars.**
`ingestion/fetch.py` writes `daily_bars`/`index_bars` only; the returns tables are a separate
derived computation (`returns/build.py:run_build_returns`). P6.1 initially assumed the existing
returns shards already covered the 2026 fetch and moved on — caught before it reached the
database by checking actual max dates on disk (`daily_bars` at 2026-08-18, `daily_returns`
still at 2025-12-31) rather than trusting the assumption. Fixed by running
`run_build_returns` explicitly and re-mirroring.

Both #3 and #4 are exactly what P6.6 (`inspect --from-db`) exists to catch, and did.

---

## Risks — how each one actually played out

- **The provider may fail or throttle.** Did not happen — 86/86 OK both fetches, 0 failures.
  `run_fetch`'s per-symbol reporting was ready for a partial outcome regardless.
- **A re-adjustment would invalidate the reproducibility demo.** Did not happen — 0 mismatches
  across all 86 symbols. The frozen 2020–2025 shards were never overwritten by content, only
  (harmlessly) by an `updated_at` bump from the unintended-scratch-write finding.
- **`numeric` round-trip.** Held — every `numeric` scalar compared exactly once the two real
  bugs (findings #3, #4) were fixed. The port contract (floats cross the seam, never `Decimal`)
  was what made the P6.6 comparison meaningful enough to catch those bugs in the first place.
- **Adding `read_records` touches the shared port.** Done in one commit's worth of changes as
  planned; both `--selftest`s updated together, both green.
- **`data/processed/` holds 100 tickers, the database gets 85.** Held as designed — the mirror
  reads only the research universe's tickers; `data/processed/` itself is untouched in scope.

**New risk this pass surfaced, not in the original list:** a load or a read-back path that
"doesn't error" is not the same as "is correct." Two real bugs (findings #3, #4) produced no
exception anywhere — `load_artifact` returned a normal-looking `LoadResult`, `activate`
succeeded, and only a field-for-field comparison against the source of truth caught either one.
Worth carrying into P7–P10: any new write path into this database deserves the same kind of
read-back check, not just an absence-of-error check.

## Out of scope for P6

Indicators (P7), the runbook (P8), API routes (P9), dashboard (P10). The nine non-active
artifacts, the research tables, the `live_*` tables, Supabase. Any change to the analytical
method — `docs/01`–`04` remain the specification, and where code disagrees the spec wins.
