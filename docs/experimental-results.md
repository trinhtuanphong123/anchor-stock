# Experimental Results — Statistics Reference

A single reference sheet of every quantitative result the system produced, for the
**Experimental Results** chapter of the thesis. Numbers are read directly from the
published artefacts (`data/artifacts/`) and the research outputs (`data/research/`);
nothing here is illustrative or invented.

Structure of the study, in one line:

```
adjusted closes → log returns → one-factor OLS on VNINDEX → residuals E
    → P = corr(E) ∘ corr(E)  (ρ²)  → greedy submodular maximisation → anchor set S
```

Two similarity measures are compared throughout: **`pearson_rho2`** (squared Pearson
correlation of residuals) and **`dcor2`** (squared distance correlation of residuals).
Five one-calendar-year runs (2021–2025) are produced for each measure — **ten artefacts
in total**. The primary reported result is **2025**.

---

## 1 Data-processing statistics (before the model)

This section reports what the raw data becomes on its way into the model — the fetch, the
cleaning, the calendar alignment, and the factor model — so the report can state exactly
what was carried into P and what was discarded.

### 1.1 Ingestion — the two fetch runs

| Property | Research fetch (P2) | Live top-up fetch (P6) |
|---|---|---|
| Run id | `59b9fb7a1ebc` | `55da77eada10` |
| Window requested | 2020-12-01 → 2025-12-31 | 2026-01-01 → 2026-08-18 |
| Source | VCI | VCI |
| Symbols requested (incl. VNINDEX) | 101 | 86 |
| Symbols succeeded | 101 (100 %) | 86 (100 %) |
| Minimum success gate | 0.90 | 0.90 |
| Aborted | No | No |
| Total rows written | 127,657 | 13,244 |
| Rows dropped / quarantined | 0 / 0 | 0 / 0 |
| Rows trimmed (outside window) | 5,709 | 1,032 |
| VNINDEX bars landed | 1,270 (2020-12-01 → 2025-12-31) | 154 (2026-01-05 → 2026-08-18) |
| Wall-clock | ~10 min (throttle 5 s/symbol) | ~8 min |

**Data-quality checks passed at fetch time** (per symbol): `sanity_bounds` (OHLC null and
range violations) and `duplicates` (composite-key uniqueness). Across all symbols in both
runs: **0 sanity violations, 0 duplicate keys, 0 nulls** in OHLC/volume — the fetch landed
clean, which is why 0 rows were dropped or quarantined.

**Per-symbol coverage (research fetch, 100 equities):** rows-per-symbol ranged **1,018 →
1,270**, median **1,270**. A full 5-year daily history is 1,270 sessions; symbols below that
are ones that listed after 2020-12-01 or had trading halts. These short histories are what
the universe filter later removes for the years they cannot cover.

### 1.2 Universe reduction — 100 → 85

| Stage | Count | Rule |
|---|---|---|
| Full collected universe | 100 equities | `list_stocks.txt` |
| **Frozen research universe** | **85 equities** | subset with a return on **every session of every year 2021–2025** (decision D-12) |
| Excluded | 15 equities | missing at least one session in at least one research year |

The frozen 85-ticker universe is what keeps **N = 85** and **q = N/T ≈ 0.34** constant
across all ten runs, so cross-year comparisons need no per-pair re-intersection.

### 1.3 Session-calendar alignment (per year)

Every year is aligned independently to the VNINDEX trading calendar. **No interpolation**:
a rectangular T×N matrix is achieved by dropping unaligned sessions/tickers, not by filling
them. Result — the alignment is exact for all five years:

| Year | Trading sessions T | N tickers | First session | Last session | Prior close | Dropped tickers | Dropped sessions |
|---|---|---|---|---|---|---|---|
| 2021 | 250 | 85 | 2021-01-04 | 2021-12-31 | 2020-12-31 | 0 | 0 |
| 2022 | 249 | 85 | 2022-01-04 | 2022-12-30 | 2021-12-31 | 0 | 0 |
| 2023 | 249 | 85 | 2023-01-03 | 2023-12-29 | 2022-12-30 | 0 | 0 |
| 2024 | 250 | 85 | 2024-01-02 | 2024-12-31 | 2023-12-29 | 0 | 0 |
| 2025 | 249 | 85 | 2025-01-02 | 2025-12-31 | 2024-12-30 | 0 | 0 |

`q = N/T`: **0.340** (T=250) / **0.341** (T=249). Zero drops in every year confirms the
frozen-universe design worked as intended — the 85 names were chosen precisely so alignment
never has to discard anything.

### 1.4 Factor model — one-factor OLS on VNINDEX

Each ticker's log-returns are regressed on the index return: `x_i = α_i + β_i·m + e_i`. The
fitted α̂, β̂, σ̂ are frozen outputs (reused to residualise future sessions without refitting).
Distribution of the fit across the 85 tickers, per year:

