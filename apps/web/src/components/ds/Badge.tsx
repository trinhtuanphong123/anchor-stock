import type { ReactNode } from "react";

/**
 * Uppercase micro pill: "Điểm neo", "độ phủ thấp", "dữ liệu cũ".
 *
 * The tones map to the STATUS token families — blue for identity, amber for below-τ or stale,
 * teal and green for the freshness pair — and never to price direction. That is the whole reason
 * the status palette is teal/amber/blue: on this product a green or red mark on a row would be
 * read as the direction that row's price moved, which is a claim a status badge does not make.
 */
export function Badge({
  children,
  tone = "default",
  title,
}: {
  children?: ReactNode;
  tone?: "default" | "anchor" | "warn" | "stable" | "fresh";
  title?: string;
}) {
  const variant = tone === "default" ? "" : ` as-badge--${tone}`;
  return (
    <span className={`as-badge${variant}`} title={title}>
      {children}
    </span>
  );
}
