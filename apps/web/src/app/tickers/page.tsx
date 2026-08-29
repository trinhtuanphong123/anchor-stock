"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTickers } from "@/hooks/dashboard";
import { LoadingState } from "@/components/states";
import { TickerList } from "@/components/ticker/TickerList";
import { TickerDetail } from "@/components/ticker/TickerDetail";
import ui from "@/components/ui.module.css";

/**
 * `/tickers/` — the list, or one ticker when `?t=` is present.
 *
 * One route for both, by necessity and then by preference. `output: "export"` cannot export a
 * `[ticker]` segment from a client component, because `generateStaticParams` is a server-side
 * export and every screen here is `"use client"` (P10 S4). The alternative — a server wrapper
 * enumerating the universe from a committed file at build time — buys prettier URLs at the cost
 * of a real failure mode: the file drifting from the active run's universe would 404 a valid
 * ticker until someone rebuilt.
 *
 * `useSearchParams` forces the whole subtree into a Suspense boundary under static export. Without
 * one, `next build` fails outright — which is the right moment to find out.
 */
export default function TickersPage() {
  return (
    <Suspense fallback={<LoadingState rows={8} label="Đang tải" />}>
      <TickersScreen />
    </Suspense>
  );
}

function TickersScreen() {
  const params = useSearchParams();
  const selected = (params.get("t") ?? "").trim().toUpperCase();

  const list = useTickers();
  const isMock = list.kind === "data" && list.isMock;

  if (selected !== "") {
    return (
      <div className={ui.page}>
        <p className={ui.caption}>
          <Link className={ui.link} href="/tickers/">
            ← Tất cả cổ phiếu
          </Link>
        </p>
        <TickerDetail ticker={selected} />
      </div>
    );
  }

  return (
    <div className={ui.page}>
      {isMock && (
        <p className={ui.mockBanner}>
          <strong>Dữ liệu giả lập.</strong> Chưa cấu hình <code>NEXT_PUBLIC_API_BASE_URL</code>,
          nên trang đang hiển thị fixture cục bộ — không phải số liệu thật từ Supabase.
        </p>
      )}
      <TickerList state={list} />
    </div>
  );
}
