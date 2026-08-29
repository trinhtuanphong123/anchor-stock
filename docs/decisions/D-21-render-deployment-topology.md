# D-21 — Render: API as a Web Service, dashboard as a Static Site

**Status:** Decided, 2026-08-18 (P8). The provider terms this rests on were checked against
Render's own documentation while writing `render.yaml`, not assumed; they are quoted below.
Provider terms do change, so the figures carry the date they were read.
**Affects:** `render.yaml`; `apps/web/next.config.ts` (`output: 'export'`); which screens can
exist; how `DATABASE_URL` is supplied. No schema, model, or pipeline changes.
**Related:** [[D-20]] (the API connects as `postgres`; the service-role key never reaches
`apps/web`), [[D-18]] (what the API serves), [[D-13]] (static dashboard — there is nothing to
schedule).

## Context

P0–P7 produced a verified system that runs on one Windows laptop. The thesis needs a URL, and
the requirement attached to it is 24/7 availability rather than throughput: this is a defence
artefact, not a product with traffic.

Two properties of the existing code decide more than the hosting choice does.

`apps/web` is **entirely client-rendered** — every screen is `"use client"`, and the data layer
is `fetch` from a browser. Nothing in it needs a Node server at runtime.

`services/api` **fails fast in production**: `runtime_guards.py` refuses to start without a
structurally valid `DATABASE_URL` and a non-empty `ALLOWED_ORIGINS`, and refuses outright if
`API_DEV_FIXTURES` is truthy. A misconfigured deployment does not boot, which is the intended
behaviour and shapes the deploy order below.

## Alternatives

**(a) Two Render Web Services, both on the free plan, both kept awake by UptimeRobot.** The
obvious reading of "deploy the backend and the frontend". Rejected, but *not* on capacity — see
the correction below.

The rejection is that it buys nothing and costs a cold start. A Web Service serving static files
can spin down; a Static Site cannot. Under (a) a visitor arriving at a cold dashboard waits
roughly a minute for the HTML itself before any request to the API is even issued. Under (c) the
page is always instant and only the data behind it can be slow. For a system whose readers are
examiners opening a link once, that difference is the whole user-visible quality of the
deployment.

It also doubles what has to be kept alive: two services to ping, two to monitor, two that can be
independently asleep, for one page.

