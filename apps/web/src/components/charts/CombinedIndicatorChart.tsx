"use client";

import type { IndicatorPoint } from "@/lib/api";
import { DASH, formatDate, formatDecimal, formatInt } from "@/components/market/format";
import { ChartLegend, type LegendItem } from "./ChartLegend";
import { ChartCrosshair, ChartTooltip, useChartHover, type TooltipRow } from "./ChartHover";
import styles from "./CombinedIndicatorChart.module.css";

/**
 * "Biểu đồ kỹ thuật tổng hợp" — four panes sharing one time axis.
 *
 * Price (close, MA20, MA50, Bollinger band) · RSI with its 70/50/30 guides · MACD with its signal
 * and histogram · volume against its own 20-session average.
 *
 * Three rules this chart follows, all of them the same rule in different clothes:
 *
 *  1. **A null is a gap, never a zero.** Every series is drawn as contiguous runs of finite
 *     points, broken wherever a value is missing. `sma_200` is null for the first 199 sessions of
 *     any window and `rsi_14` for the first 14 — joining across those gaps would draw a line the
 *     data does not contain, and substituting 0 would draw a crash that never happened.
 *  2. **Each pane scales to its own finite values.** A pane whose series are entirely null renders
 *     its frame and nothing else rather than collapsing to a flat line at the bottom.
 *  3. **The x-positions come from the index, not the date.** Sessions are equally spaced, so a
 *     holiday does not stretch the axis, and every pane's column i is the same session.
 *
 * Hand-drawn SVG rather than a charting library (P10 S5): the primitives beside this file already
 * consume the design tokens and theme correctly in light and dark, which any library would have to
 * be restyled to do anyway.
 */

const VW = 640;

/** Pane geometry in viewBox units: [top, bottom] of each plot area. */
const PANES = {
  price: [8, 208],
  rsi: [236, 296],
  macd: [324, 384],
  volume: [412, 462],
} as const;

const VH = 500;
const X0 = 44;
const X1 = 634;

type Accessor = (p: IndicatorPoint) => number | null;

interface SeriesSpec {
  key: string;
  label: string;
  value: Accessor;
  color: string;
  width?: number;
  dash?: string;
}

const PRICE_SERIES: SeriesSpec[] = [
  { key: "close", label: "Giá đóng cửa", value: (p) => p.close, color: "var(--accent)", width: 1.6 },
  { key: "sma_20", label: "MA20", value: (p) => p.sma_20, color: "var(--chart-ma20)", width: 1.2 },
  { key: "sma_50", label: "MA50", value: (p) => p.sma_50, color: "var(--chart-ma50)", width: 1.2 },
  {
    key: "bb_upper_20",
    label: "Bollinger",
    value: (p) => p.bb_upper_20,
    color: "var(--chart-band)",
    width: 1,
    dash: "3 3",
  },
  {
    key: "bb_lower_20",
    label: "",
    value: (p) => p.bb_lower_20,
    color: "var(--chart-band)",
    width: 1,
    dash: "3 3",
  },
];

const MACD_SERIES: SeriesSpec[] = [
  { key: "macd", label: "MACD", value: (p) => p.macd, color: "var(--accent)", width: 1.3 },
  {
    key: "macd_signal",
    label: "Signal",
    value: (p) => p.macd_signal,
    color: "var(--chart-ma50)",
    width: 1.1,
  },
];

/** Contiguous runs of finite points. A gap ends a run; nothing is interpolated across it. */
function runsOf(points: IndicatorPoint[], value: Accessor): Array<Array<{ i: number; v: number }>> {
  const runs: Array<Array<{ i: number; v: number }>> = [];
  let run: Array<{ i: number; v: number }> = [];
  points.forEach((p, i) => {
    const v = value(p);
    if (v !== null && Number.isFinite(v)) {
      run.push({ i, v });
    } else if (run.length > 0) {
      runs.push(run);
      run = [];
    }
  });
  if (run.length > 0) runs.push(run);
  return runs;
}

