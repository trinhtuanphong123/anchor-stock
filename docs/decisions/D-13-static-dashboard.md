# D-13 — Static dashboard: no live-apply path, no orchestration

**Status:** Decided, 2026-08-18 (recorded retroactively — the choice was made and acted on in P6)
**Affects:** `supabase/migrations/00007_live_monitors.sql` (applied, unpopulated); `docs/04` §3–4;
P9's API contract; P10's screens. Does **not** affect the model, the artifact, or any research
result.

## Context

`docs/04` specifies a two-track system: the local train track produces a frozen artifact, and a
dashboard track *applies* that artifact to new sessions with frozen α̂/β̂, never refitting. The
apply path writes `live_session_residuals`, `live_coverage_monitor`, `live_assignment_challenges`
and `live_anchor_signals`, and something has to run it every session — originally Airflow.

By P6, Airflow had been dropped (see the parent plan's P8) and the remaining question was
whether the *apply* half should be built anyway and triggered by hand.

## Alternatives

**(a) Build the live-apply path and run it manually per session.** Populates the four `live_*`
tables, so `v_active_group_health` returns real drift figures and the dashboard can show
coverage decay. Costs: a second compute path with its own correctness surface (frozen-parameter
residualisation, warmth rules, challenge detection), verified by nothing, feeding a dashboard
whose primary claim is about the *published* run rather than about drift.

**(b) Build the apply path but populate it from a backfill** — replay 2026 sessions through it.
Same code cost as (a) plus a backfill that is indistinguishable on screen from live operation,
which is worse than not having it: a reader cannot tell a replayed monitor from a real one.

**(c) Static dashboard. Serve the frozen artifact and the full price/indicator history; leave
`live_*` unpopulated.** Chosen.

## Decision

The dashboard is **static** with respect to the model. It serves:

* the active `model_run` and its frozen parameters (`v_active_model_run`, `v_active_assignment`),
* the full price and indicator history, which `docs/04` §5 already exempts from model gating.

The four `live_*` tables stay applied and empty. They are **not dead schema** — `docs/03` §8 and
`docs/04` §3–4 specify them, and deleting them would put the schema at odds with the
specification. They are reserved.

## Why

The thesis claim is about **anchor selection**: that a small set of tickers represents a
universe, and that the selection is reproducible and defensible. Live drift monitoring is
evidence *about the stability of that claim over time*, which P5's stability track already
supplies from the research years — computed on five years of real data, cross-year, and written
down. A hand-run apply path would add a second, weaker source of the same kind of evidence.

## Consequence P9 must handle

`v_active_group_health` LEFT JOINs `live_coverage_monitor`, so its monitor columns come back
NULL. **The API must pass NULL through and never render it as 0.** A zero drift figure is a
claim that drift was measured and found to be nil; NULL is the truth, which is that nothing was
measured. This is the single most likely way this decision turns into a lie on screen.

## Reversing this

Reversal is additive and does not touch anything already built: implement the apply step against
the existing frozen artifact, populate `live_*`, and `v_active_group_health` starts returning
values with no schema or view change. Nothing in P6–P10 forecloses it.

Related: [[D-19]] (no foreign-flow data) is the same shape of decision — a data source that the
static dashboard does without.
