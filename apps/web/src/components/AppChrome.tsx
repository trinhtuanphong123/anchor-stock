"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ProvenanceStrip from "./ProvenanceStrip";
import ThemeToggle from "./ThemeToggle";

/**
 * Application shell.
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
    <div className="app-shell">
      {/* Two rows, sticky as a unit (P11 S-layout). The sidebar this replaces held four links and
          then ~700px of empty column; navigation across the top gives that width back to the
          content, which is where the charts and tables need it. */}
      <header className="app-header" role="banner">
        <div className="app-header__top">
          <div className="app-header__brand">
            <span className="app-header__wordmark">Anchor Model</span>
            <span className="app-header__eyebrow">{meta.eyebrow}</span>
          </div>
          <div className="app-header__actions">
            <ThemeToggle />
          </div>
        </div>

        <nav className="tabbar" aria-label="Primary">
          {NAV_ITEMS.map(({ href, label }) => {
            const isActive =
              href === "/" ? normalized === "/" : normalized.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`tab${isActive ? " tab--active" : ""}`}
                aria-current={isActive ? "page" : undefined}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="content-well" id="main-content">
        {/* The page title left the header with the sidebar: repeating it beside a tab bar that
            already names the current screen said the same thing twice. It stays an <h1>, one per
            page, now at the head of the content it titles. */}
        <h1 className="page-heading">{meta.title}</h1>

        {children}
        {/* docs/04 §5 requires the active run's universe and as-of date on screen. Rendered
            here rather than by each screen so the requirement cannot be met on three pages
            out of four. */}
        <ProvenanceStrip />
      </main>
    </div>
  );
}
