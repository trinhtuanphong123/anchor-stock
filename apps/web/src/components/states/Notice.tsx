import type { ReactNode } from "react";

/**
 * The banner shape the non-skeleton states are built from: an optional bold lead-in, then the
 * sentence.
 *
 * The tones are status tones, never the directional pair. An error is AMBER here rather than
 * red, and that is not timidity: red means "price down" on this product, and a red block above a
 * table of price changes would be read as one.
 */
export function Notice({
  tone = "muted",
  label,
  children,
}: {
  tone?: "muted" | "error" | "stale" | "mock";
  /** Bold lead-in, e.g. "Dữ liệu giả lập:". */
  label?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <p className={`as-notice as-notice--${tone}`}>
      {label ? <span className="as-notice__label">{label}</span> : null}
      {children}
    </p>
  );
}
