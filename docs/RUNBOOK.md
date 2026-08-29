# RUNBOOK — rebuilding the database from an empty one

**Written:** 2026-08-29 (P12/F5). **Revised:** 2026-08-30 (P15) — three things this file used to
warn about are fixed rather than worked around: Supabase's schema is now applied through a real
migration runner (§1), the returns build step is gone because `daily_returns`/`index_returns` are
VIEWs (§3.4 removed), and the ten-hour write warning is gone because `pipelines/common/upsert.py`
batches through `execute_values` instead of one round trip per row (§3.5). Table/view/index
counts below are P15's; see `supabase/migrations/00003_returns.sql` and
`scripts/db/verify_schema.sql` for the numbers and how they were measured.

> **Read this line before running anything.** Every command below was checked to exist, with the
> flags it is written with, by running `--help` against the module on 2026-08-29. The individual
> steps have all been run before — that is how the current database was built, phase by phase
> (P6.1–P6.5, P7, P15). **What has never been run is this file, top to bottom, as one sequence
> against a fresh empty database.** That check is `anchor-model-operations.md`'s P11 validation
> row and it is still `not attempted`. Treat the ordering and the checks as specified-and-plausible,
> not as rehearsed. Nothing here is reported as passing.

---

## 0 What this rebuilds, and what it cannot

The chain takes an empty Postgres to the state the dashboard serves: reference data, price
history, returns, indicators, and one **active** model artifact.

It does **not** recompute the model. Artifacts under `data/artifacts/` are frozen outputs and are
*loaded*, never retrained — that is the whole point of the two-track split (`AGENTS.md`), and
`docs/04` §5 forbids a request path reaching greedy. If you want a new artifact you are on the
local train track, which is a different document.

## 1 Two targets, both scripted

| Target | Schema applied by | Idempotent? |
|---|---|---|
| Local container `datn_pg` | `scripts/db/apply_migrations.ps1` | No — re-running fails loudly on the first colliding `CREATE`, deliberately (no down-migrations) |
| Supabase (what Render reads) | a migration runner, one file at a time, in order | No — same reason |

**P15 closed the gap this section used to warn about.** Through P14, Supabase's schema was not
tracked by any migration runner — `supabase_migrations.schema_migrations` was empty while every
table and view existed and held data, meaning the SQL had been applied directly rather than
recorded. That is fixed: `qhbfjgheeyckefcwtmcq` (Singapore, ap-southeast-1) was brought up from
**empty** by applying every file in `supabase/migrations/` — `00001, 00002, 00003, 00004, 00005,
00008, 00009, 00010, 00011, 00012, 00013`, in that order (`00006`/`00007` are withdrawn to
`_archive/` and skipped; the gap in the numbering is deliberate, not a typo) — through a migration
runner that writes one row to `schema_migrations` per file applied. **`schema_migrations` now
holds 11 rows**, so the schema is a thing this repository can rebuild and verify against, not a
state that only exists in one project's history.

`00011` (revoke `anon`/`authenticated`) is not optional and must not be skipped or reordered
before it: it is the only thing standing between the public `anon` key and `TRUNCATE daily_bars`
(D-20).

Rebuilding a *second* Supabase project from scratch means re-running the same 11 files, in the
same order, through the same kind of runner — there is nothing target-specific about the sequence
above besides which project's connection string receives it.

Everything from §3 onward is storage-agnostic and works against either target — it is selected by
`DATABASE_URL` and `DATN_STORAGE`, not by different commands.

## 2 Environment

```powershell
# Only three variables are read anywhere in pipelines/.
$env:DATABASE_URL  = "postgresql://...:5432/postgres"   # session pooler on 5432, see render.yaml
$env:DATN_STORAGE  = "pg"                               # or "local" for the offline track
$env:DATN_DATA_ROOT= "D:\DATN_new\data"                 # optional; defaults to ./data
```

`DATABASE_URL` must be the **session** pooler (port 5432). `render.yaml` carries the reasoning and
what was measured about port 6543.

**Check:** `python -m pipelines.common.db --check-schema-files` — verifies every required table is
present in the migration files. It reads files, not the database, so it passes before the schema
is applied; it catches a migration that was deleted or renamed, not one that was never run.

---

## 3 The sequence

Each step names the check that tells you it worked. Run the check before moving on.

### 3.1 Apply the schema — local container only

```powershell
pwsh scripts/db/apply_migrations.ps1
pwsh scripts/db/verify_schema.ps1
```

Brings up `datn_pg` from `scripts/db/compose.db.yml` and applies `supabase/migrations/*.sql` in
order under `ON_ERROR_STOP`, non-recursively so `_archive/` is never touched.

