import type { ReactNode } from "react";

export interface DefinitionItem {
  label: string;
  value: ReactNode;
}

/**
 * Label/value grid for figures that are read rather than scanned: the run-parameter table on
 * `/about`, the per-group statistics behind a {@link Disclosure}.
 *
 * The terms are NOT uppercased, and `.as-def-term` drops the transform to make sure of it. These
 * labels carry Greek, and `text-transform: uppercase` renders τ as Τ — which reads as a Latin T,
 * so "Dưới τ" becomes "DƯỚI T" and names a threshold that does not exist.
 *
 * F̄ and F̄_adj belong in the same list, always as a pair: F̄ alone overstates coverage by about
 * 60%, because it counts each anchor covering itself at ρ²=1.
 */
export function DefinitionList({ items = [] }: { items?: DefinitionItem[] }) {
  return (
    <dl className="as-defs">
      {items.map((item) => (
        <div key={item.label}>
          <dt className="as-def-term">{item.label}</dt>
          <dd className="as-def-value">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
