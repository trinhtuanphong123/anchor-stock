"use client";

import { useCallback, useRef, useState } from "react";
import styles from "./ChartHover.module.css";

/**
 * Hover readout for the hand-drawn SVG charts (P11 S6).
 *
 * Three pieces, kept separate because the treemap needs only the third: a hook that turns a
 * pointer position into a session index, a crosshair drawn inside the SVG, and a tooltip drawn as
 * **HTML on top of** the SVG.
 *
 * Why the tooltip is HTML and not `<text>`: these charts use a fixed `viewBox` scaled by CSS, so
 * anything drawn in SVG units changes physical size with the container — the same mechanism that
 * made the treemap labels unreadable. It also cannot wrap, cannot ellipsise, and would be clipped
 * by the plot edge on the right-hand third of every chart. HTML has all three for free.
 *
 * No value is formatted here. Callers pass strings they produced through
 * `components/market/format.ts`, which is the single place a fraction becomes a percent and an
 * ISO date becomes dd/mm/yyyy, and which has tests. A tooltip that formatted its own numbers
 * would be a second such place.
 */

export interface ChartPane {
  /** Stable key the owner uses to slice rows / segments for this band. */
  key: string;
  /** viewBox y of the pane's top edge. */
  top: number;
  /** viewBox y of the pane's bottom edge. */
  bottom: number;
}

export interface ChartHoverGeometry {
  /** Number of points on the shared x axis. */
  count: number;
  /** viewBox x of the first point. */
  x0: number;
  /** viewBox x of the last point. */
  x1: number;
  /** viewBox width, i.e. the second number of `viewBox="0 0 W H"`. */
  vw: number;
  /** viewBox height, i.e. the third number of `viewBox`. Needed to resolve the pane from pointer y. */
  vh: number;
  /**
   * The chart's vertical plot bands, ordered top-to-bottom. The hook resolves which one the
   * pointer is over and exposes it as `pane`, so a multi-pane chart can restrict its crosshair
   * and tooltip to the hovered pane only.
   */
  panes: ReadonlyArray<ChartPane>;
}

/**
 * The band containing `vbY`, or the nearest when `vbY` falls in a gutter or axis row. The plot
 * panes of these charts are separated by gaps and a date-label row, and those are not dead zones —
 * a cursor in one resolves to the pane it borders, so the readout never silently vanishes.
 */
export function nearestPane(vbY: number, panes: ReadonlyArray<ChartPane>): string | null {
  if (panes.length === 0) return null;
  for (const p of panes) {
    if (vbY <= p.bottom) return p.key;
  }
  return panes[panes.length - 1].key;
}

export interface ChartHoverSurfaceProps {
  ref: React.Ref<HTMLDivElement>;
  className: string;
  tabIndex: number;
  onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerLeave: () => void;
  onBlur: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => void;
}

export interface ChartHover {
  /** Hovered/focused point, or null when the pointer is away. */
  index: number | null;
  /** The pane under the pointer, or the last pane held during keyboard navigation. Never null
   *  when `panes` is non-empty — a gutter resolves to the nearest band, so the readout cannot
   *  silently vanish mid-chart. Reset to the first pane when the pointer leaves. */
  pane: string;
  /** Spread onto a block element that wraps the `<svg>` and nothing else. */
  surfaceProps: ChartHoverSurfaceProps;
  /** viewBox x for a point index — the same mapping the surface uses to place its marks. */
  xAt: (i: number) => number;
  /** Fraction across the viewBox (0–1) for a point index, for positioning the tooltip. */
  fracAt: (i: number) => number;
}

/**
 * Pointer and keyboard tracking over an evenly-spaced series.
 *
 * The surface element must wrap the `<svg>` **exactly** — its bounding box is what pointer x is
 * measured against, so an extra axis column inside it would offset every reading.
 *
 * Keyboard parity is not decoration: without it the numbers these tooltips carry would be
 * reachable by mouse only, and the charts are the only place several of them appear at all.
 */
