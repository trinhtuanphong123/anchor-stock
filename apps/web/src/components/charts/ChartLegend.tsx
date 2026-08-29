import type { CSSProperties } from "react";
import styles from "./charts.module.css";

/**
 * One legend entry. `color` is a caller-supplied token string (e.g.
 * `"var(--cluster-3)"` or `"var(--data-neutral)"`); the component never picks a
 * color of its own and assigns no meaning. `variant` selects the swatch shape so
 * the encoding survives without relying on hue alone.
 */
export interface LegendItem {
  label: string;
  color?: string;
  variant?: "solid" | "hollow" | "line";
}

function swatchClass(variant: LegendItem["variant"]): string {
  if (variant === "hollow")
    return `${styles.legendSwatch} ${styles.legendSwatchHollow}`;
  if (variant === "line")
    return `${styles.legendSwatch} ${styles.legendSwatchLine}`;
  return styles.legendSwatch;
}

function swatchStyle(item: LegendItem): CSSProperties | undefined {
  if (!item.color) return undefined;
  return item.variant === "hollow"
    ? { borderColor: item.color }
    : { backgroundColor: item.color };
}

/**
 * Accessible legend over a small list of caller-provided items. Swatches are
 * decorative (`aria-hidden`); each entry's meaning is carried by its text label,
 * so nothing relies on color alone. Shapes and colors are supplied by the
 * caller; this component applies them without inventing any mapping.
 */
export function ChartLegend({
  items,
  className,
}: {
  items: LegendItem[];
  className?: string;
}) {
  if (items.length === 0) return null;
  return (
    <ul className={[styles.legend, className].filter(Boolean).join(" ")}>
      {items.map((item) => (
        <li key={item.label} className={styles.legendItem}>
          <span
            className={swatchClass(item.variant)}
            style={swatchStyle(item)}
            aria-hidden="true"
          />
          <span className={styles.legendLabel}>{item.label}</span>
        </li>
      ))}
    </ul>
  );
}
