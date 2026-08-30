"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { TickersResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { SearchInput } from "@/components/ds";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import styles from "./Tickers.module.css";

/**
 * The whole universe as a picker, above the ticker being read.
 *
 * **One fetch, filtered in the browser.** 85 rows is the entire universe and `/api/tickers` does
 * not paginate it, so a per-keystroke round trip would spend a request against a pooler an ocean
 * away to filter a list already in memory.
 *
 * Chips rather than the 85-row table this screen used to open with: the table stated six columns
 * about every ticker in the market to answer one question — which one am I reading next — and
 * pushed the ticker itself below the fold. A chip row answers that question in four rows of
 * pills and leaves the screen to its subject.
 *
 * Rows arrive in `position` order — the ordered universe pins every position in this system — and
 * that order is preserved; searching filters it, never re-ranks it.
 *
 * The chips are `next/link`, not plain anchors, and that is load-bearing: a full navigation would
 * refetch this list and the run parameters on every pick. A client transition changes `?t=` and
 * nothing else, so only the four per-ticker calls run again.
 */
export function TickerPicker({
  state,
  selected,
}: {
  state: ResourceState<TickersResponse>;
  selected: string;
}) {
  const [query, setQuery] = useState("");

  // Depend on the resource state itself, not on a fresh `[]` computed each render — that array
  // has a new identity every time and would defeat the memo entirely.
  const rows = useMemo(() => (state.kind === "data" ? state.data.tickers : []), [state]);

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
    <section className={styles.picker} aria-label="Chọn cổ phiếu">
      <SearchInput
        value={query}
        onChange={setQuery}
        placeholder="Tìm theo mã, tên công ty hoặc ngành"
        count={state.kind === "data" ? `${filtered.length} / ${rows.length} mã` : null}
      />

      {state.kind === "loading" && <LoadingState rows={3} label="Đang tải danh sách mã" />}
      {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}

      {state.kind === "data" &&
        (filtered.length === 0 ? (
          <EmptyState scope="Kết quả tìm" message="Không có mã nào khớp với từ khoá này." />
        ) : (
          <div className="as-chips">
            {filtered.map((r) => (
              <Link
                key={r.ticker}
                href={`/tickers/?t=${r.ticker}`}
                className={`as-chip${r.ticker === selected ? " as-chip--active" : ""}`}
                aria-current={r.ticker === selected ? "page" : undefined}
                title={
                  r.company_name
                    ? `${r.company_name}${r.sector ? ` · ${r.sector}` : ""}`
                    : undefined
                }
              >
                {r.ticker}
              </Link>
            ))}
          </div>
        ))}
    </section>
  );
}
