"use client";

import type { LiquidityResponse, MoverRow } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import styles from "./MarketHome.module.css";
import {
  DASH,
  formatDate,
  formatDecimal,
  formatInt,
  formatPercent,
  formatTurnoverTy,
  signClass,
} from "./format";

/**
 * Thanh khoản — the session's most heavily traded names, by turnover value.
 *
 * The session this ranks is `session_date` from the response, which is `v_latest_session`: the
 * SAME session the index chart's right edge and the movers table sit on. That is the alignment
 * the screen promises by putting the three panels together, and it is why the caption names the
 * date instead of saying "hôm nay" — a database loaded to Tuesday should say Tuesday.
 *
 * Two figures are computed here rather than served, and both are shares of a total that is
 * already on the page, not new measurements: each row's share of the visible turnover, and the
 * running cumulative share. Neither is a claim about the market as a whole — the denominator is
 * the ten rows shown, and the footnote says so.
 */

export function LiquidityTable({
  state,
  marketTurnover,
}: {
  state: ResourceState<LiquidityResponse>;
  /** Total session turnover from /api/market/overview, in nghìn đồng. Null while it loads. */
  marketTurnover: number | null;
}) {
  const sessionDate = state.kind === "data" ? state.data.session_date : null;

  return (
    <section className={styles.panel} aria-label="Thanh khoản trong phiên">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>
          Thanh khoản
          <span className={styles.statUnit}>
            {sessionDate ? `phiên ${formatDate(sessionDate)}` : ""}
          </span>
        </h2>
        <span className={styles.panelNote}>Xếp theo giá trị giao dịch</span>
      </div>

      <div className={styles.panelBodyFlush}>
        {state.kind === "loading" && <LoadingState rows={10} label="Đang tải thanh khoản" />}
        {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}

        {state.kind === "data" && state.data.stocks.length === 0 && (
          <EmptyState scope="Ghi chú" message="Chưa có giá trị giao dịch nào cho phiên này." />
        )}

        {state.kind === "data" && state.data.stocks.length > 0 && (
          <LiquidityBody
            rows={state.data.stocks}
            sessionDate={sessionDate}
            marketTurnover={marketTurnover}
          />
        )}
      </div>

      {state.kind === "data" && state.data.stocks.length > 0 && (
        <p className={styles.footnote}>
          <strong>Tỷ trọng</strong> tính trên tổng GT giao dịch toàn thị trường trong phiên
          {marketTurnover === null ? " (chưa có tổng)" : ""}; <strong>luỹ kế</strong> là tổng
          tỷ trọng từ đầu bảng xuống dòng đó.
        </p>
      )}
    </section>
  );
}

function LiquidityBody({
  rows,
  sessionDate,
  marketTurnover,
}: {
  rows: MoverRow[];
  sessionDate: string | null;
  marketTurnover: number | null;
}) {
  /**
   * The denominator. The market total is preferred because it answers the question a reader
   * actually has — "how concentrated is the session" — while the visible sum only says how the
   * ten compare with each other. It falls back to the visible sum when the overview has not
   * arrived, and the header says which one is in force so the number is never ambiguous.
   */
  const visibleSum = rows.reduce((acc, r) => acc + (r.turnover_value ?? 0), 0);
  const denominator =
    marketTurnover !== null && Number.isFinite(marketTurnover) && marketTurnover > 0
      ? marketTurnover
      : visibleSum;

  let running = 0;
  const largest = rows.reduce((m, r) => Math.max(m, r.turnover_value ?? 0), 0);

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col" className={styles.rank}>#</th>
            <th scope="col">Mã</th>
            <th scope="col">Tên công ty</th>
            <th scope="col">Ngành</th>
            <th scope="col" className={styles.numeric}>Giá</th>
            <th scope="col" className={styles.numeric}>±% phiên</th>
            <th scope="col" className={styles.numeric}>KL</th>
            <th scope="col" className={styles.numeric}>GT (tỷ)</th>
            <th scope="col" className={styles.numeric}>Tỷ trọng</th>
            <th scope="col" className={styles.numeric}>Luỹ kế</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isStale = sessionDate !== null && r.bar_date < sessionDate;
            const share =
              r.turnover_value !== null && denominator > 0 ? r.turnover_value / denominator : null;
            if (share !== null) running += share;
            const width = largest > 0 ? `${((r.turnover_value ?? 0) / largest) * 100}%` : "0%";
            return (
              <tr key={r.ticker}>
                <td className={styles.rank}>{i + 1}</td>
                <td className={styles.ticker}>
                  {r.ticker}
                  {isStale && (
                    <span
                      className={styles.stale}
                      title={`Dữ liệu cũ hơn phiên hiện tại — đến ${formatDate(r.bar_date)}`}
                    >
                      {" "}⚠
                    </span>
                  )}
                </td>
                <td className={styles.company} title={r.company_name ?? undefined}>
                  {r.company_name ?? "—"}
                </td>
                <td className={styles.sector}>{r.sector ?? "Khác"}</td>
                <td className={styles.numeric}>{formatDecimal(r.close_price)}</td>
                <td className={`${styles.numeric} ${styles[signClass(r.ret_1d)]}`}>
                  {formatPercent(r.ret_1d)}
                </td>
                <td className={styles.numeric}>{formatInt(r.volume)}</td>
                {/* The bar is on the turnover column here, because turnover is what this table
                    is ranked by — the same rule the movers table follows for its own ranked
                    column. Neutral, not directional: money traded has no sign, and the green of
                    `.barPos` would have read as "up" on a column that cannot go up. */}
                <td className={`${styles.numeric} ${styles.ranked} ${styles.barCell}`}>
                  <span
                    className={`${styles.bar} ${styles.barNeutral}`}
                    style={{ width }}
                    aria-hidden="true"
                  />
                  <span className={styles.barValue}>{formatTurnoverTy(r.turnover_value)}</span>
                </td>
                <td className={styles.numeric}>
                  {share === null ? DASH : formatPercentPlain(share)}
                </td>
                <td className={`${styles.numeric} ${styles.flat}`}>
                  {share === null ? DASH : formatPercentPlain(running)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * A share as an UNSIGNED percent.
 *
 * `formatPercent` in `format.ts` uses `signDisplay: "exceptZero"`, which is right for a return
 * and wrong here: a share of turnover is never negative, and "+18,4%" would read as a gain. This
 * is the one place on the screen that needs the unsigned form, so it is defined at its point of
 * use rather than adding a second general formatter to a file whose whole purpose is to have
 * exactly one of each.
 */
const SHARE_FMT = new Intl.NumberFormat("vi-VN", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatPercentPlain(fraction: number): string {
  return Number.isFinite(fraction) ? SHARE_FMT.format(fraction) : DASH;
}
