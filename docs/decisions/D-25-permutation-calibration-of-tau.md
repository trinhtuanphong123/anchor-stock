# D-25 — τ is calibrated by permutation; `docs/02` §4 narrows to per-ticker inference

**Status:** Decided, 2026-08-28
**Affects:** `docs/02` §4 and §3f; `docs/01` §6; `pipelines/research/nulls.py` (new);
`model_runs.tau` / `DEFAULT_TAU` in `pipelines/model/train.py`; [[D-2]], which stays provisional
either way.

## Context

`docs/02` §4 states, as a property of the whole method:

> No probabilistic statement. ρ² is used for ranking and selection, never for hypothesis
> testing. No p-values, no confidence intervals on coverage.

That rule was written to protect two things, and both are worth protecting. It keeps the
overlapping-returns robustness check safe (a test on overlapping windows would need a dependence
correction nobody in the report is equipped to defend), and it keeps the dCor comparison honest
(two estimators on different scales cannot be compared by significance).

But τ is a number that has to come from somewhere, and today it comes from an argument that does
not match the statistic it is applied to.

`docs/01` §6 derives a noise floor: under the null, the largest ρ² attributable to chance across
all C(85,2) = 3,570 pairs at T ≈ 250 is ≈ 0.07. [[D-2]] then set τ = 0.10 — the floor rounded up
with headroom — and recorded the value as provisional pending "real c_i distributions".

The mismatch is that **`c_i` is not a maximum over all pairs.** It is
`max_{j ∈ S} ρ²(i,j)` — a maximum over the `k` anchors that greedy *deliberately selected to be
the best explainers in the universe*. Those are two different distributions, and the second one
is the one the report quotes. Calibrating against the first is not conservative in a knowable
direction; it is simply answering a question nobody asked.

The methodological review (`danhgia_phuongphap_trien_khai.md` §3) sharpens this with a second
observation. At T = 249 the Fisher standard error is 1/√(T−3) = 0.0638, so a point estimate of
ρ² = 0.165 — which is roughly the mean coverage of non-anchor tickers — carries a 95 % interval
of [0.084, 0.250]. **τ = 0.10 sits inside that interval.** The label "covered / not covered" on
any individual ticker therefore has almost no resolving power, and the figure "33 of 85 below τ"
is being reported with a precision it does not have.

## Alternatives

**(a) Keep §4 exactly as written; drop calibration entirely.** τ stays at the analytic floor
rounded up. The review's §3 point is reported as a stated limitation and nothing is computed.

Cost: the one threshold whose entire job is to separate "adequately represented" from "not"
remains calibrated against a distribution that is never computed and does not describe the
statistic in use. A careful examiner asking "why 0.10?" gets an answer about the wrong maximum.

**(b) Permutation-calibrate τ, and narrow §4 to say what it was actually protecting.** Permute
each column of E independently along the time axis, re-run greedy and assignment, and collect the
null distribution of `c_i`. Place τ at the 95th or 99th percentile of that distribution. **Chosen.**

**(c) Compute the calibration but keep it out of the report.** Run it as an internal diagnostic so
the author knows where τ = 0.10 stands, publish nothing, amend no spec.

Rejected. A number that changes how the author reads their own results but is withheld from the
reader is worse than either of the other two options — it is (a) in public and (b) in private.
If the calibration is trustworthy enough to inform the work it is trustworthy enough to disclose;
if it is not, it should not be computed.

## Decision

**§4's prohibition narrows to inference about individual pairs and about individual tickers'
coverage.** Permutation is admitted as a **calibration device** used to place exactly **one**
reporting threshold, τ.

What stays forbidden, unchanged:

- No p-value attached to any ticker's `c_i`, or to any pair's ρ².
- No confidence interval published *as a per-ticker quantity*.
- No test of any kind inside the objective. τ remains post-hoc (`docs/02` §3f) and continues to
  take no part in the optimisation.

What is newly permitted:

- One null distribution of `c_i`, computed by column-wise permutation, used to choose τ.
- The percentiles of that distribution reported as a table, so the reader can see where the
  chosen τ sits.

## Reasoning

**The distinction is between a claim about 85 things and a claim about one number.** A p-value on
ticker *i*'s coverage is a claim about ticker *i*, and 85 such claims immediately raise a
multiple-comparison problem the report has no room to handle properly. That is the failure mode
§4 exists to prevent, and this decision does not go near it. A percentile of a null used to place
τ is a single claim, made once, about a single reporting parameter — and it is the *same kind* of
claim `docs/01` §6 already makes analytically. The register would be inconsistent if it accepted
the analytic version of this argument and refused the empirical one.

**Calibrating τ cannot change any result.** `docs/02` §3f is explicit that τ is applied after the
fact and never enters the objective. So this decision cannot change an anchor set, cannot change
F or F̄, cannot change an assignment, and cannot change an `artifact_id`. It changes exactly one
reported count — how many tickers are declared outside coverage — and the honesty of the sentence
that explains why the threshold is where it is. That bounded blast radius is most of why (b) is
acceptable where a general lifting of §4 would not be.

**The permutation null is the right null, and it must be named as such.** Permuting each column
independently destroys cross-sectional dependence while preserving each ticker's own marginal
distribution — its volatility, its fat tails, its zero-return sessions, its limit-band clustering.
The null is therefore "these residual series have no co-movement", not "these residual series are
Gaussian noise". That is the correct comparison for a coverage threshold, and it is strictly more
faithful than the analytic floor, which assumes ρ̂² ≈ χ²₁/T and thereby assumes away every
distributional feature this market actually has.

**The analytic floor is not discarded.** It becomes the cross-check: on pure-noise input the
permutation p95 must land near the `docs/01` §6 figure, and the module's selftest asserts exactly
that. Two independent derivations agreeing on the easy case is what licenses trusting the
empirical one on the hard case.

## Consequences

- `docs/02` §4 is amended to carry the narrowed wording, with a pointer to this record. `docs/01`
  §6 gains a paragraph reconciling the analytic floor with the permutation percentile — stating
  which statistic each describes, rather than presenting them as competing estimates of one thing.
- New module `pipelines/research/nulls.py`, `--selftest` idiom like the rest of
  `pipelines/research/`. Output `data/research/tau_calibration_{measure}.csv`.
- The seed is recorded in `study.json` alongside `n_reps`. A calibration whose seed is not written
  down is not reproducible, and reproducibility is not negotiable here (`docs/02` §3.3).
- **The result is accepted in advance, in both directions.** If the p95 of the null lands
  materially above 0.10, then τ = 0.10 has been understating rejection and [[D-2]] must be
  revisited — that is a consequence of taking this decision, not an outcome to renegotiate when
  the number arrives. If it lands below, τ = 0.10 is conservative and the report says so with a
  computed figure instead of an assertion.
- This record does **not** close [[D-2]]. It supplies one of the two things D-2 was waiting for.
  Choosing the final τ from the calibration, and the final `k` from the coverage evidence, remains
  a report-writing decision.
- Nothing in `services/api` or `apps/web` changes. `tau` is already served as an artifact field
  and is displayed as a number; where the number came from is a documentation question, not an
  interface one.
