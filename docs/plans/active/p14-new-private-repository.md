# P14 execution plan — a private repository, and deployment files that stop lying

**Started:** 2026-08-29
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md`
**Predecessor:** P13's market home redesign, committed before this began.
**Records produced:** [[D-29]], [[D-30]]

> **This plan changed shape mid-flight, and says so.** It began as *"split the study into a second
> repository"* — the owner's first choice — and G1 was written for that. The owner then reversed
> it in favour of a single new private repository. The old G1 is preserved below as the
> alternative it became, because a plan that quietly rewrites its own history is worth less than
> one that shows where the decision moved. [[D-29]] carries the reasoning.

> **Naming collision, stated so it is not tripped over.** The predecessor's
> `services/api/app/runtime_guards.py` cited "P14-S03A". That label was inherited from the dead
> ClusterWeb world and had nothing to do with this phase; it has been removed rather than
> renumbered. The anchor-model phases run P6…P13, so P14 is the next free number.

---

## Why

Two problems, unrelated in cause, both load-bearing.

**1 — The deployment files described a system nobody ran.** `render.yaml` declared both the API
and a Render Static Site for the dashboard, while the dashboard was served from Netlify and the
repository contained no Netlify configuration at all. `render.yaml`'s own header gives *"a thesis
defence should be able to rebuild the deployment from the repository"* as its reason for existing.
A blueprint that rebuilds a topology nobody runs fails at exactly that. [[D-30]].

**2 — The study was held in place by `.gitignore`, which git does not respect across branches.**
Git will not clobber an untracked file but *will* freely delete an ignored one. Checking out any
pre-split branch and leaving it wiped `docs/`, `pipelines/research/` and `data/research/` off disk
with no warning — recorded in the predecessor's `AGENTS.md` after it happened twice. A warning is
not a fix. [[D-29]].

---

## Progress

### G1 — The repository — **DONE, by a different route than planned**

**Planned:** keep the public repository and move the study into a second private one.
**Done:** a single new private repository at `D:\anchor-stock`, fresh `git init`, no history
carried. The public `anchor_stock` remote and the full working copy at `D:\DATN_new` are
untouched, so this is entirely reversible.

- [x] `git ls-files` from the predecessor defined the copy set — 168 tracked files, which
      automatically excluded `node_modules`, `.next`, `out`, every cache, and `.env`
- [x] `docs/` copied in and **tracked**, which is the whole of [[D-29]]
- [x] `pipelines/research/`, `data/research/` and the nine non-primary artifacts left behind.
      They are *absent*, not ignored — no branch operation here can delete them
- [x] `.gitignore` rewritten: secrets, regenerable output, machine-local directories. Nothing
      that hides a source file
- [x] `AGENTS.md` rewritten to absorb `CLAUDE.md`, which was a delta against a global rulebook
      **that did not exist on this machine**. Its substance is now stated directly
- [x] Root `README.md` added
- [x] [[D-29]] written; `docs/decisions/README.md` register corrected — **D-28 had a record on
      disk and no row in the table**, so the register understated what had been settled

**Not done, and it is a debt not an oversight:** `docs/` cites `pipelines/research/` throughout
and those citations now point outside the repository. Same class as the dangling citations D-28
accepted, same justification, stated where a reader meets it in `AGENTS.md`.

### G2 — One host, one file — **DONE** ([[D-30]])

- [x] `render.yaml` reduced to the API. Header rewritten: the "asymmetric topology" section and
      the three-step first-deploy dance both described a two-service Render deployment
- [x] `netlify.toml` added at the repository root — `base = "apps/web"`, `publish = "out"`.
      `trailingSlash: true` already makes deep links resolve, so no redirect rule is needed
- [x] `NEXT_PUBLIC_API_BASE_URL` deliberately **not** committed, with the reason at the place it
      is missing: it is build-time, mandatory, and committing a guess produces a site that builds
      green and points at nothing
- [x] [[D-30]] written, superseding [[D-21]] in provider only — its reasoning is adopted, not
      reversed

- [ ] **OPEN — why Netlify rather than Render Static.** D-21's argument (a static host never
      sleeps) does not distinguish the two, so D-30 needs a reason D-21 did not have. Recorded
      OPEN rather than invented. One sentence from the owner closes it
- [ ] `docs/RUNBOOK.md` §deploy still says the site and the service auto-deploy from the same
      `main` commit. Untrue across two providers; needs re-sequencing

### G3 — CORS, or every deploy preview breaks — **DONE**

- [x] `ALLOWED_ORIGIN_REGEX` — validated in `runtime_guards`, carried on `RuntimeConfig`, passed
      to `CORSMiddleware`. Netlify mints a new origin per preview
      (`https://<hash>--<site>.netlify.app`) that no exact-match list can enumerate
