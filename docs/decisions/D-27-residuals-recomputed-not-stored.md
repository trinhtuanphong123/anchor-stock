# D-27 — `pipelines.research.residuals` recomputes E; it is not added to the artifact

**Status:** Decided, 2026-08-28
**Affects:** `pipelines/research/residuals.py`; `pipelines/artifact/schema.py` (unchanged by
this record — that is the point); every P12 study that consumes `WindowInputs.E`.

## Context

P12's studies (diagonal comparison, the eigenvalue spectrum, flag sensitivity, exact k≤5,
sector cross-reference, the equal-weight/leave-one-out factor, the permutation calibration of τ)
all need the residual matrix E (T×N). The artifact does not carry it: `supabase/README.md`
already states the reasoning for the local track generally — "`X` and `E` genuinely are not
stored — they are recomputable from the returns and belong to a window, not to the data,"
in contrast to `P`, which *is* stored because `docs/04` §2/§6 price the full similarity matrix
at under 100 KB and treat it as a proper output.

`pipelines/research/residuals.py` is the new module that acts on that existing reasoning: it
re-fits the factor model from re-loaded returns, once per (window, universe), and hands the
result to every study as a `WindowInputs` object, rather than each study reloading it or the
artifact schema growing a field to hold it.

## Alternatives

**(a) Add `E` to `Artifact` / `manifest.json`, alongside `P`.** Every study reads it directly
off the artifact it already has, no reload, no new module.

Cost: T×N float64 per artifact. At T≈250, N=85 that is ≈170 KB — twice the size of `P.npy`
itself — times ten artifacts. More importantly, it changes `content_sha256` and therefore every
`artifact_id` on disk today, for a quantity nothing published so far has needed. It would also
have to be re-derived by any future artifact-writing code path exactly as `train_one_window`
already derives it, which duplicates the "one caller of `fit_factor_model` per run" property
`train.py`'s own docstring relies on.

**(b) Recompute E inside every study that needs it, independently.** No new module.

This is what `compare.compute_dcor_u_means` did before P12 — it was already the one exception
to "`research/*.py` stays pure, only `export.py` touches disk." Seven more studies each loading
their own returns would turn one documented exception into eight, which is worse than the
exception it started as.

**(c) One shared loader, cached by window+universe, handed to every study as loaded data.**
**Chosen.** `pipelines.research.residuals.window_inputs` / `window_inputs_for`.

## Decision

E stays unstored, per the reasoning `supabase/README.md` already gives. `residuals.py` is the
single place that re-derives it, once per distinct (window, universe) — which in practice means
once per research year, since a year's `pearson_rho2` and `dcor2` artifacts share both.

## Reasoning

**Recomputation is cheap; storage is not free.** Loading a year's returns and re-fitting the
factor model measures at ≈1.2 s; the whole five-year set is ≈6 s once per export run. Storing E
would buy back that six seconds at the cost of doubling the on-disk footprint of every artifact
and, because `content_sha256` covers everything but the excluded provenance fields, changing
every `artifact_id` — the one thing P12 as a whole is committed to not doing before Stage J is
separately approved (`method-review-followups.md`, N4).

**Centralising the load is what keeps `research/*.py` honest about its own stated rule.**
`compare.py` and `stability.py` already describe themselves as pure functions over a loaded
`Artifact`; before this record, `compute_dcor_u_means` quietly was not. This decision closes
that gap by moving the one disk-touching responsibility into a module built for it, rather than
either accepting a second (and third, and fourth) instance of the same exception, or paying for
storage the artifact schema was never designed to carry.

**A correctness check comes for free with the recomputation, and would not exist under (a).**
`residuals.assert_reproduces_p` re-derives P from the freshly re-fit E and compares it to the
artifact's own P. That is only a meaningful check because the E it uses was independently
re-loaded — an E read straight off the artifact (alternative a) could not verify anything about
itself.

## Consequences

- `WindowInputs` is process-cache-only (a module-level dict in `residuals.py`), not persisted.
  A fresh Python process re-derives E from scratch; nothing survives between `export` runs, and
  nothing needs to.
- The cache key deliberately excludes `similarity_measure`, since E does not depend on it — see
  `residuals.py`'s own module docstring for why that halves the number of loads per export run.
- No schema change, no migration, no new artifact field. `ARTIFACT_SCHEMA_VERSION` stays at 1
  because of this record specifically (Stage J, if approved, bumps it for an unrelated reason —
  `selection_objective` — and this decision has nothing to say about that).
- If a future need genuinely requires E to survive across processes (a long-running service,
  say), that is a new decision to make then, informed by why storing it was rejected here —
  not a silent reversal of this one.
