# P11 execution plan — the dashboard redesign

> ## CLOSED — moved to `completed/` on 2026-08-29 (P12/F5)
>
> **Closed by:** merged to `main` (`decd4cb`, then `2fe5d3b` / `8aa92e5`) and live. The deployed
> page serves the Strata token layer, the top nav and the per-pane chart hover — confirmed by
> loading the deployed site on 2026-08-29.
>
> **Not to be confused with `anchor-model-operations.md` §P11**, which is a different P11 — the
> one-shot refresh runbook. That one is *not* closed; see `docs/RUNBOOK.md` §5 for what is still
> open in it.

---


**Started:** 2026-08-19
**Shape:** durable planned change (`docs/WORKFLOW.md` §2)
**Parent:** `anchor-model-operations.md`
**Predecessor:** `p10-dashboard.md` — DONE. Four screens shipped, verified live against the
deployed Render API (commits `328e561` … `9434c35`).

---

## Why

P10 built the screens. Reviewing them on a real display, the project owner named four
presentation defects and one omission. All of them are visual: no analytical behaviour, no API
contract, and no output of the model changes in this phase.

The owner's instruction, with three screenshots attached:

> *"đầu tiên về tổ hợp màu thì tôi nghĩ bạn nên dựa vào tổ hợp màu sau … các dòng chữ của
> dashboard diễn biến ngành bạn đang viết không phù hợp với cái ô chứa, nhiều chữ bị ghi đè sang
> ô bên cạnh … chế độ nền thì nên để mặc định là light, và chọn light của 1 trang thì các trang
> khác cũng tương tự … tại trang cổ phiếu thì tôi muốn dùng hover để có thể mà theo dõi được số
> liệu trên các chart … các frame của các trang … nên thành hàng ngang trên cùng vì nếu để như
> hiện tại thì frame hàng dọc bị trống đoạn dưới."*

The five items, each with what was actually wrong in the code:

1. **Palette.** The tokens were the Leiden-era slate/indigo set, inherited through P8 and P10.
   The owner supplied a replacement — *Strata*, a cool paper-light analytical palette with a
   steel-blue accent and deliberately muted directional colours.
2. **Treemap labels overflow.** `SectorTreemap` gated labels on `MIN_LABEL_W`/`MIN_LABEL_H`, i.e.
   on the *tile*, never on the *string*. SVG `<text>` neither wraps nor clips, so
   `"Bất động sản và Xây dựng"` overhung its tile by roughly 100 viewBox units and was then
   half-painted-over by the next tile's `<rect>`, reading as a label belonging to the wrong
   sector. Visible in all three screenshots.
3. **Theme.** Default was dark, hard-coded in `layout.tsx`. `ThemeToggle` mutated
   `document.documentElement.dataset.theme` and persisted nothing, so any full page load reverted
   to dark.
4. **Layout.** A 248px sticky sidebar held four nav items and then ~700px of empty column.
5. **No hover readout.** There was no `onMouseMove` / `onPointer*` anywhere in `apps/web/src`.
   The only per-point affordance was the browser's native `<title>` on treemap tiles.

**Definition of done.** The same four screens, same data, same guarantees, on a light-first
Strata surface: horizontal navigation, labels that cannot leave their tile at any viewport, and a
hover readout on all three charts — verified in the browser at three widths in both themes.

---

## Decisions taken