**Check:** `verify_schema.ps1` exits non-zero if any required table is missing, executes every
view rather than merely parsing it, and prints counts to compare against P15's numbers — **17
base tables** (16 public + 1 `staging`), **13 views**, **17 PKs, 14 FKs, 46 CHECKs, 5 UNIQUEs, 44
indexes**. `scripts/db/verify_schema.sql` has the full derivation: P15 dropped 8 tables with no
writer (`00006`/`00007`), turned `daily_returns`/`index_returns` from tables into views, and
`v_active_group_health` lost seven columns along with the table it LEFT JOINed onto.

> `00013` is the one migration in this set that is not purely additive: it **drops and recreates**
> `v_latest_indicators`, `v_top_movers` and `v_anchor_group_detail`. `CREATE OR REPLACE VIEW` can
> only append columns, which would have put `ret_252d` after `computed_at` with the trailing
> returns split around an unrelated timestamp. Applying it out of order, or against a database
> where those three views do not yet exist, is the only way it can fail.

### 3.2 Reference data — stocks, universe snapshot, members

```powershell
python -m pipelines.universe.sync --file list_stocks_research.txt --sync
```

`--sync` is what touches the database; without it the module is a dry read.
`--probe-sectors` is a separate, deliberate step that writes a **draft** `sector_map.csv` for
human review and touches nothing.

**Check:** `stocks` holds exactly 85, and `universe_members` matches `list_stocks_research.txt`
**position for position**. The ordered universe pins every position in this system; a reordered
universe misaligns every vector and matrix silently, which is why artifacts store integer
positions rather than symbols.

### 3.3 Price history

Two routes, and they are not interchangeable.

**a. Mirror what is already on disk** (fast, offline, reproduces the local track exactly):

```powershell
python -m pipelines.storage.mirror --selftest     # fake backends, no DB, no network
python -m pipelines.storage.mirror --run
```

**b. Fetch from the provider** (needs network; this is how new sessions arrive):

```powershell
python -m pipelines.ingestion.fetch --universe-file list_stocks_research.txt `
    --start 2021-01-01 --end 2026-08-18 --storage pg --report data/raw/fetch_rebuild.json