| Year | R² mean | R² median | R² min | R² max | β̂ mean | β̂ median | σ̂ median (daily) |
|---|---|---|---|---|---|---|---|
| 2021 | 0.313 | 0.302 | 0.055 | 0.646 | 1.029 | 1.032 | 0.0213 |
| 2022 | 0.398 | 0.400 | 0.066 | 0.666 | 1.253 | 1.321 | 0.0230 |
| 2023 | 0.383 | 0.411 | 0.011 | 0.647 | 1.244 | 1.232 | 0.0168 |
| 2024 | 0.343 | 0.362 | 0.002 | 0.594 | 1.168 | 1.183 | 0.0137 |
| 2025 | 0.358 | 0.353 | 0.000 | 0.615 | 0.977 | 1.006 | 0.0175 |

Reading: the market factor explains on average **31–40 %** of a ticker's daily variance
(R²), leaving **60–69 % idiosyncratic** — this residual is what P is built on. β̂ centres
near 1 (the universe tracks the index), and the residual matrix E is mean-zero and
orthogonal to the index by OLS construction. **These figures are identical for both
similarity measures** — the two measures differ only in how residuals are turned into P,
not in the factor model.

**Is VNINDEX the right factor?** The universe tickers are constituents of the index they are
regressed on, so a ticker partly explains itself. Two alternatives were fitted for comparison
(`data/research/factor_alternatives.csv`): an equal-weight cross-sectional mean, and a
leave-one-out factor `f_{−i} = (N·f_ew − x_i)/(N−1)` that excludes each ticker from its own
regressor.

- **The self-inclusion leak is real but small.** `mean_r2(equal_weight) > mean_r2(loo)` in all
  10 (year, measure) pairs — the expected O(1/N) inflation, ~20× smaller at N=85 than on a
  4-ticker fixture. It rarely changes the answer: equal-weight and LOO select the **same anchor
  set in 8 of 10** pairs, and both divergences are dCor (2021, 2024), never Pearson.
- **But equal-weight is the *stronger* factor, and that is the more interesting finding.**
  `mean_r2` is higher for equal-weight than for VNINDEX in **all five years** (0.339 vs 0.313;
  0.424 vs 0.398; 0.415 vs 0.383; 0.368 vs 0.343; 0.409 vs 0.358). The VNINDEX residual
  correspondingly retains more common structure — 2025 Pearson mean off-diagonal ρ² of 0.0241
  vs 0.0146, and λ₁ of the residual 11.06 vs 6.81. A cap-weighted index dominated by a handful
  of large caps removes less of the average ticker's common variation than a plain mean does.

  This matters for how §4 is read: `fbar_excl` is higher for the VNINDEX variant in every year,
  but that is **not** evidence its anchor set is better — the three variants are scored on three
  different P matrices, so it is not a like-for-like race. The VNINDEX residual simply has more
  co-movement left to cover.
- **The cap-weighted question stays open.** Testing the index-membership constraint properly
  needs market-cap or free-float weights, and the repository holds none — only the VNINDEX series
  itself was collected. Equal-weight is a proxy, not a substitute.

### 1.5 The similarity matrix P

- Shape **85 × 85** per run, `P_ij = ρ²(e_i, e_j) ∈ [0,1]`, symmetric, unit diagonal,
  **non-negative** (the load-bearing property that makes the greedy guarantee available).
- Number of distinct off-diagonal pairs: **C(85,2) = 3,570**.
- **Noise floor at T ≈ 250:** the largest ρ² attributable to pure noise across 3,570 pairs
  is **≈ 0.070** (sd of r ≈ 0.063; E[ρ²] for one independent pair ≈ 0.004). That is a
  statement about **pairs**, and it is *not* the constraint on τ — τ is applied to
  `c_i = max_{j∈S} ρ²(i,j)`, a maximum over only the k selected anchors, whose measured null
  is τ_p95 = 0.0405–0.0460 ([[D-25]], §5.1). The runs use **τ = 0.10**, above both.

### 1.6 Is one factor enough? — residual spectrum vs. Marchenko–Pastur

The one-factor model is a modelling choice, and it is testable: if VNINDEX had absorbed all the
common variation, the eigenvalues of `corr(E)` would fall inside the Marchenko–Pastur band for
pure noise. With q = N/T ≈ 0.34, the MP upper edge (1+√q)² is **2.506** (T=250) / **2.510**
(T=249). Source: `data/research/spectrum.csv`, computed for both stages — `raw` = `corr(X)`
before the fit, `residual` = `corr(E)` after.

| Year | stage | λ₁ | λ₂ | λ₃ | eigenvalues above the MP edge |
|---|---|---|---|---|---|
| 2021 | raw | 28.94 | 5.61 | 2.72 | 3 |
| 2021 | residual | 10.26 | 5.40 | 3.40 | 5 |
| 2022 | raw | 36.17 | 4.67 | 3.48 | 3 |
| 2022 | residual | 9.47 | 7.72 | 4.07 | 5 |
| 2023 | raw | 35.38 | 2.97 | 2.25 | **2** |
| 2023 | residual | 9.70 | 3.97 | 3.59 | 5 |
| 2024 | raw | 31.31 | 3.56 | 3.16 | 3 |
| 2024 | residual | 8.27 | 4.80 | 4.14 | **4** |
| 2025 | raw | 34.85 | 3.76 | 3.04 | 3 |
| 2025 | residual | 11.06 | 5.46 | 4.60 | 5 |

