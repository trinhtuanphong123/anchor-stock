"use client";

import Link from "next/link";
import { fbarAdjusted, type AnchorMember, type AnchorRow } from "@/lib/api";
import { useAnchorDetail } from "@/hooks/dashboard";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import ui from "@/components/ui.module.css";
import {
  DASH,
  formatDecimal,
  formatInt,
  formatPercent,
  formatTurnoverTy,
  signClass,
} from "@/components/market/format";

/**
 * `/anchors/?a=X` — one anchor and the tickers it represents.
 *
 * Ordered by D-24: the group comes first (who is in it, from which sectors, how strongly), and
 * the model's own statistics — `size`, `f_j`, `rho2_mean`, `rho2_min`, `marginal_gain` — sit in a
 * secondary panel at the end. They are present because this screen is the thesis's contribution
 * and a reviewer will ask for them; they are last because a reader wanting to know which stocks
 * move with VIC should not have to read past ρ² to find out.
 */
export function AnchorDetail({
  anchor,
  nTickers,
}: {
  anchor: string;
  nTickers: number | null;
}) {
  const state = useAnchorDetail(anchor);

  if (state.kind === "loading") {
    return <LoadingState rows={6} label={`Đang tải nhóm ${anchor}`} />;
  }
  if (state.kind === "error") {
    return <ErrorState code={state.code} message={state.message} />;
  }

  const { anchor: row, members } = state.data;

  return (
    <div className={ui.page}>
      <section className={ui.section}>
        <div className={ui.sectionHead}>
          <h2 className={ui.sectionTitle}>
            {row.anchor_ticker}
            {row.company_name ? ` — ${row.company_name}` : ""}
          </h2>
          <span className={ui.sectionNote}>{row.sector ?? "Khác"}</span>
        </div>

        {/* An anchor selected past the published cut has no group: model_groups holds no row for
            it, so size/f_j/rho2_* are null and the member list is empty. That is the truth, not a
            missing join, and it must not read as a group of size zero. */}
        {!row.in_published_set ? (
          <div className={ui.panel}>
            <p className={ui.caption}>
              Mã này được thuật toán chọn ở bước thứ <strong>{row.step_k}</strong>, ngoài{" "}
              <strong>10</strong> điểm neo được công bố — nên chưa có nhóm nào được gán cho nó.
            </p>
          </div>
        ) : (
          <>
            <SectorComposition members={members} />
            <MemberTable members={members} />
          </>
        )}
      </section>

      <GroupStats row={row} nTickers={nTickers} />
    </div>
  );
}

/**
 * Sector make-up of the group.
 *
 * **Derived from `members[].sector`, not from the API's `sector_composition`.** That field is `{}`
 * for every group of the active artifact — it is a deferred field by design
 * (`pipelines/artifact/schema.py:186`), never a computed one. When a future run populates it, the
 * published value wins over this derivation.
 *
 * **This is evidence, never an input.** Sector labels come from `stocks` and never entered the
 * similarity matrix or the greedy objective. That the groups line up with sectors at all is an
 * independent check on the method; describing it as something the model used would turn that
 * check into a circular argument.
 */
