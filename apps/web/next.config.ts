import type { NextConfig } from "next";

/**
 * Static export (P8, D-21).
 *
 * `output: "export"` makes `next build` emit a plain `out/` directory instead of a server,
 * which is what lets the dashboard ship as a Render Static Site: free, never spun down, and
 * consuming none of the free tier's Web Service instance-hours. Every screen here is already
 * `"use client"` and fetches from the browser, so nothing is given up but SSR and ISR, neither
 * of which this dashboard uses.
 *
 * The constraint it imposes: a dynamic route cannot be exported from a client component,
 * because `generateStaticParams` is a server-side export. Any `[param]` route added in P10
 * needs either a server wrapper supplying the params or a query-string shape instead.
 *
 * `trailingSlash: true` makes each route resolve to `<route>/index.html`, so a deep link works
 * on a static host without a rewrite rule.
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
