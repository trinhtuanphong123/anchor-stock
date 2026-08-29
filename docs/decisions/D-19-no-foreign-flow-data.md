# D-19 — No foreign-flow (khối ngoại) data this pass

**Status:** Decided, 2026-08-18 (recorded retroactively — the choice was made in the P6–P10 plan)
**Affects:** the market page's KPI row (P10); `technical_indicators_daily.turnover_value`, which
takes the place the foreign-flow cards would have occupied. No schema anywhere holds a
foreign-flow column, so nothing is left applied-and-empty by this decision.

## Context

Vietnamese market dashboards conventionally show **khối ngoại** — foreign investors' buy and sell
value for the session, and the net. It is a headline number on every commercial HOSE dashboard,
and the reference screens this project's dashboard is modelled on carry it.

The project's collected data does not include it. `vnstock` exposes it through a different call
than the OHLC path P0–P2 built, at a different granularity, with no history guarantee comparable
to the six years of bars already landed.

## Alternatives

**(a) Collect it.** A new fetch path, a new staging shape, a new table, new high-water-mark
handling, and a new quality surface — all for a figure the model does not consume and the anchor
argument does not use. It would also need its own back-history collection against a throttled
provider, and any gap in that history shows on the market page as a missing headline number.

**(b) Show the cards with placeholder or partial data.** Rejected outright. A KPI card is read as
a measurement; an empty or partial one on a page whose whole purpose is to be checkable is worse
than an absent one.

**(c) Omit it, and put a number the project *does* have in that space.** Chosen.

## Decision

**No foreign-flow data this pass.** The space the foreign-flow cards would occupy is filled by
**total turnover** — `sum(turnover_value)` over the session, exposed by `v_market_overview`, with
per-sector turnover in `v_sector_performance` sizing the treemap tiles and per-ticker turnover in
`v_top_movers`.

`turnover_value` is `close × volume`, derived from bars already collected and verified. It is the
same *kind* of quantity a reader wants from the foreign-flow cards — where the session's money
went — computed from data this project can account for end to end.

## Why this is not a gap to apologise for

The dashboard's claim is about anchor selection, and foreign flow is not evidence for or against
it. Adding a collection path, a table and a failure mode to reproduce a convention would spend
the phase's budget on a number that no other part of the system reads. The honest version of this
dashboard shows what the project measured.

## Reversing this

Additive and self-contained: a fetch path, a table, and one more scalar subquery in
`v_market_overview`. Nothing in P6–P10 is shaped around the absence, and no column, view or index
would need to change. Related in kind: [[D-13]] (static dashboard) — both are decisions to leave
a data source out rather than to represent it badly.