function SectorComposition({ members }: { members: AnchorMember[] }) {
  if (members.length === 0) return null;

  const counts = new Map<string, number>();
  for (const m of members) {
    const key = m.sector ?? "Khác";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const rows = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const total = members.length;

  return (
    <div className={ui.panel}>
      <h3 className={ui.panelTitle}>Thành phần ngành</h3>
      <span className={ui.sectionNote}>
        Đối chiếu độc lập — ngành không tham gia vào việc chọn điểm neo
      </span>
      <div className={ui.bars}>
        {rows.map(([sector, count]) => (
          <div key={sector} className={ui.barRow}>
            <span className={ui.barLabel}>{sector}</span>
            <span className={ui.barTrack}>
              <span
                className={ui.barFill}
                style={{ width: `${(count / total) * 100}%` }}
                aria-hidden="true"
              />
            </span>
            <span className={ui.barValue}>
              {count} / {total}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MemberTable({ members }: { members: AnchorMember[] }) {
  if (members.length === 0) {
    return <EmptyState scope="Nhóm" message="Chưa có mã nào được gán vào nhóm này." />;
  }

  return (
    <div className={ui.tableWrap}>
      <table className={ui.table}>
        <thead>
          <tr>
            <th scope="col">Mã</th>
            <th scope="col">Tên công ty</th>
            <th scope="col">Ngành</th>
            <th scope="col" className={ui.numeric}>Độ phủ</th>
            <th scope="col" className={ui.numeric}>1 phiên</th>
            <th scope="col" className={ui.numeric}>5 phiên</th>
            <th scope="col" className={ui.numeric}>20 phiên</th>
            <th scope="col" className={ui.numeric}>GT GD (tỷ đ)</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.ticker}>
              <td className={ui.ticker}>
                <Link className={ui.link} href={`/tickers/?t=${m.ticker}`}>
                  {m.ticker}
                </Link>
                {m.is_anchor && (
                  <>
                    {" "}
                    <span className={`${ui.badge} ${ui.badgeAnchor}`}>Điểm neo</span>
                  </>
                )}
              </td>
              <td className={ui.company}>{m.company_name ?? DASH}</td>
              <td>{m.sector ?? "Khác"}</td>
              <td className={ui.numeric}>
                {formatDecimal(m.coverage_c, 3)}
                {m.under_tau && (
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
              <td className={`${ui.numeric} ${ui[signClass(m.ret_1d)]}`}>
                {formatPercent(m.ret_1d)}
              </td>
              <td className={`${ui.numeric} ${ui[signClass(m.ret_5d)]}`}>
                {formatPercent(m.ret_5d)}
              </td>
              <td className={`${ui.numeric} ${ui[signClass(m.ret_20d)]}`}>
                {formatPercent(m.ret_20d)}
              </td>
              <td className={ui.numeric}>{formatTurnoverTy(m.turnover_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The model's own figures for this group, kept behind a disclosure (D-24, S3).
 *
 * `f_j` and `marginal_gain` are sums of per-ticker coverage over a set larger than one, so they
 * are NOT fractions and are not bounded by 1 — they are shown as plain decimals for that reason.
 * `rho2_mean` and `rho2_min` are.
 *
 * **Two of these figures carry a tautology, and both are annotated rather than quietly shown.**
 * Because `P_jj = 1`, every anchor covers itself at exactly 1, so F contains one such term per
 * anchor and Δ contains exactly one for the candidate being added. The consequence is not
 * cosmetic: at the last steps Δ still reads near 1 while almost none of it is coverage of *other*
 * tickers. F̄_adj (D-26) removes the terms from the coverage figure and is shown beside F̄, never
 * instead of it. Δ keeps its published value — the label says what it includes, and the caption
 * says how to read it.
 *
 * Δ is **not** shown as Δ − 1. That quantity is F_excl's own marginal gain and it goes negative
 * at the late steps (the selected row leaves the sum), which is correct on that scale and reads
 * as a bug on screen. The honest decomposition — Δ = (1 − c_v) + real cover — needs `c_v` as it
 * stood *before* the step, which neither the API nor the artifact serves; it lives in
 * `data/research/diagonal_curve_*.csv` and stays there.
 */
function GroupStats({ row, nTickers }: { row: AnchorRow; nTickers: number | null }) {
  const stats: Array<{ label: string; value: string }> = [
    { label: "Bước chọn", value: formatInt(row.step_k) },
    { label: "Số mã trong nhóm", value: formatInt(row.size) },
    { label: "f_j", value: formatDecimal(row.f_j, 4) },
    { label: "ρ² trung bình", value: formatDecimal(row.rho2_mean, 4) },
    { label: "ρ² nhỏ nhất", value: formatDecimal(row.rho2_min, 4) },
    { label: "Lợi ích biên Δ (gồm tự phủ)", value: formatDecimal(row.marginal_gain, 4) },
    { label: "F(S) tại bước này", value: formatDecimal(row.coverage_f, 4) },
    { label: "F̄(S) tại bước này", value: formatDecimal(row.coverage_fbar, 4) },
    // step_k, not the run's published k — this row's figures belong to a set of that size.
    {
      label: "F̄_adj tại bước này",
      value: formatDecimal(fbarAdjusted(row.coverage_f, row.step_k, nTickers), 4),
    },
  ];

  return (
    <details className={ui.statsDetails}>
      <summary className={ui.statsToggle}>Chỉ số nhóm</summary>
      <dl className={ui.defs}>
        {stats.map((s) => (
          <div key={s.label}>
            <dt className={ui.defTerm}>{s.label}</dt>
            <dd className={ui.defValue}>{s.value}</dd>
          </div>
        ))}
      </dl>
      <p className={ui.caption}>
        Δ gồm đúng một đơn vị mà mã được chọn tự phủ chính nó, nên Δ xấp xỉ 1 có nghĩa là phần phủ
        thêm cho các mã <em>khác</em> gần bằng 0. Tương tự, F(S) chứa một số hạng tự phủ cho mỗi
        điểm neo; F̄_adj là F̄ sau khi trừ hết chúng.
      </p>
    </details>
  );
}
