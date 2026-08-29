"use client";

import type { IndexHistoryResponse, MarketOverviewResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { ErrorState, LoadingState } from "@/components/states";
import { IndexQuote } from "./IndexChart";
import styles from "./MarketHome.module.css";
import { DASH, formatInt, formatPercent, formatTurnoverTy, signClass } from "./format";

/**
 * The board header: the index quote, the session's breadth, and what it traded.
 *
 * Replaces P10's six-card KPI grid, and the reason is hierarchy rather than taste. In a grid of
 * equal cards the index level, the ticker count and the session date all carry the same weight,
 * so the screen opens with no subject. Here the quote is the subject at 26px and everything else
 * annotates it at 11–13px — the arrangement a trading terminal uses, for the same reason.
 *
 * What it does NOT show is unchanged from D-19: there are no foreign-flow (khối ngoại) figures,
 * because nothing in this system collects that data and no column exists for it. Turnover,
 * breadth and the index move are what stand in their place.
 */
export function MarketBar({
  overview,
  index,
}: {
  overview: ResourceState<MarketOverviewResponse>;
  index: ResourceState<IndexHistoryResponse>;
}) {
  if (overview.kind === "loading") {
    return <LoadingState rows={2} label="Đang tải số liệu phiên" />;
  }
  if (overview.kind === "error") {
    return <ErrorState code={overview.code} message={overview.message} />;
  }

  const o = overview.data;
  // The three counts include only tickers WITH a ret_1d, so they need not sum to n_tickers.
  const counted = o.advancers + o.decliners + o.unchanged;
  const missing = o.n_tickers - o.n_with_return;
  const pct = (n: number): string => (counted > 0 ? `${(n / counted) * 100}%` : "0%");
  const daySign = signClass(o.index_ret_1d);

  return (
    <div className={styles.marketBar}>
      {/* The quote reads from the CHART's series, not from the overview, so the big number and
          the chart's right edge are the same number by construction. The overview's own
          index_close is still used below as the session line — the two agree, and where they
          would not, the reason is a stale panel and it should be visible. */}
      {index.kind === "data" ? (
        <IndexQuote state={index} />
      ) : (
        <div className={styles.symbolBlock}>
          <div className={styles.symbolName}>
            <span className={styles.symbolTicker}>{o.index_symbol ?? "Chỉ số"}</span>
          </div>
          <div className={styles.symbolQuote}>
            <span className={styles.symbolLevel}>{DASH}</span>
          </div>
        </div>
      )}

      <div className={styles.stat}>
        <span className={styles.statLabel}>±% phiên</span>
        <span className={`${styles.statValue} ${styles[daySign]}`}>
          {/* Null when no run is active — the symbol and its move both come from the run, never
              from a hard-coded 'VNINDEX'. A dash means "không có", not "không đổi". */}
          {o.index_ret_1d === null ? DASH : formatPercent(o.index_ret_1d)}
        </span>
      </div>

      <div className={styles.breadth}>
        <div
          className={styles.breadthBar}
          role="img"
          aria-label={`${o.advancers} mã tăng, ${o.unchanged} mã đứng giá, ${o.decliners} mã giảm`}
          title={
            missing > 0
              ? `Trên ${formatInt(o.n_with_return)} mã có tỷ suất sinh lợi. ${formatInt(missing)} mã chưa đủ lịch sử nên không thuộc nhóm nào.`
              : `Trên ${formatInt(o.n_with_return)} mã có tỷ suất sinh lợi.`
          }
        >
          <span className={styles.breadthUp} style={{ width: pct(o.advancers) }} />
          <span className={styles.breadthFlat} style={{ width: pct(o.unchanged) }} />
          <span className={styles.breadthDown} style={{ width: pct(o.decliners) }} />
        </div>
        <div className={styles.breadthLegend}>
          <span className={styles.pos}>
            <b>{formatInt(o.advancers)}</b> tăng
          </span>
          <span className={styles.flat}>
            <b>{formatInt(o.unchanged)}</b> đứng
          </span>
          <span className={styles.neg}>
            <b>{formatInt(o.decliners)}</b> giảm
          </span>
        </div>
      </div>

      <div className={styles.stat}>
        {/* close is in nghìn đồng, so turnover_value is too; formatTurnoverTy does the /1e6 in
            the one place it can be done. See format.ts for the full unit chain. */}
        <span className={styles.statLabel}>GT giao dịch</span>
        <span className={styles.statValue}>
          {formatTurnoverTy(o.total_turnover)}
          <span className={styles.statUnit}>tỷ đ</span>
        </span>
      </div>

      <div className={styles.stat}>
        <span className={styles.statLabel}>KL giao dịch</span>
        <span className={styles.statValue}>
          {formatInt(o.total_volume)}
          <span className={styles.statUnit}>cp</span>
        </span>
      </div>

      <div className={styles.stat}>
        <span className={styles.statLabel}>Số mã</span>
        <span className={styles.statValue}>{formatInt(o.n_tickers)}</span>
      </div>
    </div>
  );
}
