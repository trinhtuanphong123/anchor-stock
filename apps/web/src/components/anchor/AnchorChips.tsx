"use client";

import Link from "next/link";
import { fbarAdjusted, type AnchorsResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { ErrorState, LoadingState } from "@/components/states";
import ui from "@/components/ui.module.css";
import { formatDecimal, formatInt } from "@/components/market/format";

/**
 * The published anchors, as a chip row plus a summary table.
 *
 * `/api/anchors` returns all 15 selection steps; the published cut is `in_published_set`, and the
 * filter happens here at the display edge — the route publishes the facts, the screen chooses
 * which to show.
 *
 * The five unpublished steps are shown separately rather than dropped. They are the algorithm's
 * next choices, and a reader comparing k=10 against k=15 can see what the eleventh through
 * fifteenth would have been. They carry no group statistics, which is stated rather than rendered
 * as zeros.
 *
 * **That comparison is exactly why F̄ cannot stand alone here.** Reading F̄ down the step column is
 * a comparison across different k, and raw F̄ is not comparable across k: F carries one tautological
 * self-cover term per anchor, so the figure rises with k for free. F̄_adj removes them, and D-26
 * requires the pair. `nTickers` is the universe size the adjustment needs; it comes from the active
 * run, which the screen fetches (see `app/anchors/page.tsx`), and is null until that resolves.
 */
export function AnchorChips({
  state,
  selected,
  nTickers,
}: {
  state: ResourceState<AnchorsResponse>;
  selected: string | null;
  nTickers: number | null;
}) {
  if (state.kind === "loading") return <LoadingState rows={4} label="Đang tải điểm neo" />;
  if (state.kind === "error") return <ErrorState code={state.code} message={state.message} />;

  const published = state.data.anchors.filter((a) => a.in_published_set);
  const rest = state.data.anchors.filter((a) => !a.in_published_set);

  return (
    <section className={ui.section} aria-label="Danh sách điểm neo">
      <div className={ui.sectionHead}>
        <h2 className={ui.sectionTitle}>{published.length} mã điểm neo</h2>
        <span className={ui.sectionNote}>Chọn một mã để xem nhóm được đại diện</span>
      </div>

      <div className={ui.chips}>
        {published.map((a) => (
          <Link
            key={a.anchor_ticker}
            href={`/anchors/?a=${a.anchor_ticker}`}
            className={`${ui.chip} ${selected === a.anchor_ticker ? ui.chipActive : ""}`}
            aria-current={selected === a.anchor_ticker ? "page" : undefined}
          >
            {a.anchor_ticker}
          </Link>
        ))}
      </div>

      <div className={ui.tableWrap}>
        <table className={ui.table}>
          <thead>
            <tr>
              <th scope="col">Mã</th>
              <th scope="col">Tên công ty</th>
              <th scope="col">Ngành</th>
              <th scope="col" className={ui.numeric}>Số mã đại diện</th>
            </tr>
          </thead>
          <tbody>
            {published.map((a) => (
              <tr key={a.anchor_ticker}>
                <td className={ui.ticker}>
                  <Link className={ui.link} href={`/anchors/?a=${a.anchor_ticker}`}>
                    {a.anchor_ticker}
                  </Link>
                </td>
                <td className={ui.company}>{a.company_name ?? "—"}</td>
                <td>{a.sector ?? "Khác"}</td>
                <td className={ui.numeric}>{formatInt(a.size)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {rest.length > 0 && (
        <details className={ui.statsDetails}>
          <summary className={ui.statsToggle}>
            {rest.length} mã được chọn tiếp theo (chưa công bố)
          </summary>
          <p className={ui.caption}>
            F̄(S) tính mỗi điểm neo tự phủ chính nó, nên nó tăng theo số bước một cách máy móc và
            không so sánh được giữa các mức k. F̄_adj đã trừ phần tự phủ — đó là độ phủ trên những
            mã <em>không</em> nằm trong tập neo, và là con số so sánh được.
          </p>
          <div className={ui.tableWrap}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th scope="col">Bước</th>
                  <th scope="col">Mã</th>
                  <th scope="col">Ngành</th>
                  <th scope="col" className={ui.numeric}>F̄(S)</th>
                  <th scope="col" className={ui.numeric}>F̄_adj</th>
                </tr>
              </thead>
              <tbody>
                {rest.map((a) => (
                  <tr key={a.anchor_ticker}>
                    <td className={ui.numeric}>{formatInt(a.step_k)}</td>
                    <td className={ui.ticker}>{a.anchor_ticker}</td>
                    <td>{a.sector ?? "Khác"}</td>
                    <td className={ui.numeric}>{formatDecimal(a.coverage_fbar, 4)}</td>
                    {/* step_k, not the run's published k: at step j the sum carries j tautological
                        terms and averages over N − j non-anchors. */}
                    <td className={ui.numeric}>
                      {formatDecimal(fbarAdjusted(a.coverage_f, a.step_k, nTickers), 4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}
