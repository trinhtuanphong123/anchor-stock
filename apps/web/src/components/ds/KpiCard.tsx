import type { ReactNode } from "react";
import { toneClass, type Tone } from "./tone";

/**
 * One figure with its label, in the 26px mono step. The header of a detail screen is a row of
 * these.
 *
 * The unit belongs in the LABEL — "Giá đóng cửa (nghìn đ)", "GT giao dịch (tỷ đ)" — not beside
 * the number, so a column of values stays a column of values. A missing figure is passed in
 * already formatted as an em dash; nothing here turns a null into a zero.
 */
export function KpiCard({
  label,
  value,
  tone,
}: {
  label: ReactNode;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="as-kpi">
      <span className="as-kpi__label">{label}</span>
      <span className={`as-kpi__value${toneClass(tone)}`}>{value}</span>
    </div>
  );
}

/** Auto-fit grid for a row of {@link KpiCard}s. */
export function KpiGrid({ children }: { children?: ReactNode }) {
  return <div className="as-kpi-grid">{children}</div>;
}