Reading: **neither of the two obvious answers is right.** The residual is not pure noise —
4–5 eigenvalues clear the MP edge in every year. Nor is there exactly one un-extracted factor —
λ₂ of the residual is 3.96–7.72, above the edge in all five years. There is **genuine
multi-factor structure left after removing VNINDEX**, which is the precondition for reading the
anchor groups as sector-like structure rather than as noise clusters (§4.4).

Two details that must not be smoothed over: **2024 has 4 eigenvalues above the edge, not 5**,
and at the `raw` stage **2023 has 2, not 3**. And λ₂ is *above* the edge every year but is not
"more than double" it every year — the ratio λ₂/edge runs 1.58× (2023) to 3.08× (2022).

λ₁ falls from ≈ 28–36 (raw) to ≈ 8–11 (residual): the factor model removes most, but plainly
not all, of the dominant common mode.

---

## 2 Model results — the anchor sets

### 2.1 Primary result (2025)

Both measures agree on the top-of-list structure and on the headline coverage. Ordered
anchor set, marginal gain Δ, and cumulative normalised coverage F̄ (k = 10 published, run
computed to k_max = 15):

**2025 · `dcor2` · artefact `a302a23a0f6f6` · F = 21.77, F̄ = 0.2561**

| step | anchor | marginal gain Δ | cumulative F̄ |
|---|---|---|---|
| 1 | VIC | 6.797 | 0.0800 |
| 2 | IDI | 2.709 | 0.1118 |
| 3 | PDR | 2.508 | 0.1413 |
| 4 | HCM | 1.776 | 0.1622 |
| 5 | PVT | 1.702 | 0.1823 |
| 6 | SZC | 1.364 | 0.1983 |
| 7 | NKG | 1.325 | 0.2139 |
| 8 | DCM | 1.269 | 0.2288 |
| 9 | CMG | 1.191 | 0.2428 |
| 10 | VCG | 1.130 | **0.2561** |
| *11–15* | *HDB, DGC, VNM, MBB, SBT* | *1.024 → 0.971* | *0.268 → 0.315* |

**2025 · `pearson_rho2` · artefact `ae2010a4ad426` · F = 22.35, F̄ = 0.2629**

| step | anchor | marginal gain Δ | cumulative F̄ |
|---|---|---|---|
| 1 | VIC | 5.800 | 0.0682 |
| 2 | IDI | 3.296 | 0.1070 |
| 3 | PDR | 2.907 | 0.1412 |
| 4 | PVT | 1.948 | 0.1641 |
| 5 | HCM | 1.834 | 0.1857 |
| 6 | SZC | 1.529 | 0.2037 |
| 7 | HSG | 1.418 | 0.2204 |
| 8 | DCM | 1.281 | 0.2354 |
| 9 | CMG | 1.176 | 0.2493 |
| 10 | VIB | 1.160 | **0.2629** |
| *11–15* | *VCG, FRT, HDB, BWE, VNM* | *1.148 → 0.992* | *0.276 → 0.325* |

**Marginal-gain / diminishing returns.** Δ is non-increasing by submodularity. The first
anchor alone covers **F̄ ≈ 0.068–0.080** of the universe; the drop from Δ₁ to Δ₂ is the
steepest, and by k = 10 each additional anchor buys ~0.011–0.013 of F̄. The curve is smooth
past k = 10 (no sharp elbow), which is why k is a moderate fixed choice rather than a
data-forced cutoff.

**Do not read the flatness of this curve as a finding about the market ([[D-26]]).** Because
`P_jj = 1`, a candidate's own contribution to Δ is exactly `1 − c_v`, so
`ΔF(v|S) = ΔF_excl(v|S) + 1` for every candidate: **the curve is pulled toward 1 by
construction**. The self-cover floor supplies 72–83 % of Δ at k=10 and 78.5–98.8 % at k=15
(`data/research/diagonal_curve_*.csv`), which is most of why Δ is still ≈0.99–1.02 at k_max.
The absence of an elbow is a real conclusion, but it rests on the degeneracy study (§3.2), not
on this curve. Two things the constant does *not* do: it does not reorder candidates (it is the
same for all of them), and it does not affect the swap gaps in §3.2 (equal-sized sets carry the
same k terms, which cancel).

### 2.2 Coverage across all ten runs

k = 10, N = 85 throughout. **F̄ is reported with its adjusted companion, never alone
([[D-26]]).** Every anchor covers itself at `P_jj = 1`, so `F` carries exactly k tautological
terms; `F̄_adj = (F−k)/(N−k)` removes them and equals `F_excl(S)/(N−k)`, the mean coverage of
the 75 tickers the set does *not* contain. Source: `data/research/diagonal_comparison_*.csv`.

| Year | pearson F̄ | pearson **F̄_adj** | dcor2 F̄ | dcor2 **F̄_adj** | tautology share of F (pearson / dcor) | under τ=0.10 (pearson / dcor) |
|---|---|---|---|---|---|---|
| 2021 | 0.2330 | **0.1308** | 0.2265 | **0.1234** | 50.5 % / 51.9 % | 38 / 42 |
| 2022 | 0.2632 | **0.1649** | 0.2563 | **0.1571** | 44.7 % / 45.9 % | 32 / 33 |
| 2023 | 0.2378 | **0.1362** | 0.2339 | **0.1318** | 49.5 % / 50.3 % | 39 / 40 |
| 2024 | 0.2235 | **0.1200** | 0.2168 | **0.1123** | 52.6 % / **54.3 %** | 45 / 49 |
| 2025 | 0.2629 | **0.1647** | 0.2561 | **0.1569** | 44.7 % / 45.9 % | 33 / 32 |
| **mean** | **0.2441** | **0.1433** | **0.2379** | **0.1363** | 48.4 % / 49.7 % | |

