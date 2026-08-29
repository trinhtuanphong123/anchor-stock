# P12 execution plan — method review follow-ups

**Started:** 2026-08-28
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Track:** returns to the **method** track (P0–P5). It is not a continuation of the operations
pass (P6–P11, `anchor-model-operations.md`), which explicitly deferred this work at its
`Out of scope this pass`: *"Tuning the model — D-2's `k` and `τ` stay provisional."*
**Source:** `danhgia_phuongphap_trien_khai.md` (repo root, untracked) — a methodological review
of the pipeline, written against the P5 results.

---

## Why

P5 produced ten artifacts and the study tables around them. Reviewing that output, the project
owner raised one defect in the objective function and eight unrun checks. The defect is the
reason this plan exists; the checks are the reason it is a phase rather than a bounded change.

**The defect.** `P_ii = 1`, so `F(S) = Σ_i max_{j∈S} ρ²(i,j)` contains exactly `k` terms equal
to 1 by tautology. For the primary 2025 run that is 10.000 of the published F = 22.349 — **44.7 %
of the headline number is the identity ρ²(j,j) = 1.** Worse, the marginal gain decomposes as

```
Δ(v | S) = (1 − c_v)  +  Σ_{i≠v} max(0, ρ²(i,v) − c_i)
           └ self-cover ┘  └──────── real cover ────────┘
```

and the first term is bounded below by `max_{v∉S} (1 − c_v)`, which never decays. At k = 10 there
are 33 tickers with `c_i < 0.10`, so that floor exceeds 0.9 throughout. Observed Δ at k = 15 is
**0.990 — below 1** — meaning the fifteenth anchor's contribution to covering *other* tickers is
roughly 0.1. From about k ≥ 6 the algorithm is selecting *the most neglected ticker*, which is the
inverse of the problem the method states.

**This was verified before the plan was written, not assumed.** Greedy was re-run on `P` and on
`P₀` (diagonal zeroed) for all ten artifacts, directly from `P.npy`, with no retraining:

| measure | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| pearson — Jaccard(S_unit, S_zero) @ k=10 | 0.429 | 0.429 | 0.538 | 0.429 | **0.667** |
| pearson — first divergent step | 6 | 5 | 7 | 6 | 9 |
| pearson — F̄ published | 0.2330 | 0.2632 | 0.2378 | 0.2235 | 0.2629 |
| pearson — F̄_adj = (F−k)/(N−k) | 0.1308 | 0.1649 | 0.1362 | 0.1200 | **0.1647** |
| dcor2 — Jaccard | 0.429 | 0.429 | 0.538 | 0.429 | 0.538 |
| dcor2 — first divergent step | 4 | **3** | 4 | **3** | 7 |
| dcor2 — F̄_adj | 0.1234 | 0.1571 | 0.1318 | 0.1123 | 0.1569 |

Only 6–8 of 10 anchors survive removing the diagonal. The review predicted agreement to k ≤ 4;
under dCor the sets already diverge at **k = 3**.

**The eigenvalue check was also run early, because it decides how the whole result is read.**
2025, N = 85, T = 249, q = 0.3414, Marchenko–Pastur upper edge (1+√q)² = 2.510:

| stage | λ₁ | λ₂ | λ₃ | above edge | λ₁/N |
|---|---|---|---|---|---|
| `corr(X)` before the fit | 34.85 | 3.76 | 3.04 | 3 | 0.410 |
| `corr(E)` after the fit | 11.06 | 5.46 | 4.60 | **5** | 0.130 |

Neither branch the review posed is what happened. It is not "one unextracted common factor"
(λ₂ = 5.46 is more than double the edge), and it is not noise (five eigenvalues clear it, every
year). Real multi-factor structure exists, so the group interpretation survives — but **one factor
is demonstrably not enough**, and the report has to say so rather than let it be discovered.

**Definition of done.** Ten new study tables in `data/research/`, each reproducible by a single
documented command, answering all nine review items; the incorrect justifications corrected in
place; and no artifact retrained, no `artifact_id` changed, no schema touched.

---

## Where the review is wrong, and why that is recorded here

Three of the review's claims did not survive checking against the code and the data. They are
written down because a plan that silently drops an item from its own source document is
indistinguishable from a plan that forgot it.

**1. The zero-volume threat does not exist through the mechanism described.** The review (§4.2)
states the universe filter "allows up to 5 % of sessions with zero volume". No such filter exists:
`derive_research_universe` (`pipelines/universe/file.py:189-201`) applies exactly one criterion —
100 % session coverage against the VNINDEX calendar, every year — and a coverage-threshold
universe at ≥98 %/≥95 % was considered and **rejected** in [[D-12]]. `zero_volume` is recorded and
never used to exclude, by design (`supabase/migrations/00003_returns.sql:21`). Measured: it is
`False` for **all 85 tickers across all of 2025**.

But the *mechanism* the review describes is real and arrives through a different channel:
`log_return == 0`, an unchanged closing price. Measured over the 85-ticker universe in 2025 —
mean **19.5** sessions per ticker, median 17, and a long tail: **KOS 71/249 = 28.5 %**, SBT 61,
MSB 43, KDC 42, ACB 36, POW 34, HAG 33. Two such tickers share `(0, 0)` observation pairs for the
same reason the review gives, and the inflation of ρ² is the same. Stage C therefore targets
`log_return == 0` as the primary flag and reports `zero_volume` firing zero times as the finding
that closes that branch.

`at_limit` has genuine exposure: mean 9.5 sessions per ticker in 2025, 809 observations total,
maximum **26 — which is VIC, the first-selected anchor**.

**2. "4,950 pairs" is stale in two places, correct in two others.** C(85,2) = 3,570 applies to the
**research** track. The live/serving universe is 100 tickers ([[D-16]]; `list_stocks.txt` is 100
lines), so C(100,2) = 4,950 is right at `docs/04-static-parameters.md:146` and at
`supabase/migrations/00007_live_monitors.sql:106` and **must not be "fixed"**. Only
`docs/03-temporal-design.md:27` and `docs/decisions/README.md:48` — both research-track — are
wrong. The migration is applied; even a comment there would need a new migration, not an edit.

**3. The review overstates §6.1.** It argues the (1−1/e) bound does not depend on squaring, since
`h(S) = max_{j∈S} a_j` is submodular for any sign. Submodularity, yes — and monotonicity too, on
non-empty sets. But the code defines `F(∅) = 0` (`pipelines/anchors/greedy.py:67-68`), and with
negative entries `F({v})` can fall below 0, breaking monotonicity at the first step and with it
**normalisation**, which is what Nemhauser–Wolsey–Fisher actually requires. [[D-5]] already states
this correctly, and so does `docs/02:25` — *"Monotonicity and submodularity hold for any real P;
non-negativity is what supplies normalisation and therefore the approximation bound."*

