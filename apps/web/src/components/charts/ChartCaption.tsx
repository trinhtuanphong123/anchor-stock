import styles from "./charts.module.css";

/**
 * Compact metadata caption for a chart. Each field renders only when the caller
 * supplies it; nothing is inferred or generated. `asOf` accepts `null` (the
 * typed absence some responses carry) and is then omitted. When no field is
 * supplied the component renders nothing.
 */
export function ChartCaption({
  unit,
  horizon,
  asOf,
  className,
}: {
  unit?: string;
  horizon?: string;
  asOf?: string | null;
  className?: string;
}) {
  const items: Array<{ key: string; value: string }> = [];
  if (unit) items.push({ key: "unit", value: unit });
  if (horizon) items.push({ key: "horizon", value: horizon });
  if (asOf) items.push({ key: "as-of", value: asOf });

  // Labels are Vietnamese; the keys above stay English because they are React keys, not text.
  const LABELS: Record<string, string> = {
    unit: "Đơn vị",
    horizon: "Khoảng",
    "as-of": "Dữ liệu đến",
  };

  if (items.length === 0) return null;

  return (
    <p className={[styles.caption, className].filter(Boolean).join(" ")}>
      {items.map((it) => (
        <span key={it.key} className={styles.captionItem}>
          <span className={styles.captionKey}>{LABELS[it.key] ?? it.key}</span>
          <span className={styles.captionVal}>{it.value}</span>
        </span>
      ))}
    </p>
  );
}
