import type { ReactNode } from "react";

/**
 * Sunken `<details>` for figures a reviewer will ask for but a reader should not meet first.
 *
 * Demote, don't delete: the model internals — τ, ρ², Δ, F̄ at this step — stay complete and one
 * click away. What must never go behind this is something a reader needs in order to interpret
 * what is above it.
 *
 * `flush` drops the sunken card treatment, for the one place this sits inside a container that
 * already has a rule of its own: a card nested in a card is a border inside a border.
 */
export function Disclosure({
  summary,
  children,
  open = false,
  flush = false,
}: {
  /** Uppercase micro label, e.g. "Chỉ số nhóm". */
  summary: ReactNode;
  children?: ReactNode;
  open?: boolean;
  flush?: boolean;
}) {
  return (
    <details
      className="as-details"
      open={open}
      style={flush ? { background: "transparent", border: "none", padding: 0 } : undefined}
    >
      <summary className="as-details__toggle">{summary}</summary>
      <div className="as-details__body">{children}</div>
    </details>
  );
}
