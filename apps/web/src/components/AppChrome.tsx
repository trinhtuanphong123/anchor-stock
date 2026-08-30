"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ProvenanceStrip from "./ProvenanceStrip";
import ThemeToggle from "./ThemeToggle";

/**
 * Application shell, built from the design system's global `as-*` classes.
 *
 * The shell owns no CSS Module of its own any more: its form — the sticky two-row header, the
 * tab bar, the centred content well — is the design system's, and duplicating those rules under
 * a second set of names is what made the previous palette change a component-by-component edit.
 * CSS Modules stay for screen-local layout; the frame is shared.
 *
 * P8 reduced the navigation to the one route that existed; P10 builds the rest against the
 * anchor-model contract. Two of the Leiden-era routes never come back: `/pipeline` lost its
 * endpoint in P9 (`/api/pipeline/status` had no consumer — freshness is the provenance strip
 * instead), and `/methodology` is replaced by a much shorter `/about` under D-24.
 *
 * The detail screens live at `/tickers/?t=VCB` and `/anchors/?a=VCB` rather than at a `[param]`
 * segment: `output: "export"` cannot export a dynamic route from a client component, and every
 * screen here is one. `isActive` therefore matches on the pathname only, so a ticker detail page
 * still highlights its list entry.
 */
const NAV_ITEMS = [
  { href: "/", label: "Tổng quan thị trường" },
  { href: "/tickers", label: "Cổ phiếu" },
  { href: "/anchors", label: "Điểm neo" },
  { href: "/about", label: "Giới thiệu" },
] as const;

const PAGE_META: Record<string, { eyebrow: string; title: string }> = {
  "/": { eyebrow: "Mô hình điểm neo — HOSE", title: "Tổng quan thị trường" },
  "/tickers": { eyebrow: "Mô hình điểm neo — HOSE", title: "Cổ phiếu" },
  "/anchors": { eyebrow: "Mô hình điểm neo — HOSE", title: "Điểm neo" },
  "/about": { eyebrow: "Mô hình điểm neo — HOSE", title: "Giới thiệu" },
};

export default function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // trailingSlash: true means the path arrives as "/" or "/route/"; normalise before lookup.
  const normalized =
    pathname !== "/" && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;

  const meta = PAGE_META[normalized] ?? {
    eyebrow: "Mô hình điểm neo — HOSE",
    title: "Tổng quan thị trường",
  };

  return (
    <div className="as-shell">
      {/* Two rows, sticky as a unit (P11 S-layout). The sidebar this replaces held four links and
          then ~700px of empty column; navigation across the top gives that width back to the
          content, which is where the charts and tables need it. */}
      <header className="as-header" role="banner">
        <div className="as-header__top">
          <div className="as-header__brand">
            {/* The product has no logo mark. The brand is this word, set in Roboto Medium. */}
            <span className="as-wordmark">Anchor Stock</span>
            <span className="as-eyebrow">{meta.eyebrow}</span>
          </div>
          <div className="as-header__actions">
            <ThemeToggle />
          </div>
        </div>

        {/* Links rather than the design system's buttons: these are real routes, and a button
            would cost middle-click, copy-link and the browser's own history. `.as-navtab` styles
            either element. */}
        <nav className="as-tabbar" aria-label="Primary">
          {NAV_ITEMS.map(({ href, label }) => {
            const isActive =
              href === "/" ? normalized === "/" : normalized.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`as-navtab${isActive ? " as-navtab--active" : ""}`}
                aria-current={isActive ? "page" : undefined}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="as-well" id="main-content">
        {/* The page title left the header with the sidebar: repeating it beside a tab bar that
            already names the current screen said the same thing twice. It stays an <h1>, one per
            page, now at the head of the content it titles. */}
        <h1 className="as-page-heading">{meta.title}</h1>

        {children}
        {/* docs/04 §5 requires the active run's universe and as-of date on screen. Rendered
            here rather than by each screen so the requirement cannot be met on three pages
            out of four. */}
        <ProvenanceStrip />
      </main>
    </div>
  );
}
