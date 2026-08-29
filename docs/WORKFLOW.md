# WORKFLOW.md — the three work shapes

`CLAUDE.md` maps its Rule 1 buckets onto the shapes named here. This file defines the shapes;
`CLAUDE.md` defines how they meet the rules.

## 1 Bounded change

A small, reversible edit contained to one place: fixing a bug, adjusting a constant, renaming
within a module, writing a docstring.

- Plan in the session, not on disk. No file in `plans/active/`.
- Name the check before starting, and run it after.
- If the change starts touching files you did not expect, stop — it was a durable planned
  change wearing a disguise.

## 2 Durable planned change

Multi-file refactors, schema migrations, deletions, anything that leaves the repository in a
different shape than it started.

- **Create `plans/active/<slug>.md` before mutating anything.**
- The plan carries a **Progress** checklist and a **Validation** section. Both are updated in
  the same commit as the code they describe. A commit that advances the build without touching
  the plan leaves the plan lying about the state of the repository.
- Session-level tracking (TaskCreate) and the plan file are not alternatives. The plan survives
  the session; the task list does not. Do both.
- When the work finishes, move the plan out of `active/`.

## 3 Read-only request

Research, investigation, "how does X work", "what would it take to do Y".

- Investigate and propose. **Change nothing** — not even a tidy-up you are confident about.
- The deliverable is an answer, optionally a plan. Not an edit.

## The fourth condition: consequential ambiguity

Not a shape but a stop signal, and it can fire inside any of the three.

A `DECISION REQUIRED` marker in `docs/` — or any point where proceeding means inventing a
requirement — halts the work, **even mid-implementation, even inside approved scope**. Choosing
silently would build on an invented premise, and an invented premise is indistinguishable from
a real requirement once it is three commits deep.

Surface the fork with its consequences already stated, and wait.

## Decisions

Genuine forks that were resolved go in `decisions/` — one record per decision, carrying the
alternatives and the reasoning that produced the choice, not just the choice.

Before proposing the opposite of an existing record, read it. Argue against what it actually
says rather than re-deriving the question from scratch.

Records for choices that are **not yet resolved** are welcome and should be marked `OPEN`, with
the concrete evidence needed to close them. An open decision recorded is a known gap; an open
decision unrecorded is a landmine.

## Reporting

Separate checks performed from checks not attempted. This repository has no test runner and no
CI, so "the check is X, and X is not runnable yet" is an honest and expected sentence. Writing a
command that does not exist and implying it passed is not.
