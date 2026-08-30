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
import { IndexChart, MarketBar, SectorTreemap, SessionBoard } from "@/components/market";
import { MockDataNotice } from "@/components/states";
import styles from "@/components/market/MarketHome.module.css";

/**
 * `/` — Tổng quan thị trường.
 *
 * Three blocks, laid out as a board rather than as a document: the index quote across the top,
 * the chart beside the sector map, and the session's ranked tables full width beneath.
 *
 * The split is 1.72 : 1, not 1 : 1. The chart is the subject and the treemap is context, and an
 * equal split would say they are equally important. It is the one proportion on this page chosen
 * by eye; every other size follows from what the panel holds.
 *
 * **All five hooks are called side by side, and that is load-bearing.** Each owns its own effect,
 * so calling them together issues five overlapping requests on mount. Chaining any of them —
 * rendering the treemap only once the overview resolves, say — would turn five concurrent
 * requests into five sequential ones against a pooler an ocean away. P9.6 measured that
 * difference on the ticker page at ~3.9 s versus ~1.2 s for four routes. Every block renders its
 * own loading, empty and error state, so a slow one never blanks a block that has already
 * arrived, and the layout never makes one block wait on another.
 *
 * The three pieces of state here rather than inside the panels that use them are exactly the
 * three that select what a hook FETCHES; a panel owning its own range would have to fetch inside
 * itself, and the paragraph above is about not doing that. The board's tab is not one of them and
 * lives in `SessionBoard`, because both its hooks run regardless of which tab is showing.
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
      <MockDataNotice isMock={isMock} />

      <MarketBar overview={overview} index={index} />

      <div className={styles.split}>
        <IndexChart state={index} range={range} onRangeChange={setRange} />
        <SectorTreemap state={sectors} />
      </div>

      <SessionBoard
        movers={movers}
        liquidity={liquidity}
        direction={direction}
        horizon={horizon}
        onDirectionChange={setDirection}
        onHorizonChange={setHorizon}
        sessionDate={sessionDate}
        marketTurnover={marketTurnover}
      />
    </div>
  );
}