- [x] The production guard now requires **either** origin input. Neither is still fatal
- [x] `is_overbroad_origin_regex` refuses a pattern admitting a reserved `.invalid` probe.
      The probe hostname is lowercase-only **because the first version had a hyphen and
      `[a-z:/.]*` slipped past it** — caught by the test, not by review
- [x] 13 assertions (`OriginRegexTests`), including that Starlette's `fullmatch` anchoring holds

### G4 — Cold start — **not chosen**

Render's free Web Service sleeps. With an always-instant front end the asymmetry is fully
visible: a complete-looking page whose every panel hangs.

- [ ] Render Starter / scheduled keep-alive / an honest waking-up state. Record the choice

### G5 — CI — **DONE**

- [x] `.github/workflows/ci.yml`, four independent jobs so a failing web build cannot hide a
      passing API suite
- [x] `scripts/check_locks.py` — **the check `requirements.in` admitted did not exist.** It
      restated the API's four packages under a comment saying *"nothing checks the agreement —
      there is no CI"*. The restatement is gone (`-r requirements-api.in`) and this asserts what
      remains. Both failure modes were provoked deliberately; each exited 1
- [x] `ruff.toml` folded into `pyproject.toml`
- [x] 18 pipeline self-checks driven through the repository's own idiom

**`pyproject.toml` does not carry the dependency sets, and the gap is deliberate.** Both locks
carry their regeneration procedure in their headers — a pinned pip-tools compiler inside a
disposable `python:3.13-slim` container, because a Windows-resolved lock is not authoritative for
a Linux deployment. That cannot run on this machine, and a pyproject whose extras had never been
compiled would leave pins that do not provably match their declared source. The defect that
migration was meant to fix was fixed directly instead.

### G6 — Generated response types — **not started**

- [ ] `apps/web/src/lib/api.ts` is 867 lines, much of it response shapes maintained by hand
      against FastAPI. Generate from `/openapi.json` so backend drift is a type error

### G7 — The UI pass that opened this phase — **not started**

Ordered last on purpose: a design pass onto a deployment that lies is polish on sand.

- [ ] Design canvas to settle layout, hierarchy, token values, states — **as a mockup**. Its
      output is standalone HTML with inline styling; pasting it in would destroy the
      `only var(--*)` rule that made the P11→P13 palette swap a ramp edit
- [ ] Translate into `globals.css` §2/§2b/§3 and the CSS Modules by hand
- [ ] `design:accessibility-review`. The pos/neg split at -500/-600 exists because TradingView's
      own green and red fail AA on 13px text — that reasoning must survive any repalette
- [ ] **Chart library — open.** ~1,300 hand-rolled SVG lines imitating TradingView's idiom;
      `lightweight-charts` *is* TradingView's library. Keeping the hand-rolled code is also a
      defensible thesis claim

---

## Validation

### Run in this repository, on 2026-08-29 — Windows, Python 3.13.13, `DATABASE_URL` unset

| Command | Result |
|---|---|
| `ruff check .` | All checks passed |
| `python scripts/check_locks.py` | 3/3 OK; both failure modes provoked and each exited 1 |
| `unittest discover -s services/api/tests` | **Ran 196 tests — OK** |
| `npm --prefix apps/web run test` | 57 passed |
| `npm --prefix apps/web run lint` | clean |
| `npm --prefix apps/web run build` | 7 static pages exported, no `NEXT_PUBLIC_API_BASE_URL` |
| 18 × `python -m pipelines.<module>` | every one exited 0 |

### Not attempted, named rather than papered over

| Check | Why not |
|---|---|
| The CI workflow's own green run | CI cannot run before it is pushed, and this repository has no remote yet. A path assumption holding only on Windows, or a wheel differing on Linux, would surface on the first push. **A red first run is expected, not a surprise.** |
| G3 against a real Netlify preview | The check that actually proves G3. Needs a deploy |
| Anything touching Supabase | No credentials used anywhere in this pass, by design |
| Lock regeneration from `pyproject.toml` | Needs the documented Linux container. See G5 |

---

## Traps worth naming

1. **`D:\DATN_new` is the only copy of the research.** This repository does not carry
   `pipelines/research/`, `data/research/`, or nine of the ten artifacts. Back that directory up
   before doing anything destructive to it.
2. **Two deploy triggers instead of one.** The halves ship from two pipelines that can succeed
   independently, so the API and the dashboard can disagree about which routes exist. The
   site-without-API failure `RUNBOOK.md` flags is now bidirectional.
3. **`ALLOWED_ORIGINS` and `ALLOWED_ORIGIN_REGEX` live in Render's dashboard**, not in
   `render.yaml`. The Netlify origin has to be put there by hand or the production guard keeps
   the API from booting — the guard working correctly, looking like a broken deploy.
4. **`supabase/migrations/00013` is applied to Supabase.** The database is ahead of any fresh
   clone that has not run the runbook.
