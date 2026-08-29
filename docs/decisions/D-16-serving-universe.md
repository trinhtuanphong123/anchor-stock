# D-16 — One serving universe, model and presentation

**Status:** Decided, 2026-08-18 (recorded retroactively — the choice was made and acted on in P6)
**Affects:** what `pipelines.universe.sync` writes to `stocks`; what `pipelines.storage.mirror`
carries; which tickers `pipelines.indicators.build` computes; every dashboard aggregate.
**Depends on:** [[D-12]] (the frozen research universe and how it was derived).

## Context

Two ticker lists exist:

* `list_stocks.txt` — the 100 collected in P2.
* `list_stocks_research.txt` — the 85 with a return on every session of every research year
  (D-12), which is what every model artifact was trained on.

`data/processed/` holds all 100: the local track is the research archive and keeps everything
that was ever collected. The question P6 had to answer was which of the two the *database*
holds, and specifically whether the presentation layer could serve the wider 100 while the model
served the 85.

## Alternatives

**(a) Model on 85, present 100.** The market page's breadth counts, turnover and sector treemap
would cover more of the market. Costs: 15 tickers appear in the market view but are absent from
every anchor group, with nothing on screen distinguishing "not an anchor" from "not in the
model"; and the market page's totals would no longer be the totals the coverage figures were
computed over, so `F̄` and "the market" would silently refer to different sets.

**(b) One universe end to end — the model's.** Chosen.

**(c) Model on 100 as well** — i.e. reverse D-12. Argued and rejected there; see that record.

## Decision

**The serving universe is the model's universe.** `stocks`, `daily_bars`, `daily_returns`,
`technical_indicators_daily` and every view in `00009`/`00010` cover exactly the tickers in the
research universe file. `data/processed/` keeps all 100 — the local track is the archive, and
narrowing it would discard collected data for no gain.

## Why

The dashboard's job is to make one claim legible: *these anchors represent this universe*. If
the universe on the market page is not the universe the anchors were selected over, that claim
is unfalsifiable from the screen — a reader cannot check coverage against a set they are not
being shown. Serving one set makes "the 24 tickers in Bất động sản" and "the tickers the model
saw" the same sentence.

## What is decided here, and what is not

**Decided:** there is exactly one serving universe, and it is the one the model was trained on.

**Not decided: which tickers are in it.** The current instantiation is the 85 of D-12, and that
set is known to be uneven by sector — as of 2026-08-18 the live distribution runs from 24 tickers
(Bất động sản và Xây dựng) down to 2 (Công nghệ; Công nghiệp). An equal-weighted sector average
over two names is an average of two stocks, and a treemap gives it the same visual authority as
the 24-ticker tile. Rebalancing the list is expected.

**Nothing in P6 or P7 hard-codes the membership or the count.** The universe is resolved from the
file (`pipelines.universe.file.resolve_universe`), `universe_version` is a content hash of the
list, and the P7 views compute every aggregate from whatever rows exist — no ticker, count, or
sector name appears in `00010_dashboard_views.sql`. Replacing the file and re-running the
pipeline is therefore a data change, not a code change. It **does** produce a new
`universe_version` and therefore a new artifact, which is the intended behaviour: a different
universe is a different study, and D-12's derivation has to be re-run against the new list.
