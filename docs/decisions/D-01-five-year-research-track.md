# D-1 — Research track spans 2021–2025

**Status:** Decided, 2026-08-17
**Affects:** `docs/03-temporal-design.md` §2, §3, §4, §7, §8; every per-year artifact; the
stability study; the collection start date.

## Context

`docs/03` originally fixed the research track at **four** years, 2022–2025, with 2025 as the
primary result. That number then propagated: the frequency table's denominator was 4, the
cross-year evaluation had three consecutive pairs, and §8 published four `model_run` rows.

Separately, the data-collection requirement was set at "from 2021 onward" — enough history that
2021 data would exist whether or not it was used.

Those two facts had to be reconciled: either 2021 is a research year, or it is only a buffer.

## Alternatives

**(a) 2021 as buffer only.** Fetch it, but use it solely to supply the prior close that the
2022 window needs (`docs/01` §1: T returns need T+1 closes). Research track stays at four years,
`docs/03` unchanged.

**(b) 2021 as a fifth research year.** Run greedy on it, include it in the frequency table and
the ageing pairs. Requires amending `docs/03` in five places.

**(c) Go back further** — 2018–2020 as well, deciding the span after seeing what the provider
actually returns.

## Decision

**(b).** The research track is 2021–2025. 2025 remains the primary result and the forward test
remains 2024→2025.

## Reasoning

The gain is concentrated in the cross-year evaluation, not the frequency table.

`docs/03` §4 splits the consecutive pairs into two roles: earlier pairs "characterise ageing,
establish the expected band", and the final pair is the forward test whose ratio is judged
*against* that band. Under four years the band rests on **two** observations. A band drawn from
two numbers is not a band — it is two numbers, and any forward-test ratio can be made to look
"inside" or "outside" it depending on which way they happen to fall. Three ageing pairs is the
first point at which the phrase means something.

The cost is real but bounded:

- The frequency table's middle gets slightly finer (20% steps rather than 25%) but stays coarse.
  `docs/03` §3's instruction to read the two ends rather than each level survives unchanged —
  it was already the right instruction at four years.
- The caveat in §6 is unaffected: turnover is still an upper bound on real instability, and a
  fifth year of the same T ≈ 250 does not separate estimation noise from structural change.

(c) was rejected as premature. It would decide the span from data availability rather than from
what the study is trying to show, and the further back the window reaches the more the universe
composition drifts from the one being studied — many liquid HOSE names today did not trade in
2018. Nothing prevents revisiting it later; the per-year design makes adding a year additive.

## Consequences

- `docs/03` amended: §2 table and loop, §3 denominator, §4 four pairs, §7 wording, §8 five rows.
- Collection starts **2020-12-01**, not 2021-01-01 — see [D-11](README.md#d-11).
- Five Pearson artifacts instead of four.
- The frequency-table denominator is a stored study parameter, not a constant, so a future
  change of span does not require a schema change.
