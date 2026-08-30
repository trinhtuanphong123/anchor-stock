"use client";

import { useMemo } from "react";
import type { IndexBar, IndexHistoryResponse, IndexRange } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { Panel, RangeTabs } from "@/components/ds";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ChartCrosshair, ChartTooltip, useChartHover } from "@/components/charts/ChartHover";
import { axisDate, labelIndexes, priceTicks } from "@/components/charts/scale";
import { DASH, formatDecimal, formatInt, formatPercent, formatSession } from "./format";

/**
 * The index line chart — the screen's subject.
 *
 * ONE POINT PER SESSION. The pipeline collects daily bars and nothing finer, so there is no
 * intraday series in this system and the shortest range offered is 1M. A "1D" tab drawn from
 * daily bars would be a label making a claim the data cannot support, which is why this
 * component has no such tab and `IndexRange` has no such member.
 *
 * Hand-written SVG, fixed `viewBox` scaled by CSS, `vector-effect: non-scaling-stroke` so the
 * 1.5px line stays 1.5px on a wide monitor. Form comes entirely from the global `as-chart-*`
 * classes; this file writes no colour, no size and no spacing of its own.
 *
 * The hover machinery is `components/charts/ChartHover` unchanged — the same hook, crosshair and
 * tooltip the ticker charts use. Reusing it is not only economy: it is what makes the crosshair
 * behave identically on every chart in the app, including the KEYBOARD parity (←/→/Home/End/Esc),
 * which is the part a bespoke implementation would have quietly dropped.
 */

const RANGES: Array<{ value: IndexRange; label: string }> = [
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "ytd", label: "YTD" },
  { value: "1y", label: "1N" },
  { value: "all", label: "TẤT CẢ" },
];

/** Fixed viewBox, scaled by CSS — the coordinate idiom every line chart in this package uses. */
const VW = 900;
const VH = 340;
/** The price scale lives on the RIGHT, as on every trading chart: the newest bar is there, and
 *  so is the reader's eye. That is the whole reason PAD_R is eight times PAD_L. */
const PAD_L = 8;
const PAD_R = 64;
const PAD_T = 16;
const PAD_B = 26;

const X0 = PAD_L;
const X1 = VW - PAD_R;
const Y0 = PAD_T;
const Y1 = VH - PAD_B;

interface Plot {
  bars: IndexBar[];
  /** Every bar with a drawable close, in order. */
  pts: Array<{ i: number; x: number; y: number; close: number }>;
  lo: number;
  hi: number;
  yAt: (v: number) => number;
  /** y of the range's OPENING level — what the area closes to. */
  baselineY: number | null;
  first: number | null;
  last: number | null;
  rangeReturn: number | null;
  up: boolean;
}

function buildPlot(bars: IndexBar[]): Plot | null {
  const valid = bars
    .map((b) => b.close)
    .filter((c): c is number => c !== null && Number.isFinite(c));
  if (valid.length < 2) return null;

  let lo = Math.min(...valid);
  let hi = Math.max(...valid);
  // 6% headroom so the line never touches the frame, and a floor so a dead-flat series still
  // gets a band rather than dividing by zero.
  const pad = Math.max((hi - lo) * 0.06, Math.abs(hi) * 0.001, 0.5);
  lo -= pad;
  hi += pad;

  const yAt = (v: number): number => Y1 - ((v - lo) / (hi - lo)) * (Y1 - Y0);
  const xAt = (i: number): number =>
    bars.length <= 1 ? (X0 + X1) / 2 : X0 + (i / (bars.length - 1)) * (X1 - X0);

  const pts = bars.flatMap((b, i) =>
    b.close === null || !Number.isFinite(b.close)
      ? []
      : [{ i, x: xAt(i), y: yAt(b.close), close: b.close }],
  );

  const first = pts.length > 0 ? pts[0].close : null;
  const last = pts.length > 0 ? pts[pts.length - 1].close : null;
  const rangeReturn = first !== null && last !== null && first !== 0 ? last / first - 1 : null;

  return {
    bars,
    pts,
    lo,
    hi,
    yAt,
    baselineY: first === null ? null : yAt(first),
    first,
    last,
    rangeReturn,
    // A range that ended exactly where it started is drawn as up. The alternative is a third
    // colour for an event that essentially never happens on an index over 20+ sessions.
    up: rangeReturn === null || rangeReturn >= 0,
  };
}

