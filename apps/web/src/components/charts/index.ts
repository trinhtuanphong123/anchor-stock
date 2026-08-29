/**
 * Shared, dependency-free chart primitives (P12-S06A). Presentational and data-agnostic —
 * no hooks, no data reads, no domain charts.
 *
 * P8 archived the three Leiden-specific charts that used to be re-exported here
 * (`EdgeStrengthChart`, `DirectedTimingChart`, `OutcomeQuartileChart`) along with the screens
 * that consumed them. What remains is contract-neutral and is what P10 composes the anchor
 * model's charts from.
 */
export { ChartFrame } from "./ChartFrame";
export { ChartCaption } from "./ChartCaption";
export { ChartLegend } from "./ChartLegend";
export type { LegendItem } from "./ChartLegend";
export {
  ChartSvg,
  ChartAxisLine,
  ChartTickLabel,
  ChartPlotRegion,
} from "./ChartSvg";
export { ChartAxisLabel } from "./ChartAxisLabel";
export { ChartNotice } from "./ChartNotice";
export { PriceHistoryChart } from "./PriceHistoryChart";
export type { PriceBar } from "./PriceHistoryChart";