```

`--mock` and `--selftest` need neither network nor database. `--min-success` sets the ratio below
which the run fails rather than silently landing a partial universe; `--report` writes the
per-symbol outcome, and that file is the audit record of what actually arrived.

**Check:** row counts equal on both sides per dataset, and a sampled field-for-field comparison
returns `float`, never `Decimal` — the port contract says floats cross the seam. P6.2 recorded
121,014 / 1,424 / 120,929 / 1,423 read == submitted, and `staging.ohlc_raw` empty.

### 3.4 [withdrawn, P15] Returns

There is no longer a step here against Postgres. `daily_returns` / `index_returns` are **VIEWs**
over `daily_bars` / `market_index_bars` as of `supabase/migrations/00003_returns.sql` — a pure
function of §3.3's data, computed on read. This is what closes the exact gap this step used to
guard against: P6.4 once fetched successfully but *missed* the returns rebuild, leaving a hole at
the 2025/2026 boundary that only a boundary check caught. A view cannot fall behind the table it
is derived from, so there is nothing left to run and nothing left to forget to run.

`python -m pipelines.returns.build` still exists and still writes — but only against the **local**
track (`DATN_STORAGE=local`), which remains the research archive. Pointing it at Postgres
(`writer.write_daily_returns` / `write_index_returns` on a `PostgresSink`) raises: the target is a
view with no `INSTEAD OF` rule, honestly, since there is nothing to insert into.

### 3.5 Indicators

```powershell
python -m pipelines.indicators.build --selftest    # closed-form fixtures, no network, no DB
python -m pipelines.indicators.build --universe list_stocks_research.txt --storage pg
```

**Check:** `macd == ema_12 − ema_26` on real rows; NULLs appear exactly where history is shorter
than the warm-up and nowhere else. Warm-ups measure from the first **loaded** bar, so a narrow
`--start` yields mostly-NULL output that looks like a bug and is not.

Indicators are display-only. They never enter the factor model or anchor selection (`docs/04` §5).

> **`--storage pg` against Supabase is a routine step again, as of P15/B1.**
> `pipelines/common/upsert.py` used to write through psycopg2 `executemany` — one round trip per
> row, measured at ~7 minutes per ticker and projecting to roughly ten hours for the 85-ticker
> universe. It now submits through `psycopg2.extras.execute_values` (`page_size=500`, one round
> trip per 500 rows), the same fix `docs/plans/active/p13-market-home-redesign.md` §Backfill
> flagged as the obvious follow-up and left undone. `--storage local` followed by
> `python -m pipelines.storage.mirror --run` is still the faster route when the data is already
> on disk (§3.3a) — this note is no longer about avoiding a ten-hour wait, just about which path
> re-reads from the provider and which does not.

> **Adding an indicator column? Run BOTH selftests.** `pipelines.indicators.build --selftest`
> checks the formulas; `pipelines.storage.localfs --selftest` checks that
> `pipelines/common/upsert.py`'s hand-written column list still matches `RECORD_KEYS`. P13 added
> `ret_252d`, ran only the first, and silently wrote 121,014 rows with the new column left NULL —
> the second selftest catches exactly that and takes two seconds.

### 3.6 The artifact

```powershell
python -m pipelines.artifact.load --selftest       # rejects an invalid artifact before any INSERT
python -m pipelines.artifact.load ae2010a4ad426    # loads INACTIVE
python -m pipelines.artifact.activate ae2010a4ad426
```

Loading and activating are two commands on purpose (D-8): activation is manual, so no automated
step can quietly change what the dashboard serves.

`ae2010a4ad426` is the artifact currently serving the site — 2025, `pearson_rho2`, 85 tickers,
k=10, τ=0.10. `--all-on-disk` loads all ten.

**Check:** `v_active_model_run` returns **exactly one** row, and `model_universe` order matches
`P.npy` indexing.

### 3.7 Verify the rebuild against the artifact on disk

```powershell
python -m pipelines.artifact.inspect --selftest
python -m pipelines.artifact.inspect --from-db ae2010a4ad426
```

`--from-db` reads the artifact back out of Postgres and compares it field for field against the
same `artifact_id` on disk. This is the step that makes the database *verified* rather than merely
populated, and in P6.5 it found two real bugs (`is_primary`/`is_active` swapped in the loader SQL;
`p_sha256` never threaded through the DB read).

**Check:** field-for-field equality, `P` exact.

### 3.8 Verify what the reader will see

```powershell
python -m pytest services/api/tests -q          # from services/api
npm --prefix apps/web run test
curl https://<api-host>/health                  # expects "database": "ok"
```

**Check:** `v_sector_performance` totals reconcile with `v_market_overview`; the figures on the
deployed page match a direct query of `v_market_overview`. That reconciliation was run on
2026-08-29 and is recorded in `plans/completed/p8-render-deployment.md` rows 8–11.

**The home page needs the API redeployed WITH it.** Since P13 the market screen reads three
endpoints that did not exist before — `/api/market/index-history`, `/api/market/liquidity`, and
`/api/market/movers` with a `horizon` parameter. The static site and the web service auto-deploy
from the same `main` commit, so pushing both together is the normal case; deploying the site alone
would leave three of its five panels rendering the error envelope. `/movers` without `horizon`
still answers, defaulting to `1d`, so an older site against a newer API is the harmless direction.

Sweep the three by hand after a deploy:

```powershell
curl "https://<api-host>/api/market/index-history?range=1m"
curl "https://<api-host>/api/market/movers?horizon=1y&direction=up&limit=5"
curl "https://<api-host>/api/market/liquidity?limit=5"
```

A `1y` movers call returning rows with `"ret_252d": null` throughout means the schema landed but
the backfill did not — see §3.5's note before reaching for `--storage pg`.

---

## 4 What records that a refresh happened

There is no orchestrator and no `/api/pipeline/status` route — it was dropped in P9 with no
consumer screen. So two tables are the **only** evidence a manual run occurred:

- `pipeline_runs`, written by `pipelines/common/logging.py:log_run(job_name, status, trigger, …)`
- the data-quality reports, written by `pipelines/common/quality.py:write_dqr(pipeline_run_id,
  report_scope, ref_date, check_name, passed, severity, details)`

For a manual run, `dag_id` / `dag_run_id` / `task_id` stay NULL. That is correct, not missing —
the columns exist to distinguish an orchestrated run from a hand-run one.

**Not verified:** whether every step above actually calls `log_run`. P11's checklist item
("Confirm `log_run` and `write_dqr` record the manual runs") is still open, and this file does not
close it.

---

## 5 Known gaps — deliberately listed rather than left as unticked boxes

1. **This sequence has never been executed end to end against a fresh empty database.** The
   individual steps have; the chain has not. Until it is, "reproducible" is a claim about
   plausibility, not a measured property.
2. **No test runner for `pipelines/`.** Verification is the `--selftest` / `--mock` idiom on each
   module, listed per step above. `services/api` and `apps/web` do have real runners (§3.8).

Two gaps this list used to carry are closed as of P15: Supabase's schema is now applied through a
migration runner and recorded in `schema_migrations` (§1), and `upsert.py` batches through
`execute_values` instead of `executemany` (§3.5).
