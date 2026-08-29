# RUNBOOK — rebuilding the database from an empty one

**Written:** 2026-08-29 (P12/F5). **Shape:** the one-shot refresh sequence P11 specifies in
`plans/active/anchor-model-operations.md` §P11, replacing the Airflow DAGs that were dropped.

> **Read this line before running anything.** Every command below was checked to exist, with the
> flags it is written with, by running `--help` against the module on 2026-08-29. The individual
> steps have all been run before — that is how the current database was built, phase by phase
> (P6.1–P6.5, P7). **What has never been run is this file, top to bottom, as one sequence against
> a fresh empty database.** That check is `anchor-model-operations.md`'s P11 validation row and it
> is still `not attempted`. Treat the ordering and the checks as specified-and-plausible, not as
> rehearsed. Nothing here is reported as passing.

---

## 0 What this rebuilds, and what it cannot

The chain takes an empty Postgres to the state the dashboard serves: reference data, price
history, returns, indicators, and one **active** model artifact.

It does **not** recompute the model. Artifacts under `data/artifacts/` are frozen outputs and are
*loaded*, never retrained — that is the whole point of the two-track split (`AGENTS.md`), and
`docs/04` §5 forbids a request path reaching greedy. If you want a new artifact you are on the
local train track, which is a different document.

## 1 Two targets, and only one of them is scripted

| Target | Schema applied by | Idempotent? |
|---|---|---|
| Local container `datn_pg` | `scripts/db/apply_migrations.ps1` | No — re-running fails loudly on the first colliding `CREATE`, deliberately (no down-migrations) |
| Supabase (what Render reads) | **by hand** | Unknown |

**Stated plainly because it is the weakest link in reproducibility:** the Supabase project's
schema is not tracked by any migration runner. `supabase_migrations.schema_migrations` is
**empty** (checked 2026-08-29) while all 27 tables and 10 `v_*` views exist and hold data, so the
SQL was applied directly rather than through the Supabase CLI. There is therefore no recorded,
repeatable procedure for bringing a *new* Supabase project to this schema, and no runner that
would refuse to double-apply. Rebuilding Supabase from scratch is **not** covered here, and
pretending otherwise is what this file exists to avoid.

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
view rather than merely parsing it, and prints counts to compare against P0's numbers — 27 tables,
27 PKs, 26 FKs, 65 CHECKs, 6 UNIQUEs, 63 indexes. The view count has since grown past P0's 4
(`00010`, `00012` and `00013` add more); **11** `v_*` views is the current figure — `00013` adds
`v_index_history` and recreates three others in place.

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

### 3.4 Returns

```powershell
python -m pipelines.returns.build --mock          # synthetic, no DB
python -m pipelines.returns.build --once
```

**Check:** no gap at a year boundary. P6.4 hit exactly this — the fetch succeeded and the
`daily_returns` rebuild was *missed*, leaving a hole at 2025/2026 that only a boundary check
found. Run it after every fetch, not only after the first.

### 3.5 Indicators

```powershell
python -m pipelines.indicators.build --selftest    # closed-form fixtures, no network, no DB
python -m pipelines.indicators.build --universe list_stocks_research.txt --storage pg
```

**Check:** `macd == ema_12 − ema_26` on real rows; NULLs appear exactly where history is shorter
than the warm-up and nowhere else. Warm-ups measure from the first **loaded** bar, so a narrow
`--start` yields mostly-NULL output that looks like a bug and is not.

Indicators are display-only. They never enter the factor model or anchor selection (`docs/04` §5).

> **`--storage pg` against Supabase is NOT a routine step, and this line is the correction.**
> `pipelines/common/upsert.py` writes through psycopg2 `executemany`, which issues **one round
> trip per row**. Measured on 2026-08-29 from Vietnam to `ap-southeast-2`: ~7 minutes per ticker
> at 1,424 rows each, projecting to roughly **ten hours** for the 85-ticker universe. The two
> practical routes are `--storage local` followed by `python -m pipelines.storage.mirror --run`,
> or a targeted single-column write (see `docs/plans/active/p13-market-home-redesign.md`
> §Backfill, which did exactly that in 42 seconds). Making `upsert.py` batch its writes would
> retire this whole note and is the obvious fix; it has not been done.

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
2. **Supabase's schema is unmanaged** (§1). This is the gap that would bite hardest in a rebuild.
3. **`psycopg2.extras.execute_batch` was never adopted.** `pipelines/common/upsert.py` submits
   every batch with `executemany`, which its module docstring documents as the chosen mechanism.
   It is *correct* — 121,014 indicator rows and 121,014 daily bars landed through it — but
   `executemany` round-trips per row, and P11 estimated the difference as hours against minutes
   once the pipeline runs over a network rather than a local container. Not done, not benchmarked
   here, and recorded so it is not mistaken for an oversight.
4. **No test runner for `pipelines/`.** Verification is the `--selftest` / `--mock` idiom on each
   module, listed per step above. `services/api` and `apps/web` do have real runners (§3.8).
