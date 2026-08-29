# D-6 — Adjusted-close semantics — **DECIDED: ADJUSTED**

**Status:** Decided, 2026-08-17 (during P2). **Prices ARE corporate-action-adjusted.**
**Affects:** every return in the study, therefore every residual, therefore P, therefore the
anchor sets. This was the highest-leverage question in the project; see §Verdict below for the
full evidence and §Consequence for what it changed in the pipeline design.

## Context

`docs/01` §1 states the input precondition plainly: the pipeline consumes **adjusted close**,
after "corporate-action adjustment". The reason is stated in the same section — an unadjusted
price series manufactures a fake return on the ex-date of any split, stock dividend or rights
issue, and "a fabricated return contaminates a correlation."

The old ingestion code (`pipelines/ingestion/daily.py`, now archived) hard-coded:

```python
is_adjusted = False
```

while fetching from vnstock's `Quote(symbol, source="VCI").history(...)`. VCI's `history()` is
*generally understood* to return adjusted prices — but "generally understood" is not a
verification, and the column in the schema was left deliberately nullable in the original
migration with the comment "null until confirmed by source".

So the repository currently contains a flag asserting the data is unadjusted, sitting next to a
provider that probably returns adjusted data, with no evidence either way.

## Why this cannot be guessed

The failure mode is silent and total.

A Vietnamese blue chip paying a 10% stock dividend shows a ~9% one-day drop in an unadjusted
series. That is a ~0.09 log return on a single session — roughly five standard deviations for a
typical HOSE name. Because every ticker's ex-dates are idiosyncratic and unrelated to the market
factor, the one-factor OLS will not absorb them; they land squarely in the residuals.

The residuals are precisely what P is built from. A handful of such spikes across the universe
would not produce an obviously broken matrix — it would produce a **plausible-looking** matrix
whose largest entries are partly artefacts of corporate-action timing rather than co-movement.
The anchor sets would look reasonable and be wrong, and nothing downstream would flag it.

If the data *is* adjusted and the flag merely lies, no harm is done to the numbers, only to
anyone reading the schema. If the data is *not* adjusted, the entire study is contaminated. The
two cases are indistinguishable without checking.

## How to close it

A single ticker with a documented 2024 corporate action is sufficient.

1. Pick a HOSE ticker with a known 2024 stock dividend or split and note the ex-date and ratio
   from the exchange record.
2. Fetch that ticker's daily series through the same provider path the pipeline uses.
3. Compare the close on the session before the ex-date to the close on the ex-date.
   - Drop ≈ the dividend/split ratio ⇒ series is **unadjusted**.
   - No unexplained drop, and pre-ex-date closes are scaled ⇒ series is **adjusted**.
4. Confirm on a second ticker before concluding — one observation could be a coincidence of an
   ordinary bad day.

Record the ticker, ex-date, ratio, the two closes, and the verdict in this file.

## Options once the answer is known

**If adjusted:** set `is_adjusted = true` honestly, document that the provider supplies adjusted
series, and note that `docs/04` §5's warning still applies — a retroactive adjustment rewrites
history, so α̂ and β̂ fitted before it go slightly stale until the next scheduled rebuild.

**If unadjusted:** the pipeline must apply corporate-action adjustment itself before computing
returns, which requires a corporate-actions source that this project does not currently have.
That is a genuine scope addition and should be surfaced as such rather than absorbed quietly.

**Either way:** store both `close` and `adj_close` if the provider can supply both, so the
question never has to be re-litigated from a single ambiguous column.

## Verdict — verified against vnstock 4.0.4 (VCI source), 2026-08-17

Four independent lines of evidence, all consistent, obtained by direct probing (not from
documentation) against the actually-installed library:

**(a) Price-band test — the strongest evidence.** HOSE enforces a ±7% daily band, so in an
*unadjusted* series any ex-date for a stock dividend or split must show a one-day move far
beyond that band. Full 2020–2025 daily series for four continuously-HOSE-listed tickers that all
had stock dividends in the period:

| Ticker | rows | min return | max return | breaches of ±7.5% |
|---|---|---|---|---|
| VCB | 1568 | −0.0699 | +0.0697 | **0** |
| MBB | 1568 | −0.0703 | +0.0702 | **0** |
| HPG | 1568 | −0.0702 | +0.0698 | **0** |
| SSI | 1568 | −0.0703 | +0.0708 | **0** |

Zero breaches across six years despite the dividends — impossible for an unadjusted series.

**(b) Specific ex-dates.** VCB's 49.5% stock dividend (2025-10-20 window) shows a −4.04% move,
not the ≈−33% an unadjusted series would show. ACB's 15% stock dividend (2024-05-23) shows
**+1.78%** — a rise, where an unadjusted series would show ≈−13%.

**(c) Cross-source agreement.** Two independent providers (VCI, KBS) agree to <0.2% on 2020
prices for VCB and HPG — both already back-adjusted to the same level, not raw historical
prices.

**(d) Anchoring.** VCB's most recent close (2026-08-17) is the *raw* traded price (58.2), while
its 2019-09-26 close is 34.38 — the series is back-adjusted with the **present** as the anchor.

**No parameter controls adjustment.** `grep -rn "adjust"` across the installed vnstock package
matches only the paid FMP connector; VCI, KBS and MSN expose no such control.

## Consequence — the re-anchoring problem, and how the pipeline answers it

Point (d) has a sharp implication the verdict alone does not capture: **every new corporate
action retroactively rewrites the ENTIRE history**, because the adjustment is anchored to the
present rather than fixed at ingestion time. An append-only, high-water-mark incremental fetch
would therefore splice two different adjustment bases at the seam between old and newly-fetched
rows, producing a fake jump exactly where the splice occurs.

The pipeline resolves this by **re-fetching the full window on every run** rather than
incrementing (`pipelines/ingestion/fetch.py`), which is safe because log returns are invariant
under a uniform rescale: `ln(a·P_t / a·P_{t-1}) == ln(P_t / P_{t-1})` for any constant `a`. Since
this model consumes only log returns, a full re-adjustment of the whole series changes every
level but no computed return, so re-fetching makes the re-anchoring completely harmless.

`pipelines/ingestion/normalize.py` accordingly sets `is_adjusted = True` on every `daily_bars`
record (previously hardcoded `False`, which was an actively false and dangerous claim — a
consumer trusting it would apply its own adjustment and double-adjust). The complementary fact
this boolean cannot carry — *adjusted as of when* — is carried by `fetched_at`: one timestamp,
shared by every record written in one run, recorded in the raw payload, the run's `FetchReport`,
and the `data_quality_reports` run-summary row.

## Real collection — 2020-12-01 to 2025-12-31, 100 tickers + VNINDEX

Run on 2026-08-17 via `python -m pipelines.ingestion.fetch --start 2020-12-01 --end 2025-12-31
--source VCI --storage local --throttle 5.0`. **101/101 symbols succeeded, 0 failures,
127,657 rows written.** VNINDEX produced 1,270 sessions. Four tickers (BAF, DXS, SSB, OCB) show
reduced coverage — all confirmed late HOSE arrivals in 2021, not data defects; P3's alignment
step must account for them. Chained into `pipelines.returns.build` immediately afterward:
100/100 tickers, 126,287 return rows, 1,269 index return rows — the real end-to-end proof that
the adjusted-close series produces a usable return series with no seam artefacts.
