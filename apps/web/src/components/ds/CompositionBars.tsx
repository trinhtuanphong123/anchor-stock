export interface CompositionRow {
  label: string;
  value: number;
}

/**
 * Label / track / count rows — the make-up of a group by some categorical field.
 *
 * **The fill is the accent, always.** These bars carry identity, not direction, and a green bar
 * on this product means the price rose. A sector holding 9 of 19 names has not gone up.
 *
 * `total` is the denominator when it is not the sum of the rows — a composition drawn over the
 * group's full membership stays honest when some members carry no label and are folded into a
 * catch-all by the caller rather than dropped.
 */
export function CompositionBars({
  rows = [],
  total,
}: {
  rows?: CompositionRow[];
  /** Denominator. Defaults to the sum of the values. */
  total?: number;
}) {
  const sum = total ?? rows.reduce((a, r) => a + r.value, 0);
  return (
    <div className="as-bars">
      {rows.map((r) => (
        <div key={r.label} className="as-bar-row">
          <span className="as-bar-label" title={r.label}>
            {r.label}
          </span>
          <span className="as-bar-track">
            <span
              className="as-bar-fill"
              style={{ width: `${sum > 0 ? (r.value / sum) * 100 : 0}%` }}
              aria-hidden="true"
            />
          </span>
          <span className="as-bar-value">
            {r.value} / {sum}
          </span>
        </div>
      ))}
    </div>
  );
}