Reading, on the adjusted figure — which is the one to quote: 10 anchors explain on average
**≈ 14 % of the residual variance of the tickers they do not contain**. The raw F̄ ≈ 24 % is
inflated by the identity `ρ²(j,j) = 1`, which supplies **44.7 %–54.3 %** of every published F.
Both are deliberately conservative because the market factor has already been removed.

**Against the right null.** This paragraph used to compare F̄_adj with the ≈ 0.07 analytic floor
of `docs/01` §6 — but that floor is the largest ρ² over all C(85,2) **pairs**, not a null for a
**mean coverage**, and the two must not be conflated ([[D-25]]). §5.1 sets that argument out for
τ; the same substitution was made for τ in §1.5 and in `docs/02` §3f, and this is the third
place the wrong null was being quoted. The permutation study already publishes the matching
null:
`fbar_excl_p95` is the p95 of `F_excl(S)/(N−k)` — the very quantity F̄_adj is — over 1,000
replicates with each residual column permuted independently.

| measure | observed F̄_adj | null p95 | ratio |
|---|---|---|---|
| pearson | 0.1200–0.1649 | 0.0219–0.0222 | **5.4× – 7.5×** |
| dcor2 | 0.1123–0.1571 | 0.0299–0.0309 | **3.6× – 5.2×** |

Every one of the ten runs sits above its own null, by between **3.6×** (dcor2 2024) and
**7.5×** (pearson 2022). The signal is real and the margin is wider than the old comparison
suggested — but it is a margin over chance, not a claim that residual coverage is large in
absolute terms: 0.12–0.16 still means ten anchors explain roughly an eighth to a sixth of the
residual variance of the 75 tickers they do not contain. Source:
`data/research/tau_calibration_*.csv`.

`pearson_rho2` sits **~0.006 F̄ above** `dcor2` in every year (it captures linear residual
co-movement, which dominates here); the gap survives on the adjusted scale at ~0.007.

**Raw F̄ cannot be compared across different k.** The tautology grows linearly with k, so raising
k inflates F̄ for free. From k=10 to k=15 the raw F̄ rises 23.4 % while F̄_adj rises 9.2 % — the
raw figure overstates the benefit of additional anchors by about 2.6×. Any elbow read off raw F̄
is reading the identity, not the data.

F̄_adj removes that mechanical term and is the right figure for a cross-k comparison, but it is
not perfectly scale-free either: it averages over the N−k non-anchor tickers, and that population
both shrinks and loses its best-covered members as k grows. The comparison is honest, not exact —
quote it as "coverage of the remaining tickers at this k", not as a single index of quality.

### 2.2b Coverage against k, on the tautology-free scale

[[D-2]] must choose k from coverage/τ trade-offs rather than an elbow, and after [[D-26]] those
figures have to be read on the adjusted scale. Here they are. `F̄_adj(k) = (F(k) − k)/(85 − k)`,
from the Δ curve stored to `k_max = 15` in every artifact ([[D-9]]).

| k | F̄_adj (2025 pearson) | raw F̄ | F̄_adj range, pearson | F̄_adj range, dcor2 |
|---|---|---|---|---|
| 1 | 0.0571 | 0.0682 | 0.035–0.057 | 0.044–0.069 |
| 2 | 0.0855 | 0.1070 | 0.058–0.086 | 0.061–0.090 |
| 3 | 0.1098 | 0.1412 | 0.071–0.110 | 0.072–0.110 |
| 4 | 0.1229 | 0.1641 | 0.082–0.123 | 0.082–0.121 |
| 5 | 0.1348 | 0.1857 | 0.093–0.135 | 0.089–0.131 |
| 6 | 0.1432 | 0.2037 | 0.100–0.143 | 0.095–0.137 |
| 8 | 0.1560 | 0.2354 | 0.111–0.156 | 0.105–0.149 |
| **10** | **0.1647** | **0.2629** | **0.120–0.165** | **0.112–0.157** |
| 12 | 0.1719 | 0.2888 | 0.126–0.172 | 0.119–0.164 |
| 15 | 0.1797 | 0.3245 | 0.133–0.181 | 0.125–0.171 |

**F̄_adj rises monotonically to k_max in all ten (year, measure) pairs.** Removing the tautology
does not reveal a hidden elbow — it confirms there is none. The honest curve has the same shape as
the raw one, just lower and flatter; nothing saturates by k=15.

**Consequently a small k is not supported by the data.** Cutting k=10 to k=5 costs **18.1 %–22.9 %**
of adjusted coverage (mean 20.9 % Pearson, 19.2 % dCor) — a real loss, not a rounding one. The
review's suggestion that "the genuine coverage information lives at k ≤ 5" rested on its §2.2
claim that the objective stops discriminating from k ≥ 6; stage A disproved that claim, and this
table is what remains once it is removed. (Separately, the k ≤ 5 in §3.1 is the range exhaustive
search can reach — `C(85,5) = 32.6 M` — and is a limit of the *verification*, not a recommendation
about k.)