| # | Decision | Reasoning |
|---|---|---|
| S1 | **Adopt Strata by remapping the semantic aliases, not by renaming them.** The raw ramps (`--ink-*`, `--blue-*`, `--teal-*`, `--pos-*`, `--neg-*`, `--amber-*`, `--cluster-*`) are added to `:root`; every existing alias (`--canvas`, `--text-1`, `--accent`, `--data-pos`, …) is re-expressed in terms of them | ~500 lines of CSS Modules and every `var(--*)` in every component keep working untouched. Renaming aliases to Strata's own names would have been a rewrite of the whole style layer to achieve the identical rendered result |
| S2 | **Keep both themes. Light is the default; the dark ramp is *authored*, not supplied.** Persisted in `localStorage` and applied before first paint | Strata defines light only. Simply defaulting to light and leaving the old slate dark block would leave the two themes visibly unrelated. Two Strata colours cannot survive a dark canvas untouched — see S3 |
| S3 | **`--accent` in dark is `--blue-300 #76A1CC`, not `--blue-500`.** `--data-pos` / `--data-neg` in dark are authored lifts of the Strata pair | `--blue-500 #2F5E8E` against `--ink-950 #0B0F14` is ≈2.4:1 — it fails AA outright and is unreadable as link or active-tab colour. `--pos-500` / `--neg-500` sit near 4:1, marginal for 1.2–1.6px chart strokes. This is the same move P10 made and recorded at its `globals.css:178` comment |
| S4 | **P10 S6 is preserved, not overturned.** Green up / red down survives the re-tint | P10 S6 reassigned `--data-pos` / `--data-neg` from a "non-emotional" steel-blue/clay pair to green/red, because the coloured quantity here is a price change read against every other board a Vietnamese user opens. Strata's directional pair is *also* green/clay-red (`--pos-500 #2E7D5B`, `--neg-500 #B0573F`), only muted. Nothing about S6 is reversed; this is a change of tint within the same semantics. Recorded explicitly so a later reader does not mistake the muting for a reversal |
| S5 | **Treemap labels become HTML overlaid on the SVG, not SVG `<text>`.** One absolutely-positioned `<div>` per tile, placed in percent, with `overflow: hidden` | Makes the reported defect *structurally* impossible rather than merely unlikely: a label physically cannot paint outside its own box. It also buys real `text-overflow: ellipsis` and line clamping, which SVG `<text>` has no equivalent for — the alternatives were per-tile `clipPath` (clips, but still cannot wrap) or hand-measured truncation (a font-metrics estimate that is wrong for Vietnamese diacritics) |
| S6 | **Still no charting library.** Hover is built on the existing hand-drawn SVG primitives | P10 S5 unchanged. A crosshair and a tooltip are ~200 lines against primitives that already consume the design tokens; a library would be the largest dependency in a package that has three, and would still have to be restyled onto these tokens |
| S7 | **Hover covers all three charts, including the treemap.** The treemap's native `<title>` is replaced by `aria-label` + the same custom tooltip | Half-covering it would leave the technical chart — the densest numbers on the site, four panes of MA/RSI/MACD — as the one place a value cannot be read. Keeping `<title>` alongside a custom tooltip would show two tooltips on one hover |

No decision record (`docs/decisions/`) is written by this phase: nothing here changes what the
system computes, stores, or publishes.

---

## What is already true, and must not be re-derived

- **No Tailwind, no CSS-in-JS.** `globals.css` (tokens + reset + shell) plus CSS Modules per
  component. Rule stated at `globals.css:4`: only `var(--*)` in component styles, never a
  hardcoded hex.
- **`output: "export"`** (`next.config.ts`) — the HTML is static, every screen is `"use client"`,
  and detail views ride on query strings inside `<Suspense>`. A `useEffect`-only theme restore
  would therefore flash on every full load.
- **`components/market/format.ts` is the only place** fraction→percent conversion and TZ-safe
  date parsing happen. It has tests. Tooltips reuse it; they do not format anything themselves.
- **`components/charts/treemap.ts`** implements squarified layout (Bruls/Huizing/van Wijk) and is
  unit-tested. The overflow defect is in the *label renderer*, not the geometry.
- **`apps/web/out/`** is committed build output. Never hand-edited; regenerated by `npm run build`.
- **`docs/product/DESIGN_SYSTEM.md`, cited at `globals.css:3`, does not exist** anywhere in the
  repo — a citation inherited from the Leiden codebase. Repointed at this file.

---

## Progress

### P11.1 — The Strata token layer — **DONE**

- `globals.css` §2 rewritten: Strata raw ramps in their own block, then every semantic alias
  expressed as `var(--ramp-n)`.
- §3 (`[data-theme="dark"]`) authored from the `--ink-*` scale, with the two lifted families of
  S3 carrying a comment naming the measured contrast.
- `--chart-ma20` / `--chart-ma50` / `--chart-rsi` promoted out of
  `CombinedIndicatorChart.module.css` into themed tokens — the last three hardcoded hexes in the
  component layer.
- `color-scheme: dark light` → `light dark`.

### P11.2 — Light default, persisted — **DONE**

- `layout.tsx`: `data-theme="light"`, plus a pre-paint inline script reading
  `localStorage.theme`, wrapped in `try/catch` so a blocked storage degrades to the light already
  in the markup, and `suppressHydrationWarning` on `<html>` — added after verification caught the
  mismatch the script necessarily causes (see Validation).
