"use client";

import { useState } from "react";
import type { IndicatorPoint } from "@/lib/api";
import { ChartCrosshair, ChartTooltip, useChartHover, type TooltipRow } from "./ChartHover";
import { axisDate, labelIndexes, priceTicks } from "./scale";
import { DASH, formatDecimal, formatSession } from "@/components/market/format";
import styles from "./charts.module.css";

/** Fixed viewBox scaled by CSS; the price scale on the right, as everywhere else. */
const VW = 900;
const PAD_L = 8;
const PAD_R = 64;
const X0 = PAD_L;
const X1 = VW - PAD_R;

/**
 * Two panes, and `/tickers` shows them one at a time: RSI is a different unit on a different
 * scale, and in its own frame it stops competing with the price for the same vertical space.
 */
const LAYOUT = {
  both: { vh: 420, price: [14, 250], rsi: [292, 396] },
  price: { vh: 320, price: [14, 282], rsi: null },
  rsi: { vh: 200, price: null, rsi: [18, 162] },
} as const;

export type IndicatorPane = keyof typeof LAYOUT;

type Accessor = (p: IndicatorPoint) => number | null;

interface SeriesSpec {
  key: string;
  label: string;
  value: Accessor;
  color: string;
  width: number;
  dash?: string;
}

/**
 * The price pane's five series. **Colour here is identity, never direction** — these lines are
 * five different quantities in one unit, so a red one would read as a falling price rather than
 * as a lower band.
 */
const SERIES: SeriesSpec[] = [
  { key: "close", label: "Giá đóng cửa", value: (p) => p.close, color: "var(--text-1)", width: 1.5 },
  { key: "sma_20", label: "SMA 20", value: (p) => p.sma_20, color: "var(--chart-ma20)", width: 1.25 },
  { key: "sma_50", label: "SMA 50", value: (p) => p.sma_50, color: "var(--chart-ma50)", width: 1.25 },
  {
    key: "bb_upper_20",
    label: "Bollinger trên",
    value: (p) => p.bb_upper_20,
    color: "var(--chart-band)",
    width: 1,
    dash: "3 3",
  },
  {
    key: "bb_lower_20",
    label: "Bollinger dưới",
    value: (p) => p.bb_lower_20,
    color: "var(--chart-band)",
    width: 1,
    dash: "3 3",
  },
];

/** Contiguous runs of finite points. A gap ends a run; nothing is interpolated across it. */
function runsOf(points: IndicatorPoint[], value: Accessor): Array<Array<{ i: number; v: number }>> {
  const runs: Array<Array<{ i: number; v: number }>> = [];
  let run: Array<{ i: number; v: number }> = [];
  points.forEach((p, i) => {
    const v = value(p);
    if (v !== null && Number.isFinite(v)) run.push({ i, v });
    else if (run.length > 0) {
      runs.push(run);
      run = [];
    }
  });
  if (run.length > 0) runs.push(run);
  return runs;
}

/**
 * Price with its moving averages and Bollinger band over an RSI pane — or either pane alone.
 *
 * Three rules, the same rule in different clothes:
 *
 *  1. **A null is a gap, never a zero.** `sma_50` is null for the first 49 sessions of any window
 *     and `rsi_14` for the first 14. Joining across those gaps would draw a line the data does not
 *     contain; substituting 0 would draw a crash that never happened.
 *  2. **The x-positions come from the index, not the date.** Sessions are equally spaced, so a
 *     holiday does not stretch the axis and column i is the same session in both panes.
 *  3. **The scale follows what is DRAWN.** Isolating one series rescales the pane to it, because
 *     a lone SMA 20 in a band sized for the Bollinger envelope is a flat line saying nothing.
 *
 * The legend is the control surface: click a series to isolate it, click again to restore the
 * five. That is the only interaction on this screen, and it reads nothing and writes nothing.
 */