export function IndexChart({
  state,
  range,
  onRangeChange,
}: {
  state: ResourceState<IndexHistoryResponse>;
  range: IndexRange;
  onRangeChange: (next: IndexRange) => void;
}) {
  const symbol = state.kind === "data" ? state.data.index_symbol : "Chỉ số";

  return (
    <Panel
      title={symbol}
      label="Biểu đồ chỉ số"
      controls={
        <RangeTabs value={range} onChange={(v) => onRangeChange(v as IndexRange)} options={RANGES} />
      }
      footnote={
        state.kind === "data" ? (
          <>
            Mỗi điểm là một <strong>phiên</strong>, không phải một thời điểm trong phiên — hệ thống
            chỉ thu thập dữ liệu theo ngày. {state.data.count} phiên trong khoảng đang xem.
          </>
        ) : null
      }
    >
      {state.kind === "loading" && <LoadingState rows={6} label="Đang tải chuỗi chỉ số" />}
      {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}
      {state.kind === "data" && <ChartBody data={state.data} range={range} />}
    </Panel>
  );
}

function ChartBody({ data, range }: { data: IndexHistoryResponse; range: IndexRange }) {
  const plot = useMemo(() => buildPlot(data.bars), [data.bars]);

  // Hooks must run unconditionally, so the hover geometry is built even when there is nothing to
  // draw; `count: 0` makes every handler a no-op.
  const hover = useChartHover({
    count: plot ? plot.bars.length : 0,
    x0: X0,
    x1: X1,
    vw: VW,
    vh: VH,
    panes: [{ key: "price", top: 0, bottom: VH }],
  });

  if (!plot) {
    return (
      <EmptyState
        scope="Ghi chú"
        message="Chưa đủ dữ liệu để vẽ đường chỉ số cho khoảng thời gian này."
      />
    );
  }

  const { pts, lo, hi, yAt, baselineY, last, rangeReturn, up } = plot;
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x} ${p.y}`).join(" ");
  // The area closes down to the range's OPENING LEVEL, not to the axis: what it shades is the
  // gain or loss over the window, which is the quantity the dotted amber rule marks. Closing to
  // the bottom of the frame would shade the index's absolute level, a number with no meaning as
  // an area.
  const areaFloor = baselineY ?? Y1;
  const area = `${line} L${pts[pts.length - 1].x} ${areaFloor} L${pts[0].x} ${areaFloor} Z`;

  const longRange = range === "1y" || range === "all" || range === "ytd";
  const gradientId = `idx-grad-${up ? "up" : "down"}`;

  const hovered = hover.index === null ? null : plot.bars[hover.index];
  const hoveredPt = hover.index === null ? null : pts.find((p) => p.i === hover.index);

  const dateTickIdx = labelIndexes(plot.bars.length, 6);

  return (
    <div {...hover.surfaceProps}>
      <svg
        className="as-chart-svg"
        viewBox={`0 0 ${VW} ${VH}`}
        role="img"
        aria-label={`Diễn biến ${data.index_symbol} qua ${data.count} phiên, ${
          rangeReturn === null ? "không xác định" : formatPercent(rangeReturn)
        } trong khoảng`}
      >
        <defs>
          {/* Two gradients, only one ever used per render. Both are declared so a range switch
              that flips the direction does not have to remount the <defs>. */}
          <linearGradient id="idx-grad-up" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-area-top)" />
            <stop offset="100%" stopColor="var(--chart-area-bottom)" />
          </linearGradient>
          <linearGradient id="idx-grad-down" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="var(--chart-area-top-neg)" />
            <stop offset="100%" stopColor="var(--chart-area-bottom-neg)" />
          </linearGradient>
          {/* The area path can overshoot the plot band when the baseline sits near an edge. */}
          <clipPath id="idx-clip">
            <rect x={X0} y={Y0} width={X1 - X0} height={Y1 - Y0} />
          </clipPath>
        </defs>

        {/* Horizontal gridlines and the right-hand price scale. */}
        {priceTicks(lo, hi).map((v) => (
          <g key={v}>
            <line x1={X0} y1={yAt(v)} x2={X1} y2={yAt(v)} className="as-chart-grid" />
            <text x={X1 + 8} y={yAt(v) + 4} className="as-chart-tick as-chart-tick--right">
              {formatDecimal(v, 0)}
            </text>
          </g>
        ))}

        <g clipPath="url(#idx-clip)">
          <path d={area} fill={`url(#${gradientId})`} stroke="none" />
          {baselineY !== null && (
            <line x1={X0} y1={baselineY} x2={X1} y2={baselineY} className="as-chart-baseline" />
          )}
          <path
            d={line}
            className={`as-chart-line ${up ? "as-chart-line--up" : "as-chart-line--down"}`}
          />
        </g>

        {/* Date labels along the foot. */}
        {dateTickIdx.map((i) => (
          <text
            key={i}
            x={Math.min(Math.max(hover.xAt(i), X0 + 16), X1 - 16)}
            y={VH - 8}
            className="as-chart-tick as-chart-tick--mid"
          >
            {axisDate(plot.bars[i].bar_date, longRange)}
          </text>
        ))}

        {/* The last-price chip, PINNED TO THE SCALE — the affordance for "where the series
            actually is right now", which is why it sits in the right gutter, not on the line. */}
        {last !== null && (
          <g>
            <rect
              x={X1 + 2}
              y={yAt(last) - 9}
              width={PAD_R - 6}
              height={18}
              rx={2}
              className="as-chart-lasttag"
            />
            <text x={X1 + 2 + (PAD_R - 6) / 2} y={yAt(last) + 4} className="as-chart-lasttag-text">
              {formatDecimal(last, 2)}
            </text>
          </g>
        )}

        {/* A neutral dashed rule and nothing else. The crosshair is furniture: tinting it with
            the series colour would put a directional colour on a mark that measures nothing. */}
        {hoveredPt && <ChartCrosshair x={hoveredPt.x} segments={[[Y0, Y1]]} />}
      </svg>

      {hovered && hover.index !== null && (
        <ChartTooltip
          left={hover.fracAt(hover.index)}
          title={formatSession(hovered.bar_date)}
          rows={[
            { label: "Đóng cửa", value: formatDecimal(hovered.close, 2) },
            { label: "Cao nhất", value: formatDecimal(hovered.high, 2) },
            { label: "Thấp nhất", value: formatDecimal(hovered.low, 2) },
            { label: "±% phiên", value: formatPercent(hovered.ret_1d) },
            { label: "KL", value: formatInt(hovered.volume) },
          ]}
        />
      )}
    </div>
  );
}