> **Correction, recorded rather than quietly edited.** An earlier draft of this record rejected
> (a) on arithmetic: 750 free instance hours per workspace per month, ~730 consumed by one
> continuously-awake service, therefore two cannot fit. **Those figures are right** (read from
> Render's documentation 2026-08-18, along with the 15-minute spin-down) **but the conclusion did
> not apply to this project.** The dashboard is not run continuously — it is switched on and
> pinged when it needs to be reachable, and is otherwise left to spin down. Under that operating
> model the ceiling is not binding and never was. The reasoning above is what actually decides
> the question; the hours are a constraint to remember only if this ever becomes always-on, in
> which case one always-awake service (~730 h) still fits and two do not.

**(b) Two paid Starter services.** Neither sleeps, UptimeRobot becomes genuine alerting rather
than a keep-alive, and the topology is the simplest possible. Rejected only because (c) achieves
the same availability for the dashboard at no cost; revisit if the API ever needs the headroom.

**(c) API as a Web Service, dashboard as a Static Site.** Chosen.

**(d) Serve the built frontend from FastAPI as static files.** One service, no CORS, no second
build. Rejected: it couples the two release cycles, puts frontend assets behind a service that
can cold-start, and discards Render's CDN for no gain.

## Decision

**The dashboard ships as a Render Static Site**, built with `output: 'export'`. Static Sites
deploy at no cost and **do not spin down** — that behaviour applies to web services only — so
the page itself is always instant, with no cold start and nothing to ping. (They also do not
draw on the 750 free instance hours, which matters only if this ever becomes always-on.) Since
every screen was already client-rendered, nothing is given up except SSR and ISR, neither of
which this dashboard uses.

**The API ships as a Render Web Service**, root directory `services/api`, started with
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. The root directory is load-bearing:
`app/main.py` imports `from app.health import …`, so the working directory must be
`services/api` or the import fails with no other symptom.

**Region: `singapore`.** The Supabase project is `aws-0-ap-southeast-2` (Sydney) and Render
offers no Australian region; of the five available — `oregon` (default), `ohio`, `virginia`,
`frankfurt`, `singapore` — Singapore is nearest to both the database and the intended readers.
Leaving the default would have put every query across the Pacific twice.

**UptimeRobot pings `/health` every 5 minutes** to stop the free API service spinning down after
~15 minutes idle. Stated plainly, because it is worth being honest about: this is a keep-alive,
not monitoring.

**The ping is switched on when the system needs to be reachable, not left running by default.**
This is a thesis artefact, not a service with users; between demonstrations the API is allowed
to spin down, and the first request after that pays a spin-up of roughly a minute. The static
site is unaffected either way — it never sleeps, so the dashboard always paints and only its
data waits. Enabling the monitor ahead of a demonstration is what removes that wait.

`/health` is the right target but a weak signal: it returns HTTP 200 whenever the process is
alive and reports database trouble in the body as `"database": "error"`. Render's health check
on it is therefore a liveness check. **Keep it that way** — a health check that failed on a
transient Supabase blip would restart-loop the service, turning a read outage into a total one.

### Configuration, and the cycle in it

| Variable | Service | Notes |
|---|---|---|
| `ENV=production` | API | Arms every guard in `runtime_guards.py` |
| `DATABASE_URL` | API | **Secret**, `sync: false` in the blueprint. Supabase **session pooler**, port 5432 |
| `ALLOWED_ORIGINS` | API | The static site's origin. Startup fails in production if empty |
| `NEXT_PUBLIC_API_BASE_URL` | Web | The API's URL, consumed at **build** time |

The last two reference each other. `NEXT_PUBLIC_API_BASE_URL` is inlined into the bundle by
`next build`, so it must be known before the site is built; `ALLOWED_ORIGINS` must name the
site's origin before the browser will be allowed to call the API.

**That loop cannot be closed declaratively, and this was checked rather than assumed.**
`fromService` supports exactly these properties: `host`, `port`, `hostport`, `connectionString`,
`connectionPoolString`, `user`, `password`, `database`. None yields a `https://…` origin for a
web or static service — `connectionString` produces a database URL (`postgresql://…`,
`redis://…`) and does not apply here. A bare `host` is not enough either:
`runtime_guards._normalize_origin` requires an absolute http/https origin and rejects a value
with no scheme.

So the first deploy is deliberately **two passes**, in the order written into `render.yaml`:
apply the blueprint and supply `DATABASE_URL`; note the site's URL, set `ALLOWED_ORIGINS` and
redeploy the API; note the API's URL, set `NEXT_PUBLIC_API_BASE_URL` and **rebuild** the site.

One consequence worth expecting rather than debugging: **on the first pass the API will fail to
start.** That is the guard working — `resolve_runtime` refuses to boot in production with an
empty `ALLOWED_ORIGINS`, and at that moment the site's origin does not exist yet.

### Why a blueprint rather than the dashboard UI

`render.yaml` in the repository, for the same reason D-20 gave for `00011` being a migration
rather than a hand-fix: a configuration assembled by clicking is a configuration nothing can
reproduce. A thesis defence should be able to rebuild the deployment from the repository, and a
reviewer should be able to read what the deployment is without being given an account.

The blueprint carries no secret. `DATABASE_URL` holds the `postgres` password and is set in
Render's dashboard as a secret with `sync: false`.

### The connection string, twice over

Two constraints on which Supabase endpoint to use, both non-obvious and both cheap to get wrong.

**Pooler, not direct.** Supabase's direct `db.<ref>.supabase.co` endpoint is IPv6-only, and
Render's egress cannot be assumed to be. The failure surfaces as a network error that looks
nothing like a configuration mistake.

**Session pooler (5432), not transaction pooler (6543).** `app/db/connection.py` calls
`conn.set_session(readonly=True)`, which issues `SET SESSION CHARACTERISTICS AS TRANSACTION READ
ONLY`. Under transaction pooling that setting either errors or leaks into another client's
session. The read-only characteristic is defence-in-depth worth keeping, and this deployment has
no connection-count pressure that would justify trading it away.

### What the deployment must not carry

D-20's standing rule, restated because this is the phase where it could be broken: **the
Supabase service-role key must never reach `apps/web`.** `service_role` deliberately retains
every grant, and the static bundle is public by construction. Only `NEXT_PUBLIC_*` variables
exist on the web service, and none of them is a credential.

## One consequence, recorded rather than discovered later

`output: 'export'` cannot build a dynamic route from a client component — `generateStaticParams`
is a server-side export. The dead Leiden screens `/clusters/[cluster_id]` and
`/tickers/[ticker]` therefore had to be archived in P8 rather than P10 as scheduled. The rest of
the Leiden screens went with them, for a separate reason that would have applied anyway: they
fetch endpoints the API does not implement, and publishing them would put visibly broken pages
on a public URL.

## Verified

Nothing yet — this record is written before the deploy, and the checks that close it are P8's
Validation rows 7–12: the export build emitting `out/`, deployed `/health` reporting
`"database": "ok"`, CORS admitting the site's origin and refusing another, live figures on `/`
reconciling against a direct query of `v_market_overview`, no cold start after 20 minutes idle,
and `render.yaml` provably never having carried a secret.
