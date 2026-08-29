"use client";

import { ChartSvg, ChartAxisLine, ChartTickLabel } from "./ChartSvg";
import { ChartAxisLabel } from "./ChartAxisLabel";
import { ChartLegend, type LegendItem } from "./ChartLegend";
import { ChartCrosshair, ChartTooltip, useChartHover } from "./ChartHover";
import { DASH, formatDate, formatDecimal, formatInt } from "@/components/market/format";
import styles from "./PriceHistoryChart.module.css";

/* SVG coordinate space (viewBox units). Upper region holds the close line, the
   lower region holds volume bars; the x-axis row sits below both. */
const X0 = 6;
const X1 = 634;
const PY0 = 8;
const PY1 = 150;
const VY0 = 166;
const VY1 = 224;
const XB = 236;

const nf0 = (v: number): string =>
  v.toLocaleString("en-US", { maximumFractionDigits: 0 });

/**
 * The minimum a bar must supply for this chart — the three fields it actually reads.
 *
 * Declared here rather than imported from `@/lib/api`, which is what this file used to do. A
 * presentational primitive that imports a response type is coupled to whichever API contract
 * happens to be current, and P8's rewrite of that contract broke this file for no reason
 * relating to charts. TypeScript is structural, so a richer OHLCV row from the P9 history route
 * satisfies this without a cast.
 */
export interface PriceBar {
  date: string;
  close: number;
  volume: number;
}

/**
 * Daily close-line + volume chart (UI_SPEC §5, CHART_SPEC §6, P12-S06B). Reads
 * typed daily bars only and maps their values into SVG coordinates — it computes
 * no indicators, averages, returns, or annotations, and fabricates no dates. The
 * close line is the subject series; volume bars are neutral. Bars whose close is
 * non-finite are omitted from the price line and endpoint (never substituted). The
 * final typed close is labelled at the endpoint (mono) only when it and its
 * coordinates are finite — no value is derived. Axes and units are explicit (price
 * in nghin dong -- the daily_bars convention, NOT dong -- volume in shares, x = sessions). The caller passes a unique, stable
 * `id` used for the accessible title/description association.
 */
