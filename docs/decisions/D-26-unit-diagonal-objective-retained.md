# D-26 — The unit diagonal is retained; the tautology is fixed in reporting, not in the objective

**Status:** Decided, 2026-08-28
**Affects:** `pipelines/anchors/greedy.py` (unchanged — this record says why); `docs/01` §4;
`docs/02` §3d; `docs/experimental-results.md` §2.2; the P12.J entry in
`docs/plans/active/method-review-followups.md`, which this record closes; [[D-2]], unaffected.

## Context

The methodological review (`danhgia_phuongphap_trien_khai.md` §2) raised the sharpest objection in
the whole document. `P_ii = 1`, and every anchor is assigned to itself, so

    F(S) = Σ_i max_{j∈S} P_ij

contains exactly `k` terms equal to 1 by definition, carrying no information. The review made two
claims from this, and they are separable:

1. **The published number is inflated.** At the primary `k=10`, 2025 Pearson: `F̄ = 0.2629`, of
   which 10 of 22.349 is tautology — 44.7 %. The adjusted figure `F̄_adj = (F−k)/(N−k)` is
   **0.1647**.
2. **The selection is corrupted.** Because the marginal gain decomposes as
   `Δ(v|S) = (1 − c_v) + Σ_{i≠v} max(0, P_iv − c_i)`, and the first term is floored near 1 for any
   poorly-covered candidate, the review concluded that "from about `k ≥ 6` the algorithm is no
   longer choosing the best representative but the most neglected ticker — the inverse of the
   stated problem", and proposed zeroing the diagonal as a one-line fix.

P12.A was built to test claim 2, gated so that nothing would be adopted before the evidence
existed. The evidence now exists (`data/research/diagonal_comparison_*.csv`,
`diagonal_curve_*.csv`, `approximation_*.csv`).

**Claim 1 is confirmed. Claim 2 is false.**

The self-cover term is not merely bounded below — it is **exactly 1, for every candidate**, since
`P_vv = 1` and `v ∉ S` means `v` contributes `1 − c_v` where its old contribution was `c_v`.
Therefore

    ΔF(v | S) = ΔF_excl(v | S) + 1     for every candidate v, at every step

The added constant does not depend on `v`. **Greedy on the unit diagonal is, step for step, greedy
on `F_excl`** — the very objective the review wanted. This is proved algebraically and verified in
`pipelines/research/diagonal.py`'s selftest by a reference implementation that selects directly on
`F_excl` and matches the production `greedy()` exactly on every fixture.

The measured floor share confirms the *magnitude* claim while leaving the *ordering* claim without
support: the self-cover term is 72–83 % of Δ at `k=10` and 78.5–98.8 % at `k=15`. It dominates how
large Δ is. It does not touch which candidate wins.

## Alternatives

**(a) Adopt the zero-diagonal objective `F₀` (P12.J as shaped).** Thread `exclude_self` through
`coverage()`/`greedy()`, keep `assign()` on the unit diagonal so V14 (`a(j)==j`) still holds, add
`RunMeta.selection_objective`, bump `ARTIFACT_SCHEMA_VERSION` 1→2, write a migration, produce ten
new artifacts alongside the ten existing, and schedule the primary flip.

Rejected. The stated reason for the change — that the diagonal drives selection — is disproved.
What remains is a change that produces a *different* anchor set at a real cost, with no evidence
it is a *better* one.

**(b) Retain the unit diagonal; fix the inflation where it actually lives, in reporting.** Report
`F̄_adj = (F−k)/(N−k)` alongside `F̄` everywhere a headline coverage number appears, and state the
tautology share. **Chosen.**

**(c) Store `P₀` in the artifact.** Already rejected in P12.J's own shaping, and the rejection
stands independently of this record: it breaks V13 and `assert_similarity`, makes
`anchor_columns()` publish 0 for an anchor's own row, breaks the API's `coverage_c` ordering, and
destroys the ability to recompute the unit-diagonal figures for comparison — the same schema bump
as (a) with strictly more blast radius.

## Decision

**The unit diagonal stays.** `F(S) = Σ_i max_{j∈S} P_ij` with `P_ii = 1` remains the selection
objective, unchanged. No `exclude_self` flag, no schema bump, no migration, no new artifacts.

**`F̄_adj = (F−k)/(N−k)` becomes a required companion to `F̄`** wherever a coverage headline is
published. It is not a new stored field — `coverage_f`, `k` and `n_tickers` are all already in
`RunMeta`, so `F̄_adj` is derivable at the point of display without touching the artifact schema
or the database.

