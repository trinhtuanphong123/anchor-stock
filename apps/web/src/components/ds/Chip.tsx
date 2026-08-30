import type { ReactNode } from "react";

/**
 * Mono pill holding a ticker symbol. Always Roboto Mono: a chip holds a symbol, and symbols line
 * up. Active is a filled accent.
 *
 * Rendered as a link when it navigates and as a button when it only changes local selection —
 * the anchor picker on `/anchors` writes a query string, so it wants the link form and the
 * middle-click, copy-link and history that come with it.
 */
export function Chip({
  children,
  active = false,
  onClick,
  href,
  title,
}: {
  children?: ReactNode;
  active?: boolean;
  onClick?: () => void;
  /** Present ⇒ renders an anchor rather than a button. */
  href?: string;
  title?: string;
}) {
  const className = `as-chip${active ? " as-chip--active" : ""}`;
  if (href !== undefined) {
    return (
      <a className={className} href={href} title={title} aria-current={active ? "page" : undefined}>
        {children}
      </a>
    );
  }
  return (
    <button
      type="button"
      className={className}
      onClick={onClick}
      title={title}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}

/** Wrapping row for a set of {@link Chip}s. */
export function ChipRow({ children }: { children?: ReactNode }) {
  return <div className="as-chips">{children}</div>;
}