**Where the honest gain does run out.** On the *unnormalised* `F_excl`, the marginal gain is
`ΔF_excl = ΔF − 1`, which turns slightly **negative** at the very top: k=15 in 2021/2025 Pearson
and 2021/2023/2024 dCor, and from k≈13 in 2025 dCor and k≈14 in 2022 dCor. Past that point a new
anchor removes more from the "outside" pool than it adds back to it. `F̄_adj` still rises there only
because the N−k denominator shrinks faster. So the defensible statement is: **the last two or three
anchors buy essentially nothing, and k somewhere in 10–13 is where the honest gain flattens** — but
this is a soft boundary, not an elbow, and k = 10 sits comfortably inside it.

**U_τ** (tickers whose best-anchor coverage falls below τ = 0.10) ranges 32–49 of 85; these are
the genuinely idiosyncratic names the anchor set cannot represent, and it is honest to report
them rather than hide them. τ = 0.10 is now known to be a **conservative** threshold rather than
an arbitrary one — see §5 and `docs/01` §6.

### 2.3 Reproducibility

Every artefact is content-addressed: `artifact_id` is a SHA-256 over content excluding
timestamps, ties broken by smallest index. Re-running identical data reproduces the same id
**bit-for-bit**. Example (2021 dcor): `content_sha256 =
038e5356e6e0…`, `code_version = 1ef2426`, `tie_break = smallest_index`.

---

## 3 Algorithm results — robustness of the greedy solution

### 3.1 Approximation guarantee (theory) vs. realised behaviour

The objective F is monotone, submodular and normalised (F(∅)=0, F ≥ 0), so greedy carries
the Nemhauser–Wolsey–Fisher bound **F(S_greedy) ≥ (1 − 1/e)·F(S\*) ≈ 0.632·F(S\*)**. Note which
property does which job: monotonicity and submodularity hold for *any* real P, and it is
non-negativity that supplies **normalisation**, which is what the bound needs (`docs/02` §1).

That bound is worst-case, and on this data it is very loose. `pipelines/research/exact.py`
computes the **true optimum** by exhaustive search for k ≤ 5 — 10 artifacts × 2 diagonals ×
k=1..5 = 100 rows, source `data/research/approximation_*.csv`:

| | Rows | Ratio `F_greedy / F_exact` |
|---|---|---|
| Greedy is the **exact optimum** | **85 / 100** | 1.00000 |
| Greedy is sub-optimal | 15 / 100 | 0.9890 – 0.9996 |

**Realised ratio ≥ 0.989 everywhere, against a worst-case guarantee of 0.632.** The theoretical
bound understates achieved quality by a wide margin, and the report should quote the measured
table rather than the bound alone.

The 15 sub-optimal rows are not scattered — they concentrate in one year:

| measure | diagonal | year | k where sub-optimal | worst ratio |
|---|---|---|---|---|
| pearson_rho2 | unit | 2024 | 2, 3, 4, 5 | 0.9940 |
| pearson_rho2 | zero | 2024 | 2, 3, 4, 5 | 0.9890 |
| dcor2 | unit | 2024 | 2, 3, 4, 5 | 0.9930 |
| dcor2 | zero | 2024 | **2 and 5 only** (k=3, 4 are exact) | 0.9898 |
| dcor2 | zero | 2023 | **5 only** | 0.9996 |

**2021, 2022 and 2025 are exact at every k ≤ 5, both measures, both diagonals.** 2024 is the
single year where greedy misses, and `dcor2/zero/2024` is non-monotone in k — sub-optimal at
k=2, exact at k=3 and k=4, sub-optimal again at k=5. That detail is only visible by listing all
100 rows; summarising by year hides it.

Cost is O(kN²) for greedy — negligible at N = 85. The exhaustive check at k=5 is
C(85,5) = 32.6 M subsets and takes ~25 s per row with the batched DFS in `exact.py`.

### 3.2 Degeneracy / solution stability (1-swap neighbourhood)

For each published set, every one-element swap (candidate ∉ S replacing a member ∈ S) was
evaluated — **75 candidates × 10 members = 750 swaps per run** — to measure how many
near-equivalent solutions exist and how much the best swap could improve F̄.

**The relative band is reported on both scales ([[D-26]]).** A swap's *numerator* is unaffected
by the unit diagonal — both sets have size k and each carries exactly k tautological terms, which
cancel in the difference. The *denominator* does not cancel: F̄ is 44.7–54.3 % tautology, so
"within 2 % of F̄" is a materially wider band than "within 2 % of F̄_adj". The factor is exact,
`F(S)/F_excl(S) = 1/(1 − k/F(S))`, which is **1.81–2.19** here. Counting against F̄ alone
overstates degeneracy by precisely that factor.

