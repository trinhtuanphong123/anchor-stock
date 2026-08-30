/**
 * The repeated blocks, expressed once against the design system's global `as-*` classes.
 *
 * Presentational only: no hooks, no data reads, no domain knowledge beyond the display rules the
 * product cannot break (units named at the point of display, colour on a number meaning price
 * direction and nothing else, a missing value never drawn as a zero).
 *
 * Form lives in `styles/ds/`; these files contribute no CSS of their own. A screen still owns its
 * own layout — which columns, what order, how the grid divides — in a CSS Module beside it.
 */
export { Panel, DocPanel } from "./Panel";
export { KpiCard, KpiGrid } from "./KpiCard";
export { StatBlock } from "./StatBlock";
export { BreadthBar } from "./BreadthBar";
export { CompositionBars } from "./CompositionBars";
export type { CompositionRow } from "./CompositionBars";
export { DataTable } from "./DataTable";
export type { DataTableColumn, DataTableRow } from "./DataTable";
export { Badge } from "./Badge";
export { Chip, ChipRow } from "./Chip";
export { RangeTabs } from "./RangeTabs";
export type { RangeTabOption } from "./RangeTabs";
export { SegmentedControl } from "./SegmentedControl";
export type { SegmentOption } from "./SegmentedControl";
export { SearchInput } from "./SearchInput";
export { Disclosure } from "./Disclosure";
export { DefinitionList } from "./DefinitionList";
export type { DefinitionItem } from "./DefinitionList";
export { toneClass } from "./tone";
export type { Tone } from "./tone";
