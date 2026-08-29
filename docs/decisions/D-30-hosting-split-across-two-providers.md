# D-30 — The API on Render, the dashboard on Netlify

**Status:** Decided in shape, 2026-08-29. **The provider choice itself carries an OPEN
justification — see §The open half.** Supersedes [[D-21]] in *provider only*; D-21's reasoning is
adopted unchanged.
**Affects:** `render.yaml`; `netlify.toml`; `services/api/app/runtime_guards.py` (CORS);
`docs/RUNBOOK.md` §deploy.
**Related:** [[D-21]] (Render web service + Render static site), [[D-20]] (the API connects as
`postgres`), [[D-18]] (what the API serves), [[D-13]] (static dashboard — nothing to schedule).

## Context

D-21 put the API on a Render Web Service and the dashboard on a Render Static Site. The dashboard
is now served from Netlify. `render.yaml` still declared both, so the repository asserted a
topology nobody ran — in a file whose own header gives "a thesis defence should be able to rebuild
the deployment from the repository" as its reason for existing.

That is not ordinary staleness. It is the file failing at the single thing it was written for.

## Alternatives

**(a) Move the dashboard back to Render.** Restores agreement between file and reality at zero
cost in configuration, and needs no new record. Rejected by the owner.

**(b) Keep one `render.yaml` describing both, and treat Netlify as undocumented.** Rejected
outright: it is the current broken state, and a configuration file that overstates its reach is
worse than no file, because it is trusted.

**(c) One declarative file per host, each describing only what it owns.** Chosen. `render.yaml`
declares the API; `netlify.toml` declares the dashboard. Neither overstates its reach.

## Decision

**(c).** The Blueprint format is retained for the half Render still runs — the objection was never
to the format, which is Render's native declarative form, but to a file claiming services it does
not own.

**D-21's argument is carried over intact.** A Web Service serving static files can spin down, so a
visitor arriving cold would wait for the HTML itself before any request to the API was even
issued; a static host is always instant and only the data behind it can be slow. Netlify satisfies
that exactly as Render's Static Site did. Nothing about *static hosting over a web service* is
being reversed here.

## The open half

**Why Netlify rather than Render's own Static Site is not recorded, because it is not known.**

D-21's stated reasoning does not distinguish the two: both are static hosts that never sleep, and
that is the entire basis on which D-21 chose one. A record superseding it needs a reason D-21 did
not have — build minutes, deploy previews, a custom domain, CDN presence nearer the readers, or
simply that the site is already there and moving it back is churn.

Any of those closes this. Inventing one does not, and `docs/WORKFLOW.md` is explicit that an
unresolved choice belongs in the register marked **OPEN** rather than left as a silent assumption.
**Evidence needed to close:** one sentence from the owner naming the property Netlify has that
Render Static does not.

## Consequences

**Deploy previews forced a CORS change, and it is not cosmetic.** `CORSMiddleware` was configured
with an exact-match origin list. Netlify mints a new origin for every preview deploy —
`https://<hash>--<site>.netlify.app` — which no list can enumerate, so every preview would render
`api_not_configured` on every panel and read as a broken deployment. `ALLOWED_ORIGIN_REGEX` was
added, validated in `runtime_guards`, and the production guard now requires *either* origin input
rather than the list specifically: a deployment serving only previews has no fixed origin to list.
Configuring neither remains fatal.

`is_overbroad_origin_regex` refuses a pattern that admits a reserved `.invalid` probe origin. Two
limits are deliberate and are documented at the code: a literal `ALLOWED_ORIGINS=*` is still
accepted where an equivalent regex is not — a wildcard is a legible declaration, a regex that
happens to match everything is what a typo looks like — and the probe cannot catch a pattern broad
*within* a shared domain, so scoping to the site's own name stays the operator's job.

**Two deploy triggers instead of one.** The halves now ship from two pipelines that can succeed
independently, so the API and the dashboard can disagree about which routes exist. `RUNBOOK.md`
already flagged the site-without-API case; that failure is now bidirectional.

**The cross-reference still cannot be automated.** The site must be *built* with the API's URL
(Next inlines `NEXT_PUBLIC_*` at build time) and the API must be *configured* with the site's
origin before CORS admits it. Render's `fromService` could not close that loop when both services
lived in one file; across two providers it is not even a candidate. Both cross-references are set
by hand once, and both files say so at the variable.

**Cold start is unchanged and unaddressed.** Render's free Web Service still sleeps. With an
always-instant front end the asymmetry is now fully visible: a complete-looking page whose every
panel hangs. That is the residue of D-21's choice, not a regression from it, and it is a separate
open question — Render Starter, a scheduled keep-alive, or an honest waking-up state.
