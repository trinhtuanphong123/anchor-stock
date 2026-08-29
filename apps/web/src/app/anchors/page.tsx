"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useActiveModelRun, useAnchors } from "@/hooks/dashboard";
import { LoadingState } from "@/components/states";
import { AnchorChips } from "@/components/anchor/AnchorChips";
import { AnchorDetail } from "@/components/anchor/AnchorDetail";
import ui from "@/components/ui.module.css";

/**
 * `/anchors/` — the published anchors, and one anchor's group when `?a=` is present.
 *
 * Same query-string shape as `/tickers/`, for the same reason (P10 S4), and the same mandatory
 * `<Suspense>` boundary around `useSearchParams` under `output: "export"`.
 *
 * The chip row stays mounted while a detail is open, so switching anchors is one click and the
 * `/api/anchors` response is fetched once for the whole visit.
 *
 * **Why the active run is fetched here too.** `/api/anchors` publishes `coverage_f` and `step_k`
 * per selection step but not the universe size, and F̄_adj = (F − k)/(N − k) needs N. Fetching it
 * at the screen rather than inside `AnchorChips`/`AnchorDetail` keeps both calls in one component,
 * which is what makes them overlap instead of running in sequence (see `hooks/dashboard.ts`).
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
  const isMock = anchors.kind === "data" && anchors.isMock;

  // Null while the run loads or fails. The anchor tables still render; their F̄_adj cells show a
  // dash, because a coverage figure computed against a guessed N would be worse than no figure.
  const nTickers = run.kind === "data" ? run.data.n_tickers : null;

  return (
    <div className={ui.page}>
      {isMock && (
        <p className={ui.mockBanner}>
          <strong>Dữ liệu giả lập.</strong> Chưa cấu hình <code>NEXT_PUBLIC_API_BASE_URL</code>,
          nên trang đang hiển thị fixture cục bộ — không phải số liệu thật từ Supabase.
        </p>
      )}

      <AnchorChips state={anchors} selected={selected} nTickers={nTickers} />
      {selected && <AnchorDetail anchor={selected} nTickers={nTickers} />}
    </div>
  );
}