- `ThemeToggle.tsx`: initial state `light`, writes `localStorage` on toggle. Its label is now
  Vietnamese ("Sáng"/"Tối") like the rest of the chrome, and names the theme it switches *to*.

### P11.3 — Horizontal navigation — **DONE**

- `AppChrome.tsx`: sidebar grid replaced by a two-row sticky header — brand + theme toggle, then
  a tab bar — with the page `<h1>` moved into the content well.
- `globals.css` §10–12 and the `@media (max-width: 900px)` block rewritten to match;
  `--layout-sidebar` deleted.
- `NAV_ITEMS`, `PAGE_META`, the `trailingSlash` normalisation and the `isActive` prefix match are
  carried over unchanged, so `/tickers/?t=VCB` still highlights its tab.

### P11.4 — Chart hover — **DONE**

- New `components/charts/ChartHover.tsx` + `.module.css`: `useChartHover` (pointer + keyboard),
  `ChartCrosshair`, `ChartTooltip` (HTML, not SVG).
- Wired into `PriceHistoryChart`, `CombinedIndicatorChart` (one crosshair across all four panes),
  and `SectorTreemap`.

### P11.5 — Treemap labels — **DONE**

- HTML overlay layer, percent-positioned, `overflow: hidden` per tile, four-tier font sizing from
  measured tile pixels via a `ResizeObserver`.
- `MIN_LABEL_W` / `MIN_LABEL_H` deleted, superseded by the tier table.

---

## Validation

Recorded the way P10's table was: **measured** and **not attempted** kept apart. This repository
has no CI and no UI test runner. The visual checks below were performed against the running dev
server on committed fixtures (`.env.local` set aside so `lib/api.ts` resolves to `kind: "mock"`,
then restored), and the geometry ones were *measured in the live DOM* with `getBoundingClientRect`
rather than judged by eye — see the note under the table for why.

| Check | Result |
|---|---|
| `npx tsc --noEmit`, `npx eslint src` | **PASS** — both clean |
| `npm run test` (vitest: `treemap`, `format`, `apiConfig`) | **PASS** — 29 tests, 3 files. `treemap.test.ts` green confirms P11.5 changed label rendering only, not the squarified geometry |
| `npm run build` (static export compiles with the new client hooks) | **PASS** — 7 pages exported. `out/index.html` ships `data-theme="light"` and one inline theme script; emitted CSS carries `--blue-500:#2f5e8e`, `--accent:var(--blue-500)` (light) and `--accent:var(--blue-300)` (dark) |
| No hardcoded hex anywhere in the component layer | **PASS, grepped** — zero `#rrggbb` matches across `apps/web/src` outside `globals.css`. The three `--chart-*` values were the last ones |
| `--layout-sidebar` and the sidebar rules gone from the bundle | **PASS, grepped** — 0 matches for `layout-sidebar` in all three emitted stylesheets |
| First load is light; the choice survives a hard reload | **PASS, measured** — fresh load `data-theme="light"`, canvas `rgb(245,247,250)`. Toggled to dark, navigated `/tickers/?t=VCB` → `/anchors/`, hard-reloaded: `data-theme="dark"`, canvas `rgb(11,15,20)`, `localStorage.theme === "dark"` |
| **No treemap label crosses a tile boundary** (the reported defect) | **PASS, measured at four widths** — 1280px (wrap 1216), 900 (885), 394 (379), 375 (343). At every width each label box was contained in its own tile's rect and overlapped **0** other tiles, and `scrollWidth === clientWidth` on every label (nothing overflowing its own box either). `"Bất động sản và Xây dựng"` — the string in the screenshots — sits inside tile 1 at all four |
| Tier degradation works | **PASS, measured** — at 1280px, 6 of 7 tiles labelled; the 7th (23.8 viewBox units → 45px wide, below the 48px floor) renders no label and answers on hover only |
| Hover reads the correct session | **PASS, measured** — price chart at 25%: `26/11/2025`, close `30,14`, volume `2.700.828`, crosshair 2 segments + 1 dot. Indicator chart at 88%: `07/07/2026`, all 10 rows, crosshair 4 segments + 3 dots |
| A null indicator shows `—`, never `0` | **PASS, measured** — session 1 (`01/09/2025`, before any MA/RSI/MACD window closes): MA20, MA50, BB trên, BB dưới, RSI(14), MACD, Signal, Histogram all `—`, while close `21,42` and volume `8.550.956` render as real figures |
| Tooltip stays inside the chart on the right-hand side | **PASS, measured** — at 88% the panel flips; right edge 1064px against a 1280px viewport |
| Keyboard parity | **PASS, measured** — surface focusable (`tabIndex 0`, aria-label naming the arrow keys). `End` → `18/08/2026`, `ArrowLeft` → `17/08/2026` |
| Treemap hover replaced the native `<title>` cleanly | **PASS, measured** — custom tooltip shows sector, % thay đổi, GT giao dịch, số mã, mã có TSSL, positioned inside the wrap; `document.querySelectorAll('[treemapWrap] title').length === 0`, so no double tooltip. Tile `aria-label` carries the same content for screen readers |
| Tab bar: one row, scrollable when narrow, correct active tab | **PASS, measured** — at 375px the bar is 39px tall (one row) with `scrollWidth 449 > clientWidth 375`, and `document.body.scrollWidth === window.innerWidth` (the page itself does not scroll sideways). `/tickers/?t=VCB` highlights "Cổ phiếu"; `/anchors/` highlights "Điểm neo" |
| Contrast measured in both themes | **PASS with one documented exception** — computed from the live DOM, each token against its own `--canvas`: **light** `--data-pos` 6.62, `--data-neg` 6.33, `--accent` 6.29, `--accent-text`/card 8.61, `--text-1` 17.91, `--text-3` 5.70. **dark** 6.61 / 6.78 / 7.08 / 10.30 / 17.91 / 7.79. All clear AA (4.5:1). Exception below |
| Zero console errors on all four routes | **PASS** — in a fresh tab, `/`, `/tickers/?t=VCB`, `/anchors/?a=VCB`, `/about/`: no errors. Reached only after fixing the defect below |

