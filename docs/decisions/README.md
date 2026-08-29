# Decision register

One record per genuine fork. A record carries the **alternatives and the reasoning**, not just
the choice — so that a later proposal to reverse it argues against what was actually decided
rather than re-deriving the question.

Records marked **OPEN** are unresolved. They name the evidence needed to close them.

D-13 through D-17 and D-19 were **written in P7 for decisions taken in P6**. The parent plan
said P6 would record them and P6 was reported done without them, so the register understated
what had been settled for one phase. The reasoning in each was recovered from the two plan
files, not invented; each record says so in its status line. The lesson is the one `CLAUDE.md`
already states — the plan's Progress section and the artefacts it claims must move in the same
commit.

| # | Decision | Status | Record |
|---|---|---|---|
| D-1 | Research track spans 2021–2025, not 2022–2025 | Decided | [D-01](D-01-five-year-research-track.md) |
| D-2 | Primary `k` and rejection threshold `τ` | Provisional | below |
| D-3 | Parquet for `data/processed/` | Decided | below |
| D-4 | Full-P encoding in Postgres | Decided | below |
| D-5 | dCor estimator: V-statistic feeds greedy | Decided | [D-05](D-05-dcor-v-statistic.md) |
| D-6 | Adjusted-close semantics | **Decided: ADJUSTED** | [D-06](D-06-adjusted-close-semantics.md) |
| D-7 | Rolling display window `W` | Decided | below |
| D-8 | Live rebuild activation | Decided | below |
| D-9 | Publish the full Δ curve to `k_max` | Decided | below |
| D-10 | Stability mechanisms at primary `k` only | Decided | below |
| D-11 | `prior_close_date` crosses the year boundary | Decided | below |
| D-12 | Frozen 85-ticker research universe | Decided | [D-12](D-12-frozen-research-universe.md) |
| D-13 | Static dashboard — no live-apply path | Decided | [D-13](D-13-static-dashboard.md) |
| D-14 | `staging.ohlc_raw` is local-track only | Decided | [D-14](D-14-staging-raw-local-only.md) |
| D-15 | Indicator price basis: adjusted close | Decided | [D-15](D-15-indicator-price-basis.md) |
| D-16 | One serving universe, model and presentation | Decided | [D-16](D-16-serving-universe.md) |
| D-17 | Sector label source: vnstock + curated buckets | Decided | [D-17](D-17-sector-label-source.md) |
| D-18 | API surface: FastAPI over the views | Decided — closed in P8, which landed the first routes | [D-18](D-18-api-surface-fastapi-over-views.md) |
| D-19 | No foreign-flow (khối ngoại) data this pass | Decided | [D-19](D-19-no-foreign-flow-data.md) |
| D-20 | Supabase API roles hold no grants | Decided | [D-20](D-20-api-roles-hold-no-grants.md) |
| D-21 | Render topology: API service + static dashboard | **Superseded by D-30** (provider only; its reasoning is retained) | [D-21](D-21-render-deployment-topology.md) |
| D-22 | `services/api` installs its own lock | Decided | [D-22](D-22-split-api-dependency-manifest.md) |
| D-23 | Public repo carries code + results, not `docs/` | **Superseded by D-29** | [D-23](D-23-public-repository-carries-code-not-documents.md) |
| D-24 | Dashboard shows results, not method | Decided | [D-24](D-24-dashboard-shows-results-not-method.md) |
| D-25 | τ calibrated by permutation; `docs/02` §4 narrowed | Decided | [D-25](D-25-permutation-calibration-of-tau.md) |
| D-26 | Unit diagonal retained; tautology fixed in reporting, not the objective | Decided | [D-26](D-26-unit-diagonal-objective-retained.md) |
| D-27 | `research.residuals` recomputes E; not stored on the artifact | Decided | [D-27](D-27-residuals-recomputed-not-stored.md) |
| D-28 | Public repo carries the system, not the study | **Superseded by D-29** | [D-28](D-28-repository-carries-the-system-not-the-study.md) |
| D-29 | Private repo carries the system **and** its documents | Decided | [D-29](D-29-private-repository-carries-system-and-documents.md) |
| D-30 | API on Render, dashboard on Netlify | **Superseded by D-31** (provider reverted to Render; its own reasoning — and D-21's before it — is retained) | [D-30](D-30-hosting-split-across-two-providers.md) |
| D-31 | Back to one provider (Render); returns become views; 8 tables dropped; indicators to `double precision`; baseline migrations edited in place | Decided | [D-31](D-31-single-provider-and-derived-storage.md) |

D-28 had a record on disk and **no row in this table** until D-29 was written. The register
understated what had been settled, which is the same failure its own opening paragraph warns
about one phase earlier. Corrected here rather than backfilled silently.

---

## D-2 — Primary `k` and rejection threshold `τ` — PROVISIONAL

Both are deferred by the specs. `docs/02` §5 lists candidate sizes {5, 6, 7, 8, 9, 10, 12, 15};
`docs/01` §6 fixes a hard floor of τ ≥ 0.07 (the noise ceiling at T ≈ 250 across the research
track's 3,570 pairs, C(85,2) — corrected from an earlier, stale 4,950 = C(100,2) left over from
before [[D-12]] froze the research universe at 85 tickers).

**Chosen:** `k_max = 15` always — greedy is nested, so running to the maximum candidate and
recording every Δ costs nothing and makes the elbow argument far stronger. Provisionally
`k = 10`, `τ = 0.10`.

**Why provisional is safe here:** both values live *inside* the artifact, so revising them
produces a new artifact rather than a schema change. Close this after the first 2025 run, from
the elbow plot and the realised `c_i` distribution.

**Update, P5 (2026-08-17) — the evidence now exists, and it says there is no elbow to read.**
All ten artifacts (five years × two measures) were inspected for exactly the plot this record
asks for. Every Δ curve decays smoothly from its first value (≈4–6) toward ≈1 and is **still
≈0.97–1.02 at k=15** — the marginal gain of the fifteenth anchor is barely below the first
noise-adjacent increment, in every year, under both `pearson_rho2` and `dcor2`. There is no
knee: F̄(S) keeps climbing at close to a constant rate all the way to `k_max`, so "where the
curve bends" is not a question this data answers.

At the provisional `k=10`: F̄ ranges **0.2235–0.2632** (Pearson) and **0.2168–0.2563** (dCor)
across the five years; `n_under_tau` (τ=0.10) ranges **32–45 of 85** (Pearson) and **32–49 of
85** (dCor) — roughly 40–55% of the universe sits below the noise-floor-derived rejection
threshold at k=10, in every year, under both measures. P5's near-degeneracy diagnostic
(`pipelines/research/stability.py`) explains why an elbow was never likely: for the published
k=10 set, 29–45% of all single-anchor swaps land within 2% of F̄(S), and the median best
alternative at any given anchor position costs under 0.1 percentage points of F̄. The structure
is not "ten anchors, then diminishing returns" — it is many near-equally-good candidate sets at
every k, which is a flat Δ curve by construction.

**Consequence for closing this record.** The elbow argument is not available; k will have to be
argued from F̄/τ trade-offs and the degeneracy figures instead (a report-writing decision, not a
data-gathering one). This record stays PROVISIONAL — the evidence it was waiting for now exists
and is written down here, but choosing the final `k` and `τ` from it is deliberately left to
the report rather than decided by this pass. Full figures: `data/research/degeneracy_*.csv`,
`anchor_frequency_*.csv`, and the `model_anchors` rows in every artifact's `manifest.json`.

**Update, P12 (2026-08-28) — three corrections to the evidence above; the record stays
PROVISIONAL.**

*On τ — now calibrated, and known to be conservative.* [[D-25]] permitted a permutation null for
this one threshold, and it has been computed (`data/research/tau_calibration_*.csv`, 1,000
replicates, seed 20260827). **τ_p95 = 0.0405–0.0460 in all ten (year, measure) pairs — below
τ = 0.10 in every one.** τ = 0.10 is therefore *stricter* than pure chance requires, not looser:
the "why this threshold" question now has a measured answer rather than a rounded-up floor.
Adopting τ_p95 would move 26–63 % of the rejected names into "covered" (2023 least, 2022 and 2025
most), so the choice is a real one — **τ = 0.10 is retained as the published value and τ_p95 is
reported beside it**, the conservative option for a threshold whose job is to avoid overclaiming.
Note also that the ≈0.07 floor in `docs/01` §6 describes the max over *all pairs*, a different
statistic from the max over the k selected anchors that τ is actually applied to; §6 now says so.

*On the Δ curve — the flatness is partly an artefact and must not be cited as evidence.* Because
`P_jj = 1`, `ΔF(v|S) = ΔF_excl(v|S) + 1` for **every** candidate, so the Δ curve is forced toward
1 by construction. "Still ≈0.97–1.02 at k=15" is therefore not a finding about the market; the
self-cover floor alone supplies 78.5–98.8 % of Δ at k=15. The conclusion that there is no elbow
survives — but it now rests on the degeneracy study, not on the curve. See [[D-26]], which also
records why the objective was nevertheless left unchanged (the constant cannot reorder candidates,
so the diagonal corrupts the reported number, not the selection).

*On the degeneracy figures — the "29–45 % within 2 %" number was measured on an inflated
denominator.* The numerator of a swap gap is diagonal-free (equal-sized sets, the k tautology
terms cancel), but F̄ is not: `rel_gap_excl/rel_gap = F(S)/F_excl(S) = 1.81–2.19`. Restated on the
tautology-free scale, swaps within 2 % of the published solution are **4.7 %–20.0 %** of the 750
evaluated, and within 1 % are **1.1 %–3.7 %** — against 29–46 % and 5.7 %–22.3 % on the raw scale.
`degeneracy_*.csv` now carries both (`n_within_excl_*pct`, `fbar_excl_s`,
`median_best_swap_loss_excl`). Near-degeneracy is still real and no single anchor is
irreplaceable, but the published set is considerably better separated from its neighbourhood than
the original figure implied — which **strengthens** the case for the chosen set while weakening
the "flat everywhere, so k is arbitrary" framing.

*On k itself — the F_excl-scale coverage curve, which is the evidence this record was missing.*
`experimental-results.md` §2.2b now tabulates `F̄_adj(k)` for k = 1…15. Three things follow:

- **There is still no elbow.** F̄_adj rises monotonically to k_max in all ten (year, measure)
  pairs. Removing the tautology does not uncover a hidden knee; it confirms there is none. The
  "no elbow" finding above survives on the corrected scale.
- **A small k is positively contra-indicated.** Cutting k=10 to k=5 costs **18.1 %–22.9 %** of
  adjusted coverage (mean 20.9 % Pearson, 19.2 % dCor). Any argument for k ≤ 5 has to pay that,
  and nothing in the evidence offers a reason to.
- **There is a soft upper boundary, newly visible.** On unnormalised `F_excl` the marginal gain
  `ΔF_excl = ΔF − 1` turns slightly negative at the top — k=15 in 2021/2025 Pearson and
  2021/2023/2024 dCor, from k≈13 in 2025 dCor, k≈14 in 2022 dCor. Beyond there an anchor takes
  more out of the non-anchor pool than it adds to it. So the honest gain flattens somewhere
  around **k = 10–13**, and the provisional k = 10 sits inside that band rather than being
  arbitrary within it.

This does not close the record — k = 10 is still a choice made outside the model, and the curve
still does not pick a value on its own. But the choice is now bounded on both sides by measured
figures rather than by an elbow that does not exist.

## D-3 — Parquet for `data/processed/` — DECIDED

**Alternatives:** Parquet (needs `pyarrow`) vs gzipped CSV (no new dependency).

**Chosen:** Parquet, with `pyarrow` in a new `requirements-dev.in`.

**Why:** `date`, `bool` and `float64` survive a Parquet round-trip exactly; CSV pushes every
float through a text representation. For a study whose central claim is that a run reproduces
bit-for-bit, that fidelity is worth one dev-only dependency. The dependency never enters the
Supabase or Airflow runtime. At these sizes (~126k rows) either format is fast; this is about
correctness, not speed.

## D-4 — Full-P encoding in Postgres — DECIDED

**Alternatives:** `float8[]` flattened row-major vs `bytea` of the `.npy` file.

**Chosen:** `float8[]`, with `p_sha256` stored alongside as the identity.

**Why:** both round-trip exactly (Postgres `float8` is IEEE-754 double). `bytea` is byte-
identical to the on-disk file but opaque; the array is inspectable in a SQL editor and
serialisable by PostgREST. For a thesis artefact that someone will want to poke at,
inspectability wins. ~90 KB per run at N = 100.

## D-7 — Rolling display window `W` — DECIDED

**Alternatives:** W = 120 sessions vs W = 60.

**Chosen:** W = 120, the `docs/04` §6 recommendation.

**Why:** it is the shortest window where a displayed ρ² sits comfortably above its own noise
floor (≈ 0.008 for a single pre-specified pair, versus ≈ 0.017 at W = 60), and it matches the
half-year scale already used for the live-track warm-up. Stored as a **column** (`window_w`),
not a constant, so a second window can be added without a migration.

## D-8 — Live rebuild activation — DECIDED

**Alternatives:** auto-activate a new live artifact on load vs load-inactive-then-activate
manually.

**Chosen:** load automatically, **activate manually** for the duration of the thesis.

**Why:** `docs/04` §4 is explicit that monitors *inform* the scheduled rebuild and trigger
nothing automatically — automatic retraining on a drift trigger would make the parameter set a
moving target and defeat the whole static-parameter design. Manual activation keeps a human
between a monitor and the thing users see.

## D-9 — Publish the full Δ curve to `k_max` — DECIDED

**Chosen:** yes, store every increment to `k_max`; `model_anchors.in_published_set` marks which
prefix was actually published.

**Why:** greedy is nested, so the run to k = 15 *contains* the runs to every smaller k — the
extra rows are free. The elbow argument for the chosen k is much stronger when the curve extends
past it, and storing only to the primary k would foreclose redrawing the plot later.

## D-10 — Stability mechanisms at primary `k` only — DECIDED

**Chosen:** run the frequency table and the cross-year evaluation at the primary k only, per
`docs/03` §7. `stability_studies.k` records which k a study used.

**Why:** the stability question is whether *the* anchor set is stable, and the primary k is what
defines *the* set. Reporting stability across all eight candidate sizes answers a question
nobody asked and buries the one that matters. Note this is narrower than D-9 — storing the full
Δ curve is one greedy run per year; running the stability *mechanisms* at every k is a genuine
multiplication.

A second study at another k is an extra row, not a schema change.

## D-11 — `prior_close_date` crosses the year boundary — DECIDED

**Alternatives:** (a) T returns from T+1 closes, the first close falling outside the window;
(b) T−1 returns from the T closes inside the year.

**Chosen:** (a).

**Why:** it is what `docs/01` §1 literally says, and it keeps T ≈ 250 comparable across years —
under (b) every window would be one session shorter than its nominal length, which quietly
breaks the cross-year comparison that `docs/03` §4 depends on being clean. The artifact records
`prior_close_date` explicitly so the boundary is auditable rather than implied.

Consequence: collection starts at **2020-12-01**, giving a month of margin at the 2021 boundary
rather than a single session.
