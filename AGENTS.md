# AGENTS.md — repo orientation and working rules

The only instruction file in this repository. Its predecessor split the same material across
`AGENTS.md` and a `CLAUDE.md` written as a *delta* against numbered rules (Rule 0, 1, 2, 3, 5, 8)
that lived in a global `CLAUDE.md` **which did not exist on the machine**. Half the rulebook was
therefore a set of references to nothing. That file is gone and its substance is stated directly
below, under §Working rules — the same discipline, expressed without citing a document no reader
can open.

## What this project is

A final-year thesis system for the Vietnamese equity market (HOSE). It selects a small set of
**anchor** tickers that best represent a ~100-ticker universe, by maximising a coverage objective
over a residual-similarity matrix.

The method, in one line:

```
adjusted closes → log returns → one-factor OLS on VNINDEX → residuals E
    → P = corr(E) ∘ corr(E)   (ρ², N×N, non-negative)
    → greedy submodular maximisation of  F(S) = Σ_i max_{j∈S} P_ij
    → anchor set S, assignment a(i), coverage c_i, marginal-gain curve Δ
```

`docs/01`–`docs/04` are the **authoritative specification**. Code follows the specs; where code
and spec disagree, the spec wins and the code is a bug. Read them before changing anything
analytical.

| Doc | Covers |
|---|---|
| `docs/01-data-pipeline.md` | prices → returns → factor model → similarity matrix P; noise floor; dCor² variant |
| `docs/02-algorithm-and-outputs.md` | the greedy objective, its guarantee, and the complete output contract |
| `docs/03-temporal-design.md` | which years run, research track vs live track, stability mechanisms |
| `docs/04-static-parameters.md` | what a run freezes, what the dashboard may compute from it |

## This repository is private, and what follows from that

`docs/` is **tracked here** — specs, decision records, plans, status notes, the runbook. That is
the reverse of the arrangement in the public predecessor, where D-23 and D-28 kept `docs/` out of
git by ignoring it. The reasoning is in
[D-29](docs/decisions/D-29-private-repository-carries-system-and-documents.md), which supersedes both.

Two consequences worth stating plainly, because the first is a gain and the second is a debt:

**The gitignore hazard is gone.** Git will not clobber an untracked file but *will* freely delete
an ignored one, so in the predecessor, checking out any branch from before the public/private
split and leaving it wiped `docs/`, `pipelines/research/` and `data/research/` off disk with no
warning. It happened twice. Nothing in this repository is hidden by `.gitignore` except secrets
and regenerable output, so nothing here can be lost that way.

**The research track is absent, and documents still cite it.** `pipelines/research/` (the A–G
method studies), `data/research/` (their result tables) and nine of the ten artifacts were left
behind deliberately — this repository carries the system. But `docs/` came across whole, and the
specs and decision records refer to those studies throughout. Those citations are correct against
the author's full working copy at `D:\DATN_new` and dangle here. They are left pointing at the
real location rather than stripped, because a citation that silently drops its reason is worse
than one whose reason is held elsewhere. **Nothing in the code depends on the missing tree** —
`pipelines/research/` depended on the core and nothing depended on it, and `services/api` and
`apps/web` import no `pipelines` module at all (D-18). A clone runs; the citations dangle, the
code does not.

## Two tracks

- **Local train track** — fetch daily bars to `data/`, run the model entirely offline, emit a
  versioned **artifact** (frozen parameter set). No database involved.
- **Dashboard track** — same fetch code writing to Supabase instead; the artifact is *loaded* and
  *applied* to new sessions with frozen α̂/β̂. Airflow drives it. **Never refits.**

The two tracks share one code path and differ only in the storage sink. That is enforced by
`pipelines/storage/ports.py`.

## Layout

| Path | Role |
|---|---|
| `pipelines/` | A **library of callable steps**, not a service. CLIs and Airflow both call the same functions. |
| `supabase/migrations/` | Schema baseline, `00001`–`00013`. |
| `services/api/` | FastAPI read layer. |
| `apps/web/` | Next.js dashboard, statically exported. Runs standalone on mock data when `NEXT_PUBLIC_API_BASE_URL` is unset. |
| `data/` | `reference/` (curated sector map) and `artifacts/` (the frozen parameter set the dashboard serves). `raw/` and `processed/` are regenerable and ignored. |
| `docs/` | Specs, decisions, plans, status. Tracked. |
| `scripts/db/` | PowerShell helpers for the local Postgres container. |
| `render.yaml` | Both deployed services — API and dashboard — one provider (D-31). |

## Invariants worth knowing before you edit

- **P must be non-negative.** Monotonicity and submodularity hold for *any* real matrix; what
  non-negativity supplies is **normalisation** (F(∅)=0, F never negative), and normalisation is
  what the Nemhauser–Wolsey–Fisher (1−1/e) bound actually requires. Squaring the correlation is
  what supplies it. The other two reasons to square are independent and stronger: ρ² = R² reads
  as a share of variance explained, and a strong negative correlation is structural coupling, not
  the absence of a relationship.
