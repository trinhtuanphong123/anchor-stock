# D-23 — The public repository carries the code and the results, not the working documents

**Status:** Decided, 2026-08-19 (P8).
**Affects:** `.gitignore`; what a GitHub clone contains; the resolvability of `docs/` citations
in tracked files. No behaviour, schema, or model changes.
**Related:** [[D-21]] (the deployment this was prompted by), [[D-20]] (what must never be
published at all — the service-role key).

## Context

P8 is the first phase whose output leaves this machine. The repository is **public**, and Render
deploys from it, so "what is in the repository" stopped being a private question.

Two things were conflated in the original framing and are worth separating, because only one of
them is real.

**Removing files does not help Render.** Render clones the whole repository and then runs only
the declared commands inside the declared root directories — `pip install` in `services/api`,
`npm ci && npm run build` in `apps/web`. `docs/` and `_archive/` are never read, never copied
into the image, and cost nothing at build time. There is no deployment saving to be had here.

**Publishing working documents is a real choice.** `docs/` holds the specification, the phase
plans, the decision register and the status notes — the thesis's reasoning, in draft, including
records that describe security findings (D-20) and unresolved questions. That is a defensible
thing to keep off a public URL, on its own merits and independent of Render.

## Alternatives

**(a) Publish everything.** The status quo, and the most reproducible. Rejected: it puts the
thesis's working notes and its internal security record on a public page before the work is
examined.

**(b) Publish only what Render builds** — `render.yaml`, `services/api/`, `apps/web/`, and the
API lock. Rejected, and this is the one worth arguing against properly. It would remove
`pipelines/` (the model itself), `supabase/migrations/` (the schema), and `data/artifacts/` +
`data/research/` (the study's results) from version control entirely, leaving them on one
laptop with no history and no off-machine copy. `AGENTS.md` states the opposite requirement for
exactly those artifacts: they "are the thesis results and are kept", and must be "citable and
reproducible from the repo alone". A deployment convenience is not a reason to delete the
contribution.

**(c) Ignore `docs/` and `_archive/`; publish everything else.** Chosen.

## Decision

`docs/` and `_archive/` are gitignored. Everything needed to run and verify the study stays
published: `pipelines/`, `supabase/migrations/`, `services/api/`, `apps/web/`, `scripts/`, the
universe lists, and `data/artifacts/` + `data/research/`.

`_archive/` was already ignored by rule, but 59 files were tracked under it anyway — **`git mv`
into an ignored directory still stages the move.** Both trees needed `git rm -r --cached` once
to actually leave the index. The files remain on disk, which is the point: the archived Leiden
screens are the reference P10 rewrites against.

## The consequence, stated rather than discovered later

**Tracked files cite `docs/` paths that a public clone will not contain.** Both README files,
the `requirements*` headers, several module docstrings, `CLAUDE.md`, and `AGENTS.md`'s own
tables all point into `docs/`.

Those citations are **left in place**, and `AGENTS.md` carries a note explaining why. Stripping
them would trade a reference a public reader cannot follow for a claim with no reason attached
at all — and the reason is the part that matters to anyone actually modifying the code. This
repository has already been bitten by the other failure mode: `docs/deployment/PYTHON_RUNTIME.md`
was cited four times and had never existed (fixed in P8.1). The distinction is that these paths
are real and resolve in a working copy; that one was fiction.

## Verified

* `git ls-files` after the change: `pipelines` 52, `data` 36, `apps` 35, `services` 13,
  `supabase` 12, `scripts` 4, plus the root files. `docs` and `_archive` at 0.
* Both directories confirmed still present on disk.
* `git check-ignore -v` resolves `docs/WORKFLOW.md` and
  `_archive/p8-leiden-screens/app/clusters/page.tsx` to the new rules.
* Publishable tree scanned for the Supabase project ref (**absent everywhere**), for
  `postgresql://user:pass@` connection strings, JWT-shaped tokens, and long secret-shaped
  assignments. Every hit is either a deliberately fake test fixture (`u:p@h`,
  `svc:TopSecret@host`) or the local Docker container password `datn_local_dev` from
  `scripts/db/compose.db.yml`, which is a throwaway local credential and is meant to be read.
