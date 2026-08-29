# Static Parameters, Dynamic Dashboard

What a run freezes, and what the dashboard is allowed to compute from it on each new
session.

**Depends on** file 01 (for α̂, β̂, σ̂), file 02 (for S, a(·), c) and file 03 (for the live
track). Read after all three.

## 1 The principle

Model parameters are static; the display is dynamic.

A run freezes a parameter set. Every session thereafter, new data arrives and the dashboard
**applies** those parameters to it. Nothing is refitted. The anchor set a user sees on any
given day is the one published at the last scheduled rebuild, evaluated against that day's
data.

The distinction that keeps this coherent:

| | Changes daily | Changes only at rebuild |
|---|---|---|
| Prices, volume, technical indicators | ✓ | |
| Residuals for new sessions | ✓ | |
| Rolling coupling to anchor | ✓ | |
| Coverage measured on recent data | ✓ | |
| Anchor set S | | ✓ |
| Assignment a(·) | | ✓ |
| α̂_i, β̂_i, σ̂_i | | ✓ |
| Universe, k, τ | | ✓ |

Everything in the right column is a published artefact with a version. Everything in the
left is derived on demand and stored only as a convenience.

## 2 The frozen artefact

A `model_run` publishes:

```
run metadata
    run_id, scope ∈ {year, live}, active flag
    training window: first session, last session, T
    N, q = N/T
    k, τ
    similarity measure ∈ {pearson_rho2, dcor2}

universe
    ordered list of N tickers      ← fixes row/column order of everything below

per ticker i
    α̂_i, β̂_i                       ← factor model, for residualising new sessions
    σ̂_i                            ← residual sd over training window
    a(i)                           ← assigned anchor
    c_i                            ← coverage at publication

set-level
    S ordered (j₁ … j_k)
    Δ₁ … Δ_k
    F(S), F̄(S)
    U_τ

matrix
    P[:, S]                        ← N × k, anchor columns
    P full N × N                   ← archived
```

Three things deserve comment.

**α̂ and β̂ are the load-bearing addition.** Without them a new session cannot be
residualised without refitting, and refitting is exactly what the static-parameter
principle forbids. They are why the factor-model coefficients are treated as outputs in
file 01 rather than as intermediate values.

**σ̂_i is stored although file 01, §4 normalises it away.** The dashboard needs it to
express live residuals in units comparable to the training window without recomputing
anything.

**The universe list fixes ordering.** Every stored vector and matrix is positional. A
reordered universe silently misaligns everything.

**`F̄_adj` is derived, not frozen — and that is deliberate ([[D-26]]).** The adjusted coverage
`F̄_adj = (F−k)/(N−k)`, which the report must publish beside `F̄` because `F` contains `k`
tautological self-cover terms, is computable from `F(S)`, `k` and `N` — all three already in the
list above. It is therefore a display computation under §4's rule, not a new stored parameter:
no schema field, no migration, and nothing for a consumer to keep in sync.

## 3 The daily path

```
1. ingest        new session OHLCV for the universe + VNINDEX
2. store         append to the shared data warehouse
3. returns       x_i(t) = ln(P_i(t)/P_i(t−1)),  m(t) likewise
4. residuals     e_i(t) = x_i(t) − α̂_i − β̂_i·m(t)      ← frozen coefficients, no refit
5. rolling       over trailing window W ending today:
                     ρ²_W(i, a(i))  for every ticker
6. display       coverage now vs coverage at publication, group health, drift flags
```

Step 4 is where the static/dynamic boundary sits. The coefficients are constants; the data
is new. This is a projection of new observations onto a fixed model, not an estimation.

Step 5 is the rolling similarity the dashboard shows — and it is the point at which time
returns to a system that discarded it. A ρ² computed on a trailing window is a **series**,
so a user can see the coupling between a ticker and its anchor tighten or loosen. This is a
display quantity and travels one way only: it never feeds back into selection.

## 4 Monitors

Four quantities worth surfacing, all derived from the daily path.

**Coverage drift.** F̄ over the trailing window against F̄ at publication. Falling coverage
means the published set is describing the market less well than when it was built. This is
the same quantity the cross-year evaluation measures, observed continuously instead of once
a year.

**Assignment challenges.** The count of tickers where `argmax_{j∈S} ρ²_W(i,j) ≠ a(i)` — the
set of tickers a fresh assignment would move. A monitor, not an action: a(i) does not change
between rebuilds. A rising count is early warning that the next rebuild will look different.

**Beta drift.** Rolling β_i against frozen β̂_i. Large divergence means the residuals being
computed in step 4 are drifting from the quantity the anchor set was built on. Display only.

**Warm-up state.** Whether the live track has accumulated T_min = 125 sessions. Below it,
the dashboard serves the prior year's set and should say which set it is serving. Users
should not have to infer that the anchor set predates the data they are looking at.

None of these trigger anything automatically. They inform the scheduled rebuild — automatic
retraining on a drift trigger would make the parameter set a moving target and defeat the
whole design.

## 5 Guard rails

- **No path from the dashboard to the greedy algorithm.** The dashboard reads a published
  parameter set. Selection runs only in the pipeline, on schedule.
- **Universe is frozen with the run.** A ticker listed after the training window has no α̂,
  β̂ and cannot be residualised, so it cannot be assigned. New tickers enter at the next
  rebuild. The dashboard shows the universe as of the active run, and says so.
- **Delistings are handled by omission**, not by reassignment. If an anchor is delisted
  mid-cycle, its group loses coverage until the next rebuild. This must be visible rather
  than silently patched — patching would mean the served set is no longer the published
  one.
- **Corporate actions rewrite history.** A retroactive adjustment changes past prices, so
  α̂ and β̂ fitted before it are slightly stale. The next scheduled rebuild absorbs this. No
  mid-cycle correction — that would be a refit.
- **Presentation layer is outside all of this.** Technical indicators and price history use
  the full available history, are not gated by a `model_run`, and never touch selection.

## 6 Two open choices

**Rolling window W for display similarity.**

- W = 120 sessions: for a single pre-specified pair the noise floor is ≈ 0.008 — negligible,
  since this is one pair rather than a maximum over 4,950. Responsive enough to show
  regime change over a quarter.
- W = 60: more responsive, noise floor ≈ 0.017, visibly jumpier.

Recommendation: **W = 120.** It is the shortest window where a displayed ρ² is comfortably
above its own noise floor, and it matches the half-year scale already used for T_min.

**Whether to store P in full or only its anchor columns.**

- P[:, S] at N × k is all the dashboard needs — assignment, coverage and challenges all
  read anchor columns only.
- Full P at N × N is 100× larger at k = 10 but is the only way to answer post-hoc questions
  without rerunning the pipeline.

Recommendation: **serve P[:, S], archive P in full.** The dashboard reads the small matrix;
the full one stays available for analysis and for the report. At N = 100 the full matrix is
under 100 KB, so this costs essentially nothing.

Both stay recommendations until confirmed — they are storage and presentation choices, not
forced ones.