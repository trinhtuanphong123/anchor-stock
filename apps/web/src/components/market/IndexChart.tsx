"use client";

import { useMemo } from "react";
import type { IndexBar, IndexHistoryResponse, IndexRange } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ChartCrosshair, ChartTooltip, useChartHover } from "@/components/charts/ChartHover";
import styles from "./MarketHome.module.css";
import { DASH, formatDate, formatDecimal, formatInt, formatPercent } from "./format";

/**
 * The index line chart — the screen's subject.
 *
 * ONE POINT PER SESSION. The pipeline collects daily bars and nothing finer, so there is no
 * intraday series in this system and the shortest range offered is 1M. A "1D" tab drawn from
 * daily bars would be a label making a claim the data cannot support, which is why this
 * component has no such tab and `IndexRange` has no such member.
 *
 * The hover machinery is `components/charts/ChartHover` unchanged — the same hook, crosshair and
 * tooltip the ticker charts use. Reusing it is not only economy: it is what makes the crosshair
 * behave identically on every chart in the app, including the keyboard parity, which is the part
 * a bespoke implementation would have quietly dropped.
 */

const RANGES: Array<{ value: IndexRange; label: string }> = [
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "ytd", label: "YTD" },
  { value: "1y", label: "1N" },
  { value: "all", label: "TẤT CẢ" },
];

/** Fixed viewBox, scaled by CSS — the coordinate idiom every chart in this package uses. */
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

const PRICE_TICKS = 5;
const DATE_TICKS = 6;

/**
 * A "nice" step for an axis covering `span` in about `count` divisions — 1, 2, 2.5 or 5 times a
 * power of ten. Without it the gridlines land on values like 1417.3, which is a number no reader
 * has ever wanted on an axis.
 */
export function niceStep(span: number, count: number): number {
  if (!(span > 0)) return 1;
  const rough = span / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / mag;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return step * mag;
}

