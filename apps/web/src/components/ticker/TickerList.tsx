"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { TickersResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import ui from "@/components/ui.module.css";
import {
  formatPercent,
  formatDecimal,
  signClass,
} from "@/components/market/format";

/**
 * `/tickers/` — the whole universe, searchable.
 *
 * One fetch, filtered in the browser. 85 rows is the entire universe and the API deliberately
 * does not paginate it, so a per-keystroke round trip would spend a request against a pooler an
 * ocean away to filter a list already in memory.
 *
 * Rows arrive in `position` order — the ordered universe pins every position in this system — and
 * that order is preserved unless the reader searches.
 */
export function TickerList({ state }: { state: ResourceState<TickersResponse> }) {
  const [query, setQuery] = useState("");

  // Depend on the resource state itself, not on a fresh `[]` computed each render — that array
  // has a new identity every time and would defeat the memo entirely.
  const rows = useMemo(
    () => (state.kind === "data" ? state.data.tickers : []),
    [state],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q === "") return rows;
    return rows.filter(
      (r) =>
        r.ticker.toLowerCase().includes(q) ||
        (r.company_name ?? "").toLowerCase().includes(q) ||
        (r.sector ?? "").toLowerCase().includes(q),
    );
  }, [rows, query]);

  return (
    <section className={ui.section} aria-label="Danh sách cổ phiếu">
      <div className={ui.controls}>
        <input
          type="search"
          className={ui.search}
          placeholder="Tìm theo mã, tên công ty hoặc ngành"
          aria-label="Tìm cổ phiếu"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {state.kind === "data" && (
          <span className={ui.count}>
            {filtered.length} / {rows.length} mã
          </span>
        )}
      </div>

      {state.kind === "loading" && <LoadingState rows={8} label="Đang tải danh sách mã" />}
      {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}

      {state.kind === "data" && filtered.length === 0 && (
        <EmptyState scope="Kết quả" message="Không có mã nào khớp với từ khoá này." />
      )}

      {state.kind === "data" && filtered.length > 0 && (
        <div className={ui.tableWrap}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th scope="col">Mã</th>
                <th scope="col">Tên công ty</th>
                <th scope="col">Ngành</th>
                <th scope="col">Điểm neo</th>
                <th scope="col" className={ui.numeric}>Độ phủ</th>
                <th scope="col" className={ui.numeric}>1 phiên</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.ticker}>
                  <td className={ui.ticker}>
                    <Link className={ui.link} href={`/tickers/?t=${r.ticker}`}>
                      {r.ticker}
                    </Link>
                    {r.is_anchor && (
                      <>
                        {" "}
                        <span className={`${ui.badge} ${ui.badgeAnchor}`}>Điểm neo</span>
                      </>
                    )}
                  </td>
                  <td className={ui.company}>{r.company_name ?? "—"}</td>
                  <td>{r.sector ?? "Khác"}</td>
                  <td className={ui.ticker}>
                    {r.anchor_ticker ? (
                      <Link className={ui.link} href={`/anchors/?a=${r.anchor_ticker}`}>
                        {r.anchor_ticker}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  {/* under_tau means this ticker's anchor represents it weakly. Marked, because
                      a coverage figure with no context reads as a score rather than a caveat. */}
                  <td className={ui.numeric}>
                    {formatDecimal(r.coverage_c, 3)}
                    {r.under_tau && (
                      <>
                        {" "}
                        <span
                          className={`${ui.badge} ${ui.badgeWarn}`}
                          title="Độ phủ dưới ngưỡng τ của mô hình — điểm neo đại diện yếu cho mã này"
                        >
                          thấp
                        </span>
                      </>
                    )}
                  </td>
                  <td className={`${ui.numeric} ${ui[signClass(r.ret_1d)]}`}>
                    {formatPercent(r.ret_1d)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
