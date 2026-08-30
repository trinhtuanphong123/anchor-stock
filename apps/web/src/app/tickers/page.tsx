"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useActiveModelRun, useTickers } from "@/hooks/dashboard";
import { LoadingState, MockDataNotice } from "@/components/states";
import { TickerDetail } from "@/components/ticker/TickerDetail";
import { TickerPicker } from "@/components/ticker/TickerPicker";
import styles from "@/components/ticker/Tickers.module.css";

/**
 * `/tickers/` — one ticker, with the universe as a picker above it.
 *
 * One route, by necessity and then by preference. `output: "export"` cannot export a `[ticker]`
 * segment from a client component, because `generateStaticParams` is a server-side export and
 * every screen here is `"use client"` (P10 S4). The alternative — a server wrapper enumerating
 * the universe from a committed file at build time — buys prettier URLs at the cost of a real
 * failure mode: the file drifting from the active run's universe would 404 a valid ticker until
 * someone rebuilt.
 *
 * `useSearchParams` forces the whole subtree into a Suspense boundary under static export.
 * Without one, `next build` fails outright — which is the right moment to find out.
 */
export default function TickersPage() {
  return (
    <Suspense fallback={<LoadingState rows={8} label="Đang tải" />}>
      <TickersScreen />
    </Suspense>
  );
}

/**
 * The ticker the screen opens on when the URL names none.
 *
 * VIC: the step-1 anchor and the largest published group, 19 of 85. Not `AAA`, which is only
 * first alphabetically, and not the session's most liquid name, which changes daily and would
 * make the default screen unstable from one visit to the next.
 */
const DEFAULT_TICKER = "VIC";

function TickersScreen() {
  const params = useSearchParams();
  const requested = (params.get("t") ?? "").trim().toUpperCase();
  const selected = requested === "" ? DEFAULT_TICKER : requested;

  // Both fetched ONCE for the visit, at the screen rather than inside the detail: picking another
  // ticker changes `?t=` and re-runs the four per-ticker calls, and neither of these is one of
  // them. `useTickers` feeds both the picker and the coverage orbit; the run carries τ, which is
  // the threshold ring the orbit draws.
  const universe = useTickers();
  const run = useActiveModelRun();
  const tau = run.kind === "data" ? run.data.tau : null;

  return (
    <div className={styles.screen}>
      <MockDataNotice isMock={universe.kind === "data" && universe.isMock} />
      <TickerPicker state={universe} selected={selected} />
      <TickerDetail ticker={selected} universe={universe} tau={tau} />
    </div>
  );
}