export function useChartHover({ count, x0, x1, vw, vh, panes }: ChartHoverGeometry): ChartHover {
  const ref = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState<number | null>(null);
  // The pane the pointer is over, defaulting to the first band. Kept in state so keyboard
  // navigation (which has no pointer y) can keep showing the pane that was last hovered.
  const defaultPane = panes.length > 0 ? panes[0].key : "";
  const [pane, setPane] = useState<string>(defaultPane);

  const xAt = useCallback(
    (i: number): number => (count <= 1 ? (x0 + x1) / 2 : x0 + (i / (count - 1)) * (x1 - x0)),
    [count, x0, x1],
  );

  const fracAt = useCallback((i: number): number => xAt(i) / vw, [xAt, vw]);

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const el = ref.current;
      if (!el || count === 0) return;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0) return;
      // Pixel y → viewBox y → the pane band containing it. The pane follows the pointer, so a
      // multi-pane chart can restrict its readout to the band actually hovered.
      const vbY = ((e.clientY - rect.top) / rect.height) * vh;
      setPane(nearestPane(vbY, panes) ?? defaultPane);
      if (count === 1) {
        setIndex(0);
        return;
      }
      // Pixel x → viewBox x → position along the series. Rounding (not flooring) snaps to the
      // nearest session, so the readout matches the mark under the cursor rather than the one
      // to its left.
      const vbX = ((e.clientX - rect.left) / rect.width) * vw;
      const t = (vbX - x0) / (x1 - x0);
      const i = Math.round(t * (count - 1));
      setIndex(Math.max(0, Math.min(count - 1, i)));
    },
    [count, vw, x0, x1, vh, panes, defaultPane],
  );

  const clear = useCallback(() => {
    setIndex(null);
    setPane(defaultPane);
  }, [defaultPane]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (count === 0) return;
      const current = index ?? count - 1;
      let next: number | null = null;
      if (e.key === "ArrowRight") next = Math.min(count - 1, current + 1);
      else if (e.key === "ArrowLeft") next = Math.max(0, current - 1);
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = count - 1;
      else if (e.key === "Escape") {
        setIndex(null);
        return;
      } else return;
      e.preventDefault();
      setIndex(next);
    },
    [count, index],
  );

  return {
    index,
    pane,
    xAt,
    fracAt,
    surfaceProps: {
      ref,
      className: styles.surface,
      tabIndex: 0,
      onPointerMove,
      onPointerLeave: clear,
      onBlur: clear,
      onKeyDown,
    },
  };
}

/**
 * Vertical rule at the hovered point, plus a dot per series that has a value there.
 *
 * `segments` is a list of `[y0, y1]` bands in viewBox units so one crosshair can span several
 * stacked panes without drawing over the gaps between them.
 */
export function ChartCrosshair({
  x,
  segments,
  dots,
}: {
  x: number;
  segments: Array<readonly [number, number]>;
  dots?: Array<{ y: number; color: string }>;
}) {
  return (
    <g className={styles.crosshair} aria-hidden="true">
      {segments.map(([y0, y1]) => (
        <line key={`${y0}-${y1}`} x1={x} y1={y0} x2={x} y2={y1} className={styles.crosshairLine} />
      ))}
      {dots?.map((d, i) => (
        <circle key={i} cx={x} cy={d.y} r={2.8} fill={d.color} className={styles.crosshairDot} />
      ))}
    </g>
  );
}

export interface TooltipRow {
  label: string;
  /** Already formatted. `—` for a missing value, never "0". */
  value: string;
  /** Optional swatch tying the row to its series colour. */
  color?: string;
}

/**
 * Readout panel, positioned over the chart.
 *
 * `left` and `top` are fractions of the surface (0–1). The panel flips to the other side of the
 * cursor past the horizontal midpoint so it never leaves the chart on the right — the half of
 * every time-series chart people look at most.
 */
export function ChartTooltip({
  left,
  top = 0,
  title,
  rows,
}: {
  left: number;
  top?: number;
  title: string;
  rows: TooltipRow[];
}) {
  const flip = left > 0.5;
  return (
    <div
      className={`${styles.tooltip} ${flip ? styles.tooltipFlip : ""}`}
      style={{ left: `${left * 100}%`, top: `${top * 100}%` }}
      role="status"
      aria-live="polite"
    >
      <p className={styles.tooltipTitle}>{title}</p>
      <dl className={styles.tooltipRows}>
        {rows.map((r) => (
          <div key={r.label} className={styles.tooltipRow}>
            <dt className={styles.tooltipLabel}>
              {r.color && (
                <span
                  className={styles.tooltipSwatch}
                  style={{ background: r.color }}
                  aria-hidden="true"
                />
              )}
              {r.label}
            </dt>
            <dd className={styles.tooltipValue}>{r.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
