"use client";

import type { IndexHistoryResponse, MarketOverviewResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { BreadthBar, StatBlock } from "@/components/ds";
import { ErrorState, LoadingState } from "@/components/states";
import { IndexQuote } from "./IndexChart";
import { DASH, formatInt, formatPercent, formatTrillion, signClass } from "./format";

/**
 * The board header: the index quote, the session's breadth, and what it traded.
 *
 * A symbol header, not a row of KPI cards. In a grid of equal cards the index level, the ticker
 * count and the session date all carry the same weight, so the screen opens with no subject. Here
 * the quote is the subject at the 26px mono step and everything else annotates it at 11–13px.
 *
 * What it does NOT show: there are no foreign-flow (khối ngoại) figures, because nothing in this
 * system collects that data and no column exists for it. Turnover, breadth and the index move are
 * what stand in their place.
 *
 * The two panels it draws from are INDEPENDENT. The quote reads the chart's own series so the big
 * number and the chart's right edge are the same number by construction; everything to its right
 * reads the overview. Either can still be loading while the other renders.
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
  // Tickers with no ret_1d belong to no group, so the three counts need not sum to n_tickers.
  // The bar says which denominator it is drawn over rather than leaving the gap unexplained.
  const missing = o.n_tickers - o.n_with_return;
  const note =
    missing > 0
      ? `Trên ${formatInt(o.n_with_return)} mã có tỷ suất sinh lợi. ${formatInt(missing)} mã chưa đủ lịch sử nên không thuộc nhóm nào.`
      : `Trên ${formatInt(o.n_with_return)} mã có tỷ suất sinh lợi.`;

  return (
    <div className="as-marketbar">
      <IndexQuote state={index} />

      <StatBlock
        label="±% phiên"
        // A dash means "không có", not "không đổi": index_ret_1d is null when no run is active.
        value={o.index_ret_1d === null ? DASH : formatPercent(o.index_ret_1d)}
        tone={signClass(o.index_ret_1d)}
      />

      <BreadthBar
        up={o.advancers}
        flat={o.unchanged}
        down={o.decliners}
        note={note}
      />

      {/* close is in nghìn đồng, so turnover_value is too; formatTrillion does the /1e9 in the one
          place it can be done. This is the whole-basket total, which is why it is the one figure
          on the board carried in nghìn tỷ đ rather than the per-row tỷ đ. See format.ts. */}
      <StatBlock label="GT giao dịch" value={formatTrillion(o.total_turnover)} unit="nghìn tỷ đ" />
      <StatBlock label="KL giao dịch" value={formatInt(o.total_volume)} unit="cp" />
      <StatBlock label="Số mã" value={formatInt(o.n_tickers)} />
    </div>
  );
}
