# D-28 — The repository carries the system, not the study

**Status:** Decided, 2026-08-29 (P12/F5 follow-up).
**Supersedes:** [[D-23]], which drew the line one step further out.
**Affects:** `.gitignore`; what a GitHub clone contains; `AGENTS.md`'s published-tree note.
No behaviour, schema, model, or deployment change.
**Related:** [[D-21]] (the deployment), [[D-12]] (the frozen research universe), [[D-18]] (no
import path from the API into `pipelines`).

## Context

[[D-23]] settled that `docs/` and `_archive/` are gitignored and everything else is published.
It considered "publish only what Render builds" and rejected it, correctly, on this ground:

> It would remove `pipelines/` (the model itself), `supabase/migrations/` (the schema), and
> `data/artifacts/` + `data/research/` (the study's results) from version control entirely,
> leaving them on one laptop with no history and no off-machine copy.

That objection stands and this decision does not touch it. `pipelines/`, the migrations, the API,
the dashboard and the artifact the deployment serves all stay published.

What changed is a preference the author is entitled to hold and had not stated when D-23 was
written: **the method studies built on top of the system are the author's own research, and are
to stay private until the thesis is examined** — the same reasoning D-23 already accepted for
`docs/`, applied to the same kind of material. D-23 separated "the code" from "the working
documents". The line it did not draw is the one between *the system* and *the study run on it*.

## The distinction

| | Published | Reason |
|---|---|---|
| `pipelines/` minus `research/` | yes | ingestion, normalisation, quality, returns, the factor model, greedy, indicators, artifacts, storage — **this is the system** |
| `supabase/migrations/`, `scripts/` | yes | the schema, and the runner that applies it |
| `services/api/`, `apps/web/` | yes | what is deployed, tests included |
| `data/artifacts/ae2010a4ad426/` | yes | `is_primary`, 2025 × `pearson_rho2` — **the artifact the deployed dashboard serves**, and what `docs/RUNBOOK.md` §3.6 loads |
| `data/reference/`, `list_stocks*.txt` | yes | inputs the processing chain needs |
| `pipelines/research/` | **no** | the A–G method experiments |
| `data/research/` | **no** | their result tables |
| `data/artifacts/` — the other nine | **no** | 2021–2024 × two measures, plus 2025 dCor²: they exist only to compare across years and measures, which is the study |
| `docs/`, `_archive/` | **no** | unchanged from [[D-23]] / P8 |

Measured at the split: 4,510 KB / 226 tracked files → **1,378 KB / 164**. The removed 3,132 KB is
69 % of the tracked repository and none of the deployed system.

**Fetched price data was never published and this does not change that.** `data/raw/` and
`data/processed/` have been gitignored since P8 as regenerable. The ingestion and processing code
*is* published, which is what lets a reader rebuild them.

## Alternatives

**(a) Leave D-23 as it stands.** Rejected — but only on the author's stated preference, not on a
technical argument. There is nothing wrong with publishing the studies; the author simply does
not want to before examination, and that is their call to make.

**(b) Also drop the unit tests** (`services/api/tests/`, `apps/web/tests/`). Considered and
**rejected**. They are evidence the published system works — 165 API tests and 42 web tests —
and a code repository with no tests reads as one never verified. "Experiments" in the author's
framing means the A–G studies, not the test suite.

**(c) Also drop `data/artifacts/` entirely.** Rejected. The primary artifact is not a study
output in the relevant sense: it is the frozen parameter set the running dashboard serves, and
without it `RUNBOOK.md` cannot rebuild the database the deployment reads. Keeping exactly one is
what makes the deployed state reproducible while publishing no comparison.

**(d) Rewrite history so the already-published research is actually removed.** Offered and
**declined by the author** — see the honesty note below.

## Consequences, stated rather than discovered later

**The private tree loses its off-machine copy — the exact cost D-23 named.** 62 files, 3,132 KB,
now live only in the author's working copy, alongside `docs/`. Backing them up is a manual step
outside git. This is the price of the decision, not an oversight in it.

**Nothing published imports anything private.** Verified before the split: `pipelines/research/`
imports the core one way, and nothing outside it imports `pipelines/research/`; `services/api`
and `apps/web` import no `pipelines` module at all ([[D-18]], asserted by an import sweep). A
public clone runs.

**Six tracked files cite private paths.** `.gitignore`, `AGENTS.md`,
`apps/web/src/components/anchor/AnchorDetail.tsx`, `apps/web/tests/coverageAdjusted.test.ts`,
`pipelines/model/train.py` and `pipelines/returns/matrix.py`. Every one is a comment, docstring
or argparse help string — no import, no runtime read. They are **left in place** and `AGENTS.md`
explains why, exactly as D-23 already did for `docs/`.

**`git rm -r --cached` was required.** A tracked path stays tracked no matter what `.gitignore`
says. D-23 recorded the same lesson for `_archive/`, where 59 files sat tracked inside an ignored
directory; this is the third time the repository has met it.

## The part that cannot be undone, said plainly

**The research has been public on `main` since 2026-08-17 and this decision does not retract it.**
`data/research/` first landed in commit `c99238a` (2026-08-17) and `pipelines/research/` in
`6fbd3ec` the same day; eleven days later the P12 branch push added sixteen more result tables
and eight more modules.

Untracking changes what a *future* clone checks out. It does not change history: `git log -p` on
any existing or future clone still reaches every one of those files, and forks, caches and clones
already taken are beyond reach entirely.

Removing them for real would mean rewriting every commit on every branch and force-pushing —
breaking every existing clone, and still not retracting forks or GitHub's cached views without a
support request. **The author was offered that and chose to stop tracking from here rather than
rewrite.** So the honest statement of what this decision achieves is: *new* research output stays
private, and the repository stops presenting the study as part of its published surface. What is
already out is already out.

## A trap this creates, met twice while making the change

**Switching to a branch that still tracks these paths, and then away from it, deletes them from
disk.** Git will not clobber an untracked file, but it will freely overwrite and delete an
*ignored* one — and that is exactly what these now are. It happened twice during this change:
branching from `main` removed 24 research files that existed only on the P12 branch, and the
merge back onto `main` removed the 38 that `main` had still been tracking. Both times the files
were recoverable only because `origin/p12-method-review-followups` still carries them.

The rule to work by: **before checking out any branch that predates this commit, expect
`data/research/`, `pipelines/research/` and the nine non-primary artifacts to be rewritten or
deleted on disk.** They are no longer under version control, so nothing warns and nothing
restores them automatically. Back them up outside git — the same standing hazard `docs/` has.

## Verified

* `git ls-files`: `data/research` 0, `pipelines/research` 0, `data/artifacts` 2 (both under
  `ae2010a4ad426/`). Total tracked 226 → 164.
* `git check-ignore -v` resolves `data/research/study.json`, `pipelines/research/nulls.py` and
  `data/artifacts/a038e5356e6e0/P.npy` to the new rules, and confirms
  `data/artifacts/ae2010a4ad426/P.npy` is **not** ignored (the re-include works because the parent
  `data/artifacts/` is not itself excluded — git cannot re-include a file whose parent directory
  is).
* All 44 private research files confirmed still on disk and **hash-identical** to
  `origin/p12-method-review-followups` after the branch switch that briefly removed 24 of them.
* Published tree still runs: `ruff check .`, `compileall`, the API and web test suites, and the
  import sweep asserting no `pipelines*` module loads with `app.main`.
