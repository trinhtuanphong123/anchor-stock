# From Prices to the Similarity Matrix

How a set of price series becomes the N×N matrix the selection algorithm reads.

**Depends on** nothing. This is the entry point of the specification: it takes cleaned
price series and produces the matrix every later file reads.

## 1 Input

After pre-processing — universe filtering, session-calendar alignment, corporate-action
adjustment — the inputs are:

```
P    (T+1) × N     adjusted close, P_i(t) = close of ticker i on session t
m_P  (T+1)         VNINDEX close on the same session calendar
```

with N ≈ 100 and **T ≈ 250** (one calendar year — see file 03).

Two hard preconditions:

- **No missing values.** Every ticker has all T+1 sessions. Tickers that do not are
  dropped by the universe filter. Nothing is interpolated — an interpolated price
  fabricates a return, and a fabricated return contaminates a correlation.
- **Single session calendar.** Every ticker and the index share the same T+1 timestamps.
  Misalignment by even one session shifts one series against another and destroys the
  pairwise quantities downstream.

**Currency unit.** `close` as collected and stored (`daily_bars.close`) is in **nghìn đồng**
(thousands of VND), the unit the source vendor reports in. The log-return transform in §2 is
scale-invariant, so this has no effect on X, E, or P — it is stated here because it is a
property of the price series itself, and because it is not scale-invariant one step further
downstream: `technical_indicators_daily.turnover_value = close × volume` inherits the same
unit, and a dashboard summing it across 85 tickers without converting understates the true
figure by a factor of ~1e6 against tỷ đồng. Confirmed against the collected series during P8;
recorded here rather than only in a deployment plan because the next reader of `turnover_value`
will ask the same question this file's own variables raise.

## 2 Log returns

```
x_i(t) = ln( P_i(t) / P_i(t−1) )        t = 1..T

X  T × N       ticker returns
m  T           VNINDEX returns
```

Log rather than simple returns: they aggregate additively across sessions, and they are
symmetric under equal up and down moves. The second property matters on HOSE, where the
±7% band produces a high frequency of large moves whose asymmetry under simple returns
would bias the covariance.

## 3 Market-factor removal

The raw correlation matrix of X is dominated by the market mode: every pair looks similar
because every ticker moves with the index. A coverage objective built on it saturates
trivially and the selected set carries no discriminating information.

One-factor OLS per ticker removes it:

```
x_i(t) = α_i + β_i · m(t) + e_i(t)

β̂_i = Cov(x_i, m) / Var(m)
α̂_i = mean(x_i) − β̂_i · mean(m)
e_i(t) = x_i(t) − α̂_i − β̂_i · m(t)

E  T × N      residual matrix
```

N independent regressions, each O(T). Cost is negligible.

Two properties of OLS-with-intercept are used downstream:

- `Σ_t e_i(t) = 0` — residuals are exactly mean-zero, so §4 does not need to re-centre.
- `e_i ⟂ m` — residuals are orthogonal to the index by construction.

**α̂_i and β̂_i are outputs, not scratch values.** They are frozen into the published
parameter set and reused to residualise future sessions without refitting. See file 04.

## 4 The ρ² matrix

Normalise each column of E to unit length:

```
z_i(t) = e_i(t) / sqrt( Σ_s e_i(s)² )

Z  T × N
```

The Pearson correlation matrix is then one matrix product:

```
R = Zᵀ Z        N × N,   R_ij = corr(e_i, e_j)
P = R ∘ R       N × N,   P_ij = ρ²(i,j) ∈ [0,1]
```

`∘` is elementwise multiplication.

This is why the specification says "correlation matrix then square" rather than N(N−1)
regressions. The squared Pearson coefficient of a residual pair equals the R² of the
simple regression of e_i on e_j — and equals the R² of e_j on e_i, which is why the
quantity is symmetric. One matrix product replaces 9,900 regressions at N=100.

Properties of P:

| Property | Value | Why it matters |
|---|---|---|
| Symmetry | P_ij = P_ji | Assignment is well-defined in either direction |
| Diagonal | P_ii = 1 | A ticker represents itself perfectly — correct facility-location semantics |
| Non-negativity | P_ij ≥ 0 | Supplies **normalisation** (F(∅)=0, F never negative) — the property the (1−1/e) bound needs. Monotonicity and submodularity hold for any real P; see the paragraph below the table |
| Dimensionality | ticker × ticker | The time axis is gone |

Cost O(N²T) — a single BLAS call, milliseconds at these sizes.

The unit diagonal has a cost that belongs here rather than being discovered later: since
`F(S) = Σ_i max_{j∈S} P_ij` sums over every ticker including the anchors themselves, and
`P_jj = 1` is the maximum possible value, publishing k anchors adds exactly k tautological
terms of 1 to F — 44.7% of F at the primary k=10 in the 2025 run. `docs/02` §3d and the
diagonal-comparison study (`data/research/diagonal_comparison_*.csv`) report the adjusted
figure F̄_adj = (F−k)/(N−k) alongside F̄ for this reason.

Non-negativity is the load-bearing property, but it is not the *only* condition — see
`docs/02` §1, which states plainly that monotonicity and submodularity hold for any real
P. What non-negativity supplies is **normalisation** (F(∅)=0 with F never going negative),
and normalisation is what the Nemhauser–Wolsey–Fisher (1−1/e) bound actually needs. Two
further reasons justify squaring rather than leaving the guarantee unaddressed by it:
ρ² = R² reads as a share of variance explained, which is the quantity Section 2's OLS
chapter already speaks in; and a strong negative correlation (ρ ≈ −0.9) is structural
coupling between two tickers, not the absence of a relationship, so treating it as
dissimilar would throw away real information the squared measure keeps.

## 5 Where the time axis goes

