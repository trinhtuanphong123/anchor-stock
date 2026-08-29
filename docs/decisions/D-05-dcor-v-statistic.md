# D-5 — dCor estimator: the V-statistic feeds greedy

**Status:** Decided, 2026-08-17
**Affects:** `pipelines/model/dcor.py`; the measure comparison in `docs/01` §7.

## Context

`docs/01` §7 carries squared distance correlation as a second similarity measure, for comparison
against Pearson-ρ² in the written report. It also warns that dCor "has a positive bias under
independence that shrinks with T, and at T ≈ 250 that bias is visible."

There are two standard estimators, and the bias warning is exactly what distinguishes them.

## Alternatives

**(a) V-statistic** (Székely, Rizzo & Bakirov 2007). Double-centre each pairwise distance
matrix, then `dCov²(u,v) = ⟨A_u, A_v⟩_F / T²`. Biased upward under independence. **Always
non-negative** — a theorem, not an accident of the data.

**(b) U-statistic** (Székely & Rizzo 2013, U-centring). Unbiased under independence. **Can take
negative values**, by construction — that is how it achieves unbiasedness.

## Decision

The **V-statistic** produces the matrix that greedy consumes. The U-statistic is computed and
reported alongside in `measure_comparison`, as a bias diagnostic only.

## Reasoning

Non-negativity is not a nicety here. `docs/01` §4 and `docs/02` §1 both identify it as the
**load-bearing property** — the single condition the coverage objective actually requires. It is
what makes F normalised, and normalisation is what licenses the (1 − 1/e) approximation bound of
Nemhauser–Wolsey–Fisher. Feed greedy a matrix with negative entries and the problem becomes
non-monotone submodular maximisation, where plain greedy carries no guarantee at all.

So (b) would trade a bias correction for the theoretical result the whole method rests on. That
is not a trade worth making, and it would have to be disclosed in the report as such.

Running both is nearly free: the U-statistic differs only in the centring step, and the
comparison table is a handful of rows. Reporting the unbiased estimate next to the one that was
actually used satisfies §7's honesty requirement — a reader can see the size of the bias without
the objective having been compromised to show it to them.

## Consequences

- `residual_dcor2()` returns the V-statistic and asserts the same properties as
  `residual_similarity()` (symmetric, unit diagonal, bounded to [0,1]), so the two measures are
  drop-in interchangeable. That interchangeability is what makes `docs/01` §7's claim — "only §4
  changes" — true in code rather than only in prose.
- `measure_comparison` carries the U-statistic figures as a diagnostic column.
- The comparison between measures is reported on **rankings and resulting anchor sets** (Jaccard
  overlap, rank agreement), never on absolute magnitudes — dCor² and ρ² are not on the same
  scale, and a side-by-side of raw values says nothing. This is `docs/01` §7's own instruction.
