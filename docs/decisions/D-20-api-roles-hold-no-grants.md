# D-20 — Supabase's API roles hold no grants; `postgres` is the only read path

**Status:** Decided, 2026-08-18
**Affects:** `supabase/migrations/00011_revoke_api_roles.sql`; how `services/api` connects (P9);
what `apps/web` may hold (P10). No table, view or column changes.
**Related:** [[D-13]] (static dashboard). This record settles who may reach the database, not
what the API serves — that is [[D-18]], written in P8 on top of this one.

## Context

P7's promotion to Supabase surfaced a state nobody had chosen. Measured on the live project
immediately after the data load:

* RLS enabled on **0 of 26** tables — the migrations are plain SQL and never enable it, so
  nothing filters rows;
* `anon` held `SELECT` on **all 35 relations** (26 tables + 9 views) **and `INSERT`, `UPDATE`,
  `DELETE`, `TRUNCATE` on every table**;
* `public` is a PostgREST-exposed schema, so those grants are reachable over HTTPS.

Supabase's default privileges are the source: `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN
SCHEMA public GRANT ALL ... TO anon, authenticated, service_role` ships with every project, and
our migrations create their tables straight into `public`.

The `anon` key is **public by design** — it ships in the browser bundle. So the state above did
not merely expose the frozen artifact for reading. It meant anyone with the project URL could
`TRUNCATE daily_bars`. Read exposure was the finding; write exposure was the risk.

## Alternatives

**(a) Enable RLS with read-only policies on the views.** The Supabase-idiomatic answer, and it
would let a browser talk to PostgREST directly with no API layer. But RLS is a *row filter*, not
an access model: the tables stay reachable, and the correctness of the boundary becomes a policy
per table, re-derived every time a table is added — 26 today, and `docs/03`/`docs/04` reserve
more. One missed policy on one table is a silent regression to the state above.

**(b) Revoke the API roles' grants; `services/api` connects as `postgres`.** Chosen.

**(c) Decide the artifact is publishable and leave read access open** (fixing only the write
grants). Defensible for the price data, which is not secret. Rejected because it would still
have left `model_ticker_params` and `model_similarity_full` — α̂, β̂, σ̂ and the full P matrix —
served to anyone, and because "publishable" should be an act, not a default nobody chose.

## Decision

`anon` and `authenticated` hold **nothing** in `public`: no table, sequence or function
privileges, no schema `USAGE`, and no default privileges for objects created later. PostgREST
and pg_graphql are not part of this system's read surface. `services/api` connects as
`postgres` over `DATABASE_URL` and is the only path to the data.

This also keeps `docs/04` §5's guard rail meaningful. "The API reads views, not ad-hoc SQL" says
nothing about safety if a browser can query `model_ticker_params` directly — such a client has
walked around the guard rail entirely, whatever the FastAPI layer does.

## Why a migration rather than a fix in the dashboard

`00011` is a migration because the refresh runbook has to rebuild this database from nothing. A
privilege state repaired by hand is a state the runbook cannot reproduce, and the next project
created from these migrations would be wide open with no step that catches it.

It is written to be a **no-op on the local track**: `anon`/`authenticated` do not exist on the
`datn_pg` container, so every statement is guarded by a role-existence check and
`apply_migrations.ps1` keeps working against a plain `postgres:17-alpine`. `REVOKE` is
idempotent, so re-applying is safe.

## The part that took two passes, and is worth knowing

Revoking `USAGE ON SCHEMA public FROM anon` **did not remove anon's schema access.** `public`
carries the standard grant to `PUBLIC` (the ACL reads `=U/pg_database_owner`), which every role
inherits; revoking the role's own entry leaves the inherited one. Measured after the first pass:
table privileges 0, schema usage still `true`.

Closing it needs `REVOKE USAGE ON SCHEMA public FROM PUBLIC`, which touches every role rather
than just the two. The roles that legitimately need the schema were therefore checked
individually rather than assumed: `postgres` (member of `pg_database_owner`, plus an explicit
grant) and `service_role` (explicit grant) are unaffected; `supabase_admin` is superuser and
bypasses checks; `dashboard_user` is neither, would have lost access, and is re-granted
explicitly because it backs parts of the Supabase Studio UI. Breaking the project's own
inspection tooling is not part of this decision.

## What is deliberately still granted

**`service_role` keeps everything.** It is reachable only with the service-role key, which is
secret by design; it is also what Studio's Table Editor uses. Revoking it would break inspection
tooling to close a hole that only a leaked secret opens. **The consequence is a rule for P10:
the service-role key must never reach `apps/web`.** If it leaks, rotate it — this record is not
a substitute for that.

## One residual, stated rather than hidden

`ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin` fails with `permission denied` — `postgres`
is not a member of that role on hosted Supabase. So a table created **by `supabase_admin`** in
`public` would still be granted to `anon`. This repo creates none; the migration reports the
failure as a `NOTICE` rather than swallowing it. The `REVOKE ... FROM PUBLIC` above is the layer
that covers this case, which is the reason it is worth its extra blast radius.

## Verified

* `anon` / `authenticated`: schema usage `false`, and 0 of 35 relations for `SELECT`, `INSERT`,
  `UPDATE`, `DELETE`, `TRUNCATE`.
* Default privileges `FOR ROLE postgres IN public` name neither role, on tables, sequences or
  functions.
* **Empirically, not just by reading the ACL:** a table created as `postgres` after `00011`
  returns `false` for every privilege check by both roles.
* The read path is intact — all 9 views execute as `postgres`, `PostgresSource.read_records`
  returns VCB's 1,424 records, and P7's full verification passes unchanged after the revoke.
* `00011` applied twice to the local container: clean no-op both times.
