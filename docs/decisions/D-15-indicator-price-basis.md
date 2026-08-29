# D-15 — Indicator price basis: adjusted close

**Status:** Decided, 2026-08-18
**Affects:** `pipelines/indicators/compute.py`, `pipelines/indicators/build.py`,
`technical_indicators_daily` (every price-derived column); the ticker page's chart caption (P10).
**Depends on:** [[D-06]] (adjusted-close semantics), which fixed the same choice for the model.

## Context

D-6 decided that the model consumes **source-adjusted** closes: `vnstock`'s adjusted series,
where a dividend or split is retroactively applied to the whole prior history. That was the right
call for returns — an unadjusted series puts a ~5% "loss" in `log_return` on every ex-dividend
date, which the factor model would read as a real move and the residual as real idiosyncratic
risk.

P7 computes a second family of price-derived numbers from the same table, but for a different
consumer: a human looking at a chart. The question is whether the display layer should share the
model's basis.

## Alternatives

**(a) Adjusted, same as the model.** One price series in the database, one meaning for `close`.
The chart, the returns, and the residuals all describe the same series. Cost: the chart will not
match a broker's default chart across an ex-date, and a reader who checks will find a
discrepancy.

**(b) Raw (unadjusted) for display, adjusted for the model.** Matches what a reader sees
elsewhere. Costs: a second price column or a second `source` in `daily_bars`; two collection
paths; and — the deciding objection — `ret_1d` computed on raw prices would disagree with
`daily_returns.log_return` computed on adjusted ones, for the same ticker on the same date, in
the same database, with nothing on screen explaining why.

**(c) Adjusted, plus a raw series collected alongside purely for the chart.** Gets both, at the
cost of doubling collection against a throttled provider and doubling the reconciliation surface,
to fix a cosmetic mismatch on a small number of dates per ticker per year.

## Decision

**Adjusted.** Every column of `technical_indicators_daily` is computed from the same
`daily_bars.close` the factor model uses, and this is **stated on the dashboard**, not left for
a reader to discover.

## Why the dashboard has to say it

An adjusted chart is not wrong, but it is not what a reader expects, and the disagreement is
concentrated exactly where a reader is most likely to look closely: a large single-day move that
turns out to be a dividend. Left unexplained, the honest answer ("the chart is adjusted") is
indistinguishable from the dishonest one ("the data is wrong"). One sentence on the ticker page
converts a credibility problem into a methodology note.

The same caveat covers `high_252d` / `low_252d` and `drawdown_from_252d_high`, which are the
columns where adjustment compounds most visibly: a 252-session high on an adjusted series is not
the price the stock actually printed a year ago.

## Consequence

`ret_1d` in `technical_indicators_daily` and `log_return` in `daily_returns` are now guaranteed
to describe the same underlying move — verified directly in P7: across all 120,929 rows where
both exist, `|ret_1d - (exp(log_return) - 1)| ≤ 6e-17`. They differ only in being simple versus
log, which is a display choice recorded in P7's plan (S2), not a data difference.
