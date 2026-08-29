# D-17 — Sector label source: vnstock industries plus a curated bucket table

**Status:** Decided, 2026-08-18 (recorded retroactively — the choice was made and acted on in P6)
**Affects:** `pipelines/universe/sync.py` (`_INDUSTRY_TO_SECTOR`, `SECTOR_VOCABULARY`);
`stocks.sector` / `stocks.industry`; `data/reference/sector_map.csv`;
`v_sector_performance`, `v_top_movers`, `v_anchor_group_detail`, `model_groups.sector_composition`.

## Context

`docs/02` §3g is explicit that sector labels **never enter the similarity matrix or the
objective**. They are attached to the *output*, for display and for external validation: showing
that return-derived anchor groups line up with sectors is evidence the method found real
structure. Feeding sectors in would make that evidence circular.

So the labels are needed, and their accuracy matters for the validation argument — but nothing
in the model depends on them, which is what makes a pragmatic source acceptable.

Two things were wanted and could not both come from one call:

* a **fine** label for the ticker-detail page ("Ngân hàng", "Chế biến Thủy sản"),
* a **coarse** bucket for the treemap and for group composition, small enough that a nine-tile
  treemap is readable.

`vnstock`'s coarse ICB hierarchy (`Listing().industries_icb()`) is **not implemented** by the KBS
source this install uses — it raises `NotImplementedError` naming exactly that.

## Alternatives

**(a) Fine labels only, treemap tiles per fine label.** No curation, no hand-maintained table.
Produces a treemap of ~30–40 tiles over 85 tickers, most holding one or two names, which is a
scatter plot with rectangles.

**(b) Hand-assign a sector to each of the 85 tickers.** Complete control. 85 judgements, none of
them checkable by anyone reviewing the thesis, and the table has to be revisited every time the
universe changes — which [[D-16]] says it will.

**(c) A paid or scraped ICB feed.** Correct by construction, and a new external dependency plus a
credential for data that is explicitly display-only.

**(d) vnstock's fine labels plus a small curated fine→coarse table.** Chosen.

## Decision

Two steps, two columns:

1. `Listing().symbols_by_industries()` gives each ticker a fine `industry_name`. This lands in
   **`stocks.industry`**.
2. A hand-curated table of ~20 entries maps each fine label to one of nine Vietnamese buckets
   (`_INDUSTRY_TO_SECTOR`, validated against `SECTOR_VOCABULARY`). This lands in
   **`stocks.sector`**.

A ticker vnstock has no label for, or whose fine label is not in the curated table, gets **both
fields NULL** — never a guess. `data/reference/sector_map.csv` records every ticker's fine label,
its mapped bucket, and where each came from, so the curation is reviewable as a file rather than
as code.

## Why ~20 curated entries and not 85

Curating ~20 industry labels is a judgement a reader can check by reading twenty lines. Curating
85 tickers is a judgement nobody will check. The table also survives a universe change: adding
tickers usually adds no new fine labels at all, and when it does, the gap surfaces as a NULL
sector rather than as a silent misfiling.

## Result on the live universe

vnstock matched **85/85 with zero misses**; the CSV fallback path exists but was not exercised.
Nine buckets, no NULL sector. The distribution is uneven — 24 tickers in the largest bucket, 2 in
the smallest two — which is a property of the universe, not of this decision; see [[D-16]].

## NULL is a rendering choice, not a data choice

`stocks.sector` stores NULL and the views pass NULL through (`v_sector_performance` groups it as
its own NULL row). Displaying it as "Khác" belongs at the display edge. Writing "Khác" into the
column would make an absent label indistinguishable from a label that genuinely means "other".
