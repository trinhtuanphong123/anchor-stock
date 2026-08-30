import type { ReactNode } from "react";

/**
 * Two containers, deliberately not one.
 *
 * `Panel` is the board's block: a hairline card with a HEAD RAIL — title on the left, controls or
 * a micro note on the right, a rule under both — and a body that can run flush for a full-bleed
 * table. Every block on the market screen is one of these, and the rail is what lets a chart, a
 * treemap and a ranked table sit in a row and read as the same kind of object.
 *
 * `DocPanel` is the document screens' block: a padded box, no rail, no title slot. `/tickers` and
 * `/anchors` are read rather than scanned, and they run at a looser density on purpose.
 *
 * Merging them is the obvious-looking refactor and it is wrong in both directions: giving the
 * document box a rail adds a divider to prose that has nothing to divide, and giving the board
 * panel the box's padding puts a gutter between a table and the border it is supposed to reach.
 * The two densities disagree by design — see the layout rules in CLAUDE.md.
 *
 * Cards do not float. A 1px border on a tinted canvas is the whole elevation story; neither of
 * these takes a shadow.
 */
export function Panel({
  title,
  note,
  controls,
  children,
  flush = false,
  footnote,
  label,
}: {
  title?: ReactNode;
  /** Uppercase micro note on the right of the head rail, e.g. "Diện tích: GT · Màu: ±%". */
  note?: ReactNode;
  /** Controls on the right of the head rail — RangeTabs, SegmentedControl. Wins over `note`. */
  controls?: ReactNode;
  children?: ReactNode;
  /** Drop the body padding. Use it when the body is a table, so rows reach the border. */
  flush?: boolean;
  /** Hairline-separated caption under the body, for a caveat about the data. */
  footnote?: ReactNode;
  label?: string;
}) {
  const hasHead = title !== undefined || note !== undefined || controls !== undefined;
  return (
    <section
      className="as-panel"
      aria-label={label ?? (typeof title === "string" ? title : undefined)}
    >
      {hasHead && (
        <div className="as-panel__head">
          {title ? <h2 className="as-panel__title">{title}</h2> : <span />}
          {controls ?? (note ? <span className="as-panel__note">{note}</span> : null)}
        </div>
      )}
      <div className={flush ? "as-panel__body--flush" : "as-panel__body"}>{children}</div>
      {footnote ? <p className="as-panel__foot">{footnote}</p> : null}
    </section>
  );
}

/** The document screens' padded box. Not a `Panel` without a title — a different container. */
export function DocPanel({
  children,
  label,
}: {
  children?: ReactNode;
  label?: string;
}) {
  return (
    <section className="as-doc-panel" aria-label={label}>
      {children}
    </section>
  );
}
