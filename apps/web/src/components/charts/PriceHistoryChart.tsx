"use client";

import { useId } from "react";
import { ChartCrosshair, ChartTooltip, useChartHover } from "./ChartHover";
import { axisDate, labelIndexes, priceTicks } from "./scale";
import {
  DASH,
  formatCompactVolume,
  formatDecimal,
  formatInt,
  formatSession,
} from "@/components/market/format";

/**
 * The minimum a bar must supply — the three fields this chart actually reads.
 *
 * Declared here rather than imported from `@/lib/api`: a presentational primitive that imports a
 * response type is coupled to whichever API contract happens to be current. TypeScript is
 * structural, so a richer OHLCV row from the history route satisfies this without a cast.
 */
export interface PriceBar {
  date: string;
  close: number;
  volume: number;
}

/** Fixed viewBox scaled by CSS — the coordinate idiom every chart in this package uses. */
const VW = 900;
/** The price scale lives on the RIGHT, where the newest bar is. */
const PAD_L = 8;
const PAD_R = 64;
const X0 = PAD_L;
const X1 = VW - PAD_R;

/**
 * One component, two framings.
 *
 * `pane="price"` and `pane="volume"` each own a full-height plot and their own axis, which is how
 * `/tickers` shows them: two frames, each saying one thing and titling itself in full words.
 * `pane="both"` keeps the stacked reading, where volume is a THIRD of the height and never half —
 * volume is context for the price, and a pane that competes with the subject makes the reader
 * choose which chart they are reading.
 */
const LAYOUT = {
  both: { vh: 360, price: [14, 250], vol: [268, 332] },
  price: { vh: 300, price: [14, 262], vol: null },
  volume: { vh: 220, price: null, vol: [18, 182] },
} as const;

export type PricePane = keyof typeof LAYOUT;

/**
 * Daily close line over a volume histogram, or either pane alone.
 *
 * Four rules, all of them the design system's rather than this file's:
 *
 *  1. **The area closes to the range's OPENING level**, marked by the dashed amber baseline — not
 *     to the bottom of the frame. What it shades is the gain or loss over the window; closing to
 *     the frame would shade the price's absolute level, a quantity with no meaning as an area.
 *     (The handoff kit closes to the frame. The chart law in CLAUDE.md is explicit and wins, and
 *     it is what `market/IndexChart` already does — two line charts in one product shading
 *     different quantities would be worse than either choice on its own.)
 *  2. **A non-finite close is a gap, never a zero.** Runs break at a missing bar and nothing is
 *     interpolated across them.
 *  3. **Volume bars are tinted by their own session's direction**, using the `-mark` step — those
 *     tokens are for fills and strokes, never for text.
 *  4. **The crosshair is neutral and keyboard-reachable.** `useChartHover` carries the
 *     arrow/Home/End/Esc parity a bespoke pointer handler quietly drops.
 */