| Year | Measure | swaps | within 1 % of F̄ | of **F̄_adj** | within 2 % of F̄ | of **F̄_adj** | median best-swap loss |
|---|---|---|---|---|---|---|---|
| 2021 | pearson | 750 | 77 | **14** | 335 | **73** | 8.3e-4 |
| 2022 | pearson | 750 | 65 | **20** | 245 | **79** | 6.5e-4 |
| 2023 | pearson | 750 | 76 | **13** | 219 | **78** | 7.7e-4 |
| 2024 | pearson | 750 | 43 | **14** | 255 | **35** | 4.0e-4 |
| 2025 | pearson | 750 | 86 | **20** | 277 | **100** | 5.6e-4 |
| 2021 | dcor2 | 750 | 167 | **28** | 321 | **150** | 7.5e-4 |
| 2022 | dcor2 | 750 | 66 | **19** | 240 | **76** | 7.2e-4 |
| 2023 | dcor2 | 750 | 70 | **8** | 230 | **69** | 8.1e-4 |
| 2024 | dcor2 | 750 | 86 | **17** | 344 | **72** | 3.9e-4 |
| 2025 | dcor2 | 750 | 71 | **13** | 345 | **92** | 8.1e-4 |

(`median best-swap loss` is quoted on the F̄ scale; the F̄_adj value is the same number × N/(N−k)
= × 1.133, since only the denominator changes.)

Reading, in two parts:

**The solution is a strong local optimum.** No swap ever improves it. The best single swap at any
anchor position costs a median of order 1e-4 in F̄ — under 0.1 percentage points. This holds on
both scales and is unaffected by the diagonal.

**Near-degeneracy is real but roughly half to a fifth of what the raw scale suggests.** On the
tautology-free scale, swaps within 2 % of the published solution are **4.7 %–20.0 %** of the 750
evaluated (35–150 swaps), against **29 %–46 %** when measured against raw F̄. At the 1 % band it
is **1.1 %–3.7 %** rather than 5.7 %–22.3 %. So the honest statement is: *some* alternative sets
sit close to the chosen one, and no single anchor is irreplaceable, but the solution is a good
deal more distinguished from its neighbourhood than the raw figure implies. Anywhere the earlier
"29–45 % of swaps land within 2 %" figure was used as evidence — including [[D-2]]'s argument for
why no elbow was ever likely — it should be restated on the F_excl scale.

### 3.3 Sensitivity to data-quality flags

Three per-session flags were tested by recomputing ρ² **pairwise-complete** — each pair uses only
the sessions where neither of its two tickers is flagged — then re-selecting and scoring both sets
on `F_excl/(N−k)`. Defined for `pearson_rho2` only; a per-pair masked recompute has no meaning for
dCor, whose double-centering is defined over a common support. Source:
`data/research/flag_sensitivity_pearson_rho2.csv`, `zero_return_pairs_*.csv`.

| flag | flagged sessions, 2025 | range over 5 years | Jaccard(S) before/after | F̄_excl before → after |
|---|---|---|---|---|
| `zero_volume` | **0** | **0**, every year, all 85 tickers | 1.000 | unchanged |
| `zero_return` | 1,660 | 1,259 – 1,941 | 0.818 – 1.000 | **rises** every year (0.131→0.139 … 0.165→0.176) |
| `at_limit` | 809 | 243 – 2,287 | 0.333 – 0.818 | **falls** every year (0.131→0.113 … 0.165→0.143) |

Three findings, and the third reverses the expectation that motivated the test:

1. **`zero_volume` is a non-issue here.** It never fires. The universe filter (`docs/01`,
   [[D-12]]) requires a return on **100 %** of the VNINDEX session calendar — it has no volume
   threshold to leak through — so the "5 % of sessions may have zero volume" hazard does not
   exist in this data.
2. **`zero_return` does not manufacture correlation.** It flags the most sessions yet moves the
   anchor set least, and masking it *raises* F̄_excl. Spearman between a pair's count of
   simultaneous zero-return sessions and that pair's ρ², across all 3,570 pairs: **−0.058**
   (pearson 2025) and **−0.018** (dcor2 2025); 2021 gives −0.029 and −0.004. No rank
   relationship, and what little there is points the wrong way for the spurious-correlation
   story. A flat-price session is closer to *no information* than to a false signal.
3. **`at_limit` carries signal, not noise.** It flags far fewer sessions than `zero_return` but
   moves the anchor set much more, and removing it **lowers** F̄_excl in every year. In 2025,
   VIC — which has 26 limit-up/limit-down sessions — **drops out of the anchor set entirely**
   when `at_limit` is masked. Limit sessions are high-information sessions, and discarding them
   destroys real co-movement along with any truncation artefact.

**What this does *not* settle.** The design cannot separate "±7 % truncation manufactures spurious
co-movement" from "limit sessions are exactly when tickers genuinely move together" — both predict
the same drop in F̄_excl on masking. That remains an open limitation, not a closed question.

---

## 4 Comparison & temporal research

### 4.1 Cross-year staleness (does last year's set still work this year?)

A set fitted on year *t* is applied — unrefitted — to year *t+1*'s matrix (`fbar_stale`) and
compared to that year's freshly-fitted set (`fbar_direct`). The **retention ratio =
stale/direct** measures how much coverage survives a year of ageing.

