# Temporal Design: Research Track and Live Track

Which years the algorithm runs on, which year is the headline result, and how the running
system relates to the reported one.

**Depends on** file 01 (for P and the noise floor) and file 02 (for S, F̄ and the greedy
procedure).

## 0 Why this exists

The similarity matrix collapses an entire estimation window into one N×N picture (file 01,
§5). An anchor set built from it therefore says nothing about whether the structure it
captured held throughout the window or was an average over sub-periods that each looked
different.

If the anchors would have been entirely different in each year, a single published set is
an average over regimes rather than a description of any one of them, and presenting it as
"the representative set" would mislead. Everything below exists to test that possibility
rather than assume it away — and, in §5, to decide what the running system does about it.

## 1 One-year estimation windows throughout

Every run — research or live — estimates on a **single calendar year**, T ≈ 250 sessions.
There is no multi-year run and no full-series run.

This is a change from the earlier design and it propagates. The noise floor that used to
apply only to per-year robustness runs now applies to the headline result: across the
research track's 3,570 pairs (C(85,2) — the frozen research universe, §2 below), the
largest ρ² attributable to pure noise is ≈ 0.07 (file 01, §6).
Every interpretive threshold inherits that floor.

The compensating gain is that every run is directly comparable to every other. Under the
old design the full-series run and the per-year runs differed in both window length and
period, so a difference between them had two possible causes. Now only the period varies.

## 2 Research track — 2021 to 2025

| Year | Role |
|---|---|
| 2021 | In-sample — characterises ageing |
| 2022 | In-sample — characterises ageing |
| 2023 | In-sample — characterises ageing |
| 2024 | In-sample — characterises ageing |
| **2025** | **Primary result** — the anchor set the report presents |

Five independent runs. Nothing crosses a year boundary:

```
for y in 2021..2025:
    sessions_y ← trading days in year y
    fit factor model on sessions_y       → α_i^y, β_i^y, E_y
    P_y ← corr(E_y) ∘ corr(E_y)
    S_y ← GREEDY(P_y, k)
```

All five runs share one **frozen universe** of 85 tickers — the subset of the full 100-ticker
list with a return on every session of every research year (D-12). This is what keeps N and
q constant across the five runs and is why §4's cross-year evaluation needs no per-pair
universe intersection: `P_t` and `P_{t+1}` are always the same N×N shape over the same names.

### The prior close

A window of T returns needs T+1 closes (file 01, §1), and the first of those closes falls
*outside* the estimation window. The 2021 window therefore needs the last trading session of
2020. Collection starts at **2020-12-01** — one month of margin rather than one session,
because a provider gap at exactly the year boundary would otherwise cost the whole first
return.

Each run records its `prior_close_date` explicitly, so the boundary is auditable rather than
implied.

The factor model is refitted inside each year, residuals recomputed, matrix rebuilt. A beta
fitted on 2023 and applied to 2024 is a different quantity from one fitted on 2024, and
mixing them makes residuals incomparable across years — which would silently corrupt the
cross-year comparison in §4, the one place the comparison has to be clean.

All five sets are frozen and published. The static-parameter principle is intact: five
fixed sets, none of them moving.

### No in-year split

The earlier 80/20 within-window split is dropped. Two reasons, and the second is the real
one:

- 20% of 250 sessions is 50 sessions — too thin for a coverage estimate to mean much.
- More importantly, a held-out tail of the same year shares one factor-model fit and one
  market regime with the training portion. Calling it out-of-sample is nominal. The
  year-level structure in §4 is a genuine separation: the factor model, the residuals and
  the matrix are all rebuilt on data the earlier set never saw.

## 3 Mechanism 1 — Frequency table

```
for each ticker i:
    n_years(i) = |{ y ∈ 2021..2025 : i ∈ S_y }|
report n_years(i) and n_years(i)/5, sorted descending
```

The **shape of the distribution** is the result, not the list. Concentrated — a handful of
tickers in most years — means persistent structure. Flat — everything appearing once or
twice — means the method is picking up year-specific artefacts and the 2025 set should be
read with caution.

With five years each step is 20%, so the middle of the distribution is still coarse: 2/5 and
3/5 are hard to tell apart. Report the **two ends** — how many tickers appear in all five
years (the stable core) and how many in exactly one (noise or year-specific) — rather than
reading each level.

## 4 Mechanism 2 — Cross-year evaluation

```
for consecutive (t, t+1):
    stale  = F̄(S_t)     evaluated on P_{t+1}
    direct = F̄(S_{t+1}) evaluated on P_{t+1}
    ratio  = stale / direct         ∈ [0,1]
```

`direct` is the best achievable on year t+1 — anchors chosen on the very data scoring
them. `stale` is what carrying last year's set forward actually delivers.

Four pairs, and they are **not of equal standing**:

```
2021→2022,  2022→2023,  2023→2024     characterise ageing, establish the expected band
2024→2025                             forward test — the result that carries weight
```

