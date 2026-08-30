import type { ReactNode } from "react";

/**
 * Padded card around a hand-drawn SVG chart: title, an "as of" line, body.
 *
 * Form comes entirely from the global `as-chart-frame*` classes — this file contributes no CSS.
 * It is deliberately NOT the market board's `Panel`: a panel has a head RAIL with controls and a
 * rule under it, which is the density of a dashboard. `/tickers` is a document and its charts sit
 * in a quieter box, which is the same disagreement `Panel` and `DocPanel` already encode.
 *
 * `asOf` is the session the figures belong to, written as a subtitle rather than a caption
 * because on this screen the model's window and the price date are not the same day.
 */
export function ChartFrame({
  title,
  asOf,
  subtitle,
  children,
}: {
  title: string;
  /** Already formatted session date. Rendered as "Đến phiên DD/MM/YY". */
  asOf?: string | null;
  /** Wins over `asOf` when the frame has something more specific to say. */
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  const sub = subtitle ?? (asOf ? `Đến phiên ${asOf}` : null);
  return (
    <figure className="as-chart-frame">
      <div className="as-chart-frame__head">
        <span className="as-chart-frame__title">{title}</span>
        {sub ? <span className="as-chart-frame__sub">{sub}</span> : null}
      </div>
      <div>{children}</div>
    </figure>
  );
}