## Reasoning

**`ΔF = ΔF_excl + 1` settles the question that the change was meant to settle.** A constant added
to every candidate's gain at every step cannot reorder candidates. Whatever else the unit diagonal
does, it does not choose different anchors. Adopting `F₀` would therefore not be *correcting* the
selection — it would be *replacing* a correct selection with a different one.

**The two anchor sets do differ, and the difference is not evidence for `F₀`.** Jaccard between the
unit-diagonal and zero-diagonal sets runs 0.43–0.67, first divergence at step 5–9 (Pearson) and 3–7
(dCor). Scored on `F_excl` — the review's own preferred yardstick — the published unit-diagonal set
is higher in all ten (year, measure) pairs. **That result must be read for exactly what it is:**
since greedy-on-unit *is* greedy-on-`F_excl`, it is greedily optimising the metric being scored, so
its winning is close to a tautology of its own and is **not** an independent test. What can be
concluded is only consistency — and, negatively, that nothing in the data supports `F₀`. `F₀`
optimises a third function, one that sums over anchors' rows too and therefore mildly **rewards
anchors resembling one another** — the review's own stated counter-effect, weight `k/N ≈ 12 %`,
opposite in sign to the tautology it removes. Trading a known harmless constant for an unquantified
preference in the wrong direction is not an improvement.

**Corroboration from P12.D.** Greedy attains the exact optimum in 85 of 100 (year, measure,
diagonal, k≤5) rows, and the worst ratio anywhere is 0.9890 — far above the `1 − 1/e ≈ 0.632` worst
case. A selection procedure that is essentially exact on the objective it is given is not the place
where this method loses fidelity.

**The reporting problem is real and is not dismissed with it.** 44.7 %–54.3 % of every published
`F` is `ρ²(j,j) = 1`. A reader given `F̄ = 0.2629` without `F̄_adj = 0.1647` is being given a number
nearly half of which is an identity. That is a genuine defect in the write-up, and (b) fixes it at
the only place it exists.

**The guarantee is not the reason for either choice.** Facility location is monotone and submodular
for any real matrix; non-negativity supplies *normalisation*, which is what the
Nemhauser–Wolsey–Fisher bound needs (`docs/02` §1). Both `F` and `F₀` are non-negative and both
carry the bound. The guarantee does not discriminate here and should not be cited as if it did.

## Consequences

- **P12.J is closed, not deferred.** `docs/plans/active/method-review-followups.md` records it as
  closed by this record. `ARTIFACT_SCHEMA_VERSION` stays at 1; `export.assert_single_primary`
  continues to see exactly one primary per measure.
- `docs/01` §4 already carries the tautology paragraph and the `F̄_adj` pointer; `docs/02` §3d and
  `docs/experimental-results.md` §2.2 gain `F̄_adj` and `tautology_share` beside `F̄`.
- **Chapter 3 must not quote `F̄` alone.** Every headline coverage figure appears with its adjusted
  companion and the tautology share.
- **A separate claim falls with claim 2 and must not be re-derived from it.** The review argued that
  near-degeneracy is an artefact of the diagonal, because the Δ curve flattens at ≈1.0 rather than
  0. The first half stands — the raw Δ curve *is* mathematically forced to flatten near 1, so **the
  Δ curve does not evidence near-degeneracy** and Chapter 3 must stop citing it for that. The
  conclusion nevertheless survives on independent evidence: the 1-swap neighbourhood study
  (`degeneracy_*.csv`, [[D-2]]) does not involve the diagonal, since two equal-sized sets carry the
  same `k` tautology terms and they cancel in the difference. What does *not* survive unexamined is
  the **denominator**, which does not cancel. Since the numerator is identical on both scales,
  `rel_gap_excl / rel_gap = F(S) / F_excl(S) = 1/(1 − k/F(S))` exactly — **1.81 to 2.19 across the
  ten artifacts**, so "within 2 % of `F̄`" is a 3.6–4.4 % band on `F̄_excl`. The reported degeneracy
  share is therefore measured on an inflated scale. `pipelines/research/stability.py` now computes
  both, `degeneracy_*.csv` carries the `*_excl` columns beside the originals, and the report quotes
  the `F_excl`-relative figure.
- `services/api` and `apps/web` are untouched by this decision. If `F̄_adj` is later surfaced there
  it is computed at the display layer from fields already served; this record grants no schema
  change for it, and [[D-24]] governs whether the dashboard shows it at all.
- This record does not touch [[D-2]]. `k` and `τ` remain where D-2 leaves them.