Three ageing pairs rather than two is the concrete gain from adding 2021: a band drawn from
three observations is worth quoting, where a band drawn from two is barely a band at all.

The last pair matters because S_2024 was selected without sight of a single 2025 session
and is then scored on P_2025. If its ratio falls inside the band set by the first two, the
ageing behaviour is predictive rather than retrospective, and the live track's reliance on
a prior-year set (§5) has measured justification. If it falls outside, that is also a
result: 2025 differed from the regime the earlier years described, and the report says so.

**No oracle run is required.** Because 2025 is simultaneously the last evaluation year and
the primary result, `direct` for the final pair is F̄(S_2025) on P_2025 — the headline
number, computed anyway. Under the earlier design, where the holdout year sat outside the
research period, the denominator would have needed a greedy run on held-out data purely as
a ceiling. That complication is gone.

## 5 Live track — 2026 onward

2026 does not appear in the report. It is the operating system: the report establishes that
the method works, and the dashboard then applies it to current data for users who do not
need the methodology re-argued.

### Warm-up

Year-to-date data is too thin to select on early in a year. From the noise table:

| Point in year | T | Largest ρ² from pure noise |
|---|---|---|
| End of January | ≈ 20 | approaches 1 |
| End of March | ≈ 60 | ≈ 0.31 |
| End of June | ≈ 125 | ≈ 0.15 |
| End of December | ≈ 250 | ≈ 0.07 |

An anchor set built in January is close to pure noise. **T_min = 125 sessions** before a
live set is published; until then the dashboard serves the prior year's set.

This is not a workaround — it is the operational consequence of §4. The 2024→2025 ratio
measures exactly what serving a prior-year set costs, so the warm-up behaviour is licensed
by a measured quantity rather than asserted. That link between the two tracks is worth a
paragraph in the report.

### Rebuild cadence

**Monthly.** Twelve versions a year, each a frozen parameter set. Quarterly was the
alternative — steadier, but slow to react if structure shifts mid-year. Monthly keeps the
set responsive without users seeing it move often enough to lose the meaning of "the
representative set".

Each rebuild estimates on a trailing one-year window ending at the rebuild date, keeping T
constant at ≈ 250 and consistent with every research run.

### The anchor set is never recomputed daily

Prices, technical indicators and rolling coupling update every session. The anchor set does
not. A set that changed each session would flicker and the phrase "representative set"
would stop meaning anything.

Between rebuilds the dashboard **applies** frozen parameters to new sessions — see
file 04. There is no code path from the dashboard to the greedy algorithm.

### Presentation layer is not gated by this

Technical indicators, price history and the analytical displays built for the dashboard use
the full available history and are unaffected by anything here. They do not pass through
the model, are not gated by a `model_run`, and have no bearing on selection.

## 6 The caveat that must be stated

Every run is estimated on ≈ 250 sessions. Some of the year-to-year turnover in §3 is
estimation noise, not structural change, and this analysis **cannot separate the two**.

The frequency table's turnover is therefore an **upper bound on real instability**, not a
measurement of it. Report it as such. Claiming all turnover is structural change overstates
what the data supports, and a careful examiner will ask precisely this.

Under the earlier design this caveat applied only to secondary per-year runs while a
long-window full-series run anchored the report. It now applies to the primary result too.
That is a real cost of the one-year design and the report should state it plainly rather
than let it be discovered.

## 7 One open choice

Whether the per-year runs publish all eight candidate set sizes (5, 6, 7, 8, 9, 10, 12, 15)
or only the primary one.

- All eight across five years multiplies the stored rows, and multiplies the frequency
  tables — one per k.
- Only the primary size stays compact but ties the stability story to a single k.

Recommendation: **run the frequency table (§3) and the cross-year evaluation (§4) at the
primary k only.** The stability question is whether *the* anchor set is stable, and the
primary k is what defines *the* set. Reporting stability across all eight sizes answers a
question nobody asked and buries the one that matters.

Note this is narrower than the recommendation in file 02, §5, which stores the full Δ curve
to the maximum k. That is one greedy run per year recording every increment — cheap because
greedy is nested. What this section declines is running the *stability mechanisms* at every
k, which is a genuine multiplication.

This stays a recommendation until confirmed, because it is a reporting choice, not a forced
one.

## 8 What is published

Into `results`:

- Five `model_run` rows with `scope = 'year'` for 2021–2025, the 2025 row flagged as the
  primary result.
- A `stability_study` container holding `anchor_frequency` (§3) and `cross_year_eval` (§4).
- One `model_run` per live rebuild with `scope = 'live'`, versioned, one active at a time.

`ratio` in `cross_year_eval` is stored rather than derived, because it is the figure the
report quotes and storing it fixes its definition.

Research runs and live runs share a table and differ only by scope. They are the same
artefact produced by the same procedure — separating them into different structures would
imply a methodological difference that does not exist.