/** Evenly spaced tick VALUES covering [lo, hi] on a nice step. */
export function priceTicks(lo: number, hi: number): number[] {
  const step = niceStep(hi - lo, PRICE_TICKS);
  const first = Math.ceil(lo / step) * step;
  const out: number[] = [];
  for (let v = first; v <= hi + 1e-9; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

/**
 * Date label for a session, at the granularity the range warrants.
 *
 * Over a year, `dd/MM` on six labels repeats months and reads as noise; over a month, `MM/yy`
 * gives six identical labels. The axis says what changes across the window and nothing else.
 */
export function axisDate(iso: string, longRange: boolean): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const [, y, mo, d] = m;
  return longRange ? `${mo}/${y.slice(2)}` : `${d}/${mo}`;
}

interface Plot {
  bars: IndexBar[];
  /** Index of each bar that has a drawable close, in order. */
  pts: Array<{ i: number; x: number; y: number; close: number }>;
  lo: number;
  hi: number;
  yAt: (v: number) => number;
  baselineY: number | null;
  /** Close at the left edge of the range — what the change over the range is measured from. */
  first: number | null;
  last: number | null;
  rangeReturn: number | null;
  up: boolean;
}

function buildPlot(bars: IndexBar[]): Plot | null {
  const closes = bars.map((b) => b.close);
  const valid = closes.filter((c): c is number => c !== null && Number.isFinite(c));
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
  const symbol = state.kind === "data" ? state.data.index_symbol : "VN-INDEX";

  return (
    <section className={styles.panel} aria-label="Biểu đồ chỉ số">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>{symbol}</h2>
        <div className={styles.tabs} role="group" aria-label="Khoảng thời gian">
          {RANGES.map((r) => (
            <button
              key={r.value}
              type="button"
              className={`${styles.tab} ${range === r.value ? styles.tabActive : ""}`}
              aria-pressed={range === r.value}
              onClick={() => onRangeChange(r.value)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.panelBody}>
        {state.kind === "loading" && <LoadingState rows={6} label="Đang tải chuỗi chỉ số" />}
        {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}
        {state.kind === "data" && <ChartBody data={state.data} range={range} />}
      </div>

      {state.kind === "data" && (
        <p className={styles.footnote}>
          Mỗi điểm là một <strong>phiên</strong>, không phải một thời điểm trong phiên — hệ thống
          chỉ thu thập dữ liệu theo ngày. {state.data.count} phiên trong khoảng đang xem.
        </p>
      )}
    </section>
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
  // The area closes down to the BASELINE, not to the axis: what it shades is the gain or loss
  // over the range, which is the quantity the dotted rule marks. Closing to the bottom of the
  // frame would shade the index's absolute level, a number with no meaning as an area.
  const areaFloor = baselineY ?? Y1;
  const area = `${line} L${pts[pts.length - 1].x} ${areaFloor} L${pts[0].x} ${areaFloor} Z`;

  const longRange = range === "1y" || range === "all" || range === "ytd";
  const gradientId = `idx-grad-${up ? "up" : "down"}`;
  const clipId = "idx-clip";

  const hovered = hover.index === null ? null : plot.bars[hover.index];
  const hoveredPt = hover.index === null ? null : pts.find((p) => p.i === hover.index);

  const dateTickIdx = Array.from({ length: DATE_TICKS }, (_, k) =>
    Math.round((k / (DATE_TICKS - 1)) * (plot.bars.length - 1)),
  ).filter((v, k, a) => a.indexOf(v) === k);

  return (
    <div className={styles.chartWrap}>
      <div {...hover.surfaceProps}>
        <svg
          className={styles.chartSvg}
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
            <clipPath id={clipId}>
              <rect x={X0} y={Y0} width={X1 - X0} height={Y1 - Y0} />
            </clipPath>
          </defs>

          {/* Horizontal gridlines and the right-hand price scale. */}
          {priceTicks(lo, hi).map((v) => (
            <g key={v}>
              <line x1={X0} y1={yAt(v)} x2={X1} y2={yAt(v)} className={styles.chartGrid} />
              <text
                x={X1 + 8}
                y={yAt(v) + 4}
                className={`${styles.chartTick} ${styles.chartTickRight}`}
              >
                {formatDecimal(v, 0)}
              </text>
            </g>
          ))}

          <g clipPath={`url(#${clipId})`}>
            <path d={area} fill={`url(#${gradientId})`} className={styles.chartArea} />
            {baselineY !== null && (
              <line x1={X0} y1={baselineY} x2={X1} y2={baselineY} className={styles.chartBaseline} />
            )}
            <path
              d={line}
              className={`${styles.chartLine} ${up ? styles.chartLineUp : styles.chartLineDown}`}
            />
          </g>

          {/* Date labels along the foot. */}
          {dateTickIdx.map((i) => {
            const x = hover.xAt(i);
            return (
              <text
                key={i}
                x={Math.min(Math.max(x, X0 + 16), X1 - 16)}
                y={VH - 8}
                className={`${styles.chartTick} ${styles.chartTickMid}`}
              >
                {axisDate(plot.bars[i].bar_date, longRange)}
              </text>
            );
          })}

          {/* The last-price chip, pinned to the price scale — TradingView's own affordance for
              "where the series actually is right now". */}
          {last !== null && (
            <g>
              <rect
                x={X1 + 2}
                y={yAt(last) - 9}
                width={PAD_R - 6}
                height={18}
                rx={2}
                className={styles.chartLastTag}
              />
              <text x={X1 + 2 + (PAD_R - 6) / 2} y={yAt(last) + 4} className={styles.chartLastTagText}>
                {formatDecimal(last, 2)}
              </text>
            </g>
          )}

          {hoveredPt && (
            <ChartCrosshair
              x={hoveredPt.x}
              segments={[[Y0, Y1]]}
              dots={[
                {
                  y: hoveredPt.y,
                  color: up ? "var(--data-pos-mark)" : "var(--data-neg-mark)",
                },
              ]}
            />
          )}
        </svg>

        {hovered && hover.index !== null && (
          <ChartTooltip
            left={hover.fracAt(hover.index)}
            title={formatDate(hovered.bar_date)}
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
    </div>
  );
}

/**
 * The index header: level, change over the SELECTED RANGE, and the session's own move.
 *
 * Two different changes side by side is not redundancy — it is the point. The big number is
 * "what this window shows", which moves when the reader switches tabs; the small one is "what
 * happened today", which does not. Showing only the first would make the tabs silently rewrite
 * a figure a reader might take for the daily move.
 */
export function IndexQuote({ state }: { state: ResourceState<IndexHistoryResponse> }) {
  const plot = useMemo(
    () => (state.kind === "data" ? buildPlot(state.data.bars) : null),
    [state],
  );

  if (!plot) return null;
  const lastBar = plot.bars[plot.bars.length - 1];
  const dir = plot.rangeReturn === null ? "flat" : plot.rangeReturn > 0 ? "pos" : plot.rangeReturn < 0 ? "neg" : "flat";
  const absChange =
    plot.first !== null && plot.last !== null ? plot.last - plot.first : null;

  return (
    <div className={styles.symbolBlock}>
      <div className={styles.symbolName}>
        <span className={styles.symbolTicker}>
          {state.kind === "data" ? state.data.index_symbol : DASH}
        </span>
        <span className={styles.symbolMeta}>
          Phiên {formatDate(lastBar?.bar_date)} · {plot.bars.length} phiên
        </span>
      </div>
      <div className={styles.symbolQuote}>
        <span className={styles.symbolLevel}>{formatDecimal(plot.last, 2)}</span>
        <span className={`${styles.symbolChange} ${styles[dir]}`}>
          {absChange === null ? DASH : `${absChange > 0 ? "+" : ""}${formatDecimal(absChange, 2)}`}
          {"  "}
          {formatPercent(plot.rangeReturn)}
        </span>
      </div>
    </div>
  );
}
