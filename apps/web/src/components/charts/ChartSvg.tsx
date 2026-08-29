import type { ReactNode } from "react";
import styles from "./charts.module.css";

/**
 * Accessible SVG wrapper. Exposes `role="img"` and is always named through
 * `aria-labelledby`. The caller must supply a unique, stable `id` per chart
 * instance; the title and description element IDs are derived from it, so
 * associations stay correct when several charts render on one page. `viewBox` is
 * caller-supplied and the element is responsive (width 100%, height auto). This
 * wrapper draws no data — callers place their own coordinate-based children.
 */
export function ChartSvg({
  title,
  desc,
  viewBox,
  id,
  className,
  preserveAspectRatio = "xMidYMid meet",
  children,
}: {
  title: string;
  desc?: string;
  viewBox: string;
  id: string;
  className?: string;
  preserveAspectRatio?: string;
  children: ReactNode;
}) {
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const labelledBy = desc ? `${titleId} ${descId}` : titleId;

  return (
    <svg
      role="img"
      viewBox={viewBox}
      preserveAspectRatio={preserveAspectRatio}
      className={[styles.svg, className].filter(Boolean).join(" ")}
      aria-labelledby={labelledBy}
    >
      <title id={titleId}>{title}</title>
      {desc && <desc id={descId}>{desc}</desc>}
      {children}
    </svg>
  );
}

/**
 * A straight line for an axis (`variant="axis"`) or a gridline
 * (`variant="grid"`); coordinates come from the caller. Stroke color is
 * token-backed via the module class; `strokeWidth` is optional.
 */
export function ChartAxisLine({
  x1,
  y1,
  x2,
  y2,
  variant = "axis",
  strokeWidth,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  variant?: "axis" | "grid";
  strokeWidth?: number;
}) {
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      strokeWidth={strokeWidth}
      className={variant === "grid" ? styles.gridLine : styles.axisLine}
    />
  );
}

/** A tick / axis text label at a caller-supplied position. */
export function ChartTickLabel({
  x,
  y,
  anchor = "middle",
  children,
}: {
  x: number;
  y: number;
  anchor?: "start" | "middle" | "end";
  children: ReactNode;
}) {
  return (
    <text x={x} y={y} textAnchor={anchor} className={styles.tickLabel}>
      {children}
    </text>
  );
}

/** A grouping element for a chart's plot region; presentational only. */
export function ChartPlotRegion({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <g className={className}>{children}</g>;
}
