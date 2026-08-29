# Plan — migrate the repository to the anchor model

**Started:** 2026-08-17
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Scope of this pass:** P0–P5. Supabase is *designed* but not populated; technical indicators
and Airflow are deliberately out of scope.

Update **Progress** and **Validation** in the same commit as the code they describe.

---

## Why

The repository holds two worlds. The old one (Leiden clustering → behavior windows → outcome
analysis → dashboard snapshots) owns most of the orchestration, schema and API. The new one
(anchor model) is correctly implemented in `pipelines/{returns,factor,anchors}` but wired to
nothing.

The old world is already dead at runtime — `pipelines/clustering/` does not exist and
`pipelines/outcomes/` is empty, so its daily chain cannot complete. The migration set cannot be
applied to an empty database because `00012` grants on eleven tables no migration creates. The
real Supabase project is empty. See `docs/00-project-status.md` for the full survey.

**Target:** one world. A local train track that runs offline and emits versioned artifacts, and
a schema ready for the dashboard track to load them into.

## Decisions taken

| # | Decision |
|---|---|
| Q1 | Old world removed. `apps/web` untouched — it runs standalone on mocks. |
| Q2 | Bespoke orchestration removed. `pipelines/` becomes a library of callables; Airflow drives it later. |
| Q3 | The 5-minute intraday layer removed entirely. Daily bars only. |
| Q4 | Supabase gets a clean baseline; the 13 old migrations are archived. |
| Q5 | Technical indicators stored in explicit typed columns. |
| Q6 | Minimum-session thresholds removed; session **alignment** kept (`docs/01` §1) and reported. |
| Q7 | Universe comes from `list_stocks.txt`, not from the `stocks` table. |
| Q8 | 2021 becomes the fifth research year — see [D-1](../../decisions/D-01-five-year-research-track.md). |
| Q9 | `services/api` keeps only neutral infrastructure. |
| Q11 | `data/processed/` uses Parquet; `pyarrow` is dev-only. |

Open: [D-6 adjusted-close semantics](../../decisions/D-06-adjusted-close-semantics.md) — must
close before any figure is quoted as a finding.

> **No git.** This directory is not a repository, so deletions are irreversible. Superseded
> files move to `_archive/` instead of being deleted. Delete `_archive/` when comfortable.

---

## Progress

### P0 — Docs, demolition, baseline schema

- [x] P0.1a Amend `docs/03` to five research years (§2 table + loop, §3 denominator, §4 four
      pairs, §7 wording, §8 five rows) and add the prior-close subsection
- [x] P0.1b Move the four specs into `docs/` as `01`–`04`
- [x] P0.1c Write `docs/00-project-status.md`, `docs/WORKFLOW.md`, `AGENTS.md`
- [x] P0.1d Write `docs/decisions/` register + records D-1, D-5, D-6
- [x] P0.1e Write this plan
- [x] P0.2 Archive the old world from `pipelines/`; surgical edits to `common/db.py`,
      `common/upsert.py`, `common/quality.py`, `pipelines/__init__.py`, `ruff.toml`
- [x] P0.3 Trim `services/api` to `/health` + infrastructure
- [x] P0.4 `list_stocks.txt` (100 liquid HOSE tickers) + `pipelines/universe/file.py`
- [x] P0.5 Archive 13 migrations; write baseline `00001`–`00009`; update `.gitignore`

