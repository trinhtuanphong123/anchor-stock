# The Selection Algorithm and Its Output Contract

What the greedy procedure does with P, and the complete set of artefacts a run produces.

**Depends on** file 01 for P. Everything here reads P and nothing else — no prices, no
returns, no residuals.

## 1 The objective

```
F(S) = Σ_{i=1..N}  max_{j ∈ S}  P_ij          F(∅) = 0
```

Read: each ticker i contributes how well the best member of S represents it. The sum is
total coverage of the universe by the set S.

The three properties that make the guarantee available:

- **Normalised.** F(∅) = 0 by convention, and F ≥ 0 because P ≥ 0.
- **Monotone.** Adding an element cannot lower any inner `max`, so F(S ∪ {e}) ≥ F(S).
- **Submodular.** The marginal gain of e given S is `Σ_i [P_ie − max_{j∈S} P_ij]₊`, which is
  non-negative and non-increasing in S — the larger S is, the more of P_ie is already
  covered.

Monotonicity and submodularity hold for *any* real P; non-negativity is what supplies
normalisation and therefore the approximation bound. This is the minimal-conditions
statement worth proving explicitly in the report, because it is what licenses every
extension: it establishes that no metric property, no boundedness and no symmetry is
required.

The problem `max_{|S| = k} F(S)` is NP-hard, which is why an approximation algorithm rather
than an exact one.

## 2 The algorithm

```
Input:  P ∈ [0,1]^{N×N},  k
Output: S (ordered),  c,  Δ

S ← ∅
c ← zeros(N)                       # c[i] = current coverage of ticker i

for step = 1..k:
    for each j ∉ S:
        gain[j] ← Σ_i max( P[i,j] − c[i], 0 )
    j* ← argmax gain                # ties: smallest index
    Δ[step] ← gain[j*]
    S ← S ∪ {j*}
    for each i:
        c[i] ← max( c[i], P[i,j*] )
```

The `max(·, 0)` is the marginal-gain expression `[P_ij − c_i]₊` written literally. Carrying
the coverage vector c means each step costs O(N²) instead of recomputing F from scratch;
total O(kN²), which at N = 100 is trivial.

Ties broken by smallest index. Arbitrary but **deterministic** — a run must reproduce
exactly, and near-ties do occur.

### Guarantee

By Nemhauser, Wolsey & Fisher (1978), for monotone submodular normalised F under a
cardinality constraint:

```
F(S_greedy) ≥ (1 − 1/e) · F(S*) ≈ 0.632 · F(S*)
```

with S* the optimum. This is worst-case; realised performance on structured data is
typically far closer to optimal, and the report should say so rather than presenting 0.632
as an expected loss.

**Lazy greedy** (Minoux 1978) returns the identical set faster by exploiting submodularity
to skip candidates that cannot beat the current best. Not needed at N = 100, but worth one
sentence in the report — it demonstrates that the submodular structure buys something
beyond the bound.

## 3 Output contract

A run produces the following, all derived from S, c and Δ.

**a. Ordered anchor set**

```
S = (j₁, j₂, …, j_k)
```

Selection order is meaningful and must be preserved: j₁ is the single best representative
of the whole universe, each subsequent element adds coverage the earlier ones missed. A
set stored unordered loses the marginal-contribution story.

**b. Assignment**

```
a(i) = argmax_{j ∈ S} P_ij         ties: smallest index
```

Every ticker in the universe belongs to exactly one anchor. The groups
`C_j = { i : a(i) = j }` partition the universe into k groups.

Single-loading is a modelling choice, not a consequence of the objective — F itself only
ever reads the best anchor per ticker, so the assignment is the natural readout.

**c. Per-ticker coverage**

```
c_i = ρ²( i, a(i) )  ∈ [0,1]
```

Read as: the share of ticker i's idiosyncratic variance explained by its anchor.

**d. Total and normalised coverage**

```
F(S)     = Σ_i c_i
F̄(S)     = F(S) / N            ∈ [0,1]
F̄_adj(S) = (F(S) − k) / (N − k) ∈ [0,1]
```

**F̄_adj is the comparable number** — across k, across years, across measures. F̄ is comparable
across years and measures at a *fixed* k, but not across different k (see below). Everything
comparative in the report quotes a normalised figure, never raw F.

**F̄ never appears alone ([[D-26]]).** Every anchor covers itself at `P_jj = 1`, so `F` contains
exactly `k` tautological terms — **44.7 %–54.3 % of the published F** across the ten research
artifacts. `F̄_adj` removes them: it is identical to `F_excl(S)/(N−k)` where
`F_excl(S) = Σ_{i∉S} max_{j∈S} P_ij` (verified to 5.6e-17 on real data), i.e. the mean coverage
of the tickers the set does *not* contain. At the primary k=10, 2025 Pearson: F̄ = 0.2629 against
F̄_adj = 0.1647.

