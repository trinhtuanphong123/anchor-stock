"use client";

import { useState } from "react";
import type { IndexRange, MoverDirection, MoverHorizon } from "@/lib/api";
import {
  useIndexHistory,
  useMarketLiquidity,
  useMarketOverview,
  useMarketSectors,
  useTopMovers,
} from "@/hooks/dashboard";
import {
  IndexChart,
  LiquidityTable,
  MarketBar,
  MoversTable,
  SectorTreemap,
} from "@/components/market";
import styles from "@/components/market/MarketHome.module.css";

/**
 * `/` — Tổng quan thị trường.
 *
 * Five panels over five routes, laid out as a board rather than as a document: the index quote
 * across the top, the chart and the sector map side by side beneath it, then the two ranked
 * tables full width.
 *
 * The split is 1.72 : 1, not 1 : 1. The chart is the subject and the treemap is context, and an
 * equal split would say they are equally important. It is the one proportion on the page chosen
 * by eye; every other size follows from what the panel holds.
 *
 * **All five hooks are called side by side, and that is load-bearing.** Each owns its own effect,
 * so calling them together issues five overlapping requests on mount. Chaining any of them —
 * rendering the treemap only once the overview resolves, say — would turn five concurrent
 * requests into five sequential ones against a pooler an ocean away. P9.6 measured that
 * difference on the ticker page at ~3.9 s versus ~1.2 s for four routes.
 *
 * The three pieces of interactive state live here rather than inside the panels that use them,
 * because each one selects what its hook FETCHES; a panel owning its own range would have to
 * fetch inside itself, and the paragraph above is about not doing that.
 */
export default function MarketOverviewPage() {
  const [range, setRange] = useState<IndexRange>("1y");
  const [direction, setDirection] = useState<MoverDirection>("up");
  const [horizon, setHorizon] = useState<MoverHorizon>("1d");

  const overview = useMarketOverview();
  const index = useIndexHistory(range);
  const sectors = useMarketSectors();
  const movers = useTopMovers(direction, horizon, 10);
  const liquidity = useMarketLiquidity(10);

  // Used to mark rows whose latest indicator date is older than the session.
  const sessionDate = overview.kind === "data" ? overview.data.session_date : null;
  const marketTurnover = overview.kind === "data" ? overview.data.total_turnover : null;

  // Only reachable in local development with no API configured — every deployed build is
  // production-like and renders a visible error instead of mock data. Saying so on the page
  // matters: an unlabelled mock is indistinguishable from a working backend.
  const isMock = [overview, index, sectors, movers, liquidity].some(
    (s) => s.kind === "data" && s.isMock,
  );

  return (
    <div className={styles.board}>
      {isMock && (
        <p className={styles.mockBanner}>
          <strong>Dữ liệu giả lập.</strong> Chưa cấu hình <code>NEXT_PUBLIC_API_BASE_URL</code>,
          nên trang đang hiển thị fixture cục bộ — không phải số liệu thật từ Supabase.
        </p>
      )}

      <MarketBar overview={overview} index={index} />

      <div className={styles.split}>
        <IndexChart state={index} range={range} onRangeChange={setRange} />
        <SectorTreemap state={sectors} />
      </div>

      <MoversTable
        state={movers}
        direction={direction}
        horizon={horizon}
        onDirectionChange={setDirection}
        onHorizonChange={setHorizon}
        sessionDate={sessionDate}
      />

      <LiquidityTable state={liquidity} marketTurnover={marketTurnover} />
    </div>
  );
}
