import styles from "./charts.module.css";

/**
 * Reusable axis title. The quantity `label` and the optional `unit` are supplied
 * by the caller; the unit is appended in parentheses only when present, and is
 * never inferred. `axis="y"` orients the text vertically for a y-axis title.
 */
export function ChartAxisLabel({
  axis,
  label,
  unit,
  className,
}: {
  axis: "x" | "y";
  label: string;
  unit?: string;
  className?: string;
}) {
  const text = unit ? `${label} (${unit})` : label;
  const classes = [
    styles.axisLabel,
    axis === "y" ? styles.axisLabelY : undefined,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return <span className={classes}>{text}</span>;
}