### P1 — Storage ports — **DONE**
- [x] `common/paths.py` + `processed_table_dir()` / `shard_path()`
- [x] `storage/ports.py` — `Dataset`, `BarSink`, `BarSource`, and the four contract tables
- [x] `storage/localfs.py` — jsonl.gz + per-symbol parquet shards, atomic replace
- [x] `storage/pg.py` — verbatim delegation + the six absorbed SELECTs
- [x] `storage/factory.py` — default `local`
- [x] Rewire `returns/matrix.py` and `returns/build.py`; `_resolve_tickers` → `resolve_universe`
- [x] Fix `_json_safe` non-finite handling + `allow_nan=False` (latent bug #2)
- [x] Add the `source` filter to every typed read (latent bug #1)
- [x] Trim `hwm.py` to the one function P2 still needs; `requirements-dev.in`

Scope held: `ingestion/daily.py` and `ingestion/index_bars.py` were **not** rewired, because P2
replaces them. `common/hwm.py` keeps `get_daily_hwms` for the same reason.

### P2 — Provider untangle and collection
- [x] `ingestion/{provider,normalize,quality,fetch}.py` written **against the ports directly**
- [x] Archive `daily.py`, `index_bars.py`; delete `common/hwm.py` (`staging.py` removed too)
- [x] **Close D-6 before collecting in earnest** — decided ADJUSTED, see D-06
- [ ] Resolve latent bugs #3 (staging-vs-typed HWM frontier) and #5 (`ohlc_raw.provider`) —
      **not verified done.** Commit c99238a's diff never touches `common/db.py` or
      `common/upsert.py`, where both bugs live; nothing in the commit message claims them
      fixed. Left open for whichever phase next touches ingestion HWM logic.
- [ ] Reconcile the vnstock version: installed 4.0.4, manifest still pins `>=3,<4`
      (`requirements.in`/`requirements.lock` untouched by commit c99238a). The code runs
      against 4.0.4 today; the lock file is simply wrong, which is worse than absent.
- [x] Collect 2020-12-01 → 2025-12-31 for 100 tickers + VNINDEX — 101/101 symbols,
      127,657 raw bars, 126,287 return rows (commit c99238a)

### P3 — Returns, alignment, sigma
- [x] `AlignmentReport`; `FactorFit.sigma` (T−2 dof)
- [x] Remove `_MIN_TICKERS` / `_MIN_SESSIONS`; keep the intersection — already absent from
      the tree (done incidentally during the P1 `matrix.py` rewrite); this pass additionally
      changed the intersection itself to drop any ticker short of full coverage rather than
      only zero-overlap ones (previously the one path that could still silently shrink T —
      see D-12)
- [x] Latent bug #4: write `index_returns.close` / `prev_close`
- [x] D-12: freeze the research universe at 85 tickers (`list_stocks_research.txt`) so the
      five research-year runs share one N and one q — not originally scoped as a P3 line
      item, but required to make the alignment fix produce T=250/249/249/250/249 (no
      session lost) rather than T=18 for 2021 under the real 100-ticker universe

### P4 — Artifact and training
- [x] `artifact/{schema,identity,io,validate,inspect}.py`
- [x] `model/{similarity,train}.py` — the only caller of `greedy()`
- [x] Defined V1–V14 (referenced by this plan's Validation table since P0, never previously
      written down) — one function per rule in `artifact/validate.py`, each raising a named
      `ValidationError`; `artifact/inspect.py --selftest` proves each catches a deliberate
      violation, matching the P0 guard-rail standard (16/16, not an inventory)
- [x] Fixed a machine-dependent path in `AlignmentReport.universe_path` (P3 left it absolute)
      before it could enter a content hash — `matrix.repo_relative_path()`, reused by both
      `matrix._run_window` and `model.train`; the five `data/research/alignment_*.json` were
      regenerated
- [x] Produced all five research-year artifacts (2021–2025) on real data, 2025 marked
      `is_primary`

Two bugs found only by running against real data, both fixed:
- `RunMeta.q` initially copied `AlignmentReport.q` (rounded to 4dp for human-readable JSON),
  which V5's exact `N/T` recomputation correctly rejected. Fixed by computing `q` fresh in
  `train.py` rather than inheriting a display-rounded value.
- `io.write_artifact`'s idempotency check originally compared raw `manifest.json` bytes, which
  differ between two runs of the *same* content because `created_at` (deliberately excluded
  from the digest) differs. Fixed to compare `content_sha256` instead — same idea as
  `ON_CONFLICT_KEEP` preserving `ingested_at` elsewhere in this repo: the first-written
  timestamp survives, a content-identical re-run is a no-op.

### P5 — dCor and the research track
- [x] `model/dcor.py` (V-statistic, matmul route) — both estimators; U-statistic is a bias
      diagnostic only (D-5), never fed to greedy
- [x] Wired `model/similarity.py`'s `dcor2` branch; produced five `dcor2` artifacts (2021–2025)
      alongside the five `pearson_rho2` ones (P4) — 10 artifacts total, all pass V1–V14.
      Cross-checked per year: `alpha_hat`/`beta_hat`/`sigma_hat`/`r2`/`alignment` byte-identical
      between the two measures for the same year (only §4 differs, verified in code not just
      asserted in prose); exactly one `is_primary=true` repo-wide (unchanged: 2025 Pearson)
- [x] `research/{stability,compare,export}.py` — `_fixtures.py` added too (shared synthetic
      Artifact builder, built from real `greedy`/`assign` output, for the two modules'
      `--selftest`s); `Artifact.published_tickers()` added to `artifact/schema.py` for reuse
- [x] Frequency table (both measures); four cross-year pairs (both measures); measure
      comparison (Jaccard/Spearman/U-statistic diagnostic); near-degeneracy diagnostic (new,
      no schema table) — all computed on real data and written to `data/research/`
- [x] D-2 amended with what the runs show: no elbow in any of the ten Δ curves (still
      ≈0.97–1.02 at k=15); F̄ 0.2168–0.2632 and 32–49/85 tickers under τ at k=10, both measures;
      near-degeneracy explains why (29–45% of single-anchor swaps land within 2% of F̄(S))

Two fixture-design bugs caught only by running the `--selftest`s, both traced to the same root
cause: a **symmetric** block-similarity matrix gives every within-block member an identical
column sum, so greedy's smallest-index tie-break always resolves to position 0 — permuting
*which* block sits where does not change that, because the permutation does not break the tie.
The first synthetic "unstable" fixture (rotating a symmetric 3-block structure) and the first
synthetic cross-year "unstable" fixture (swapping two symmetric blocks) both accidentally
produced *stable* results for this reason. Fixed by adding `hub_p()` to `_fixtures.py` — one
column/row made strong to everyone, everyone else uniformly weak — which gives greedy an
unambiguous, controllable pick with no tie to break.

A third, unrelated bug: `frequency_summary()` initially inferred the study's total year count
from `max(len(r.years_selected) for r in rows)`. That inference is wrong exactly in the case
this function exists to describe — when *no* ticker was selected in every year (the real
Pearson result), the observed max understates the true span, corrupting the "in all years"
count's denominator. Fixed by requiring the caller to pass `n_total_years` explicitly.

---

## Validation

No test runner, no CI. Each phase names a check runnable by hand, following the repo's existing
`main()` + `--mock` idiom. **Record what was actually run, and say plainly what was not.**

| Phase | Check | Status |
|---|---|---|
| P0 | `ruff check .` | **PASS** — ruff 0.16.3 installed; 61 pre-existing findings in inherited code, 53 auto-fixed and 8 fixed by hand. Repo is clean. None were in code written for this migration. |
| P0 | `python -m pipelines.common.db --check-schema-files` | **PASS** — 27 required tables found across the 9 baseline files |
| P0 | import sweep (`pkgutil.walk_packages` over `pipelines`) | **PASS** — 0 failures |
| P0 | `python -m compileall pipelines services` | **PASS** |
| P0 | `python -m unittest tests.test_runtime_guards` (from `services/api`) | **PASS** — 64/64 |
| P0 | `python -m pipelines.universe.file --check` | **PASS** — 100 tickers, version `u9b6b4ab3`; order-independence and malformed-line rejection verified |
| P0 | migrations apply cleanly to an empty database | **PASS** — all 9 applied in order under `ON_ERROR_STOP` against a throwaway `postgres:17-alpine` container. Result: 27 tables (26 public + 1 staging), 4 views, 27 PKs, 26 FKs, 65 CHECKs, 6 UNIQUEs, 63 indexes. All 4 views execute, not merely parse. Container destroyed afterwards; the user's own PostgreSQL was never touched. |
| P0 | the guard rails actually reject what they claim to | **PASS — 16/16, 0 failures.** Behavioural test, not an inventory: each rule was given a deliberate violation and had to refuse it. Covers dCor-can-never-be-active, one-active-set-per-measure (while still allowing an inactive second run), one primary result, prior-close-outside-window, k ≤ k_max, the composite FK tying ticker params to a run's universe position, σ̂ > 0, ρ² ∈ [0,1], the flattened P being exactly N·N long, session_seq iff trading day, unique universe position, and daily bars requiring a close. |
| P0 | static structural lint of the migrations | **PASS** — superseded by the live apply above, kept because it needs no server. |
| P1 | `python -m pipelines.storage.localfs --selftest` | **PASS — 11/11.** Round-trip, `float`/`date` types (never `Decimal`), byte-identical re-write, `ingested_at` preserved on conflict while `close` updates, HWM pre-seeding, stray `.tmp` invisible, null/inf/NaN/missing-key/path-traversal all rejected, two sources isolated. Assertion 1 parses the SQL in `common/upsert.py` and asserts the contract tables match it — that one fails the moment the two sides drift. |
| P1 | `python -m pipelines.storage.pg --selftest` (fake cursor, no DB) | **PASS — 10/10.** Sink hands records **unmodified** to the *identity* of `upsert.py`'s SQL object; `Decimal`→`float`; every typed read carries `source = %s`; HWM is one batched query per dataset; source/dataset mismatch and corrupt raw payloads raise. |
| P1 | **acceptance: `returns.build` end-to-end with `DATABASE_URL` unset** | **PASS.** Seeded 30 sessions × 2 tickers + VNINDEX into a temp `data/`, ran the real CLI with `DATN_STORAGE=local`, got 29 return rows per series in real parquet shards, read back as `float`. One compute path, no database. |
| P1 | `factory`: default `local`, `$DATN_STORAGE` honoured, bad value raises | **PASS** |
| P2 | live fetch to `--sink local`; inspect the payload | **PASS** (commit c99238a) — full 100-ticker + VNINDEX collection, not just 3: 101/101 symbols, 0 failures, 127,657 raw bars, `data/research/fetch_p2.json` written. `--selftest` green on all four new ingestion modules plus one live `--probe` call. |
| P2 | D-6: ex-date close comparison | **PASS** (commit c99238a) — decided ADJUSTED, verified four ways: zero ±7% band breaches over six years for continuously-listed tickers, a 49.5% stock dividend showing −4% not −33%, cross-provider agreement, present-anchored back-adjustment. See `docs/decisions/D-06`. |
| P3 | `python -m pipelines.returns.matrix --mock` | **PASS** — `T00` (partial coverage) now excluded with `reason="incomplete"`; the other three tickers keep T=30 unchanged; `dropped_sessions=[]`. Asserted inline by the CLI itself, not just eyeballed. |
| P3 | `python -m pipelines.factor.model` recovers known betas + sigma | **PASS** — β̂ error 0.017 against synthetic β; σ̂ error 0.0009 against the true σ=0.008 used to generate the synthetic residuals; `T<3` correctly raises `ValueError`. |
| P3 | `python -m pipelines.storage.localfs --selftest` (re-run after `RECORD_KEYS` change) | **PASS — 11/11**, including assertion 1 (SQL ↔ `RECORD_KEYS` agreement) against the new `index_returns` columns. |
| P3 | `python -m pipelines.storage.pg --selftest` (re-run after SQL change) | **PASS — 10/10.** |
| P3 | live rebuild of `index_returns` after the `close`/`prev_close` schema fix | **PASS.** Deleted the stale `data/processed/index_returns/` shard (old schema had no `close`/`prev_close`) and re-ran `returns.build` over 2020-12-01→2025-12-31. New shard: 1,269 rows, all with non-null `close`/`prev_close`, `log_return == ln(close/prev_close)` to 1e-9 on every row. |
| P3 | live alignment, all five research years, frozen 85-ticker universe | **PASS.** `python -m pipelines.returns.matrix --window {2021..2025} --report data/research/alignment_<start>_<end>.json`: T=250/249/249/250/249, **N=85 every year, 0 dropped tickers, 0 dropped sessions.** `prior_close_date` lands in December of the prior year every time (D-11). Reports written to `data/research/`. |
| P3 | end-to-end chain: X → `fit_factor_model` → `residual_similarity`, all five years | **PASS.** For every year: `assert_rectangular`, `assert_residual_mean_zero`, `assert_similarity` (symmetric, unit diagonal, `[0,1]`), `assert_sigma_positive` all hold; `q` = 0.34 or 0.3414 depending on leap-adjacent session count. |
| P3 | strict-mode contract check: `assert_full_coverage` on the unfrozen 100-ticker universe | **PASS.** `--window 2021 --universe list_stocks.txt` raises naming exactly the 11 tickers 2021 costs; `--no-strict` on the same input instead reports `N=89, T=250` without raising — confirms the assertion is load-bearing, not decorative. |
| P3 | `ruff check .` / import sweep / `compileall` / API tests, re-run after all P3 edits | **PASS** — ruff clean (one auto-fixable import-order finding, fixed), 0 import failures, `compileall` clean, `test_runtime_guards` 64/64. |
| P4 | `python -m pipelines.anchors.greedy` (block fixture vs `brute_force_best`) | **PASS** — greedy/exact ratio 1.0000 at N=12, k=3; `assert_identities` OK. First run against this code since P0; nothing in P1–P3 touched it. |
| P4 | `python -m pipelines.artifact.inspect --selftest` | **PASS — 16/16.** 14 clean-fixture checks + 14 deliberate-violation checks (one per V-rule, each confirmed to raise) + one io round-trip/idempotency/collision check. Fixture is built from `pipelines.anchors.greedy`'s own real output, not a hand-typed stand-in. |
| P4 | `python -m pipelines.model.train --window 2025 --dry-run`, twice | **PASS — reproducibility.** Both runs produced `artifact_id=aceacfbe18b63`. Two real bugs surfaced and fixed only by running against real data: (1) `RunMeta.q` inheriting `AlignmentReport`'s 4dp-rounded value tripped V5's exact recomputation — fixed by computing `q` fresh; (2) `io.write_artifact`'s idempotency check compared raw manifest bytes, which differ run-to-run only in the digest-excluded `created_at` — fixed to compare `content_sha256`. |
| P4 | live: `python -m pipelines.model.train --window 2021 2022 2023 2024 2025 --primary 2025` | **PASS — 5/5.** Every artifact: N=85, T=250/249/249/250/249 matching P3 exactly, `prior_close_date` in December of the prior year, Δ non-increasing, P symmetric/unit-diagonal/`[0,1]` (checked directly from `P.npy` on disk, not just via `inspect`), F̄ ∈ [0,1]. Exactly one `is_primary=true` (2025); all five `is_active=false`. Each artifact's embedded `alignment` compared field-for-field against the standalone `data/research/alignment_*.json` P3 wrote — **identical** in all five. |
| P4 | `python -m pipelines.artifact.inspect <id>` on all five written artifacts | **PASS — 14/14 on each**, run against the files actually on disk in `data/artifacts/`, not the in-memory objects that produced them. |
| P4 | `ruff check .` / import sweep / `compileall` / storage selftests / API tests, re-run after all P4 edits | **PASS** — ruff clean, 0 import failures, `compileall` clean, `localfs` 11/11, `pg` 10/10, `test_runtime_guards` 64/64. |
| P5 | `python -m pipelines.model.dcor` | **PASS.** Matmul route vs a naive double loop at N=8, T=40: max abs err 1.11e-16 (well under the 1e-10 bar). `assert_similarity` holds on the V-statistic output. A perfectly dependent pair (identical columns) gives dCor²=1.000000. On independent Gaussian columns, V-statistic mean 0.0825 vs U-statistic mean 0.0058 — the upward bias D-5 describes, made visible rather than asserted. |
| P5 | constant-residual-column edge case | **PASS** (checked by hand, not yet in `main()`) — a constant column under `residual_dcor2` gives 0 off-diagonal, 1 on the diagonal, matching Pearson's handling of the same case exactly. |
| P5 | `residual_dcor2_u` on `T<=3` | **PASS** — raises `ValueError` naming the requirement, rather than dividing by zero. |
| P5 | live: `python -m pipelines.model.train --window 2021 2022 2023 2024 2025 --measure dcor2` | **PASS — 5/5.** No `--primary` passed (deliberately — see the plan's trap note). All five pass `inspect` V1–V14. Δ non-increasing and P symmetric/unit-diagonal/`[0,1]` verified directly from `P.npy` on disk, same as P4's Pearson check. |
| P5 | cross-check: `pearson_rho2` vs `dcor2` for the same year | **PASS**, verified in code (`train_one_window` called with both measures, compared in-memory before writing) — `alignment` dict equal; every ticker's `alpha_hat`/`beta_hat`/`sigma_hat`/`r2` equal (0 mismatches / 85); `P` and `artifact_id` differ. Confirms docs/01 §7's "only §4 changes" in code, not only in the spec text. |
| P5 | global cross-artifact check | **PASS** — 10 artifacts on disk (5 `pearson_rho2` + 5 `dcor2`), exactly one `is_primary=true` (2025 Pearson, unchanged from P4), zero `is_active=true`. No index file; checked by scanning `data/artifacts/*/manifest.json` directly. |
| P5 | `ruff check .` / import sweep / `compileall` / storage selftests / `artifact.inspect --selftest` / `greedy.py` / API tests | **PASS** — ruff clean, 0 import failures, `compileall` clean, `localfs` 11/11, `pg` 10/10, `artifact.inspect --selftest` 16/16, `greedy.py` ratio 1.0000 vs brute force, `test_runtime_guards` 64/64. |
| P5 | `python -m pipelines.research.stability --selftest` | **PASS — 4/4** (after fixing two fixture-tie-break bugs, see Findings). Stable fixture → concentrated frequency table; unstable (rotating hub) fixture → flat table with all 5 rotations one-off; frequency table covers the whole universe including never-selected tickers; degeneracy diagnostic correctly ranks a near-tied block above a sharply-separated one. |
| P5 | `python -m pipelines.research.compare --selftest` | **PASS — 5/5.** Stable fixture → cross-year ratio > 0.99 on every pair; unstable (flipping hub) fixture → ratio < 0.5 on every pair; universe-mismatch guard raises on a deliberately mismatched pair; Spearman gives exactly 1.0 comparing a matrix to itself and `<0.5` against an unrelated random one; `measure_comparison` self-comparison gives jaccard=1, spearman=1. |
| P5 | live: `python -m pipelines.research.export` over all ten artifacts | **PASS.** Pearson `cross_year_eval` reproduced **0.9044 / 0.9184 / 0.9630 / 0.9048** exactly (measured during planning, before any research/ code existed). Pearson `anchor_frequency`: **0 tickers in all 5 years, 17 in exactly 1** — also an exact match. dCor cross-year: 0.9157 / 0.9020 / 0.9727 / 0.9621. dCor frequency: 0 in all 5, 15 in exactly 1. All eight `ratio` values ∈ (0,1] — no clamping needed, none exceeded 1. `measure_comparison`: Jaccard 0.43–1.00, Spearman 0.79–0.87 across the five years — the two measures agree on ranking more than they disagree. `dcor_u_statistic_mean` (recomputed from E, not stored) sits below the corresponding `dcor2` artifact's own V-statistic mean in **all five years** (e.g. 2021: U=0.0144 vs V=0.0285) — D-5's bias claim, confirmed on real data, not just the synthetic case in `dcor.py`'s own self-check. Nine CSV/JSON files written to `data/research/`. |
| P5 | near-degeneracy diagnostic, all ten artifacts | **PASS, and explains the flat frequency table.** 750 single-anchor swaps evaluated per artifact (k=10, N=85). 29–46% land within 2% of F̄(S); median loss of the *best* alternative at any given anchor position is under 0.1 percentage point of F̄ in every case. Written to `degeneracy_<measure>.csv`; folded into the D-2 amendment. |
| P5 | global cross-artifact `is_primary` check, via `research.export.assert_single_primary` | **PASS** — exactly one, across all ten artifacts on disk. |

P0, P1, P3 (mock), P4 and P5 need neither network nor database. Only P2 needs the live provider.

---

## Findings during execution

Things discovered while doing the work that were not visible when planning it.

**The repo was not under version control while P0 ran**, so deletions had no undo and everything
the plan called "delete" was moved to `_archive/` instead.

It is now: `origin` is `git@github.com:trinhtuanphong123/anchor_stock.git` on `main`, with one
commit taken *after* P0 finished. Two consequences:

- `.env` and `apps/web/.env.local` are **not tracked** and never were — the only env file in
  history is `apps/web/.env.example`. No secret was pushed.
- `_archive/` is gitignored and therefore **not in history at all**. The old Leiden code exists
  only on this disk. Deleting `_archive/` is still irreversible. If that code is worth keeping,
  commit it once before removing it; if it is not, `rm -rf _archive` is safe and intended.

**vnstock installed is 4.0.4; the manifest pins 3.x.** `requirements.in` says `vnstock>=3,<4`
and `requirements.lock` pins `vnstock==3.5.1`, but the interpreter has 4.0.4. The import paths
the old code used still resolve (`vnstock.api.quote.Quote`, `vnstock.Quote`,
`vnstock.api.listing.Listing`), but the signature moved: `Quote.history` now takes `symbol` as a
method parameter rather than only a constructor argument. P2 must be written against the
*installed* version and the manifest corrected to match — a lock file that disagrees with the
environment is worse than no lock file, because it makes a green run unreproducible.

**`pyarrow` is already installed**, so D-3 costs nothing to adopt. `requirements-dev.in` should
still be written so the dependency is declared rather than incidental.

**`ruff` was never installed**, so the repo's `ruff.toml` had never been enforceable and 61
findings had accumulated in the inherited code. Now installed (0.16.3) and the repo is clean.

**The migrations were verified against a real server**, via a throwaway `postgres:17-alpine`
container rather than the developer's own PostgreSQL — no credential of theirs was involved and
nothing of theirs was touched. The container was destroyed afterwards. Worth repeating whenever
a migration changes; the two scripts used live in the session scratchpad and can be promoted
into the repo on request.

**`.env` holds only a placeholder `DATABASE_URL`** (`postgresql://...host:PORT/...` literally).
Nothing in the project has ever connected to a database. That is consistent with Supabase being
empty, and it means P6 starts from zero.

**pyarrow reads a hive-partitioned path even when handed a single file.** The shards live at
`processed/daily_bars/ticker=VCB/data.parquet`, and `pq.read_table(path)` treats the
`ticker=VCB` directory as a partition — it synthesises a *dictionary-encoded* `ticker` column
from the path, which collides with the real string `ticker` column inside the file:
`ArrowTypeError: Unable to merge: Field ticker has incompatible types`. Every parquet read had
to become `pq.ParquetFile(path).read()`, which opens exactly one file with no dataset
inference. Wrapped in `localfs._read_parquet` with the reason written down, because the
"simplification" back to `read_table` is an easy and silent regression.

**The alignment intersection had a second, worse failure mode than the one the plan named.**
Removing `_MIN_TICKERS`/`_MIN_SESSIONS` (already done by P1) was necessary but not sufficient:
`assemble_matrix` still kept any ticker with *nonzero* overlap and intersected sessions across
all of them, so one partially-covered ticker silently shrank T for every other column. Against
real 2021 data this was not a corner case — it cost 232 of 250 sessions. Fixed by dropping any
ticker short of full coverage (not just zero-coverage), which turns the intersection into a
no-op whenever the universe itself has full coverage — which is what D-12's frozen 85-ticker
universe guarantees for all five research years. The two fixes are independent and both
necessary: the mechanism fix makes any single bad ticker harmless; the frozen universe makes
"harmless" also mean "no year loses tickers relative to the others."

**Re-running `returns.build` after a `RECORD_KEYS` schema change is not automatically safe.**
The existing `data/processed/index_returns/` shard predated the `close`/`prev_close` columns
added for latent bug #4. `LocalSink._merge` builds each merged row via
`{c: rec[c] for c in RECORD_KEYS[dataset]}`, so an old row missing the new keys would raise
`KeyError` at write time — not corrupt data, but a hard stop. Worked around by deleting the
stale shard before rebuilding rather than patching around it; `daily_returns` was untouched
since its schema didn't change. Worth remembering for any future `RECORD_KEYS` addition: check
whether existing shards predate it, don't assume the merge step upgrades them in place.

## Out of scope this pass

P6 (load artifacts into real Supabase, `model/apply.py`), P7 (`pipelines/indicators/`),
P8 (`airflow/` + DAGs). Their schema is written in P0.5, so continuing needs no migration edit.