/**
 * The index header: level, change over the SELECTED RANGE, and the session it ends on.
 *
 * The big number is "what this window shows", and it moves when the reader switches range tabs.
 * That is why the market bar carries the session's own ±% beside it as a separate figure: without
 * it, the tabs would silently rewrite a number a reader could take for the daily move.
 */
export function IndexQuote({ state }: { state: ResourceState<IndexHistoryResponse> }) {
  const plot = useMemo(() => (state.kind === "data" ? buildPlot(state.data.bars) : null), [state]);

  const symbol = state.kind === "data" ? state.data.index_symbol : "Chỉ số";

  if (!plot) {
    return (
      <div className="as-symbol">
        <div className="as-symbol__name">
          <span className="as-symbol__ticker">{symbol}</span>
        </div>
        <div className="as-symbol__quote">
          <span className="as-symbol__level">{DASH}</span>
        </div>
      </div>
    );
  }

  const lastBar = plot.bars[plot.bars.length - 1];
  const dir =
    plot.rangeReturn === null || plot.rangeReturn === 0
      ? "flat"
      : plot.rangeReturn > 0
        ? "pos"
        : "neg";
  const absChange = plot.first !== null && plot.last !== null ? plot.last - plot.first : null;

  return (
    <div className="as-symbol">
      <div className="as-symbol__name">
        <span className="as-symbol__ticker">{symbol}</span>
        <span className="as-symbol__meta">
          Phiên {formatSession(lastBar?.bar_date)} · {plot.bars.length} phiên
        </span>
      </div>
      <div className="as-symbol__quote">
        <span className="as-symbol__level">{formatDecimal(plot.last, 2)}</span>
        <span className={`as-symbol__change as-${dir}`}>
          {absChange === null ? DASH : `${absChange > 0 ? "+" : ""}${formatDecimal(absChange, 2)}`}
          {"  "}
          {formatPercent(plot.rangeReturn)}
        </span>
      </div>
    </div>
  );
}