- **The ordered universe pins every position.** Vectors and matrices are stored positionally;
  reordering the universe silently misaligns everything. Artifacts store integer positions, not
  symbols, so a reorder fails validation instead of passing quietly.
- **α̂, β̂, σ̂ are outputs, not scratch values.** They are frozen and reused to residualise future
  sessions without refitting.
- **The session-alignment intersection is not a sufficiency gate.** Spec 01 §1 requires a
  rectangular matrix and forbids interpolation; dropping unaligned sessions is how that is
  achieved. Minimum-session *thresholds* were removed; the alignment was not.
- **Runs must reproduce bit-for-bit.** Greedy breaks ties by smallest index. An artifact's id is a
  content hash that excludes timestamps, so re-running the same data yields the same id.

## Verification

**There is CI** — `.github/workflows/ci.yml`, four independent jobs:

| Job | Runs |
|---|---|
| `lint` | `ruff check .` (configured in `pyproject.toml`) and `scripts/check_locks.py` |
| `api` | `python -m unittest discover -s services/api/tests -t services/api/tests` |
| `web` | `npm ci`, `run lint`, `run test` (vitest), `run build` |
| `pipelines` | 18 module self-checks |

Locally, the same commands work. Note the two that are easy to get wrong:

```bash
PYTHONPATH=services/api python -m unittest discover -s services/api/tests -t services/api/tests
npm --prefix apps/web run test
```

`services/api` tests are **stdlib `unittest`, not pytest** — deliberately. All three modules say
so in their opening docstring, and they use `subTest`, which pytest reports reliably only from
9.x while `requirements-dev.in` pins `pytest>=8,<9`. Under that pin a failing subtest can pass
unnoticed. Do not "modernise" this to pytest without re-establishing that subtest failures fail
the run.

`pipelines/` has **no test runner**, and that is a convention rather than an omission. Its
verification idiom is a `main()` self-check on each module, runnable as
`python -m pipelines.<module>`, usually with `--mock` or `--selftest` so it needs neither network
nor database. Extend that idiom rather than replacing it. Two `__main__` entry points are real
CLIs and not self-checks — `model.train` (needs `--window`) and `universe.sync` (needs `--file`)
— and `common.db` run bare only prints usage; its check is `--check-schema-files`.

**Never report a command as passing when it does not exist.** Separate checks performed from
checks not attempted.

## Working rules

### The three work shapes

**Bounded change** — a small, reversible edit contained to one place: fixing a bug, adjusting a
constant, renaming within a module. Plan in the session, not on disk. Name the check before
starting and run it after. If it starts touching files you did not expect, stop: it was a durable
planned change wearing a disguise.

**Durable planned change** — multi-file refactors, schema migrations, deletions, anything that
leaves the repository in a different shape than it started. **Create `docs/plans/active/<slug>.md`
before mutating anything.** The plan carries a **Progress** checklist and a **Validation**
section, both updated in the same commit as the code they describe — a commit that advances the
build without touching the plan leaves the plan lying about the state of the repository. Session
task tracking and the plan file are not alternatives: the plan survives the session, the task list
does not. Move the plan out of `active/` when the work finishes.

**Read-only request** — research, investigation, "how does X work", "what would it take to do Y".
Investigate and propose. Change nothing, not even a tidy-up you are confident about. The
deliverable is an answer, optionally a plan. Not an edit.

### The stop signal

A `DECISION REQUIRED` marker in `docs/`, or any point where proceeding means inventing a
requirement, **halts the work — even mid-implementation, even inside approved scope.** Choosing
silently would build on an invented premise, and an invented premise is indistinguishable from a
real requirement once it is three commits deep. Surface the fork with its consequences already
stated, and wait.

### Existing decisions

`docs/decisions/` records genuine forks that were resolved, with the alternatives and the
reasoning — not just the choice. **Read the relevant record before proposing its opposite**, and
argue against what it actually says rather than re-deriving the question from scratch. Records for
choices *not yet resolved* are welcome and should be marked `OPEN`, naming the evidence needed to
close them: an open decision recorded is a known gap; an open decision unrecorded is a landmine.

### Where new files go

`docs/plans/active/` and `docs/decisions/` expect new files. Editing existing documents elsewhere
in `docs/` is normal and often required: amending the affected specification is the first step of
any behaviour change, not a follow-up. Creating *new* files outside those two directories,
unasked, signals a misread task.

> The predecessor's `CLAUDE.md` sourced that update rule to `docs/product/README.md`. **No such
> directory has ever existed** — it belongs on the list in `docs/00-project-status.md` §5, which
> catalogues exactly this kind of citation. The rule itself is real and is restated above; only
> its phantom authority is dropped.

## Environment

Windows development machine. Python 3.13. Bash examples need a PowerShell equivalent, and Airflow
runs through Docker Desktop rather than natively.

The author's full working copy — including `pipelines/research/`, `data/research/` and the nine
non-primary artifacts this repository does not carry — is at `D:\DATN_new`.
