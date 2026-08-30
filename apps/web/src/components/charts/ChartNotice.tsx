import type { ReactNode } from "react";

/**
 * Sunken caption under a chart, for a caveat the chart itself cannot state — an adjusted price
 * series that will not match a broker's raw chart across an ex-date, say.
 *
 * The text is content, not decoration: it is the sentence that stops a reader concluding the
 * figures are wrong. It is never a dismissible hint and carries no control.
 */
export function ChartNotice({
  children,
  label = "Lưu ý",
}: {
  children: ReactNode;
  label?: string;
}) {
  return (
    <p className="as-chart-notice" role="note">
      <span className="as-chart-notice__label">{label}</span>
      {children}
    </p>
  );
}