export function PriceHistoryChart({
  id,
  bars,
  ticker,
  interval,
}: {
  id: string;
  bars: PriceBar[];
  ticker?: string;
  interval?: string;
}) {
  const n = bars.length;

  // Called before the empty-bars guard below: hooks cannot sit behind an early return, and the
  // hook is written to tolerate count === 0. The two plot bands (price / volume) are passed so the
  // hook can say which pane the pointer is over, keeping the crosshair and tooltip of each pane
  // from projecting into the other.
  const hover = useChartHover({
    count: n,
    x0: X0,
    x1: X1,
    vw: 640,
    vh: 240,
    panes: [
      { key: "price", top: PY0, bottom: PY1 },
      { key: "volume", top: VY0, bottom: VY1 },
    ],
  });

  if (n === 0) return null;

  const xFor = (i: number): number =>
    n <= 1 ? (X0 + X1) / 2 : X0 + (i / (n - 1)) * (X1 - X0);

  // Split finite closes into contiguous runs, breaking the sequence whenever a
  // non-finite close appears. Each run keeps its bars' original indexes (and thus
  // x-positions), so a run is never joined across a gap, x-spacing is never
  // compressed, and no value is substituted, filled, or interpolated.
  const runs: { i: number; close: number }[][] = [];
  let run: { i: number; close: number }[] = [];
  for (let i = 0; i < n; i++) {
    const c = bars[i].close;
    if (Number.isFinite(c)) {
      run.push({ i, close: c });
    } else if (run.length > 0) {
      runs.push(run);
      run = [];
    }
  }
  if (run.length > 0) runs.push(run);
  const hasClose = runs.length > 0;

  // Presentational min/max over all finite closes across every run; volume max is
  // independent of price geometry.
  let minC = Infinity;
  let maxC = -Infinity;
  for (const r of runs) {
    for (const p of r) {
      if (p.close < minC) minC = p.close;
      if (p.close > maxC) maxC = p.close;
    }
  }
  let maxV = 0;
  for (const b of bars) {
    if (b.volume > maxV) maxV = b.volume;
  }

  const priceY = (c: number): number =>
    maxC === minC
      ? (PY0 + PY1) / 2
      : PY1 - ((c - minC) / (maxC - minC)) * (PY1 - PY0);

  const barW = Math.max(0.5, Math.min(6, ((X1 - X0) / n) * 0.6));

  // dd/mm/yyyy, through the one formatter that does the conversion — the axis of a chart
  // is not a place to introduce a second date format on the same screen.
  const first = formatDate(bars[0].date);
  const last = formatDate(bars[n - 1].date);

  // Endpoint = the final typed bar, drawn only when its close and both derived
  // coordinates are finite. A non-finite final close draws no dot and no label,
  // and is not substituted by an earlier finite bar.
  const lastClose = bars[n - 1].close;
  const lastX = xFor(n - 1);
  const lastCloseFinite = Number.isFinite(lastClose);
  const lastY = lastCloseFinite ? priceY(lastClose) : NaN;
  const showEndpoint =
    lastCloseFinite && Number.isFinite(lastX) && Number.isFinite(lastY);
  const lastLabelY = lastY <= PY0 + 14 ? lastY + 12 : lastY - 6;

  const title = `${ticker ? `${ticker} — ` : ""}giá và khối lượng theo phiên`;
  const desc = `Giá đóng cửa và khối lượng qua ${n} phiên, từ ${first} đến ${last}.${
    showEndpoint ? ` Giá đóng cửa gần nhất ${nf0(lastClose)} nghìn đồng.` : ""
  }`;

  // The hovered bar, if any. A bar whose close is non-finite still has a volume worth reading, so
  // the tooltip shows the dash for price and the real figure for volume — the same rule the line
  // itself follows, where a gap is never filled in.
  const hoverBar = hover.index !== null ? bars[hover.index] : null;

  const legendItems: LegendItem[] = [
    { label: "Giá đóng cửa (nghìn đ)", color: "var(--accent)", variant: "line" },
    { label: "Khối lượng (cp)", color: "var(--data-neutral)", variant: "solid" },
  ];

  return (
    <div className={styles.wrap}>
      <p className={styles.range}>
        {first} &rarr; {last} &middot; {n} phiên
        {interval ? ` · ${interval}` : ""}
      </p>

      <ChartLegend items={legendItems} />

      <div className={styles.chartRow}>
        <div className={styles.yAxis}>
          <ChartAxisLabel axis="y" label="Giá" unit="nghìn đ" />
          <ChartAxisLabel axis="y" label="KL" unit="cp" />
        </div>
        <div
          {...hover.surfaceProps}
          className={`${hover.surfaceProps.className} ${styles.svgBox}`}
          aria-label={`${title}. Dùng phím mũi tên để đọc từng phiên.`}
        >
          <ChartSvg id={id} title={title} desc={desc} viewBox="0 0 640 240">
            <ChartAxisLine x1={X0} y1={PY0} x2={X1} y2={PY0} variant="grid" />
            <ChartAxisLine x1={X0} y1={PY1} x2={X1} y2={PY1} variant="axis" />
            <ChartAxisLine x1={X0} y1={VY1} x2={X1} y2={VY1} variant="axis" />

            {bars.map((b, i) => {
              const h = maxV > 0 ? (b.volume / maxV) * (VY1 - VY0) : 0;
              return (
                <rect
                  key={`v-${i}`}
                  x={xFor(i) - barW / 2}
                  y={VY1 - h}
                  width={barW}
                  height={h}
                  className={styles.volBar}
                />
              );
            })}

            {runs.map((r) =>
              r.length >= 2 ? (
                <polyline
                  key={`run-${r[0].i}-${r[r.length - 1].i}`}
                  points={r
                    .map(
                      (p) =>
                        `${xFor(p.i).toFixed(2)},${priceY(p.close).toFixed(2)}`,
                    )
                    .join(" ")}
                  className={styles.closeLine}
                />
              ) : null,
            )}
            {showEndpoint && (
              <>
                <circle
                  cx={lastX}
                  cy={lastY}
                  r={2.5}
                  className={styles.lastDot}
                />
                <ChartTickLabel x={lastX - 4} y={lastLabelY} anchor="end">
                  {nf0(lastClose)}
                </ChartTickLabel>
              </>
            )}

            {hasClose && (
              <ChartTickLabel x={X0} y={PY0 + 9} anchor="start">
                {nf0(maxC)}
              </ChartTickLabel>
            )}
            {hasClose && (
              <ChartTickLabel x={X0} y={PY1 - 2} anchor="start">
                {nf0(minC)}
              </ChartTickLabel>
            )}
            <ChartTickLabel x={X0} y={VY0 + 8} anchor="start">
              {nf0(maxV)}
            </ChartTickLabel>
            <ChartTickLabel x={X0} y={XB} anchor="start">
              {first}
            </ChartTickLabel>
            <ChartTickLabel x={X1} y={XB} anchor="end">
              {last}
            </ChartTickLabel>

            {hoverBar && (
              <ChartCrosshair
                x={xFor(hover.index as number)}
                segments={
                  hover.pane === "price"
                    ? [[PY0, PY1]]
                    : hover.pane === "volume"
                      ? [[VY0, VY1]]
                      : []
                }
                dots={
                  hover.pane === "price" && Number.isFinite(hoverBar.close)
                    ? [{ y: priceY(hoverBar.close), color: "var(--accent)" }]
                    : undefined
                }
              />
            )}
          </ChartSvg>

          {hoverBar && (
            <ChartTooltip
              left={hover.fracAt(hover.index as number)}
              top={
                hover.pane === "volume" ? VY0 / 240
                : hover.pane === "price" ? PY0 / 240
                : 0
              }
              title={formatDate(hoverBar.date)}
              rows={
                hover.pane === "volume"
                  ? [
                      {
                        label: "Khối lượng",
                        value: formatInt(hoverBar.volume),
                        color: "var(--data-neutral)",
                      },
                    ]
                  : [
                      {
                        label: "Giá đóng cửa",
                        value: Number.isFinite(hoverBar.close)
                          ? formatDecimal(hoverBar.close, 2)
                          : DASH,
                        color: "var(--accent)",
                      },
                    ]
              }
            />
          )}
        </div>
      </div>

      <ChartAxisLabel axis="x" label="Phiên giao dịch" className={styles.xAxis} />
    </div>
  );
}
