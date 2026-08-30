"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AnchorRow, AnchorsResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { DataTable, DocPanel } from "@/components/ds";
import { AnchorShareDonut } from "@/components/charts";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { formatInt } from "@/components/market/format";

/**
 * The published anchor set: the partition it induces, then the roster itself.
 *
 * **`in_published_set` is the filter, and it happens here at the display edge.** `/api/anchors`
 * returns all 15 selection steps because the route publishes facts; the run publishes ten, and
 * steps 11–15 are not a shorter list of the same thing — they carry no group at all (`size`,
 * `f_j`, `rho2_*` are null past the cut). Showing them beside the ten invited exactly one
 * reading — comparing F̄ down the step column — that raw F̄ cannot support, since F carries one
 * tautological self-cover term per anchor and so rises with k for free.
 *
 * **One list, not two.** A chip row above a four-column table said the same ten symbols twice and
 * neither said more than the other. The table is the list: its rows carry the company, the sector
 * and the group size, and the whole row navigates.
 *
 * **The donut is a pie, and that is defensible here, which is rare.** The ten groups partition the
 * universe — every ticker is represented exactly once — so the arcs sum to the whole and a share
 * is a real share. It is also the one place the run's most striking result is visible: the largest
 * group is nearly five times the smallest, which a column of sizes states but does not show.
 *
 * Rows arrive in selection order and stay in it. Sorting them by size would read as a ranking the
 * model did not produce — step 1 is the greediest choice, not the biggest group by definition.
 */
export function AnchorRoster({ state }: { state: ResourceState<AnchorsResponse> }) {
  const router = useRouter();

  if (state.kind === "loading") return <LoadingState rows={6} label="Đang tải điểm neo" />;
  if (state.kind === "error") return <ErrorState code={state.code} message={state.message} />;

  const published = state.data.anchors.filter((a) => a.in_published_set);
  if (published.length === 0) {
    return (
      <EmptyState scope="Tập điểm neo" message="Lần chạy đang phục vụ chưa công bố điểm neo nào." />
    );
  }

  // Summed, not assumed: it is 85 for the active run, and a run over a different universe must
  // not be described with a number this screen hardcoded.
  const covered = published.reduce((sum, a) => sum + (a.size ?? 0), 0);
  const open = (ticker: string) => router.push(`/anchors/?a=${ticker}`);

  return (
    <section className="as-section" aria-label="Tập điểm neo được công bố">
      <div className="as-section__head">
        <h2 className="as-section__title">{published.length} mã điểm neo</h2>
        <span className="as-section__note">Chọn một mã để xem nhóm được đại diện</span>
      </div>

      <DocPanel label="Tỷ trọng rổ theo điểm neo">
        <h3 className="as-panel__title">Tỷ trọng rổ theo điểm neo</h3>
        <span className="as-section__note">
          Mỗi nhóm chiếm bao nhiêu phần trong {formatInt(covered)} mã được phân bổ
        </span>
        <AnchorShareDonut
          centerValue={formatInt(covered)}
          centerLabel="mã được đại diện"
          onSelect={open}
          slices={published.map((a) => ({
            label: a.anchor_ticker,
            value: a.size ?? 0,
            note: `${formatInt(a.size)} mã`,
          }))}
        />
        <p className="as-caption">
          Mười nhóm phủ kín rổ và không chồng lấn — mỗi mã thuộc đúng một nhóm — nên các phần cộng
          lại bằng toàn bộ {formatInt(covered)} mã. Màu ở đây là danh tính của nhóm, không phải
          chiều biến động giá.
        </p>
      </DocPanel>

      <DataTable
        doc
        getRowKey={(r) => String(r.ticker)}
        onRowClick={(r) => open(String(r.ticker))}
        rows={published.map((a: AnchorRow) => ({
          ticker: a.anchor_ticker,
          company: a.company_name ?? "—",
          sector: a.sector ?? "Khác",
          size: formatInt(a.size),
        }))}
        columns={[
          {
            key: "ticker",
            header: "Mã",
            cell: "as-ticker",
            render: (r) => (
              <Link className="as-link" href={`/anchors/?a=${r.ticker}`}>
                {String(r.ticker)}
              </Link>
            ),
          },
          { key: "company", header: "Tên công ty", cell: "as-company" },
          { key: "sector", header: "Ngành" },
          { key: "size", header: "Số mã đại diện", align: "num" },
        ]}
      />
    </section>
  );
}
