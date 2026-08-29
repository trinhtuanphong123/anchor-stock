# D-12 — Frozen 85-ticker research universe

**Status:** Decided, 2026-08-17
**Affects:** `list_stocks_research.txt` (new); `docs/01-data-pipeline.md` §6 (M, q, MP edge);
`docs/03-temporal-design.md` §2; every per-year research artifact from P4 onward.

## Context

P2's collection (100 tickers + VNINDEX, 2020-12-01 → 2025-12-31) is real data, and real data
has mid-window listings. `pipelines.returns.matrix.assemble_matrix` builds X by intersecting
the sessions of every ticker it keeps; before this pass, "keeps" meant only "has at least one
session in the window" — a ticker with *partial* coverage stayed in and dragged the shared
session count down to its own shortest run. Measured against the real 100-ticker universe:

| Year | Index sessions | T after the old intersection |
|---|---|---|
| 2021 | 250 | **18** |
| 2022 | 249 | 236 |
| 2023 | 249 | 244 |
| 2024 | 250 | 244 |
| 2025 | 249 | 249 |

2021's collapse traces to four names alone: BAF (listed Dec 2021, 20 sessions), DXS (116), SSB
(197), OCB (231). At T=18 the noise floor (`docs/01` §6) swamps any threshold worth quoting, and
2021 is one of D-1's five research years — `docs/03` §4 needs it for three ageing pairs.

This decision is about the **universe**, separate from the alignment-mechanism fix that
addresses the *general* case (any single incomplete ticker is now dropped rather than shrinking
T for everyone — see `pipelines/returns/matrix.py`, `AlignmentReport`). Even with that fix, a
per-year universe still changes N year to year (89 in 2021, 100 by 2025), which is its own
problem: the cross-year evaluation (`docs/03` §4) compares `F̄(S_t)` computed on `P_t` against
`F̄(S_{t+1})` computed on `P_{t+1}` — clean only if both matrices describe the same set of
tickers.

## Alternatives

**(a) Per-year universe, N following availability (89→97→99→99→100).** Each research year uses
whichever tickers have full coverage that year. Uses every session every ticker has. The
cross-year evaluation must then restrict `S_t` to the intersection of the two years' universes
before scoring on `P_{t+1}`, and `q = N/T` is not constant across years.

**(b) Coverage-threshold universe (e.g. ≥98%) with intersection still applied on the survivors.**
Keeps more tickers than a 100% rule (2021: N=93, T=236 at 98%; N=96, T=223 at 95%), but
introduces a tunable parameter with no principled value, and reintroduces exactly the mechanism
this decision exists to avoid — a handful of near-complete tickers still shave sessions off
everyone else's T.

**(c) Frozen universe: the subset of the 100 with 100% coverage in every one of the five
research years, computed once.** Chosen.

## Decision

**(c).** `list_stocks_research.txt` holds the 85 tickers with a return on every session of
2021–2025. Derived by `python -m pipelines.universe.file --derive-research-universe` (a one-off
query against collected data, not a per-run computation) and committed as a plain file, exactly
like `list_stocks.txt` — same normalisation, same hash-based `version`.

Fifteen tickers are excluded from the research track only: BAF, BSI, DXS, EVF, OCB, ORS, PAN,
SHB, SSB, VIX, VND (cost 2021), CTR, HHV (cost 2022), SIP (cost 2023), NAB (cost 2024). They
remain in `list_stocks.txt` — still collected, still served to the dashboard and the live track
(`docs/03` §5), which is not gated by this file at all.

Measured against the frozen universe, the old intersection mechanism becomes a no-op — every
research year keeps every session:

| Year | Index sessions | T | dropped_sessions | q = N/T |
|---|---|---|---|---|
| 2021 | 250 | 250 | 0 | 0.3400 |
| 2022 | 249 | 249 | 0 | 0.3414 |
| 2023 | 249 | 249 | 0 | 0.3414 |
| 2024 | 250 | 250 | 0 | 0.3400 |
| 2025 | 249 | 249 | 0 | 0.3414 |

## Reasoning

(a) is not wrong, but it moves work downstream rather than removing it: the cross-year
evaluation would need a per-pair intersection step that D-1's design does not currently call
for, and every reported N, q and noise-floor figure would need a year subscript. (b) trades one
arbitrary constant (τ, already provisional per D-2) for a second arbitrary constant with no
noise-floor argument behind it, and does not actually solve the shared-T problem — it only
raises the bar at which a ticker starts causing it.

(c) is the only option under which "the anchor set is stable across five years" (`docs/03` §3–§4)
compares five runs of the *same* universe. It costs fifteen tickers, three of them VN30 members
(SHB, VND — and VIX, sizeable but not VN30) with real liquidity. That cost is visible and
auditable rather than smoothed over: `list_stocks_research.txt` names every exclusion and the
year it cost, and the derivation is reproducible from `data/processed/` on demand.

The alignment mechanism itself (drop any ticker without full coverage, keep the rest at full T)
is kept regardless of this decision — it is what makes "frozen universe" a checkable claim
rather than an assumption. `AlignmentReport.assert_full_coverage()` raises if a ticker in
`list_stocks_research.txt` ever turns out incomplete for some window, rather than silently
re-shrinking N — the file's premise is meant to fail loudly if the data underneath it changes.

## Consequences

- `docs/01` §6: the noise-floor table is computed over C(N,2) pairs. At N=85 that is 3,570 pairs
  (not 4,950), the largest ρ² attributable to pure noise is ≈0.071 (not ≈0.074) — the "≈0.07"
  headline is unchanged, but the pair count and q must be quoted correctly.
- `docs/01` §6 point 3: q = 85/250 ≈ 0.34 (not 0.40), Marchenko–Pastur upper edge
  (1+√q)² ≈ 2.51 (not 2.66).
- `docs/03` §2 should note the five research runs share this one frozen universe, so a reader of
  §4's cross-year evaluation knows why it needs no per-pair intersection step.
- `list_stocks.txt` is untouched — this decision affects only which tickers a *research* run
  reads, never collection, the dashboard, or the live track.
- If the liquidity screen behind `list_stocks.txt` changes (its own header calls it a starting
  point), `list_stocks_research.txt` must be re-derived and this table re-measured.