| Transition | `pearson` ratio | `dcor2` ratio |
|---|---|---|
| 2021 → 2022 | 0.904 | 0.916 |
| 2022 → 2023 | 0.918 | 0.902 |
| 2023 → 2024 | 0.963 | 0.973 |
| 2024 → 2025 (forward test) | 0.905 | 0.962 |
| **mean** | **0.923** | **0.938** |

Reading: a one-year-old anchor set retains **~92–94 % of the coverage** of a freshly-fitted
one. The structure P captures is **not a single-year artefact** — it persists across regimes,
which is the central justification for publishing one set and refreshing it only at scheduled
rebuilds (the live track never refits intra-window). The 2024→2025 row is a true forward
test (the set predates the data it is scored on) and still retains 90–96 %.

### 4.2 Anchor selection frequency (2021–2025)

How often each ticker is chosen across the five years (share = years-selected / 5). No ticker
is selected in **all** five years; the most persistent are:

**`pearson_rho2`:** HSG 4/5, LCG 4/5; DCM, HCM, MBB, PVT, SZC 3/5. 15 tickers appear in
exactly one year. (n_in_all_years = 0.)

**`dcor2`:** LCG 4/5; DCM, IDI, MBB, NKG, PVT 3/5. 17 tickers appear in exactly one year.
(n_in_all_years = 0.)

Reading: the anchor *role* rotates year to year (regime-dependent), but a stable core
(**LCG, DCM, MBB, PVT** under both measures) recurs — consistent with §4.1's high retention.
The rotation is why the report presents the 2025 set as *the current* representative set, not
a timeless one, and backs it with the cross-year evidence rather than a single snapshot.

### 4.3 Measure comparison — `pearson_rho2` vs `dcor2`

Per-year agreement between the two measures' selected sets:

| Year | Jaccard(S) | F̄ pearson | F̄ dcor | Spearman rank-agreement | mean dCor U-stat |
|---|---|---|---|---|---|
| 2021 | 0.667 | 0.2330 | 0.2265 | 0.865 | 0.0144 |
| 2022 | 0.818 | 0.2632 | 0.2563 | 0.851 | 0.0177 |
| 2023 | **1.000** | 0.2378 | 0.2339 | 0.809 | 0.0139 |
| 2024 | 0.429 | 0.2235 | 0.2168 | 0.794 | 0.0108 |
| 2025 | 0.667 | 0.2629 | 0.2561 | 0.841 | 0.0203 |
| **mean** | **0.716** | 0.2441 | 0.2379 | **0.832** | 0.0154 |

Reading: the two measures agree on **~72 % of anchors** on average (Jaccard) and their
per-ticker coverage rankings correlate at **Spearman ≈ 0.83** — high agreement that peaks at
a perfect 1.0 in 2023 and dips to 0.43 in 2024 (the most regime-unstable year, which also has
the lowest coverage and the most under-τ names). The near-zero **mean dCor U-statistic**
(≈ 0.015, bias-corrected) indicates residuals carry little *non-linear* dependence beyond the
linear part — which is why `pearson_rho2` (simpler, and marginally higher-coverage) is a
defensible primary choice, with `dcor2` retained as the non-linear robustness check.

### 4.4 Do the anchor groups track real sectors?

Sector labels never enter P or the objective (`docs/02` §3g), so agreement between return-derived
groups and human sector labels is external validation. Reported at **two granularities** — the
9-bucket `sector` and the finer vnstock `industry` label — because they disagree often enough
that quoting one alone overstates concentration. Source: `data/research/group_sectors_*.csv`,
100 anchor-rows (10 artifacts × 10 anchors).

**`dominant_share` ≠ `dominant_industry_share` in 34 of 100 rows.** The clearest recurring case
is **LCG**, which diverges in **7 of the 8** times it is an anchor:

| measure | year | sector share | industry share |
|---|---|---|---|
| pearson | 2021 | 0.438 | 0.250 |
| pearson | 2022 | 0.714 | 0.429 |
| pearson | 2023 | 0.714 | 0.429 |
| dcor2 | 2021 | 0.476 | 0.286 |
| dcor2 | 2022 | 0.706 | 0.471 |
| dcor2 | 2023 | 0.556 | 0.333 |
| dcor2 | 2024 | 0.556 | 0.444 |

Only pearson 2024 (0.75 / 0.75) does not diverge. **SZC, by contrast, never diverges** — it is an
anchor 5 times (3 pearson, 2 dcor2) and `dominant_share == dominant_industry_share` every time,
at 0.375–0.60. A narrative built on SZC as the industrial-park cluster is not supported by these
numbers; LCG is where the granularity actually matters.

**Group tightness is very uneven, and this is a result, not a caveat.** Group `rho2_mean` as
stored includes the anchor's own `ρ²(j,j) = 1`; removing it gives the mean coverage of the
*other* members, which is the comparable quantity. For 2025 pearson:

| anchor | size | mean ρ² of non-anchor members |
|---|---|---|
| SZC | 5 | **0.285** |
| HSG | 4 | 0.259 |
| HCM | 6 | 0.239 |
| IDI | 8 | 0.228 |
| PDR | 15 | 0.196 |
| PVT | 6 | 0.192 |
| DCM | 9 | 0.135 |
| VIB | 6 | 0.121 |
| CMG | 7 | **0.098** |
| VIC | 19 | **0.092** |