### One defect found during verification, and fixed

**Hydration mismatch on `<html data-theme>`.** The pre-paint script rewrites the attribute before
React hydrates, so React reported the difference between the exported `"light"` and the restored
`"dark"` as an error on every load with dark stored. Fixed with `suppressHydrationWarning` on the
`<html>` element in `layout.tsx` — the prop exists for exactly this case, and it scopes to that
element's own attributes, so children are still diffed normally. Re-verified in a clean tab:
zero errors.

### The one contrast exception, stated rather than buried

`--text-4` measures **3.50:1** in light and **3.14:1** in dark. It is Strata's `--text-subtle`
(`--ink-400`), used for eyebrows, uppercase micro-labels and chart tick labels, and at those sizes
AA wants 4.5:1. Two things are true and both belong in the record: it is a **deliberate value from
the supplied palette**, and it is a **large improvement** on what P10 shipped, where the same role
resolved to `#94a3b8` on `#f8fafc` ≈ 2.6:1. Left at the palette's value; raising it would collide
with `--text-3` (`--ink-500`) and flatten the two tiers into one. Worth revisiting if tick labels
ever become primary reading rather than reference marks.

### Not attempted

- **No visual-regression tooling**, and none added. There is no baseline to diff against.
- **Wide-viewport *appearance* was not verified by image.** The browser preview pane in this
  environment is ~591px wide, so screenshots could not show a 1280px layout. Every wide-viewport
  claim in the table above is therefore a *measurement* (`getBoundingClientRect`, computed styles,
  contrast computed from resolved token values), not an eyeball check. Screenshots at pane width
  did confirm the light and dark surfaces, the tab bar, and label containment on a narrow screen.
- **Not run against the live Render API.** `NEXT_PUBLIC_API_BASE_URL` points at `localhost:8000`
  on this machine and nothing was listening. Nothing in this phase touches the API or the response
  types, so mock fixtures exercise the same render path; P10 already verified the live path.

---

## Out of scope

- Any change to `pipelines/`, `services/api/`, or the database.
- Any change to what a screen *says* — the P10/D-24 editorial line stands; this phase changes how
  it looks, not what is on it.
- `charts/treemap.ts`, `market/format.ts`, `lib/api.ts`, `lib/mock.ts`, `hooks/`, and every screen
  component. The redesign is confined to the token layer, the shell, and three chart renderers.