```
P    (T+1)×N   ──log──▶   X  T×N   ──OLS on m──▶   E  T×N
                                                     │
                                        corr, then square
                                        ◀── time collapses here
                                                     ▼
                                              P  N×N  (ρ²)
```

X and E are T×N — one row per session, time still present. P is N×N — both axes are
tickers. The `Σ_t` inside the correlation is the collapse: two series of length T become
one number stating how much the two tickers moved together **over the whole window**, with
no statement about any individual session.

Everything downstream reads only P. The algorithm never touches X, E or prices again.

The consequence is that a run's anchor set is a still photograph of its estimation window.
Anything time-varying that the dashboard shows — rolling coupling between a ticker and its
anchor, for example — is a separate display computation, not part of selection.

## 6 Noise floor at T ≈ 250

With a one-year window this stops being a footnote and becomes a constraint on
interpretation.

Under independence, the sample correlation of two residual series is approximately
Gaussian with standard deviation 1/√(T−1). Across the C(N,2) pairs in the matrix, the
largest value arising from pure noise is approximately σ·√(2·ln(2M)) with M = C(N,2):

| T (sessions) | sd of r | E[ρ²] for one pair | Largest ρ² from pure noise |
|---|---|---|---|
| 250 (full year) | 0.063 | 0.004 | **≈ 0.07** |
| 125 (half year) | 0.090 | 0.008 | ≈ 0.15 |
| 60 (quarter) | 0.130 | 0.017 | ≈ 0.31 |
| 20 (one month) | 0.229 | 0.053 | approaches 1 |

The last row is where the Gaussian approximation breaks down, since |r| ≤ 1 caps it — but
the direction is the point: at one month of data the luckiest noise pair is
indistinguishable from a genuine relationship.

The T=250 row's exact value depends on which N the run uses. The research track's frozen
85-ticker universe (D-12) gives M = C(85,2) = 3,570 and a largest-noise-ρ² of ≈0.070; the
full 100-ticker universe gives M = 4,950 and ≈0.073. Both round to the ≈0.07 headline above,
so the table is unaffected — but a figure quoted to three decimal places must say which N it
used.

Three consequences that must be carried forward:

1. **τ cannot sit below ≈ 0.07 *as a statement about pairs*.** A rejection threshold under
   the noise ceiling declares coverage that random data would have produced. The floor is
   fixed and defensible for the statistic this section describes.

   **But that is not the statistic τ is applied to, and the two must not be conflated
   ([[D-25]]).** This section derives the maximum over **all C(N,2) pairs**. τ is applied to
   `c_i = max_{j∈S} ρ²(i,j)` — a maximum over only the `k` anchors greedy *deliberately
   selected to be the best explainers*. Two different distributions, and the second is the
   one the report quotes. `pipelines/research/nulls.py` measures it directly by permuting
   each residual column independently along time and re-running greedy:

   | statistic | null value |
   |---|---|
   | max over all C(85,2) pairs (this section, analytic) | ≈ 0.070 |
   | max over all pairs (permutation, Gaussian input — cross-check) | ≈ 0.055 |
   | max over the `k` greedy-selected anchors, p95 (`tau_p95`) | **0.0405–0.0460** |

   The first two agree on the easy case, which is what licenses trusting the third. The
   third is **lower** than the published τ = 0.10 in all ten (year, measure) pairs, so
   **τ = 0.10 is conservative** — stricter than pure chance requires — rather than
   permissive. That is a computed figure, not an assertion, and it is what an examiner
   asking "why this threshold" should be given. See `data/research/tau_calibration_*.csv`;
   the final choice of τ remains with [[D-2]].
2. **T_min for a live run.** The half-year row is why the live track refuses to publish an
   anchor set before roughly 125 sessions have accumulated. See file 03.
3. **Random-matrix context.** At the research track's N = 85 (D-12), q = N/T ≈ 0.34 at one
   year. The Marchenko–Pastur upper edge (1+√q)² ≈ 2.51 means eigenvalues below that are not
   separable from noise. (At the full N = 100 universe, q ≈ 0.40 and the edge ≈ 2.66.) Worth
   one paragraph in the report, not a section.

## 7 The distance-correlation variant

Pearson-ρ² captures linear co-movement only. The second measure carried by this project is
squared distance correlation (Székely, Rizzo & Bakirov 2007):

```
P_dcor[i,j] = dCor²(e_i, e_j)      ∈ [0,1]
```

**Only §4 changes.** §1–3 produce the same E; §5 onward is untouched, because dCor² is
also non-negative and bounded, so the objective keeps every property it needs. Same data,
same algorithm, one different measure — a clean comparison with nothing else varying.

Cost is O(N²T²) naively, which at N=100, T=250 is tractable but no longer a single BLAS
call. If it becomes a bottleneck, the O(T log T) univariate algorithm exists.

Two cautions when reporting the comparison:

- dCor has a **positive bias under independence** that shrinks with T, and at T ≈ 250 that
  bias is visible. Compare the two measures on **rankings and resulting anchor sets**, not
  on absolute values — dCor² and ρ² are not on the same scale and a side-by-side of raw
  magnitudes says nothing.
- The interesting outcome is either direction. High Jaccard overlap between the two anchor
  sets says the linear measure was sufficient and supports the simpler choice. Low overlap
  says nonlinear dependence is present that Pearson misses, which is a finding.

## 8 What is published

Per run, into `results`:

- The parameter set consumed downstream: universe list, per-ticker α̂_i, β̂_i, and residual
  standard deviation σ̂_i over the training window.
- The matrix P, or at minimum its anchor columns — see file 04 for which, and why.
- Estimation-window metadata: first and last session, T, N, q = N/T.

σ̂_i is stored even though §4 normalises it away, because the dashboard needs it to express
live residuals in comparable units without refitting.