export function PriceHistoryChart({
  bars,
  pane = "both",
  longRange = false,
  ticker,
}: {
  bars: PriceBar[];
  pane?: PricePane;
  /** Month labels rather than day labels — true past roughly half a year. */
  longRange?: boolean;
  ticker?: string;
}) {
  const L = LAYOUT[pane];
  const n = bars.length;

  // Two instances of this chart live on the ticker screen, so the gradient ids must be unique per
  // mount — a shared id makes the second instance paint the first one's fill.
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");

  // Before the guard below: hooks cannot sit behind an early return, and the hook tolerates
  // `count: 0`. The panes are passed so the readout belongs to the band under the pointer only.
  const hover = useChartHover({
    count: n,
    x0: X0,
    x1: X1,
    vw: VW,
    vh: L.vh,
    panes: [
      ...(L.price ? [{ key: "price", top: L.price[0], bottom: L.price[1] }] : []),
      ...(L.vol ? [{ key: "volume", top: L.vol[0], bottom: L.vol[1] }] : []),
    ],
  });

  const closes = bars.map((b) => b.close).filter((c) => Number.isFinite(c));
  if (n < 2 || closes.length < 2) return null;

  let lo = Math.min(...closes);
  let hi = Math.max(...closes);
  // 8% headroom so the line never touches the frame, and a floor so a dead-flat series still gets
  // a band rather than dividing by zero.
  const pad = Math.max((hi - lo) * 0.08, 0.01);
  lo -= pad;
  hi += pad;

  const maxVol = Math.max(0, ...bars.map((b) => (Number.isFinite(b.volume) ? b.volume : 0)));

  const xAt = (i: number): number => X0 + (i / (n - 1)) * (X1 - X0);
  const yAt = (v: number): number =>
    L.price === null ? 0 : L.price[1] - ((v - lo) / (hi - lo)) * (L.price[1] - L.price[0]);
  const vAt = (v: number): number =>
    L.vol === null || maxVol === 0 ? 0 : L.vol[1] - (v / maxVol) * (L.vol[1] - L.vol[0]);

  // Contiguous runs of drawable closes. A gap ends a run (rule 2).
  const runs: Array<Array<{ i: number; x: number; y: number; close: number }>> = [];
  let run: Array<{ i: number; x: number; y: number; close: number }> = [];
  bars.forEach((b, i) => {
    if (Number.isFinite(b.close)) {
      run.push({ i, x: xAt(i), y: yAt(b.close), close: b.close });
    } else if (run.length > 0) {
      runs.push(run);
      run = [];
    }
  });
  if (run.length > 0) runs.push(run);

  const drawn = runs.flat();
  const first = drawn[0];
  const last = drawn[drawn.length - 1];
  const up = last.close >= first.close;
  const baselineY = yAt(first.close);

  const line = (r: typeof drawn): string =>
    r.map((p, k) => `${k === 0 ? "M" : "L"}${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" ");
  // The area spans the whole drawn extent and closes to the opening level (rule 1).
  const area = `${line(drawn)} L${last.x.toFixed(2)} ${baselineY.toFixed(2)} L${first.x.toFixed(2)} ${baselineY.toFixed(2)} Z`;

  const barW = Math.max(1, ((X1 - X0) / n) * 0.7);
  const gradientId = `pv-${up ? "up" : "down"}-${uid}`;
  const clipId = `pv-clip-${uid}`;

  const hovered = hover.index === null ? null : bars[hover.index];
  const hoveredX = hover.index === null ? 0 : xAt(hover.index);
  // The crosshair spans the hovered band only: a rule crossing both panes read as the pane below
  // being "synced" to the one under the cursor.
  const hoveredBand: Array<readonly [number, number]> =
    hover.pane === "volume" && L.vol !== null
      ? [[L.vol[0], L.vol[1]]]
      : L.price !== null
        ? [[L.price[0], L.price[1]]]
        : [];
  const label =
    pane === "volume"
      ? `Khối lượng giao dịch qua ${n} phiên`
      : pane === "price"
        ? `Giá giao dịch qua ${n} phiên`
        : `Giá và khối lượng qua ${n} phiên`;
  const named = ticker ? `${ticker} — ${label}` : label;

  return (
    <div {...hover.surfaceProps} aria-label={`${named}. Dùng phím mũi tên để đọc từng phiên.`}>
      <svg className="as-chart-svg" viewBox={`0 0 ${VW} ${L.vh}`} role="img" aria-label={named}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop
              offset="0%"
              stopColor={up ? "var(--chart-area-top)" : "var(--chart-area-top-neg)"}
            />
            <stop
              offset="100%"
              stopColor={up ? "var(--chart-area-bottom)" : "var(--chart-area-bottom-neg)"}
            />
          </linearGradient>
          {L.price && (
            <clipPath id={clipId}>
              {/* The area overshoots the band when the baseline sits near an edge. */}
              <rect x={X0} y={L.price[0]} width={X1 - X0} height={L.price[1] - L.price[0]} />
            </clipPath>
          )}
        </defs>

        {L.price &&
          priceTicks(lo, hi).map((v) => (
            <g key={v}>
              <line x1={X0} y1={yAt(v)} x2={X1} y2={yAt(v)} className="as-chart-grid" />
              <text x={X1 + 8} y={yAt(v) + 4} className="as-chart-tick as-chart-tick--right">
                {formatDecimal(v, 2)}
              </text>
            </g>
          ))}

        {L.price && (
          <>
            <g clipPath={`url(#${clipId})`}>
              <path d={area} fill={`url(#${gradientId})`} stroke="none" />
              <line x1={X0} y1={baselineY} x2={X1} y2={baselineY} className="as-chart-baseline" />
              {runs.map((r) =>
                r.length >= 2 ? (
                  <path
                    key={`run-${r[0].i}`}
                    d={line(r)}
                    className={`as-chart-line ${up ? "as-chart-line--up" : "as-chart-line--down"}`}
                  />
                ) : null,
              )}
            </g>
            {/* The last-close chip, PINNED TO THE SCALE — "where the series actually is now",
                which is why it sits in the right gutter and not on the line. */}
            <rect
              x={X1 + 2}
              y={yAt(last.close) - 9}
              width={PAD_R - 6}
              height={18}
              rx={2}
              className="as-chart-lasttag"
            />
            <text
              x={X1 + 2 + (PAD_R - 6) / 2}
              y={yAt(last.close) + 4}
              className="as-chart-lasttag-text"
            >
              {formatDecimal(last.close, 2)}
            </text>
          </>
        )}

        {L.vol && maxVol > 0 && (
          <>
            {priceTicks(0, maxVol, 3).map((v) => (
              <g key={`v-${v}`}>
                <line x1={X0} y1={vAt(v)} x2={X1} y2={vAt(v)} className="as-chart-grid" />
                <text x={X1 + 8} y={vAt(v) + 4} className="as-chart-tick as-chart-tick--right">
                  {formatCompactVolume(v)}
                </text>
              </g>
            ))}
            {bars.map((b, i) => {
              if (!Number.isFinite(b.volume) || b.volume <= 0) return null;
              // The session's OWN direction, against the previous close — a bar's colour says
              // which way that session went, not which way the window went.
              const prev = i > 0 ? bars[i - 1].close : b.close;
              const rising = !Number.isFinite(prev) || b.close >= prev;
              return (
                <rect
                  key={`vol-${i}`}
                  x={xAt(i) - barW / 2}
                  y={vAt(b.volume)}
                  width={barW}
                  height={Math.max(0.5, L.vol[1] - vAt(b.volume))}
                  fill={rising ? "var(--data-pos-mark)" : "var(--data-neg-mark)"}
                  opacity={hover.index === i ? 0.95 : 0.45}
                />
              );
            })}
          </>
        )}

        {labelIndexes(n, 6).map((i) => (
          <text
            key={i}
            x={Math.min(Math.max(xAt(i), X0 + 16), X1 - 16)}
            y={L.vh - 4}
            className="as-chart-tick as-chart-tick--mid"
          >
            {axisDate(bars[i].date, longRange)}
          </text>
        ))}

        {/* A neutral dashed rule. Tinting the crosshair would put a directional colour on a mark
            that measures nothing. */}
        {hovered && (
          <ChartCrosshair
            x={hoveredX}
            segments={hoveredBand}
            dots={
              hover.pane === "price" && L.price !== null && Number.isFinite(hovered.close)
                ? [
                    {
                      y: yAt(hovered.close),
                      color: up ? "var(--data-pos-mark)" : "var(--data-neg-mark)",
                    },
                  ]
                : undefined
            }
          />
        )}
      </svg>

      {hovered && hover.index !== null && (
        <ChartTooltip
          left={hover.fracAt(hover.index)}
          title={formatSession(hovered.date)}
          rows={
            hover.pane === "volume"
              ? [{ label: "Khối lượng (cp)", value: formatInt(hovered.volume) }]
              : [
                  {
                    label: "Giá đóng cửa (nghìn đ)",
                    value: Number.isFinite(hovered.close) ? formatDecimal(hovered.close, 2) : DASH,
                  },
                  ...(L.vol ? [{ label: "Khối lượng (cp)", value: formatInt(hovered.volume) }] : []),
                ]
          }
        />
      )}
    </div>
  );
}
