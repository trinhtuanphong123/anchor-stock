"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useActiveModelRun, useAnchors } from "@/hooks/dashboard";
import { LoadingState, MockDataNotice } from "@/components/states";
import { AnchorCrumbs } from "@/components/anchor/AnchorCrumbs";
import { AnchorDetail } from "@/components/anchor/AnchorDetail";
import { AnchorRoster } from "@/components/anchor/AnchorRoster";
import styles from "@/components/anchor/Anchors.module.css";

/**
 * `/anchors/` — the published anchor set, and one anchor's group when `?a=` is present.
 *
 * Same query-string shape as `/tickers/`, for the same reason (P10 S4), and the same mandatory
 * `<Suspense>` boundary around `useSearchParams` under `output: "export"`.
 *
 * **Two states, never both at once.** The roster — the share donut over the ten groups, then the
 * roster table — until an anchor is picked; then that anchor's group, with the roster folded away
 * and a crumb row in its place. The group starts at the top of the screen instead of below a
 * table the reader is done with, and switching anchors is still one click.
 *
 * **Why the active run is fetched here.** `/api/anchors` publishes `coverage_f` and `step_k` per
 * selection step but neither the universe size nor τ: F̄_adj = (F − k)/(N − k) needs N, and the
 * orbit's threshold ring needs τ. Both sit on the run. Fetching it beside `/api/anchors` at the
 * screen rather than inside the blocks keeps the two calls in one component, which is what makes
 * them overlap instead of running in sequence (see `hooks/dashboard.ts`).
 *
 * It does mean this page issues a second `/api/model/active` — `ProvenanceStrip` in `AppChrome`
 * already issues one, as it does on `/about`. Both are one-row reads running in parallel, so the
 * cost is a request rather than latency. Collapsing them into one shared context belongs to
 * `AppChrome`, not here.
 */
export default function AnchorsPage() {
  return (
    <Suspense fallback={<LoadingState rows={6} label="Đang tải" />}>
      <AnchorsScreen />
    </Suspense>
  );
}

function AnchorsScreen() {
  const params = useSearchParams();
  const selected = (params.get("a") ?? "").trim().toUpperCase() || null;

  const anchors = useAnchors();
  const run = useActiveModelRun();

  // Both null while the run loads or fails, and both degrade rather than block: F̄_adj shows a
  // dash, and the orbit simply draws no threshold ring. A coverage figure computed against a
  // guessed N, or a ring drawn at a τ this system invented, would be worse than neither.
  const nTickers = run.kind === "data" ? run.data.n_tickers : null;
  const tau = run.kind === "data" ? run.data.tau : null;

  return (
    <div className={styles.screen}>
      <MockDataNotice isMock={anchors.kind === "data" && anchors.isMock} />

      {selected === null ? (
        <AnchorRoster state={anchors} />
      ) : (
        <>
          <AnchorCrumbs state={anchors} selected={selected} />
          <AnchorDetail anchor={selected} nTickers={nTickers} tau={tau} />
        </>
      )}
    </div>
  );
}
