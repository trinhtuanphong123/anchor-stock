"use client";

import {
  MOVER_RET_FIELD,
  type MoverDirection,
  type MoverHorizon,
  type MoverRow,
  type MoversResponse,
} from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import styles from "./MarketHome.module.css";
import {
  formatDate,
  formatDecimal,
  formatInt,
  formatPercent,
  formatTurnoverTy,
  signClass,
} from "./format";

/**
 * Top movers, ranked at one of five horizons in one direction.
 *
 * The ordering and the cut are the API's, not this component's — `v_top_movers` is deliberately
 * unordered and unlimited so "which horizon, which direction, how many" stays the caller's
 * question. This renders what it is given, in the order it is given, and marks WHICH column the
 * order came from. That mark is the part worth getting right: five return columns with no
 * indication of which one is sorted is a table that looks ranked by whichever column the reader
 * happens to look at first.
 */

const DIRECTIONS: Array<{ value: MoverDirection; label: string; cls: string }> = [
  { value: "up", label: "Tăng", cls: styles.segmentUp },
  { value: "down", label: "Giảm", cls: styles.segmentDown },
];

/**
 * The five horizons, with the SESSION COUNT each one actually means.
 *
 * The subtitle carries that count rather than hiding it. "1M" is 20 sessions and "1Y" is 252 —
 * trading conventions, not calendar arithmetic — and a reader comparing this table against a
 * broker's own screen deserves to know which convention produced the number.
 */
const HORIZONS: Array<{ value: MoverHorizon; label: string; sessions: string }> = [
  { value: "1d", label: "1D", sessions: "1 phiên" },
  { value: "5d", label: "5D", sessions: "5 phiên" },
  { value: "1m", label: "1M", sessions: "20 phiên" },
  { value: "3m", label: "3M", sessions: "60 phiên" },
  { value: "1y", label: "1N", sessions: "252 phiên" },
];

const COLUMNS: Array<{ horizon: MoverHorizon; label: string }> = HORIZONS.map((h) => ({
  horizon: h.value,
  label: h.label,
}));

/** Largest absolute value across the visible rows at the ranked horizon, for the inline bars. */
function barScale(rows: MoverRow[], horizon: MoverHorizon): number {
  const field = MOVER_RET_FIELD[horizon];
  let max = 0;
  for (const r of rows) {
    const v = r[field];
    if (typeof v === "number" && Number.isFinite(v)) max = Math.max(max, Math.abs(v));
  }
  return max;
}

export function MoversTable({
  state,
  direction,
  horizon,
  onDirectionChange,
  onHorizonChange,
  sessionDate,
}: {
  state: ResourceState<MoversResponse>;
  direction: MoverDirection;
  horizon: MoverHorizon;
  onDirectionChange: (next: MoverDirection) => void;
  onHorizonChange: (next: MoverHorizon) => void;
  sessionDate: string | null;
}) {
  const active = HORIZONS.find((h) => h.value === horizon) ?? HORIZONS[0];

  return (
    <section className={styles.panel} aria-label="Top cổ phiếu biến động mạnh">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>
          Biến động mạnh nhất
          <span className={styles.statUnit}>{active.sessions}</span>
        </h2>

        <div style={{ display: "flex", gap: "var(--space-5)", alignItems: "center", flexWrap: "wrap" }}>
          <div className={styles.tabs} role="group" aria-label="Khoảng biến động">
            {HORIZONS.map((h) => (
              <button
                key={h.value}
                type="button"
                className={`${styles.tab} ${horizon === h.value ? styles.tabActive : ""}`}
                aria-pressed={horizon === h.value}
                onClick={() => onHorizonChange(h.value)}
              >
                {h.label}
              </button>
            ))}
          </div>

          <div className={styles.segment} role="group" aria-label="Chiều biến động">
            {DIRECTIONS.map((d) => (
              <button
                key={d.value}
                type="button"
                className={`${styles.segmentOpt} ${d.cls}`}
                aria-pressed={direction === d.value}
                onClick={() => onDirectionChange(d.value)}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.panelBodyFlush}>
        {state.kind === "loading" && <LoadingState rows={10} label="Đang tải danh sách" />}
        {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}

        {state.kind === "data" && state.data.movers.length === 0 && (
          <EmptyState
            scope="Ghi chú"
            message={`Chưa mã nào có tỷ suất sinh lợi ${active.sessions} để xếp hạng.`}
          />
        )}

        {state.kind === "data" && state.data.movers.length > 0 && (
          <MoversBody rows={state.data.movers} horizon={horizon} sessionDate={sessionDate} />
        )}
      </div>

      {horizon === "1y" && state.kind === "data" && (
        <p className={styles.footnote}>
          Mã có dưới 253 phiên lịch sử không có TSSL 252 phiên và không được xếp hạng ở mốc này —
          ô trống là “chưa tính được”, không phải 0%.
        </p>
      )}
    </section>
  );
}

function MoversBody({
  rows,
  horizon,
  sessionDate,
}: {
  rows: MoverRow[];
  horizon: MoverHorizon;
  sessionDate: string | null;
}) {
  const scale = barScale(rows, horizon);

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
            <th scope="col" className={styles.numeric}>KL</th>
            <th scope="col" className={styles.numeric}>GT (tỷ)</th>
            {COLUMNS.map((c) => (
              <th
                key={c.horizon}
                scope="col"
                className={styles.numeric}
                // The sorted column is announced, not merely tinted — a screen reader gets the
                // same "this is the ranking" cue the inline bar gives a sighted reader.
                aria-sort={c.horizon === horizon ? "other" : undefined}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((m, i) => {
            // A ticker that stopped trading keeps its last indicator date. Marking it is the
            // difference between a stale row and a row that looks like today's.
            const isStale = sessionDate !== null && m.bar_date < sessionDate;
            return (
              <tr key={m.ticker}>
                <td className={styles.rank}>{i + 1}</td>
                <td className={styles.ticker}>
                  {m.ticker}
                  {isStale && (
                    <span
                      className={styles.stale}
                      title={`Dữ liệu cũ hơn phiên hiện tại — đến ${formatDate(m.bar_date)}`}
                    >
                      {" "}⚠
                    </span>
                  )}
                </td>
                <td className={styles.company} title={m.company_name ?? undefined}>
                  {m.company_name ?? "—"}
                </td>
                <td className={styles.sector}>{m.sector ?? "Khác"}</td>
                <td className={styles.numeric}>{formatDecimal(m.close_price)}</td>
                <td className={styles.numeric}>{formatInt(m.volume)}</td>
                <td className={styles.numeric}>{formatTurnoverTy(m.turnover_value)}</td>
                {COLUMNS.map((c) => {
                  const value = m[MOVER_RET_FIELD[c.horizon]] as number | null;
                  const ranked = c.horizon === horizon;
                  const sign = signClass(value);
                  const width =
                    ranked && scale > 0 && typeof value === "number" && Number.isFinite(value)
                      ? `${(Math.abs(value) / scale) * 100}%`
                      : "0%";
                  return (
                    <td
                      key={c.horizon}
                      className={[
                        styles.numeric,
                        styles[sign],
                        ranked ? styles.ranked : "",
                        ranked ? styles.barCell : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {ranked && (
                        <span
                          className={`${styles.bar} ${
                            sign === "neg" ? styles.barNeg : styles.barPos
                          }`}
                          style={{ width }}
                          aria-hidden="true"
                        />
                      )}
                      <span className={styles.barValue}>{formatPercent(value)}</span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