Two things follow, and both matter for how the report reads:

- **Raw F̄ cannot be compared across different k.** The tautology grows linearly with k, so
  raising k inflates F̄ for free. From k=10 to k=15 the raw F̄ rises 23.4 % while F̄_adj rises
  9.2 % — the raw figure overstates the benefit of more anchors by about 2.6×. F̄_adj is the
  figure to use, with the caveat that it averages over the N−k non-anchors, a population that
  shrinks as k grows; it is the honest comparison, not an exact one.
- **F̄_adj does not change the selection.** `ΔF = ΔF_excl + 1` for every candidate at every step,
  so the tautology is a constant that cannot reorder candidates. This is a reporting correction,
  not an algorithmic one; see [[D-26]] for why the objective itself was left alone.

`F̄_adj` is derived, not stored — `coverage_f`, `k` and `n_tickers` are already in `RunMeta`.

**e. Marginal-gain curve**

```
Δ₁ ≥ Δ₂ ≥ … ≥ Δ_k
```

Non-increasing, which is submodularity made visible. The elbow of cumulative F̄ against k
is the evidence for the final k. Plot both the increments and the cumulative curve — the
increments show where returns die, the cumulative shows what was bought.

**f. Rejection set**

```
U_τ = { i : c_i < τ }
```

Tickers **not** adequately represented. τ takes no part in the optimisation; it is applied
after the fact, to report "at k anchors, |U_τ| tickers remain outside coverage at level τ".
Keeping it out of the objective preserves the guarantee — a thresholded objective would be
a different function requiring its own analysis.

The floor on τ used to be stated here as the ≈ 0.07 noise ceiling of file 01 §6, with the
final value "deferred until real c_i distributions exist". **Both halves are superseded**
([[D-25]]).

≈ 0.07 is still correct *for the statistic file 01 §6 derives* — the largest ρ² attributable
to chance across all C(85,2) pairs. That is not the statistic τ is applied to. `c_i` is
`max_{j∈S} ρ²(i,j)`, a maximum over only the `k` anchors greedy **deliberately selected to be
the best explainers**; calibrating the one against the other answers a question nobody asked.
And the c_i distributions are no longer awaited: `pipelines/research/nulls.py` measures them
directly (1,000 permutation replicates, seed 20260827), giving

```
τ_p95 = 0.0405 – 0.0460     across all ten (year, measure) pairs
τ_p99 = 0.0531 – 0.0569     the same ten
```

every one of them **below** the published τ = 0.10. So τ = 0.10 is **conservative** — it
rejects more names than chance alone requires, not fewer — and it is retained on that ground,
with τ_p95 reported beside it. See `docs/experimental-results.md` §5.1 and
`data/research/tau_calibration_*.csv`. The final choice of τ remains with [[D-2]].

**g. Group table**

Per group C_j: size, mean and minimum ρ² within the group, ICB sector composition.

Sector composition is **external validation only**. Sector labels never enter P and never
enter the objective — showing that return-derived groups line up with sectors is evidence
the method found real structure; feeding sectors in would make that circular.

## 4 What a run does not produce

- **No time series.** The anchor set describes the estimation window as a whole. Any
  time-varying quantity on the dashboard is a display computation over frozen parameters.
- **No probabilistic statement about any individual pair or ticker.** ρ² is used for
  ranking and selection, never for hypothesis testing. No p-value on any ticker's `c_i` or
  any pair's ρ²; no confidence interval published as a per-ticker quantity; no test of any
  kind inside the objective. This is what makes the overlapping-returns robustness check
  safe and what keeps the dCor comparison honest.

  **One narrow exception, granted by [[D-25]]:** a permutation null of `c_i` may be computed
  and its percentiles reported, for the sole purpose of calibrating the single reporting
  threshold τ (§3f). The distinction is between a claim about 85 things and a claim about
  one number — 85 per-ticker claims raise a multiple-comparison problem this report cannot
  handle, whereas placing one threshold is the same kind of claim `docs/01` §6 already makes
  analytically. τ remains post-hoc and still takes no part in the optimisation, so the
  exception cannot change an anchor set, F, F̄, an assignment, or an `artifact_id`.
- **No portfolio weights.** Selecting representatives is not allocating capital. The
  anchor set is a description of structure, and the report should not imply otherwise.

## 5 One open choice

Whether the marginal-gain curve is published for the full candidate range of k or only up
to the primary k.

- Full range means running greedy once to the maximum k and recording every Δ — cheap,
  since greedy is nested: the run to k = 15 contains the runs to every smaller k.
- Only to primary k is smaller but forecloses redrawing the elbow plot later.

Recommendation: **run greedy once to the maximum candidate k and store the whole Δ curve.**
Nesting makes it free, and the elbow argument for the chosen k is much stronger when the
curve extends past it. This stays a recommendation until confirmed, since it affects the
stored row count.