import type { ReactNode } from "react";
import { toneClass, type Tone } from "./tone";

/**
 * A labelled figure in the 13px mono step, with an optional trailing unit. The board's
 * annotation: deliberately smaller than whatever it sits beside, because it qualifies that
 * subject rather than competing with it.
 *
 * The unit is named here rather than assumed. Basket totals run in nghìn tỷ đ and per-row
 * figures in tỷ đ — two currency units coexist on purpose, so neither may be left implicit.
 */
export function StatBlock({
  label,
  value,
  unit,
  tone,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="as-stat">
      <span className="as-stat__label">{label}</span>
      <span className={`as-stat__value${toneClass(tone)}`}>
        {value}
        {unit ? <span className="as-stat__unit">{unit}</span> : null}
      </span>
    </div>
  );
}
