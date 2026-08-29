# D-29 — A private repository carrying both the system and its documents

**Status:** Decided, 2026-08-29. Supersedes [[D-23]] and [[D-28]], both of which arranged the
opposite for a repository that was public.
**Affects:** `.gitignore`; whether `docs/` is under version control; whether the plan-and-code
commit rule in `AGENTS.md` is satisfiable at all; where `pipelines/research/` lives.
**Related:** [[D-28]] (published the system and withheld the study), [[D-23]] (its predecessor),
[[D-30]] (the hosting split decided in the same pass).

## Context

D-23, then D-28, kept this project's documents out of git. `docs/`, `pipelines/research/`,
`data/research/` and nine of the ten artifacts were listed in `.gitignore` so that a public clone
would receive the runnable system and none of the author's study.

The arrangement worked, and it cost three things that were only visible after living with it.

**One: git deletes ignored files across a branch switch.** Git will not clobber an *untracked*
file, but it will freely delete an *ignored* one. Checking out any branch from before the split
and leaving it wiped `docs/`, `pipelines/research/` and `data/research/` off disk with no warning.
D-28's own record and `AGENTS.md` both carry the warning, added after **it happened twice**. A
warning is not a fix: the mechanism stayed armed, and it guarded the only copy of the research.

**Two: the repository's own commit rule became unsatisfiable.** `AGENTS.md` requires a durable
planned change to carry a plan file, and requires the plan's Progress and Validation sections to
move in the same commit as the code they describe. Plans live in `docs/`. Ignored files cannot be
in any commit. So from the moment D-28 landed, every durable change violated the rule by
construction, and the violation looked like negligence rather than like the structural
consequence it was.

**Three: many tracked files cited paths a clone would not contain.** D-28 accepted this
knowingly and argued the citations should point at the real location rather than be stripped. That
argument still holds. But the count kept growing — both READMEs, the `requirements*` headers,
several module docstrings, `CLAUDE.md`, the tables in `AGENTS.md`, comments in `apps/web` and
`pipelines/`.

Set against that, the benefit of publishing: a reviewer could read the system without an account.

## Alternatives

**(a) Keep one public repository, ignore `docs/` as before.** Status quo. Rejected because it
retains all three costs and the deletion hazard in particular is a live risk to files that exist
in one copy.

**(b) Two real repositories — a public `anchor-stock` for the system, a private `anchor-study`
for `docs/` and the research.** This was chosen first and then reversed by the owner. It removes
the deletion hazard, because nothing is hidden by ignore rules any more. It does not solve the
plan-commit rule: plans would live in the study repository while the code they describe lives in
the system repository, so the two still cannot move in one commit. It also doubles the number of
places a change has to land.

**(c) One private repository carrying the system and the documents.** Chosen.

## Decision

**(c).** `docs/` is tracked. `.gitignore` excludes only secrets, regenerable output, and
machine-local directories — nothing that a reader would want and cannot rebuild.

The research track is *absent from this repository* rather than *ignored within it*:
`pipelines/research/`, `data/research/` and the nine non-primary artifacts stay in the author's
working copy at `D:\DATN_new`. That is the owner's instruction and it is what makes this a system
repository rather than a second copy of everything. The distinction from D-28 matters: those paths
are not on an ignore list here, so no branch operation can delete them, because they are not here
at all.

## Consequences

**The deletion hazard is retired.** Not documented, not warned about — removed. There is no
ignored source file left to lose.

**The plan-and-code commit rule works for the first time.** A durable change can now put its plan
file and its code in one commit, which is what `AGENTS.md` asked for and what D-28 made
impossible.

**Publishing is given up.** A reviewer needs to be granted access rather than handed a URL. This
is the real cost, and it is the whole of what D-23 and D-28 were buying. The judgement is that a
thesis is examined by named examiners who can be granted access, not by anonymous readers, so the
public URL was purchasing convenience rather than a requirement.

**The dangling citations move rather than disappear.** `docs/` came across whole and refers to the
research studies throughout; those references now point outside this repository. This is the same
class of citation D-28 accepted, with the same justification — a citation that silently drops its
reason is worse than one whose reason is held elsewhere — and `AGENTS.md` says so where a reader
will meet it. **No code depends on the missing tree:** `pipelines/research/` depended on the core
and nothing depended on it, and neither `services/api` nor `apps/web` imports any `pipelines`
module ([[D-18]]).

**If the project is ever published again**, this record is what to argue against, and the argument
has to answer the three costs above rather than restate the benefit.