export function CombinedIndicatorChart({
  points,
  pane = "both",
  longRange = false,
  ticker,
}: {
  points: IndicatorPoint[];
  pane?: IndicatorPane;
  longRange?: boolean;
  ticker?: string;
}) {
  const [isolated, setIsolated] = useState<string | null>(null);
  const L = LAYOUT[pane];
  const n = points.length;

  const hover = useChartHover({
    count: n,
    x0: X0,
    x1: X1,
    vw: VW,
    vh: L.vh,
    panes: [
      ...(L.price ? [{ key: "price", top: L.price[0], bottom: L.price[1] }] : []),
      ...(L.rsi ? [{ key: "rsi", top: L.rsi[0], bottom: L.rsi[1] }] : []),
    ],
  });

  if (n < 2) return null;

  const shown = SERIES.filter((s) => isolated === null || s.key === isolated);

  // Rule 3: the price band is scaled by the series actually on the plot.
  const values: number[] = [];
  if (L.price !== null) {
    for (const p of points) {
      for (const s of shown) {
        const v = s.value(p);
        if (v !== null && Number.isFinite(v)) values.push(v);
      }
    }
  }
  const hasPrice = L.price !== null && values.length >= 2;
  let lo = hasPrice ? Math.min(...values) : 0;
  let hi = hasPrice ? Math.max(...values) : 1;
  const pad = Math.max((hi - lo) * 0.07, 0.01);
  lo -= pad;
  hi += pad;

  const xAt = (i: number): number => X0 + (i / (n - 1)) * (X1 - X0);
  const yAt = (v: number): number =>
    L.price === null ? 0 : L.price[1] - ((v - lo) / (hi - lo)) * (L.price[1] - L.price[0]);
  // RSI is bounded [0,100] by definition, so its axis is fixed rather than data-driven — the
  // 70/30 rules are only meaningful against a fixed scale.
  const rAt = (v: number): number =>
    L.rsi === null ? 0 : L.rsi[1] - (v / 100) * (L.rsi[1] - L.rsi[0]);

  const path = (value: Accessor, y: (v: number) => number): string =>
    runsOf(points, value)
      .filter((r) => r.length >= 2)
      .map((r) => `M${r.map((p) => `${xAt(p.i).toFixed(2)} ${y(p.v).toFixed(2)}`).join(" L")}`)
      .join(" ");

  // The Bollinger envelope as a filled ribbon, drawn only with the full set on the plot: once a
  // single series is isolated the ribbon is no longer what the pane is about.
  const band = ((): string => {
    if (L.price === null || isolated !== null) return "";
    const upper: string[] = [];
    const lower: string[] = [];
    points.forEach((p, i) => {
      const u = p.bb_upper_20;
      const d = p.bb_lower_20;
      if (u !== null && d !== null && Number.isFinite(u) && Number.isFinite(d)) {
        upper.push(`${xAt(i).toFixed(2)} ${yAt(u).toFixed(2)}`);
        lower.unshift(`${xAt(i).toFixed(2)} ${yAt(d).toFixed(2)}`);
      }
    });
    return upper.length > 1 ? `M${upper.join(" L")} L${lower.join(" L")} Z` : "";
  })();

  const hovered = hover.index === null ? null : points[hover.index];
  const hoveredBand: Array<readonly [number, number]> =
    hover.pane === "rsi" && L.rsi !== null
      ? [[L.rsi[0], L.rsi[1]]]
      : L.price !== null
        ? [[L.price[0], L.price[1]]]
        : [];

  const num = (v: number | null | undefined, digits = 2): string =>
    v === null || v === undefined || !Number.isFinite(v) ? DASH : formatDecimal(v, digits);

  const rows: TooltipRow[] =
    hovered === null
      ? []
      : hover.pane === "rsi"
        ? [{ label: "RSI 14", value: num(hovered.rsi_14, 1), color: "var(--chart-rsi)" }]
        : shown.map((s) => ({
            label: s.label,
            value: num(s.value(hovered)),
            color: s.color,
          }));

  const label =
    pane === "rsi"
      ? `RSI 14 qua ${n} phiên`
      : pane === "price"
        ? `Giá và đường trung bình qua ${n} phiên`
        : `Giá, đường trung bình và RSI qua ${n} phiên`;
  const named = ticker ? `${ticker} — ${label}` : label;
  const toggle = (key: string): void => setIsolated((cur) => (cur === key ? null : key));

  return (
    <div className={styles.stack}>
      <div {...hover.surfaceProps} aria-label={`${named}. Dùng phím mũi tên để đọc từng phiên.`}>
        <svg className="as-chart-svg" viewBox={`0 0 ${VW} ${L.vh}`} role="img" aria-label={named}>
          {hasPrice &&
            priceTicks(lo, hi, 4).map((v) => (
              <g key={v}>
                <line x1={X0} y1={yAt(v)} x2={X1} y2={yAt(v)} className="as-chart-grid" />
                <text x={X1 + 8} y={yAt(v) + 4} className="as-chart-tick as-chart-tick--right">
                  {formatDecimal(v, 2)}
                </text>
              </g>
            ))}

          {band !== "" && <path d={band} fill="var(--chart-band)" opacity="0.1" stroke="none" />}

          {hasPrice &&
            // Reversed so the close, first in the legend, is drawn last and sits on top.
            shown
              .slice()
              .reverse()
              .map((s) => (
                <path
                  key={s.key}
                  d={path(s.value, yAt)}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={s.width}
                  strokeDasharray={s.dash}
                  opacity={s.dash ? 0.7 : 1}
                  vectorEffect="non-scaling-stroke"
                  className="as-chart-series"
                  onClick={() => toggle(s.key)}
                />
              ))}

          {L.rsi !== null && (
            <>
              {[70, 30].map((level) => (
                <g key={level}>
                  <line
                    x1={X0}
                    y1={rAt(level)}
                    x2={X1}
                    y2={rAt(level)}
                    className="as-chart-grid"
                    strokeDasharray="2 4"
                  />
                  <text
                    x={X1 + 8}
                    y={rAt(level) + 4}
                    className="as-chart-tick as-chart-tick--right"
                  >
                    {level}
                  </text>
                </g>
              ))}
              <path
                d={path((p) => p.rsi_14, rAt)}
                fill="none"
                stroke="var(--chart-rsi)"
                strokeWidth={1.25}
                vectorEffect="non-scaling-stroke"
              />
              {/* The bands are a market convention, not a threshold this system computed, and the
                  label says so — the number itself is not a verdict. */}
              <text x={X0} y={L.rsi[0] - 8} className="as-chart-tick">
                RSI 14 · dải 70/30 là quy ước thị trường
              </text>
            </>
          )}

          {labelIndexes(n, 6).map((i) => (
            <text
              key={i}
              x={Math.min(Math.max(xAt(i), X0 + 16), X1 - 16)}
              y={L.vh - 4}
              className="as-chart-tick as-chart-tick--mid"
            >
              {axisDate(points[i].bar_date ?? "", longRange)}
            </text>
          ))}

          {hovered && hover.index !== null && (
            <ChartCrosshair x={xAt(hover.index)} segments={hoveredBand} />
          )}
        </svg>

        {hovered && hover.index !== null && (
          <ChartTooltip
            left={hover.fracAt(hover.index)}
            title={formatSession(hovered.bar_date)}
            rows={rows}
          />
        )}
      </div>

      {L.price !== null && (
        <ul className="as-legend">
          {SERIES.map((s) => (
            <li key={s.key}>
              <button
                type="button"
                aria-pressed={isolated === s.key}
                onClick={() => toggle(s.key)}
                className={`as-legend__item as-legend__btn${
                  isolated !== null && isolated !== s.key ? " as-legend__btn--off" : ""
                }`}
              >
                <span className="as-legend__swatch" style={{ background: s.color }} />
                <span className="as-legend__label">{s.label}</span>
              </button>
            </li>
          ))}
          <li>
            <span className="as-legend__hint">
              {isolated !== null ? "Bấm lại để hiện tất cả" : "Bấm một đường để xem riêng"}
            </span>
          </li>
        </ul>
      )}
    </div>
  );
}