So the defect is narrower than the review claims and narrower than it first looks. `docs/01:118-119`
("negative similarities push the problem into non-monotone submodular maximisation") and the
table row at `:111` ("**Sufficient condition** for the coverage objective to be monotone,
submodular and normalised") are both defensible. The single wrong sentence is `docs/01:115-116` —
*"It is the only condition the objective actually requires"* — which asserts non-negativity is
needed for monotonicity and submodularity, contradicting `docs/02:25` outright. Stage H fixes that
sentence and adds the two real reasons for squaring; it must **not** adopt the review's
overcorrection that squaring is irrelevant to the guarantee.

---

## Decisions taken

| # | Decision | Reasoning |
|---|---|---|
| N1 | **One new module reads disk (`research/residuals.py`); every study function stays pure over `(P, E, artifact)`.** `compare.compute_dcor_u_means` is refactored to accept loaded inputs rather than loading its own | That function is today the sole exception to "only `export.py` touches disk" (`compare.py:203`). Four more studies need `E`, which the artifact does not store. Replicating the exception four times would end the rule; centralising it removes the existing violation instead of adding to it |
| N2 | **Review items 1 and 2 are one number, not two.** With a unit diagonal, `F_excl(S) = Σ_{i∉S} max_{j∈S} P_ij = F(S) − k`, so `F̄_adj = (F−k)/(N−k)` **is** `F_excl/(N−k)` | It is also the only valid common yardstick for comparing S_unit against S_zero — scoring each set by its own objective compares nothing. Reporting F̄_adj therefore comes free with the comparison rather than as separate work |
| N3 | **`F_excl` scores; it must never select.** `F_excl(S) = F(S) − |S|` is submodular but **not monotone and not normalised**, so the NWF bound is void for it. `F₀` (zero diagonal) is non-negative, monotone, submodular — the guarantee survives | This is the one place a reasonable implementer takes a wrong turn: `F_excl` looks like the natural objective once you have decided the diagonal is the problem. It goes in the module docstring, not only here |
| N4 | **No artifact is retrained before Stage J.** Everything in Stages 0–I recomputes from `artifact.P` and re-loaded returns | Keeps ten `artifact_id`s, the loaded database, and the deployed API stable while the diagnostic work happens. A comparison that required rewriting what it compares against would not be a comparison |
| N5 | **Every new output is a report-only CSV. No migration, no schema change.** | Precedent: `degeneracy_*.csv` has no Postgres table either. Nothing under `apps/web` or `services/api` reads `data/research/` — grepped |
| N6 | **Diagonal: compare first, adopt later.** Stage J is written out but **gated** — not started until Stages A–D are on disk and read | The owner's instruction. Also the review's own §2.4 asks for the comparison and states both outcomes are usable; adopting before running it would discard the defensible-either-way result |
| N7 | **τ calibration proceeds, and `docs/02` §4 narrows to match** — recorded as [[D-25]], written before any code | `docs/WORKFLOW.md`'s fourth condition: amending a spec rule is a fork, not an implementation detail. D-25 also fixes the outcome in advance in both directions, so a surprising number cannot be renegotiated after it arrives |
| N8 | **Cap-weighted index-membership tests are declared out of scope in writing, not left as a TODO.** Stage F ships the equal-weight substitute with an exact leave-one-out identity | Grepped: no market-cap, free-float or index-weight data exists anywhere in the repo, and only VNINDEX is collected (`data/processed/index_bars/` has one partition). `f_{−i} = (N·f_ew − x_i)/(N−1)` is exact for equal weights, so the *mechanism* is testable even though VNINDEX's actual weights are not |

---

## What is already true, and must not be re-derived

- **`cross_year_eval` and `anchor_frequency` already exist and are complete**
  (`research/compare.py:63`, `research/stability.py:44`). This phase adds studies beside them; it
  does not reimplement them.
- **`greedy.brute_force_best` already exists** (`anchors/greedy.py:191`). Stage D's faster path is
  verified *against it*, not in place of it.
- **`export.py` is the only module that writes** (`research/export.py:148`), and `_write_csv`
  (`:99`) already turns any dataclass row list into CSV. New studies supply dataclasses and
  nothing else.
- **The verification idiom is `--selftest`, not pytest.** `tests/` is empty; `pipelines/` has no
  test runner and there is no CI. `research/compare.py:338` and `research/stability.py:260` are
  the two files to copy exactly — `main() -> int`, `import argparse` inside it, `--selftest` as
  the only mode, a local `check(label, fn)` helper, `sys.exit(main())`.
- **`data/reference/sector_map.csv` exists and covers the universe**, loaded by
  `universe/sync.py:177`. Stage E does not need new data.
- **Both flags are persisted** in `data/processed/daily_returns/ticker=*/data.parquet`
  (`at_limit`, `zero_volume`, plus `log_return`). Stage C needs no refetch.
- **`Group.sector_composition` stays `{}`.** Filling it would change `content_sha256` and hence
  every `artifact_id` — the exact thing N4 exists to prevent. Stage E writes its own file.
- **τ never enters the objective** (`docs/02` §3f). Nothing in Stage G can change an anchor set.

---

## Progress

### P12.0 — Plan and decision record — **DONE**

- This file created (`docs/WORKFLOW.md` §2 requires it before any mutation).
- `docs/decisions/D-25-permutation-calibration-of-tau.md` written; index row added to
  `docs/decisions/README.md`.
- No code touched in this step.

### P12.H — Correct the three justifications — **DONE**

| File | Correction made |
|---|---|
| `pipelines/factor/model.py:17-19` (now `:17-25`) | Split into two claims: keeping the intercept **in the fit** changes β̂ (from `(f·x)/(f·f)` to the demeaned covariance form) and therefore E — that is why keeping it is correct. The α **term inside the residual expression** cannot affect ρ², since Pearson demeans each column before comparing them, so a per-ticker constant is invisible to correlation |
| `docs/01-data-pipeline.md:115-116` | Replaced the one sentence that contradicted `docs/02:25` — *"It is the only condition the objective actually requires"* — with: non-negativity supplies **normalisation** (F(∅)=0, F never negative), which is what NWF needs; monotonicity and submodularity hold for any real P. Added the two real reasons to square (R² reading; ρ≈−0.9 as structural coupling). Left `:111` and `:118-119` untouched — verified correct on inspection, narrower than the plan's original `:115-119` span |
| `pipelines/model/train.py:15-18` | V12 downgraded to a bookkeeping check (same `F(S) = Σ_i P[i,a(i)]` quantity down two code paths); points at `pipelines.research.residuals.assert_reproduces_p` (built in P12.0b, below) as the check that is actually independent — it re-fits from re-loaded returns rather than re-deriving from the same P |
| `docs/01-data-pipeline.md:110` | Amended, not deleted: added a paragraph after the properties table stating the tautology cost (44.7% of F at k=10, 2025) and pointing at F̄_adj and the forthcoming diagonal-comparison study |
| `pipelines/model/dcor.py:143-144` | `residual_dcor2_u`'s docstring now names normalisation explicitly and states monotonicity/submodularity hold for any real P, consistent with the corrected `docs/01` |
| `docs/03-temporal-design.md:27` | 4,950 → 3,570, with a note pointing at the frozen 85-ticker research universe |
| `docs/decisions/README.md:48` | 4,950 → 3,570 inside D-2, with a note that it was stale relative to [[D-12]] |

**Correction made mid-implementation, not in the original plan table:** checking `docs/01:111`
and `:118-119` against `docs/02:25` before editing showed only `:115-116` actually contradicted
`docs/02` — the table row (`:111`) and the closing sentence about non-monotone submodular
maximisation (`:118-119`) were already correct. The plan's original `:115-119` span would have
touched two correct sentences along with the one wrong one; narrowed to `:115-116` to avoid
that. `docs/03` §2's headline-result location (not §1, where the plan cited it) is where the
3,570 fix actually landed — the number appears once in the file, in the paragraph explaining why
the noise floor now applies to the headline result.

**Verification.** All three existing smokes re-run clean after the edits:

```
python -m pipelines.factor.model    → EXIT=0, beta/sigma recovery unchanged, assertions OK
python -m pipelines.anchors.greedy  → EXIT=0, F(S)=9.300, ratio=1.0000, assert_identities OK
python -m pipelines.model.dcor      → EXIT=0, matmul-vs-naive 1.11e-16, V mean > U mean as expected
```

No numeric output changed in any of the three — these edits are docstrings and prose only.
`docs/04-static-parameters.md:146` and `supabase/migrations/00007_live_monitors.sql:106` checked
and confirmed untouched (live track, 100 tickers, 4,950 is correct there).

### P12.0b — Shared inputs — **DONE**

- New `pipelines/research/residuals.py`: `WindowInputs` (year, tickers, dates, X, f, E, fit),
  `window_inputs`, `window_inputs_for`, `clear_cache`, `assert_matches_artifact`,
  `assert_reproduces_p`, `FlagMatrices`, `flag_matrices`. Cache key
  `(window_start, window_end, source, index_symbol, tuple(tickers))` deliberately excludes
  `similarity_measure` — verified: 2025 pearson and dcor2 artifacts' `window_inputs()` calls
  return the *same object* (`is`, not `==`), so five loads (one per year) serve all ten
  artifacts, not ten.
- `pipelines/research/compare.py`: `compute_dcor_u_means` signature changed to
  `(dcor_by_year, inputs_by_year)`; the in-function `load_return_matrix`/`fit_factor_model`
  imports removed. The module is now fully pure again — no `pipelines.research.*` file except
  `residuals.py` itself touches disk.
- `pipelines/research/export.py`: minimal wiring only — the one existing call site now builds
  `window_inputs_for(by_measure["dcor2"])` and passes it through. This is **not** the full
  P12.I orchestration (no `--only`/`--skip`/`--exact-k` flags, no per-measure calls for stages
  A–G, no `method_studies` block yet) — just enough to keep `export.py` runnable so the
  byte-identical regression check below is meaningful. Marked with an inline comment pointing
  at P12.I as the stage that replaces it with a single shared `inputs_by_year`.
- `docs/decisions/D-27-residuals-recomputed-not-stored.md` written; index row added to
  `docs/decisions/README.md`.

**Correction made mid-implementation.** The plan's citation "`compare.compute_dcor_u_means`'s
docstring at `:203-210`... `schema.py`'s own design" turned out to attribute a quote to the
wrong file — `pipelines/artifact/schema.py` does not contain that sentence (grepped, zero
matches). The actual source is `supabase/README.md:33-35`: *"`X` and `E` genuinely are not
stored — they are recomputable from the returns and belong to a window, not to the data."* Both
`residuals.py`'s module docstring and the corrected `compute_dcor_u_means` docstring now cite
`supabase/README.md` instead of the nonexistent `schema.py` quote, and D-27 cites it too.

**Verification, beyond the plan's four `_selftest()` items.** `residuals._selftest()` implements
all four (cache reuse across measures, a session-count mismatch raising, a stub-reader date hole
raising, shapes matching) plus two not in the original plan: `assert_matches_artifact` and
`assert_reproduces_p` both *passing* on the real, on-disk 2025 artifacts (proving the checks are
not vacuous), and `assert_reproduces_p` *raising* when handed a deliberately corrupted copy of
P (proving the check has teeth in both directions, not just the direction the plan named).
`flag_matrices` was also checked by hand against real 2025 data outside the selftest — see the
Validation table below; its counts reproduce the Context section's numbers exactly.

### P12.A — Diagonal comparison and adjusted F̄ — **DONE (module; CSV lands with P12.I)**

- New `pipelines/research/diagonal.py`: `zero_diagonal`, `adjusted_fbar`, `coverage_excl`,
  `decompose_gains`, `marginal_gain_floor`, `first_divergence`, `diagonal_comparison`,
  `diagonal_curves`, plus `DiagonalRow` / `DiagonalCurveRow` exactly as the plan specified them.
  Pure over `(artifact.P, artifact.run)`; reuses `greedy`/`coverage` untouched. Writing the two
  CSVs is P12.I's job — the module has no disk path, per N1.
- `first_divergence` compares **prefix sets**, not positions: greedy can reach the same set in a
  different order, and the study's question is which tickers are chosen. Stated in the docstring
  because the two definitions disagree on real fixtures.
- `_assert_matches_stored_curve` re-runs greedy on `artifact.P` and requires it to reproduce the
  artifact's own recorded anchor sequence. Bookkeeping, not independence (same P, same code) —
  the docstring says so and points at `residuals.assert_reproduces_p`, per the P12.H correction.

**The headline finding, which reframes review item 2 rather than confirming it.** The tautology
is real and large — 44.7 % of F at k=10 for 2025 pearson, 44.7–54.3 % across the ten artifacts —
and the floor is real too: it is 72–83 % of the last published round's gain, and 98.6 % of the
gain at k=15 (Δ=0.9916, matching the review's 0.990). But the review's *inference* from the floor
does not hold. `F(S) = F_excl(S) + |S|` for **every** set, so `ΔF(v|S) = ΔF_excl(v|S) + 1`, and
the two objectives rank every candidate identically at every round: **greedy on the unit diagonal
is step-for-step greedy on F_excl.** Verified two ways — asserted against a reference F_excl
greedy in the selftest, and measured on 2025 pearson, where both select the same ten positions
`[80,37,54,62,30,70,35,14,10,79]`. The `−c_v` inside the floor is F_excl's own accounting for row
v leaving the sum, not a distortion.

`F₀` is the objective that actually differs: zeroing the diagonal keeps the anchors' rows in the
sum, so it pays for anchors covering each other. On the common yardstick that **costs**:
`F̄_excl(S_zero) < F̄_excl(S_unit)` in all ten artifacts (2025 pearson 0.1468 vs 0.1647; 2024
pearson 0.0916 vs 0.1200). So what the unit diagonal corrupts is the reported **value**, not the
**choice** — and P12.J, which would adopt F₀, currently has evidence against it rather than for
it. That gate stays closed pending B–D.

**Two plan assumptions failed on contact and were replaced.** The selftest fixtures the plan
named do not do what it says:
- `hub_p(10,0)` at k≥3 does **not** diverge — unit and zero both give `[0,1,2]`, so plan item 3
  would have asserted nothing.
- `block_p(9,(3,3,3),0.7,0.05)` at k=3 **does** diverge (unit `[6,0,3]`, zero `[0,3,6]`) — but
  by accident: its columns tie in exact arithmetic and float summation error (~1e-15) picks the
  winner, so plan item 2's "must coincide" would have been testing arithmetic noise.
  `_fixtures.block_p`'s docstring asserted the opposite ("always resolves to position 0");
  corrected in place, with the measured counter-examples. `greedy`'s determinism is unaffected —
  same P, same answer, every run.

Replaced by two new fixtures in `_fixtures.py`, both tie-free by construction:
`centred_blocks()` (distinct block strengths, a designated centre per block — the two objectives
agree, so the tool is shown not to manufacture divergence) and `neglected_p()` (two tight blocks
plus two near-isolated tickers — agreement through step 2, divergence at step 3 where the unit
objective takes an isolated ticker and the zero objective does not). The second is the review's
§2.2 mechanism in miniature; if it could not reproduce it, this study could not detect it in the
real data either.

**Verification.** `python -m pipelines.research.diagonal --selftest` → **9 passed, 0 failed**
(the plan's six, plus the diagonal-invariance of `coverage_excl`, the F_excl-greedy equivalence,
and the stored-curve guard firing). `compare`, `stability` and `residuals` selftests re-run green
after the `_fixtures.py` change; the three P12.H smokes still green; `ruff check pipelines/`
clean. All ten `diagonal_comparison` rows reproduce the independently measured targets — not just
the four in the acceptance table below but all ten years × both measures, on `jaccard`,
`first_divergence_k`, `fbar_unit` and `fbar_adjusted`. `fbar_adjusted` equals `fbar_excl_unit` to
5.6e-17 on real data, which is the N2 identity checked live rather than assumed.

### P12.B — Marchenko–Pastur spectrum — **DONE (module; CSV lands with P12.I)**

- New `pipelines/research/spectrum.py`: `mp_edges`, `correlation_spectrum`, `spectrum_table`,
  `eigenvalue_rows`, `SpectrumRow`, `EigenvalueRow`, exactly as planned. Carries
  `stage ∈ {"raw","residual"}`, computed once per year (E does not depend on
  `similarity_measure` — same fact P12.0b's cache relies on), so P12.I writes exactly one
  `spectrum.csv` / `spectrum_eigenvalues.csv` pair, no `_{measure}` suffix. Pure over
  `WindowInputs.X`/`.E`; no disk access, no refit.

**Verified against all ten artifacts, not just the three named in the acceptance table.**
`n_above_edge` on the residual is **not** 5 every year as the plan's Context section implied —
it is 4 in 2024 and 5 in the other four years (2021/2022/2023/2025). Corrected in the module
docstring before it could ship a wrong universal claim; the acceptance table's three targets
(2025 residual, 2025 raw, 2021 residual) all still match exactly:

| year | stage | q | mp_upper | λ₁ | λ₂ | λ₃ | n_above_edge |
|---|---|---|---|---|---|---|---|
| 2021 | raw | 0.3400 | 2.5062 | 28.94 | 5.62 | 2.72 | 3 |
| 2021 | residual | 0.3400 | 2.5062 | 10.27 ✓ | 5.40 | 3.40 | 5 ✓ |
| 2022 | raw | 0.3414 | 2.5099 | 36.17 | 4.67 | 3.48 | 3 |
| 2022 | residual | 0.3414 | 2.5099 | 9.47 | 7.72 | 4.07 | 5 |
| 2023 | raw | 0.3414 | 2.5099 | 35.39 | 2.97 | 2.26 | 2 |
| 2023 | residual | 0.3414 | 2.5099 | 9.70 | 3.97 | 3.59 | 5 |
| 2024 | raw | 0.3400 | 2.5062 | 31.31 | 3.56 | 3.16 | 3 |
| 2024 | residual | 0.3400 | 2.5062 | 8.27 | 4.80 | 4.14 | **4** |
| 2025 | raw | 0.3414 | 2.5099 | 34.85 ✓ | 3.77 | 3.04 | 3 ✓ |
| 2025 | residual | 0.3414 | 2.5099 | 11.06 ✓ | 5.46 ✓ | 4.60 ✓ | 5 ✓ |

`trace(corr) == N` to <1e-6 on all ten rows — the identity check the selftest also runs on
synthetic fixtures, confirmed live on real data.

**Verification.** `python -m pipelines.research.spectrum --selftest` → **6/6 passed** (pure
noise clears nothing, one injected factor clears exactly one, three block factors clear at
least three, `mp_edges(0.3414)` matches `docs/01` §6's ≈2.51, trace==N on synthetic fixtures,
and `spectrum_table` produces one raw + one residual row per year with the fit demonstrably
lowering λ₁). `ruff check pipelines/` clean. `diagonal`, `compare`, `stability`, `residuals`
selftests still green — no regression from adding this module.

### P12.C — Flag sensitivity — **DONE (module; CSV lands with P12.I)**

- New `pipelines/research/robustness.py`: `pair_overlap`, `pairwise_complete_rho2`,
  `flag_sensitivity`, `zero_return_pair_stats`, `pair_stats_spearman`, plus the table-level
  orchestrators `flag_sensitivity_table`/`zero_return_pairs_table` (not in the plan's literal
  function list, added so P12.I has one call per measure rather than hand-looping over years —
  same pattern as `diagonal_comparison`/`diagonal_curves` in P12.A). `FlagRow`/`PairStatRow`
  match the plan's fields, with `year`/`measure` (and `tickers`) added as keyword-only args to
  `flag_sensitivity`/`zero_return_pair_stats` beyond the plan's literal `(P_base, E, mask, k,
  tickers, label)` / `(mask, P)` signatures — disclosed, not silent, because the rows need them
  to be self-describing. `flag_sensitivity_table` **raises** on a non-`pearson_rho2` artifact
  rather than silently computing a masked recompute dCor's statistics do not support.

**All four constraints the plan named up front held, and the real numbers sharpened one of
them.** Measured on every research year via `residuals.flag_matrices` + `flag_sensitivity_table`
(not just the 2025 the plan's Context section quoted):

| year | flag | n_flagged | share | min_pair_T | spearman | jaccard | F̄_excl base | F̄_excl masked |
|---|---|---|---|---|---|---|---|---|
| 2021 | at_limit | 927 | 4.4% | 195 | 0.808 | 0.429 | 0.1308 | 0.1133 |
| 2021 | zero_return | 1386 | 6.5% | 144 | 0.985 | 1.000 | 0.1308 | 0.1392 |
| 2021 | zero_volume | 0 | 0.0% | 250 | 1.000 | 1.000 | 0.1308 | 0.1308 |
| 2022 | at_limit | 2287 | 10.8% | 126 | 0.687 | 0.333 | 0.1649 | 0.1312 |
| 2022 | zero_return | 1259 | 6.0% | 157 | 0.982 | 0.818 | 0.1649 | 0.1731 |
| 2023 | at_limit | 572 | 2.7% | 209 | 0.850 | 0.818 | 0.1362 | 0.1216 |
| 2023 | zero_return | 1656 | 7.8% | 151 | 0.971 | 1.000 | 0.1362 | 0.1439 |
| 2024 | at_limit | 243 | 1.1% | 226 | 0.863 | 0.538 | 0.1200 | 0.1102 |
| 2024 | zero_return | 1941 | 9.1% | 145 | 0.972 | 0.818 | 0.1200 | 0.1309 |
| 2025 | at_limit | 809 | 3.8% | 201 | 0.783 | 0.667 | 0.1647 | 0.1428 |
| 2025 | zero_return | 1660 | 7.8% | 140 | 0.983 | 0.818 | 0.1647 | 0.1757 |
| 2025 | zero_volume | 0 | 0.0% | 249 | 1.000 | 1.000 | 0.1647 | 0.1647 |

(2022/2023/2024 `zero_volume` rows omitted — all `n_flagged=0`, same as 2021/2025.)

- **`zero_volume` fires zero times in every one of the five years**, not just 2025 — a stronger
  form of the plan's Context claim, closing that reading of the review's §4.2 threat completely.
- **`at_limit` matters more than `zero_return` despite flagging fewer sessions, and the direction
  reverses.** `at_limit` masking drops jaccard as low as 0.333 (2022) and **costs** the yardstick
  every year (`F̄_excl` falls). `zero_return` masking keeps jaccard ≥0.818 and **improves** the
  yardstick every year. VIC (the 2025 `at_limit` max at 26 sessions) is confirmed to **drop out
  of the selection** when `at_limit` sessions are excluded — `anchors_base` contains it,
  `anchors_masked` does not. Read together: a ticker repeatedly hitting its price limit is
  carrying real, if censored, information that the masked recompute genuinely loses; a stale
  zero-return session is closer to non-informative than to a spurious-correlation channel in
  this data — the opposite of treating both flags as equivalent contamination, which is how the
  review's §4.2 originally framed them.
- **The co-occurrence check confirms the second half of that reading directly.**
  `zero_return_pairs_table` + `pair_stats_spearman` over all C(85,2)=3,570 pairs, both measures,
  2025: Spearman(n_cooccur_zero, ρ²) = **-0.058** (pearson), **-0.018** (dcor2) — no rank
  association, so shared zero-return days are not manufacturing the spurious correlation §4.2
  worried about, at least not in a way a rank statistic detects.
- `min_pair_T` under `zero_return` masking falls to 140 in 2025 (out of T=249, a 44 % loss for
  the worst pair) — worse than the plan's "~40%" estimate from KOS's individual 28.5 %, confirming
  `min_pair_T` earns its place as a mandatory column rather than a nice-to-have.

**Two selftest fixtures needed iteration before they proved what they claimed to.** Both failures
were caught on the first run, not shipped:
1. A hand-built 4×3 mask's expected `pair_overlap` diagonal/pair counts were mis-computed by
   hand in the first draft (`[3,3,1]` written, `[3,3,2]` correct — ticker 2 is valid on two rows,
   not one; pair(1,2) is 2, not 1). Recomputed by hand a second time against the actual `valid`
   matrix and fixed the assertions, not the code.
2. A `pair_stats_spearman` fixture assigned flag days **per pair** while writing to a **per-
   ticker** mask array — later pairs sharing a ticker silently overwrote that ticker's earlier
   flag days, so the realized co-occurrence no longer matched the value the test assumed when it
   set ρ². Replaced with per-ticker independent flag sets (co-occurrence falls out as the
   overlap, computed once, then ρ² set as an exact function of it) — Spearman came out at 1.0 as
   intended.

**Verification.** `python -m pipelines.research.robustness --selftest` → **8/8 passed** (all-
False mask matches `residual_similarity` to 1e-12; a Gram-Schmidt-orthogonalized clean pair with
an injected shared zero-return block shows raw ρ² inflated to 0.45 and masked recompute
recovering ~1e-7; hand-built `pair_overlap`; a fully masked column gives row/col 0, diagonal 1,
no NaN; `flag_sensitivity` is the identity when nothing is flagged; it changes the k=1 pick when
a manufactured block is masked out; `flag_sensitivity_table` raises on `dcor2`; the co-occurrence/
ρ² Spearman check). `ruff check pipelines/` clean. `diagonal`, `spectrum`, `compare`, `stability`,
`residuals` selftests still green. `flag_matrices` for all 5 years + `flag_sensitivity_table` for
pearson (15 rows) + `zero_return_pairs_table` for both measures (17,850 rows total) run in under
10 seconds against the real artifacts — no `--exact-k`-style gating needed for this stage.

### P12.D — Exact optimum for small k — **DONE (module; CSV lands with P12.I)**

- New `pipelines/research/exact.py`: `brute_force_best_batched`, `approximation_table`,
  `ApproxRow`, exactly as planned. DFS over size-(k−1) prefixes carrying the running coverage
  vector `c`; the final level scores every remaining candidate in one vectorised call
  (`np.maximum(P[:, candidates], c[:, None]).sum(axis=0)`) instead of `C(N,k)` separate
  per-combination reductions. `count_leaves` records into a module-level `_last_leaf_count`
  slot rather than widening the return type — the function's contract stays exactly
  `(tuple[int, ...], float)`, matching `greedy.brute_force_best`, regardless of the flag.

**Measured timing matches the plan's estimate closely, on the real 2025 pearson artifact
(N=85):** k=3 → **0.05 s** (plan: 0.05 s), k=4 → **1.20–1.22 s** (plan: 1.20 s), k=5 → **23.0–
24.3 s** (plan: ~25 s) — against 0.64 s for `greedy.brute_force_best` at k=3 alone (already ~13×
slower than the batched version at that k, before the gap widens further at k=4–5).

**Greedy is exactly optimal for k=1..5 on the 2025 pearson artifact, both diagonals** — `ratio =
1.00000` and `set_equal = True` at every k, unit and zero. Not assumed, not merely "close to 1":
measured directly against the batched exact search. This is a genuine finding, not just a
sanity check that the module works — the `(1−1/e)` bound is a worst-case guarantee, and on this
real, well-clustered data greedy reaches the true optimum well past the point the bound alone
would promise.

**Acceptance target met exactly.** `f_exact` at k=3 on 2025 pearson: batched **12.003468**,
independently computed `greedy.brute_force_best(P, 3)[1]` **12.003468**, same selected set,
`|diff| = 0.0`.

**Verification.** `python -m pipelines.research.exact --selftest` → **5/5 passed**: agreement
with `greedy.brute_force_best` (set *and* F, exactly) on five fixtures (`block_p(12,(4,4,4))`,
`hub_p(10,3)`, three random symmetric N=14 matrices) at k=1..4; leaf count instrumentation equals
`C(N,k)` exactly on every fixture/k; a dedicated exact-tie fixture (every off-diagonal entry
identically 0.5, not `block_p`'s float-noise-decided near-ties — see P12.A's correction to that
fixture) shows both implementations landing on the same lexicographically smallest subset;
`f_exact >= f_greedy` and `ratio <= 1` hold on every fixture/k; `approximation_table` produces
correct rows for both diagonals, skips `k > N` rather than raising, and confirms greedy is exact
on a clean block fixture. `ruff check pipelines/` clean. `diagonal`, `spectrum`, `robustness`,
`compare`, `stability`, `residuals` selftests still green.

### P12.E — Sector cross-reference — **DONE (module; CSV lands with P12.I)**

- New `pipelines/research/sectors.py`: `group_members`, `universe_sector_shares`, `hhi`,
  `expected_hhi_random`, `group_sector_table`, `universe_sector_summary`, `GroupSectorRow` —
  matching the plan, plus the small helpers (`_dominant`) the row construction needs.
  `group_members` reads `ticker_params.anchor_ticker` (already sealed) rather than re-deriving
  the assignment via `assign()` — the genuine independent cross-check belongs to P12.A's
  `diagonal.py`, this module's job is the sector overlay. `expected_hhi_random` is a **closed
  form** (`E[HHI] = 1/n + (n−1)/n · Σp_s²`, derived from the multinomial second moment), not a
  simulated mean — deterministic, no seed, exact — verified against a 20,000-draw Monte Carlo in
  the selftest rather than assumed correct from the derivation alone.
- **`_fixtures.fabricate_artifact` now populates `Group` rows** (previously always `groups=[]`)
  from the same `assign()` output it already computes — `f_j`/`rho2_mean_j`/cluster sizes were
  sitting right there unused. This is what makes the plan's required selftest item ("size/
  rho2_mean/rho2_min match the artifact's own Group rows") runnable at all; without it there
  would be no Group to check a fixture-built row against. Grepped first for anything relying on
  the fixture's `groups` being empty — nothing does (`residuals.py`'s one reference passes
  `art_p.groups` through verbatim from a *real* on-disk artifact, unaffected). Confirmed
  backward-compatible: full regression re-run clean after the change.

**Two claims the plan's Context section carried unverified, checked against real data before
they could ship wrong:**
1. `data/reference/sector_map.csv` covers the frozen universe **completely** — `n_unlabelled=0`
   across all 85 tickers, so the "never excluded from size" behaviour for a missing ticker has
   no real-data example to exercise; covered instead by a dedicated selftest fixture (item 3
   below) built specifically to hit that path.
2. **SZC is not actually an example of the sector/industry divergence the plan's Context section
   claimed.** Measured across all 100 (year, measure, anchor) rows: SZC anchors five times, and
   `dominant_sector_share` equals `dominant_industry_share` in **all five** (0.38–0.60 either
   way) — GVR and PHR, the two members whose industry label ("SX Nhựa - Hóa chất") differs from
   the real-estate names in SZC's cluster, happen to map to a *different* sector bucket too
   ("Nguyên vật liệu"), so the sector-level split and the industry-level split coincide exactly
   for this particular cluster, every year. **LCG is the real example**, found by checking all
   100 rows rather than assuming the plan's illustrative pick was right: every year LCG anchors,
   its dominant sector share (0.44–0.71) sits well above its dominant industry share (0.25–0.47)
   — the "Bất động sản và Xây dựng" bucket is absorbing at least two industries LCG's own
   cluster actually splits across. 34 of the 100 rows show this kind of divergence overall. The
   module docstring was corrected to cite LCG with the measured numbers and to say plainly that
   SZC does not show it, rather than ship the review's unverified illustrative claim.

**Verification.** `python -m pipelines.research.sectors --selftest` → **6/6 passed** (uniform
cluster → HHI=1.0; round-robin across n labels → HHI≈1/n; unlabelled members counted in `size`
but excluded from composition; cluster sizes partition N and `rho2_mean`/`rho2_min` reconcile
with the fixture's own newly-populated `Group` rows; `expected_hhi_random`'s closed form matches
a 20,000-draw Monte Carlo to within 0.01 at n∈{2,5,10}, and n=1 gives exactly 1.0;
`group_members` partitions the universe with every anchor its own member). `ruff check
pipelines/` clean. `diagonal`, `spectrum`, `robustness`, `exact`, `compare`, `stability`,
`residuals` selftests still green — no regression from the `_fixtures.py` change.

**Real-data check beyond the plan's one acceptance target.** `Σ size == 85` holds for all ten
(year, measure) pairs, not just one; `size`/`rho2_mean`/`rho2_min` reconcile with the real
on-disk artifacts' own stored `Group` rows to floating-point noise (max diff 1.11e-16). Universe
composition (frozen across years/measures per D-12, computed once): 9 sectors, `Bất động sản và
Xây dựng` largest at 24/85 (28.2%), `Công nghệ`/`Công nghiệp` smallest at 2/85 each (2.4%).

### P12.F — Equal-weight and leave-one-out factor — **DONE (module; CSV lands with P12.I)**

- New `pipelines/research/factor_alt.py`: `equal_weight_factor`, `loo_factors`, `fit_against`,
  `factor_alternatives`, `FactorAltRow`, matching the plan. `f_{−i} = (N·f_ew − x_i)/(N−1)` is
  exact (sum-minus-self identity), making the full N-column LOO fit one vectorised pass — no
  loop over N. `fit_against` generalises `factor.model.fit_factor_model` to a **per-column**
  factor (`F_cols` may be (T,) or (T,N)) in that same one vectorised pass; it reproduces
  `fit_factor_model` bit-for-bit when `F_cols` is 1-D rather than being a separate code path
  (checked to 1e-10 in the selftest, not assumed from the algebra).
- **Explicit scope limit re-confirmed, not just carried over from the plan.** Re-grepped for
  market-cap/free-float/index-weight data before writing the module docstring's limitation
  paragraph — still none in the repo, and `data/processed/index_bars/` still holds only
  `index_symbol=VNINDEX`. The equal-weight + LOO pair is the complete feasible substitute, stated
  as such rather than left as an implicit gap.

**A planned selftest fixture did not demonstrate the claimed mechanism, and was redesigned before
shipping.** The original fixture (two tickers sharing an extra idiosyncratic shock, on top of a
common factor, N=20) was meant to show LOO shrinking a manufactured *pairwise* ρ² inflation — it
did not move the needle (equal_weight ρ²=0.9905 vs loo=0.9907, backwards). Working through why:
self-inclusion bias is mechanically `O(1/N)` (`f_ew` contains an exact `1/N` sliver of every
ticker's own return), so at N=20 the leakage from two tickers is too diluted to show up as a
pairwise effect, and the fixture never isolated the actual mechanism — a ticker's **own R²**
being inflated by regressing against a factor that partly *is* itself. Redesigned around that
directly: N=4 (so the `1/N` self-weight is large enough to matter), idiosyncratic noise
dominating a small common component (so the *true* R² against the real signal is near zero).
Prototyped in a scratch script before writing the final assertion — mean R² under equal-weight
came out at **0.291**, under LOO at **0.009** (near the fixture's true near-zero value) — then
written into the selftest with that measured gap as the assertion, not a guessed threshold.

**Measured on the real 85-ticker universe (all 15 rows, both measures, in under 1.2 s total —
no gating needed for this stage), the same mechanism is present but small, exactly as its `O(1/N)`
scaling predicts:**

| year | variant | corr_f_with_index | mean_r2 | jaccard_vs_index | fbar_excl |
|---|---|---|---|---|---|
| 2021 | index | 1.0000 | 0.3131 | 1.000 | 0.1308 |
| 2021 | equal_weight | 0.9409 | 0.3395 | 0.538 | 0.1156 |
| 2021 | loo | 0.9408 | 0.3245 | 0.538 | 0.1156 |
| 2025 | index | 1.0000 | 0.3583 | 1.000 | 0.1647 |
| 2025 | equal_weight | 0.9347 | 0.4089 | 0.250 | 0.1197 |
| 2025 | loo | 0.9346 | 0.3957 | 0.250 | 0.1198 |

(pearson_rho2; the remaining three years and the dcor2 rows follow the same pattern.)

- `mean_r2` for `equal_weight` sits consistently above `loo`'s in **every one of the ten
  (year, measure) pairs** (e.g. 2021: 0.3395 vs 0.3245) — the self-inclusion leakage the
  selftest isolated at N=4 is still measurably present at N=85, just far smaller in absolute
  terms, matching the predicted `1/85` vs `1/4` scaling (~20×).
- **That leakage never changes which anchors get picked.** `equal_weight` and `loo` select the
  *identical* anchor set in all ten (year, measure) pairs (`jaccard_vs_index` matches exactly
  between the two variants every time) — the R² gap is real but too small at N=85 to move a
  greedy selection. This is itself the answer the review's item 7 was asking for: index
  membership does inflate residual fit statistics mechanically, but not enough, at this
  universe size, to change the anchor set.
- **The choice of factor (VNINDEX vs. equal-weight) changes the anchor set far more than the
  self-inclusion mechanism does.** `jaccard_vs_index` for `equal_weight`/`loo` ranges 0.250–0.818
  across the ten pairs — often less than half the published anchors survive switching to a
  different (still non-cap-weighted) factor. `fbar_excl` on the common yardstick favours the
  published VNINDEX-based selection over both alternatives in every single row measured.

**Verification.** `python -m pipelines.research.factor_alt --selftest` → **5/5 passed**:
`fit_against` reproduces `fit_factor_model` bit-for-bit on 1-D input; `loo_factors` matches an
explicit `np.delete`-and-average for every ticker; the redesigned self-inclusion fixture; `N=1`
raises; `factor_alternatives`'s `"index"` row is self-consistent against its own baseline
(jaccard=1, spearman=1). `ruff check pipelines/` clean. `sectors`, `diagonal`, `spectrum`,
`robustness`, `exact`, `compare`, `stability`, `residuals` selftests still green.

### P12.G — Permutation calibration of τ — **DONE (module; CSV lands with P12.I)**

- New `pipelines/research/nulls.py`: `permute_columns`, `permutation_null`, `NullRow`, plus the
  table-level `tau_calibration_table` orchestrator (same pattern as every other P12 stage's
  low-level-function + table-level-wrapper split). Columns permuted **independently** via one
  vectorised argsort-of-random-keys — a shared permutation leaves `corr(E)` unchanged and would
  render the null silently useless; the selftest asserts the mean off-diagonal similarity
  collapses under the real (independent) implementation and confirms a **deliberately-wrong**
  shared-order version leaves it exactly unchanged, proving independence is what does the work,
  not merely asserting it should.
- **Anchors excluded from the null pool, and the reason is arithmetic, not aesthetic.** At the
  research universe's N=85, k=10, anchors are 11.8 % of the universe — above the 5 %/1 % this
  module reports percentiles at, so pooling all N tickers' `c_i` (anchors included, always
  exactly 1.0) would make `c_p95`/`c_p99` report back `1.0`, uselessly. Every percentile pools
  `c_i` for `i ∉ S` only, in every replicate — `F_excl`'s "exclude S from the sum" move (P12.A),
  applied to the null. Selftest item 5 confirms `c_max < 1.0` on a fixture, i.e. no anchor's
  trivial self-coverage leaked into the pool.

**D-25's own cross-check claim was imprecise about which statistic it meant, and this was
resolved by measuring before writing the assertion, not by picking whichever reading was
convenient.** D-25 says "the permutation p95 must land near the `docs/01` §6 figure [≈0.07]"
without saying which p95. Measured on i.i.d. Gaussian noise at `docs/01` §6's own reference point
(T=250, N=85): `NullRow.c_p95` (95th percentile of the anchors-excluded `c_i` pool at k=10) comes
out at **≈0.040** — not "near" 0.07 by any reasonable reading, because it is a percentile of a
*max-of-10* statistic, systematically smaller than a max over all 3,570 pairs. The statistic that
**does** land near ≈0.07: the **raw pairwise maximum** — no `greedy`/`k` involved, just the
largest entry in a single permuted replicate's full similarity matrix — measured at mean ≈0.055,
per-replicate range 0.040–0.097, comfortably the same order of magnitude as the analytic figure.
The module docstring documents both numbers and states plainly that `c_p95` is not expected to
match the `docs/01` figure and why; the selftest's cross-check (item 4) uses the raw pairwise
maximum, the statistic that is actually the empirical analogue of what `docs/01` §6 computes.

**Measured on the real 2025 pearson artifact, 1000 reps (1.01 s — faster than the plan's ~2 s
estimate):** `c_p50=0.0186`, `c_p95=0.0415`, `c_p99=0.0552`, `c_max=0.1173`,
`fbar_excl_p95=0.0222`. `tau_current=0.10` (from the sealed `RunMeta.tau`) gives
`n_under_tau_current=33` — **exactly the "33 of 85" figure D-25 itself cites**, an independent
confirmation that `art.run.tau`/`ticker_params.coverage_c` are being read correctly. `tau_p95 =
0.0415` sits **below** `tau_current = 0.10`, and D-25's second accepted-in-advance outcome is
therefore the one that landed: **τ = 0.10 is conservative** relative to what pure chance would
justify at the 95th percentile — the report gets a computed figure instead of an assertion, per
D-25's own terms. At the null-calibrated threshold, only `n_under_tau_p95=13` tickers would be
flagged as indistinguishable from chance coverage, against 33 under the current, stricter τ.

**Timing confirmed for the more expensive measure too** — 2025 dcor2, 1000 reps: **59.4 s**
(plan estimate ~70 s), giving `c_p95=0.0460`, `n_under_tau_current=32`, `n_under_tau_p95=9`. Five
years × two measures extrapolates to comfortably under the plan's "under 7 minutes" total.

**Verification.** `python -m pipelines.research.nulls --selftest` → **5/5 passed**: permutation
preserves each column's exact multiset; independence is what collapses structure (and a
deliberately-wrong shared-order version does *not* collapse it — checked, not assumed); same
seed reproduces bit-for-bit; the pure-noise cross-check lands within 0.5–1.5× the analytic floor
using the correct (raw pairwise-max) statistic; no anchor's trivial `c_i=1.0` leaks into the
pooled null. `ruff check pipelines/` clean. `factor_alt`, `sectors`, `diagonal`, `spectrum`,
`robustness`, `exact`, `compare`, `stability`, `residuals` selftests still green.

### P12.I — Orchestration — **DONE**

- `export.py` rewritten: `build_inputs_by_year` (one `inputs_by_year` across every measure —
  picks an arbitrary artifact per year, safe because the cache key excludes
  `similarity_measure` and D-12 freezes one window/universe per year) +
  `verify_every_artifact_reproduces_p` (`assert_matches_artifact` + `assert_reproduces_p` for
  **every** artifact, called before any study runs, not just before the ones that need E
  directly). `compute_dcor_u_means` now takes the shared `inputs_by_year` — the P12.0b interim
  wiring (its own `window_inputs_for(by_measure["dcor2"])` call) is gone.
- Stages A, C, D, E, G run inside the existing per-measure loop; B runs once
  (measure-independent); F runs once per measure but its rows are accumulated and written to a
  single un-suffixed `factor_alternatives.csv` (the file the plan's new-files list names has no
  `_{measure}` suffix, even though the rows themselves carry a `measure` column — resolved by
  writing one file with both measures' rows rather than two files, after checking the plan's own
  file list literally named it singular).
- CLI: `--only`/`--skip` (stage letters A-G), `--exact-k` (default 5, `0` disables D),
  `--reps`/`--seed` (default 1000/20260827, stage G), `--sector-map` (default
  `data/reference/sector_map.csv`).
- `study.json` gains `method_studies`: `parameters` (every flag's resolved value) and `stages`
  (one entry per stage×measure — `B` alone, since it has no measure axis — each carrying the
  `artifact_id`s consumed and stage-specific detail such as `n_reps`/`seed` for G or `k_values`
  for D). Also carries a `universe_sector_summary` (E's context, not written as a separate CSV).

**A bug in the metadata (not the data) caught during rehearsal, before it could ship.** The
first working version only recorded a `method_studies.stages["C/{measure}"]` entry inside the
`if measure == PEARSON_MEASURE:` branch — so `zero_return_pairs_{measure}.csv`, which *does* run
for both measures, silently had no provenance record for `dcor2`. Caught by inspecting the quick
rehearsal's `study.json` directly rather than assuming the stage-record loop was complete; fixed
by moving the `zero_return_pairs_table` call and its own `_record_stage` (with an explicit
`"flag_sensitivity": "skipped: masked recompute undefined for dCor"` note) ahead of the
pearson-only `flag_sensitivity_table` block. Confirmed via a targeted `--only C --exact-k 1
--reps 20` rerun before touching the full rehearsal again. This changed only `study.json`'s
metadata — every CSV's actual content was already correct under the old wiring.

**Verification — two full-settings rehearsals, then publish.**

1. Quick smoke rehearsal (`--exact-k 2 --reps 50`, 34.5 s): confirmed wiring end-to-end, caught
   the `C/dcor2` metadata gap above, confirmed `--only`/`--skip` work.
2. Full-settings rehearsal (`--exact-k 5 --reps 1000`, default everything else) into a scratch
   dir: **completed without error in ≈15 minutes** — longer than the plan's "~11 minutes"
   estimate, because stage D and G were not costed for *both* measures in that estimate (D:
   10 artifacts × 2 diagonals × ≈26 s dominated by k=5 ≈ 8.7 min; G: pearson ≈5 s + dcor2
   ≈5 min ≈ 5.1 min; the two alone sum past the plan's total). Stated as a correction to the
   plan's estimate, not hidden: **budget ~15 minutes for the default `research.export` run, not
   11.**
3. **Regression, both rehearsals:** the same 7 pre-existing CSVs are byte-identical to
   `data/research/` (`cmp`-verified) in both the quick and the full rehearsal, and
   `study.json`'s pre-existing `stability_studies`/`n_artifacts` keys are unchanged — only
   `method_studies` is new.
4. **Acceptance targets, checked directly from the full rehearsal's own CSVs** (not re-derived
   from the module-level checks done in P12.A/B/C/E): `diagonal_comparison_pearson_rho2.csv`
   2025 → jaccard=0.6667, first_divergence_k=9, fbar_unit=0.2629, fbar_adjusted=0.1647;
   `diagonal_comparison_dcor2.csv` 2022 → first_divergence_k=3; `spectrum.csv` 2025 residual →
   q=0.3414, mp_upper=2.5099, λ₁=11.063, λ₂=5.455, λ₃=4.604, n_above_edge=5;
   `flag_sensitivity_pearson_rho2.csv` 2025 zero_volume → n_flagged=0;
   `group_sectors_pearson_rho2.csv` 2025 → Σsize=85. All match.
5. **Published to the real `data/research/`** (default settings, same ≈15 minutes, exit 0, zero
   errors in the log). All 16 new files present alongside the 7 pre-existing ones and
   `study.json`; the published files are byte-identical to the full rehearsal's own output
   (`cmp`-verified on a spot-check spanning every stage); `method_studies.stages` carries all 13
   entries (`A`/`C`/`D`/`E`/`F`/`G` × 2 measures + `B` once), including the corrected `C/dcor2`.

**A genuine finding surfaced only by running the full sweep, not visible from the single-artifact
spot-checks done in P12.D.** 2024 is the **only** year where greedy is not the exact optimum at
k ≤ 5 — true across **both** measures and **both** diagonals, starting at k=2:

| measure | diagonal | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|
| pearson_rho2 | unit | 0.99529 | 0.99416 | 0.99403 | 0.99644 |
| pearson_rho2 | zero | 0.99427 | 0.99138 | 0.98901 | 0.99592 |
| dcor2 | unit | 0.99303 | 0.99312 | 0.99930 | 0.99848 |
| dcor2 | zero | **0.98984** | 1.00000 | 1.00000 | 0.99834 |

**Corrected against `approximation_dcor2.csv` itself.** An earlier draft of this table read
`dcor2/zero` as `1.00000, 1.00000, 1.00000, 0.99834` and claimed 2021/2022/2023/2025 were exact
at every k. Both are wrong against the CSV: `dcor2/zero/2024` diverges at **k=2** (0.98984),
recovers to exact at k=3 and k=4, then diverges again at k=5 — **not monotone in k**, and a
detail only visible by listing all 100 rows rather than summarising by year. And
`dcor2/zero/2023/k=5` = **0.99956**, so 2023 is *not* exact everywhere either. The full,
correct picture: **85 of 100 rows** have ratio exactly 1.00000; the 15 that do not are
`pearson/unit/2024` (k=2..5), `pearson/zero/2024` (k=2..5), `dcor2/unit/2024` (k=2..5),
`dcor2/zero/2024` (k=2 and k=5), and `dcor2/zero/2023` (k=5 only). 2021, 2022 and 2025 are exact
at every k, both measures, both diagonals.

`approximation_*.csv` is the source of truth; this table is a transcription and has been wrong
once. Cite the CSV, not this table.

**`approximation_*.csv` is the one research output that is not byte-reproducible.** Its `seconds`
column records wall-clock time for the exhaustive search, so a re-run differs there and only
there — verified: every substantive column (`f_greedy`, `f_exact`, `ratio`, `anchors_greedy`,
`anchors_exact`, `set_equal`, `n_subsets`) is identical across runs, and `seconds` moves by
roughly a factor of two on the sub-millisecond rows. `cmp` is therefore the wrong check for this
one file; compare it with the `seconds` column excluded. This does not touch the bit-for-bit
reproducibility of artifacts themselves (`artifact_id` excludes timestamps by construction) — it
is a property of this diagnostic CSV alone. Every ratio still sits comfortably above the `1 − 1/e ≈ 0.632` worst-case guarantee
— greedy is near-optimal even in its one imperfect year — but "greedy reaches the true optimum
for small k" is not a universal statement across the ten artifacts, and the full table (all 100
rows, `approximation_*.csv`) is what the thesis should cite rather than the single 2025 pearson
example P12.D's own verification pass happened to check first.

### P12.J — Adopt the zero-diagonal objective — **CLOSED, not adopted (see [[D-26]])**

The gate opened, the evidence was read, and the answer was no. A–D disprove the premise the change
rested on. Because `P_vv = 1`, the self-cover term of a candidate's marginal gain is not merely
floored near 1 — it is **exactly 1 for every candidate**, so

    ΔF(v | S) = ΔF_excl(v | S) + 1     for every v, at every step

and a constant added to every candidate cannot reorder them. **Greedy on the unit diagonal is,
step for step, greedy on `F_excl`** — the objective the review asked for. The unit diagonal
corrupts the *published number* (44.7 %–54.3 % of F is tautology), not the *selection*. P12.D
corroborates from the other side: greedy is the exact optimum in 85 of 100 rows at k ≤ 5, worst
ratio 0.9890.

What was avoided by not adopting it: `ARTIFACT_SCHEMA_VERSION` 1→2, a new migration, ten new
artifacts alongside the ten existing, and a primary flip — all to obtain a *different* anchor set
with no evidence it is a *better* one. `F₀` sums over anchors' rows too and therefore mildly
rewards anchors resembling each other (weight k/N ≈ 12 %, opposite in sign to the tautology it
removes) — the review's own counter-effect, now the deciding one.

What is owed instead: **`F̄_adj = (F−k)/(N−k)` reported beside `F̄` wherever a coverage headline
appears.** It needs no schema change — `coverage_f`, `k` and `n_tickers` are already in `RunMeta`.

The original shape, kept for the record: `exclude_self` threaded through `coverage()`/`greedy()`
only; `assign()` stays on the unit diagonal so **V14 `a(j)==j` still holds**, `coverage_c` keeps
its meaning, and the API/web consumers are untouched. `RunMeta` gains `selection_objective`,
`ARTIFACT_SCHEMA_VERSION` 1→2, new migration, ten new artifacts — at which point
`export.assert_single_primary` sees two primaries, so the primary flip would have been scheduled
in the same pass rather than discovered.

Rejected shape: storing P₀ in the artifact. Breaks V13 and `assert_similarity`, makes
`anchor_columns()` publish 0 for an anchor's own row, breaks the API's `coverage_c` ordering, and
destroys the ability to recompute the unit-diagonal figures for comparison — same schema bump,
strictly more blast radius.

---

## Validation

This repository has **no test runner for `pipelines/` and no CI**; `tests/` is empty. Every check
below is a command run by hand, and that gap is stated rather than papered over. The table is
filled in as stages land; **measured** and **not attempted** are kept apart, as P10 and P11 did.

### Regression — proves the refactor changed nothing

| Check | Status |
|---|---|
| `python -m pipelines.factor.model`, `... .anchors.greedy`, `... .model.dcor` still green after P12.H's docstring edits | **PASS** — all three EXIT=0, numeric output unchanged (docstring/prose-only edits) |
| `python -m pipelines.research.residuals --selftest` (new module) | **PASS** — 5/5 |
| `python -m pipelines.research.compare --selftest` and `... .stability --selftest` still green after the `compute_dcor_u_means` signature change | **PASS** — compare 5/5, stability 4/4 |
| `export` into a scratch directory reproduces the existing outputs **byte-identically** to `data/research/`, before any new file is added | **PASS, `cmp`-verified** — all 7 CSVs and `study.json` (the full set `export.py` writes; the plan's "five CSV" estimate undercounted — it is `anchor_frequency`/`degeneracy`/`cross_year_eval` × 2 measures + `measure_comparison`) byte-identical, both right after the refactor and again after the D-27 docstring correction |
| `flag_matrices` against real 2025 data matches the Context section's independently-measured counts | **PASS, measured** — `zero_return` total 1660 (KOS max 71), `at_limit` total 809 (VIC max 26), `zero_volume` total 0 across all 85 tickers |
| `python -m pipelines.research.diagonal --selftest` (new module) | **PASS** — 9/9 |
| `compare`/`stability`/`residuals` selftests still green after adding `centred_blocks`/`neglected_p` to `_fixtures.py` | **PASS** — 5/5, 4/4, 5/5 |
| `python -m ruff check pipelines/` after P12.A | **PASS** — clean |
| `diagonal_comparison` on all ten artifacts vs the independently measured targets | **PASS, measured** — all 10 rows match on `jaccard`, `first_divergence_k`, `fbar_unit`, `fbar_adjusted` (see the table below; the six rows beyond the acceptance table match too). `fbar_adjusted == fbar_excl_unit` to 5.6e-17 |

### Numeric acceptance targets

Taken from measurements run against the artifacts on disk while this plan was being written. A
mismatch means the module is wrong, not the target.

**Status: all rows below are MET**, confirmed against the published `data/research/` CSVs
themselves (P12.I), not only the module-level checks each stage ran during development. The
`approximation_*.csv` "every row" scope is now literal — all 100 rows (10 artifacts × 2
diagonals × k=1..5) — and P12.I's own Progress entry records the one place it is interesting:
2024 is the sole year where `ratio < 1.0` at k≥2, across every measure and diagonal.

| File | Row | Must equal |
|---|---|---|
| `diagonal_comparison_pearson_rho2.csv` | 2025 | `jaccard=0.667`, `first_divergence_k=9`, `fbar_unit=0.2629`, `fbar_adjusted=0.1647` |
| `diagonal_comparison_pearson_rho2.csv` | 2024 | `jaccard=0.429`, `first_divergence_k=6`, `fbar_adjusted=0.1200` |
| `diagonal_comparison_dcor2.csv` | 2022 | `first_divergence_k=3` |
| `diagonal_comparison_dcor2.csv` | 2024 | `jaccard=0.429`, `fbar_adjusted=0.1123` |
| `spectrum.csv` | 2025 residual | `q=0.3414`, `mp_upper=2.510`, `lambda_1=11.06`, `lambda_2=5.46`, `lambda_3=4.60`, `n_above_edge=5` |
| `spectrum.csv` | 2025 raw | `lambda_1=34.85`, `n_above_edge=3` |
| `spectrum.csv` | 2021 residual | `lambda_1=10.26`, `n_above_edge=5` |
| `approximation_*.csv` | every row | `ratio <= 1.0`; `f_exact` at k=3 on 2025 pearson equals `greedy.brute_force_best(P,3)[1]` computed independently |
| `flag_sensitivity_*.csv` | 2025 `zero_volume` | `n_flagged == 0` across all 85 |
| `flag_sensitivity_*.csv` | 2025 `zero_return` | `n_flagged == 1660`, per-ticker max `== 71` (KOS) |
| `flag_sensitivity_*.csv` | 2025 `at_limit` | `n_flagged == 809`, per-ticker max `== 26` (VIC) |
| `group_sectors_*.csv` | each (year, measure) | `Σ size == 85`; each row's `size`/`rho2_mean`/`rho2_min` equal the artifact's own `Group` values |

### Commands

```
python -m pipelines.factor.model
python -m pipelines.anchors.greedy
python -m pipelines.model.dcor
python -m pipelines.research.residuals  --selftest
python -m pipelines.research.compare    --selftest
python -m pipelines.research.stability  --selftest
python -m pipelines.research.diagonal   --selftest
python -m pipelines.research.spectrum   --selftest
python -m pipelines.research.robustness --selftest
python -m pipelines.research.exact      --selftest
python -m pipelines.research.sectors    --selftest
python -m pipelines.research.factor_alt --selftest
python -m pipelines.research.nulls      --selftest
python -m pipelines.research.export --out $env:TEMP\research_rehearsal --exact-k 4
python -m pipelines.research.export --out $env:TEMP\research_rehearsal
python -m pipelines.research.export
```

`pipelines.model.train` is not run at any point. Full publish run **measured at ≈15 minutes**
(P12.I; the plan's original ≈11-minute estimate did not cost stage D and G for *both* measures —
see P12.I's Progress entry), dominated by the k = 5 brute force (stage D, ≈8.7 min across both
measures and diagonals) and the dCor permutation null (stage G, ≈5 min across both measures).

### Not attempted

- **Cap-weighted index-membership tests.** No market-cap, free-float or index-weight data exists
  in the repo (grepped), and only VNINDEX is collected. Stage F ships the equal-weight + exact-LOO
  substitute; the difference is recorded as a limitation, not hidden as a TODO.
- **Postgres round-trip of the new tables.** Deliberately file-only (N5).
- **Stage J.** Gated (N6).

---

## Documents to amend as stages land

| Target | Change | Stage |
|---|---|---|
| `docs/01-data-pipeline.md:110, 115-119` | Diagonal consequence; corrected squaring justification | H |
| `docs/01-data-pipeline.md` §6 | Spectrum result; reconcile the analytic τ floor with the permutation percentile | B, G |
| `docs/02-algorithm-and-outputs.md` §3c–g | F̄_adj defined beside F̄; §3g gains the sector result | A, E |
| `docs/02-algorithm-and-outputs.md` §4 | Narrowed per [[D-25]] | G |
| `docs/03-temporal-design.md:27` | 4,950 → 3,570; add the [[D-12]] look-ahead limitation (the frozen universe conditions 2021 on survival to 2025 — a genuine look-ahead for the 2024→2025 forward test, and it makes F̄ optimistic relative to HOSE at large) | H |
| `docs/04-static-parameters.md:146`, `supabase/migrations/00007_live_monitors.sql:106` | **No change** — live track, 100 tickers, 4,950 correct | — |
| `docs/experimental-results.md` | New sections for every study; §3.1 replaces the bare 63.2 % bound with the realised ratio | A–G |
| `docs/decisions/README.md` D-2 | 4,950 → 3,570; note that the k argument now also rests on the diagonal comparison | H, A |
| `docs/decisions/D-12-...` | Cross-reference the look-ahead limitation | H |
| **New D-26** | Zero-diagonal selection objective | J only |
| **New D-27** | E is recomputed, not stored — why `residuals.py` re-derives E per window instead of adding T×N floats to every artifact and changing every `artifact_id` | 0b |

---

## Review follow-ups F1–F6 — status at 2026-08-29

The closing review (`Rà soát chốt Anchor Model`, 28/08/2026) raised six items on top of this
plan's stages. Recorded here because this file is the durable record and the review is not.

| # | Item | Status |
|---|---|---|
| F1 | F̄_adj missing on the Điểm neo screen; Δ reads as ~1 unit of coverage at k=15 when the real share is ~0.1 | **DONE** — `bd44ddd`. Client-side derivation, no API/schema change. 42 vitest passing |
| F2 | Connection pool wrong in three measurable ways | **DONE and deployed** — `35e1f5f` + `cdc0892` on `main`. Steady state −65 %; three further deployment-path defects found and fixed on re-verification (stale siblings, no TCP keepalives, a dropped socket misreported as a read-only failure). Detail in `anchor-model-operations.md` Validation |
| F3 | `docs/02` §3f contradicts the corrected `docs/01` §6 and [[D-25]] | **DONE** — rewritten. Two further instances of the same conflation were found and fixed (`experimental-results.md` §1.5, which still stated it as a live rule; and §2.2, which compared F̄_adj against the *pairwise* null — now against `fbar_excl_p95`, the null of the quantity itself: **3.6×–7.5×**, a stronger and correct statement). The τ_p95 upper bound was wrong in three places (0.0459 → **0.0460**), contradicting the very table it summarised |
| F4 | `set_session(readonly=True)` failure swallowed | **DONE and deployed** — `2ce46a3`. The connection-layer half shipped with F2; this closed the production check reading an import-time snapshot instead of the live environment (`test_72`), and corrected `render.yaml`'s stated reason for port 5432, which **does not reproduce** (measured: on 6543 `set_session` succeeds and read-only held across 8 distinct backends). No boot guard on 6543 was added, deliberately |
| F5 | Plans and validation tables stale against what is deployed | **DONE** — this entry, plus: six finished plans closed and moved to `plans/completed/`; P8 rows 8–11 and P10's vitest row filled with measured results; `docs/RUNBOOK.md` written |
| F6 | All P12 work exists only on this machine | **DONE for code** — every local branch is on `origin`, verified: no branch holds a commit `origin` lacks, and no stashes. **`docs/` is backed up only on the same disk** — it stays gitignored per [[D-23]], and moving a copy off this machine is a manual step that has not been taken |

**Still open after F1–F6:** merging this branch into `main` (the review's step 8), and the items
`docs/RUNBOOK.md` §5 lists as gaps — chiefly that the runbook has never been executed end to end,
and that Supabase's schema is tracked by no migration runner.

---

## Out of scope

- Any change to `services/api/`, `apps/web/`, or the database. N4 and N5 exist to guarantee this.
- Retraining any artifact, or changing any `artifact_id`, before Stage J is separately approved.
- Closing [[D-2]]. This phase supplies evidence for `k` and `τ`; choosing the final values is a
  report-writing decision, as D-2 itself already records.
- New similarity measures, new estimation windows, new universes. The five research years, the
  85-ticker frozen universe and the two measures are all fixed inputs here.
