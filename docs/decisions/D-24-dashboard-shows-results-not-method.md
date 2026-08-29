# D-24 — The dashboard shows results, not method

**Status:** Decided, 2026-08-19 (P10)
**Affects:** every screen in `apps/web`; `p10-dashboard.md` S1–S3. Does **not** affect the API,
the model, the artifact, or any research result — no route changes and no number changes.

## Context

By the end of P9 the API published everything the model produces: the estimation window, `k`, `τ`,
`F̄(S)`, `n_under_tau`, the similarity measure, the artifact id, the full 15-step marginal-gain
curve, and per-group `f_j` / `rho2_mean` / `rho2_min`. The one screen that existed put nine of
those fields in a strip across the top of the market overview, above the prices.

The project owner, shown that strip, asked for the model-internal content to come out:

> *"tôi muốn bỏ đi các thông tin như là kiểu … mô hình này chạy như nào, thuật toán rồi độ đo là
> gì … người dùng thì họ thường quan tâm tới kết quả hơn, ví dụ như thay vì viết MA20 tính như
> nào thì họ chỉ cần biết chỉ số đó là MA20 thôi, vì đa phần người sử dụng sẽ có kiến thức về các
> chỉ số cơ bản."*

This is not a new position. `docs/03-temporal-design.md` §5 already states it:

> *"the report establishes that the method works, and the dashboard then applies it to current
> data for users who do not need the methodology re-argued."*

The screens had simply been built as though the reader were the examiner.

The complication is that two other documents pull the other way. `docs/04` §5 requires the
dashboard to show the universe as of the active run **and say so**; the parent plan requires a
provenance strip on every page. And the anchor screen is the thesis's own contribution — a defence
will ask to see `f_j` and `ρ²`.

## Alternatives

**(a) Leave the screens as built.** Every model figure visible at the top of every page. Honest,
auditable, and wrong for the stated audience: nine mathematical symbols stand between the reader
and the first price. It also fails `docs/03` §5 on its own terms.

**(b) Remove the model content entirely.** The simplest reading of the instruction. It breaks
`docs/04` §5 outright — with no as-of date on screen, a reader cannot tell that the anchor set was
estimated on 2025 while the prices beside it run to 2026-08. That gap is the single most
misleading thing about this dashboard if left unstated, and `docs/04` §5 exists precisely to
prevent it. It would also strip the anchor screen of the evidence the thesis rests on.

**(c) Demote, don't delete.** Chosen.

## Decision

Model content is **moved down one tier**, in three specific places:

1. **The provenance strip** becomes one line — `Dữ liệu đến {latest_session} · {n_tickers} mã ·
   {k} điểm neo` — with the estimation window, `τ`, `F̄(S)`, `n_under_tau`, the measure and the
   artifact id behind a `Chi tiết mô hình` disclosure. The first line alone satisfies `docs/04` §5:
   it names the universe and the as-of date.
2. **`/methodology` becomes `/about`**, one screen: what the system does in three or four
   sentences, the as-of date, the not-investment-advice disclaimer, and the run's parameter table.
   The archived `MethodologyScreen.tsx` — ~300 lines of "It does / It does not", seven limitations,
   two verbatim disclaimers and two charts drawn on fabricated data — is not restored.
3. **`/anchors` leads with members, sectors and price**, and keeps `size`, `f_j`, `rho2_mean`,
   `rho2_min` and `marginal_gain` in a secondary `Chỉ số nhóm` panel.

Alongside this, explanatory prose is removed from result screens: the gap notice under the
provenance strip, the six hint lines under the KPI cards, the caption under the movers table, and
the methodology sentence in the page metadata. A label names an indicator (`MA20`); it does not
define one.

## Why

The two audiences want different things and do not have to be served by the same tier of the same
page. A reader checking whether VCB is above its MA20 needs the label and the number. A reviewer
reproducing the result needs the artifact id and `F̄(S)`. Putting the second audience's content one
click away costs them a click; putting it first costs the first audience the screen.

Demotion is also what makes this reversible and honest. Nothing is thrown away — every field the
API publishes is still reachable from the UI, so the dashboard cannot be accused of hiding a figure
that would weaken it. That distinction is what separates (c) from (b).

## What this decision does not license

- **Removing a fact that is load-bearing for correctness.** `n_with_return` still has to be
  reachable, because `advancers + decliners + unchanged` is not a partition of the universe. Such
  facts move into tooltips and units; they do not disappear.
- **Rendering `null` as `0`.** Cutting explanatory text must not take the null-safety with it.
  D-13 already names this as the single most likely way a decision of this kind turns into a lie on
  screen, and it applies to every nullable column in every route.
- **Simplifying the sector-composition panel into an input.** It is external validation
  (`docs/02` §3g) — sector never entered the similarity matrix. A label that implies otherwise
  turns the one independent check this system has into a circular argument.
- **Implying `k = 10` was read off an elbow.** [[D-2]] is provisional and P5's evidence says there
  is no knee. Ten is the published cut, not a derived optimum.

## Reversing this

Reversal is presentational and touches no data path: expand the disclosure by default, and restore
the longer `/about`. The API already publishes every field either version would need, so nothing
in P10 forecloses a more methodological dashboard later.

Related: [[D-13]] (static dashboard) sets the floor this decision stops at — the NULL-not-zero rule
survives the trim. [[D-19]] (no foreign-flow data) is the same instinct applied to a data source:
show what the project measured, and do not apologise for the rest.