/** Finite min/max across several accessors, or null when every value is missing. */
function extentOf(
  points: IndicatorPoint[],
  accessors: Accessor[],
): { min: number; max: number } | null {
  let min = Infinity;
  let max = -Infinity;
  for (const p of points) {
    for (const a of accessors) {
      const v = a(p);
      if (v !== null && Number.isFinite(v)) {
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
  }
  if (min === Infinity) return null;
  if (min === max) {
    // A flat series still needs a band to sit in, or it divides by zero below.
    const pad = Math.abs(min) * 0.05 || 1;
    return { min: min - pad, max: max + pad };
  }
  return { min, max };
}

const fmt = (v: number, digits = 2): string =>
  v.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function CombinedIndicatorChart({
  id,
  points,
  ticker,
}: {
  id: string;
  points: IndicatorPoint[];
  ticker: string;
}) {
  const n = points.length;

  // Before the guard: hooks cannot sit behind an early return.
  const hover = useChartHover({
    count: n,
    x0: X0,
    x1: X1,
    vw: VW,
    vh: VH,
    panes: [
      { key: "price", top: PANES.price[0], bottom: PANES.price[1] },
      { key: "rsi", top: PANES.rsi[0], bottom: PANES.rsi[1] },
      { key: "macd", top: PANES.macd[0], bottom: PANES.macd[1] },
      { key: "volume", top: PANES.volume[0], bottom: PANES.volume[1] },
    ],
  });

  if (n === 0) return null;

  const xFor = (i: number): number =>
    n <= 1 ? (X0 + X1) / 2 : X0 + (i / (n - 1)) * (X1 - X0);

  /** Build a y-mapper for one pane, or null when the pane has nothing finite to draw. */
  const scaleFor = (
    pane: readonly [number, number],
    accessors: Accessor[],
    forced?: { min: number; max: number },
  ) => {
    const ext = forced ?? extentOf(points, accessors);
    if (!ext) return null;
    const [top, bottom] = pane;
    return (v: number) => bottom - ((v - ext.min) / (ext.max - ext.min)) * (bottom - top);
  };

  const priceY = scaleFor(PANES.price, PRICE_SERIES.map((s) => s.value));
  const priceExt = extentOf(points, PRICE_SERIES.map((s) => s.value));
  // RSI is bounded [0,100] by definition, so its axis is fixed rather than data-driven — the
  // 70/30 guides are only meaningful against a fixed scale.
  const rsiY = scaleFor(PANES.rsi, [(p) => p.rsi_14], { min: 0, max: 100 });
  const macdY = scaleFor(PANES.macd, [
    ...MACD_SERIES.map((s) => s.value),
    (p) => p.macd_hist,
  ]);
  const macdExt = extentOf(points, [...MACD_SERIES.map((s) => s.value), (p) => p.macd_hist]);
  const volExt = extentOf(points, [(p) => p.volume, (p) => p.volume_sma_20]);

  const path = (runs: Array<Array<{ i: number; v: number }>>, y: (v: number) => number): string =>
    runs
      .filter((r) => r.length >= 2)
      .map(
        (r) =>
          "M " +
          r.map((p) => `${xFor(p.i).toFixed(2)},${y(p.v).toFixed(2)}`).join(" L "),
      )
      .join(" ");

  const first = formatDate(points[0].bar_date);
  const last = formatDate(points[n - 1].bar_date);

  const legend: LegendItem[] = [
    ...PRICE_SERIES.filter((s) => s.label !== "").map((s) => ({
      label: s.label,
      color: s.color,
      variant: "line" as const,
    })),
    { label: "RSI(14)", color: "var(--chart-rsi)", variant: "line" as const },
    { label: "MACD", color: "var(--accent)", variant: "line" as const },
    { label: "Khối lượng", color: "var(--data-neutral)", variant: "solid" as const },
  ];

  const barW = Math.max(0.5, Math.min(5, ((X1 - X0) / n) * 0.7));
  const [volTop, volBottom] = PANES.volume;

  // --- Hover readout -------------------------------------------------------
  // Rule 3 guarantees column i is the same session in every pane, but the readout belongs to the
  // pane under the cursor only — a crosshair spanning all four panes read as the pane below being
  // "synced" to the one hovered. `num` keeps rule 1 intact at the readout: a null is a dash,
  // never a zero and never the previous session's value carried forward.
  const hp = hover.index !== null ? points[hover.index] : null;
  const num = (v: number | null | undefined, digits = 2): string =>
    v === null || v === undefined || !Number.isFinite(v) ? DASH : formatDecimal(v, digits);

  const pane = hover.pane;

  const hoverRows: TooltipRow[] =
    hp === null || pane === ""
      ? []
      : pane === "price"
        ? [
            { label: "Giá đóng cửa", value: num(hp.close), color: "var(--accent)" },
            { label: "MA20", value: num(hp.sma_20), color: "var(--chart-ma20)" },
            { label: "MA50", value: num(hp.sma_50), color: "var(--chart-ma50)" },
            { label: "BB trên", value: num(hp.bb_upper_20), color: "var(--chart-band)" },
            { label: "BB dưới", value: num(hp.bb_lower_20), color: "var(--chart-band)" },
          ]
        : pane === "rsi"
          ? [
              { label: "RSI(14)", value: num(hp.rsi_14, 1), color: "var(--chart-rsi)" },
            ]
          : pane === "macd"
            ? [
                { label: "MACD", value: num(hp.macd, 3), color: "var(--accent)" },
                { label: "Signal", value: num(hp.macd_signal, 3), color: "var(--chart-ma50)" },
                { label: "Histogram", value: num(hp.macd_hist, 3) },
              ]
            : [
                {
                  label: "Khối lượng",
                  value: hp.volume === null || !Number.isFinite(hp.volume)
                    ? DASH
                    : formatInt(hp.volume),
                  color: "var(--data-neutral)",
                },
              ];

  /** Dot for the hovered pane's series, when it has a value at the hovered session. */
  const hoverDot =
    hp === null
      ? null
      : pane === "price" && priceY && hp.close !== null && Number.isFinite(hp.close)
        ? { y: priceY(hp.close), color: "var(--accent)" }
        : pane === "rsi" && rsiY && hp.rsi_14 !== null && Number.isFinite(hp.rsi_14)
          ? { y: rsiY(hp.rsi_14), color: "var(--chart-rsi)" }
          : pane === "macd" && macdY && hp.macd !== null && Number.isFinite(hp.macd)
            ? { y: macdY(hp.macd), color: "var(--accent)" }
            : null;

  // The hovered pane's band, for the crosshair. `pane` is never null when `panes` is non-empty.
  const crossSegments =
    pane === "price"
      ? [PANES.price]
      : pane === "rsi"
        ? [PANES.rsi]
        : pane === "macd"
          ? [PANES.macd]
          : pane === "volume"
            ? [PANES.volume]
            : [];

  return (
    <div className={styles.wrap}>
      <ChartLegend items={legend} />

      <div
        {...hover.surfaceProps}
        aria-label={`${ticker} — biểu đồ kỹ thuật tổng hợp. Dùng phím mũi tên để đọc từng phiên.`}
      >
      <svg
        className={styles.svg}
        viewBox={`0 0 ${VW} ${VH}`}
        role="img"
        aria-labelledby={`${id}-title`}
      >
        <title id={`${id}-title`}>
          {`${ticker} — biểu đồ kỹ thuật tổng hợp qua ${n} phiên, từ ${first} đến ${last}`}
        </title>

        {/* --- Price pane --- */}
        <PaneFrame label="Giá" top={PANES.price[0]} bottom={PANES.price[1]} />
        {priceExt && priceY && (
          <>
            <AxisValue y={PANES.price[0] + 9} text={fmt(priceExt.max)} />
            <AxisValue y={PANES.price[1] - 2} text={fmt(priceExt.min)} />
            {PRICE_SERIES.map((s) => (
              <path
                key={s.key}
                d={path(runsOf(points, s.value), priceY)}
                fill="none"
                stroke={s.color}
                strokeWidth={s.width ?? 1.2}
                strokeDasharray={s.dash}
                className={styles.line}
              />
            ))}
          </>
        )}

        {/* --- RSI pane. The 70/50/30 lines are conventional reading levels, not thresholds
                this system computed — drawn as guides, labelled with their numbers only. --- */}
        <PaneFrame label="RSI(14)" top={PANES.rsi[0]} bottom={PANES.rsi[1]} />
        {rsiY && (
          <>
            {[70, 50, 30].map((level) => (
              <g key={level}>
                <line
                  x1={X0}
                  y1={rsiY(level)}
                  x2={X1}
                  y2={rsiY(level)}
                  className={level === 50 ? styles.guideFaint : styles.guide}
                />
                <text x={X0 - 6} y={rsiY(level) + 3} className={styles.axisValue} textAnchor="end">
                  {level}
                </text>
              </g>
            ))}
            <path
              d={path(runsOf(points, (p) => p.rsi_14), rsiY)}
              fill="none"
              stroke="var(--chart-rsi)"
              strokeWidth={1.3}
              className={styles.line}
            />
          </>
        )}

        {/* --- MACD pane --- */}
        <PaneFrame label="MACD" top={PANES.macd[0]} bottom={PANES.macd[1]} />
        {macdY && macdExt && (
          <>
            <AxisValue y={PANES.macd[0] + 9} text={fmt(macdExt.max)} />
            <AxisValue y={PANES.macd[1] - 2} text={fmt(macdExt.min)} />
            {/* Histogram bars hang from the zero line; a null histogram draws no bar at all. */}
            {points.map((p, i) => {
              const h = p.macd_hist;
              if (h === null || !Number.isFinite(h)) return null;
              const zero = macdY(0);
              const y = macdY(h);
              return (
                <rect
                  key={`mh-${i}`}
                  x={xFor(i) - barW / 2}
                  y={Math.min(zero, y)}
                  width={barW}
                  height={Math.abs(zero - y)}
                  fill={h >= 0 ? "var(--data-pos)" : "var(--data-neg)"}
                  opacity={0.45}
                />
              );
            })}
            <line x1={X0} y1={macdY(0)} x2={X1} y2={macdY(0)} className={styles.guideFaint} />
            {MACD_SERIES.map((s) => (
              <path
                key={s.key}
                d={path(runsOf(points, s.value), macdY)}
                fill="none"
                stroke={s.color}
                strokeWidth={s.width ?? 1.2}
                className={styles.line}
              />
            ))}
          </>
        )}

        {/* --- Volume pane --- */}
        <PaneFrame label="KL" top={PANES.volume[0]} bottom={PANES.volume[1]} />
        {volExt && (
          <>
            {points.map((p, i) => {
              const v = p.volume;
              if (v === null || !Number.isFinite(v)) return null;
              const h = (v / volExt.max) * (volBottom - volTop);
              return (
                <rect
                  key={`vol-${i}`}
                  x={xFor(i) - barW / 2}
                  y={volBottom - h}
                  width={barW}
                  height={h}
                  className={styles.volBar}
                />
              );
            })}
            <path
              d={path(
                runsOf(points, (p) => p.volume_sma_20),
                (v) => volBottom - (v / volExt.max) * (volBottom - volTop),
              )}
              fill="none"
              stroke="var(--chart-ma20)"
              strokeWidth={1.1}
              className={styles.line}
            />
          </>
        )}

        <text x={X0} y={VH - 6} className={styles.axisValue}>
          {first}
        </text>
        <text x={X1} y={VH - 6} className={styles.axisValue} textAnchor="end">
          {last}
        </text>

        {hp && (
          <ChartCrosshair
            x={xFor(hover.index as number)}
            segments={crossSegments}
            dots={hoverDot ? [hoverDot] : undefined}
          />
        )}
      </svg>

        {hp && (
          <ChartTooltip
            left={hover.fracAt(hover.index as number)}
            top={crossSegments.length > 0 ? crossSegments[0][0] / VH : 0}
            title={formatDate(hp.bar_date)}
            rows={hoverRows}
          />
        )}
      </div>
    </div>
  );
}

function PaneFrame({ label, top, bottom }: { label: string; top: number; bottom: number }) {
  return (
    <g>
      <line x1={X0} y1={top} x2={X1} y2={top} className={styles.guideFaint} />
      <line x1={X0} y1={bottom} x2={X1} y2={bottom} className={styles.axis} />
      <text x={X0} y={top - 5} className={styles.paneLabel}>
        {label}
      </text>
    </g>
  );
}

function AxisValue({ y, text }: { y: number; text: string }) {
  return (
    <text x={X0 - 6} y={y} className={styles.axisValue} textAnchor="end">
      {text}
    </text>
  );
}