(Cross-check: these sum to 12.349 over 75 non-anchor tickers = 0.1647 = F̄_adj. ✓)

Reading: SZC is the **tightest** group, not the only tight one — HSG, HCM and IDI are the same
order. At the other end, **VIC (19 members) and CMG (7) fall below τ = 0.10**: the largest group
in the table is effectively a residual bucket for tickers that belong nowhere, and the report
should say so rather than let group *size* read as group *strength*.

---

## 5 Frozen parameters of a run (for the methods table)

| Parameter | Value | Meaning |
|---|---|---|
| N | 85 | frozen research universe |
| T | 249–250 | trading sessions per year |
| q = N/T | 0.340–0.341 | aspect ratio |
| k | 10 | published anchors (k_max = 15 computed) |
| τ | 0.10 | coverage rejection threshold — **conservative**, see below |
| τ_p95 (permutation) | 0.0405–0.0460 | calibrated null threshold, not adopted |
| Similarity | `pearson_rho2` (primary), `dcor2` (robustness) | ρ² of residuals |
| Index | VNINDEX | market factor |
| Source | VCI | price vendor |
| Tie-break | smallest index | determinism |
| Objective | F(S) = Σ_i max_{j∈S} P_ij, P_ii = 1 | monotone submodular coverage; unit diagonal retained ([[D-26]]) |
| Guarantee | ≥ 0.632 · F(S*) | Nemhauser–Wolsey–Fisher (1978) — realised ratio ≥ 0.989 (§3.1) |

### 5.1 Where τ = 0.10 comes from

`docs/01` §6 gives an analytic noise floor of ≈ 0.070 — but that is the maximum over **all
C(85,2) pairs**, whereas τ is applied to `c_i = max_{j∈S} ρ²(i,j)`, a maximum over only the k
anchors greedy *selected to be the best explainers*. Two different distributions ([[D-25]]).

`pipelines/research/nulls.py` measures the right one directly: permute each residual column
independently along time (destroying cross-sectional dependence, preserving each ticker's own
marginals), re-run greedy and assignment, and pool `c_i` over non-anchors. 1,000 replicates,
seed 20260827. Source: `data/research/tau_calibration_*.csv`.

| measure | year | tickers under τ = 0.10 | τ_p95 | tickers under τ_p95 |
|---|---|---|---|---|
| pearson | 2021 | 38 | 0.0405 | 17 |
| pearson | 2022 | 32 | 0.0406 | 12 |
| pearson | 2023 | 39 | 0.0411 | 29 |
| pearson | 2024 | 45 | 0.0417 | 20 |
| pearson | 2025 | 33 | 0.0415 | 13 |
| dcor2 | 2021 | 42 | 0.0454 | 16 |
| dcor2 | 2022 | 33 | 0.0456 | 12 |
| dcor2 | 2023 | 40 | 0.0458 | 27 |
| dcor2 | 2024 | 49 | 0.0459 | 19 |
| dcor2 | 2025 | 32 | 0.0460 | 9 |

**τ_p95 is below 0.10 in all ten (year, measure) pairs**, so **τ = 0.10 is conservative** — it
rejects more names than chance alone would require, not fewer. That is the answer to "why this
threshold": not an arbitrary round number above a floor, but a threshold now known by measurement
to sit on the strict side of its own null.

**τ = 0.10 is retained as the published threshold** and τ_p95 is reported beside it. Adopting the
calibrated value would relabel between 26 % and 63 % of the rejected names as covered — 2023 is
the least affected (39→29 pearson, 40→27 dcor2), 2022 and 2025 the most — and the conservative
choice is the defensible one for a threshold whose entire job is to avoid overclaiming coverage.
[[D-2]] holds the final say and remains provisional.

---

### Source files

- Artefact manifests: `data/artifacts/<id>/manifest.json` (run metadata, ticker_params, anchors, groups).
- Research outputs: `data/research/` — `study.json`, `measure_comparison.csv`,
  `cross_year_eval_{pearson_rho2,dcor2}.csv`, `anchor_frequency_*.csv`, `degeneracy_*.csv`,
  `alignment_*.json`, `fetch_p2.json`, `fetch_p6.json`.
- Method studies (P12, one stage per module in `pipelines/research/`):
  `diagonal_comparison_*.csv` + `diagonal_curve_*.csv` (§2.2 — unit vs. zero diagonal, [[D-26]]);
  `spectrum.csv` + `spectrum_eigenvalues.csv` (§1.6 — Marchenko–Pastur);
  `flag_sensitivity_pearson_rho2.csv` + `zero_return_pairs_*.csv` (§3.3 — data-quality flags);
  `approximation_*.csv` (§3.1 — exact optimum for k ≤ 5);
  `group_sectors_*.csv` (§4.4 — sector cross-reference);
  `factor_alternatives.csv` (§1.4 — equal-weight and leave-one-out factors);
  `tau_calibration_*.csv` (§5.1 — permutation calibration of τ, [[D-25]]).
  All regenerate with `python -m pipelines.research.export`; no artifact is retrained.
- Specification (authoritative): `docs/01`–`docs/04`.
