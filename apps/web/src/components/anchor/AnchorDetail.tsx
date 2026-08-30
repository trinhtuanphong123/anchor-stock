"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { fbarAdjusted, type AnchorMember, type AnchorRow } from "@/lib/api";
import { useAnchorDetail } from "@/hooks/dashboard";
import {
  Badge,
  CompositionBars,
  DataTable,
  DefinitionList,
  Disclosure,
  DocPanel,
  type CompositionRow,
} from "@/components/ds";
import { CoverageOrbit } from "@/components/charts";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import {
  DASH,
  formatBillion,
  formatDecimal,
  formatInt,
  formatPercent,
  signClass,
} from "@/components/market/format";
import styles from "./Anchors.module.css";

/**
 * `/anchors/?a=X` — one anchor and the tickers it represents.
 *
 * Ordered by D-24: the group comes first — its shape, its sectors, its members — and the model's
 * own statistics sit behind a disclosure at the end. They are present because this screen is the
 * thesis's contribution and a reviewer will ask for them; they are last because a reader wanting
 * to know which stocks move with VIC should not have to read past ρ² to find out.
 *
 * The orbit draws coverage as DISTANCE from the anchor, which is what turns a column of 0.312s
 * into a shape: who sits close, who is out past τ, how uneven the spread is. It costs no request
 * of its own — the members are already here.
 */
export function AnchorDetail({
  anchor,
  nTickers,
  tau,
}: {
  anchor: string;
  /** Universe size N, for F̄_adj. Null until the active run resolves — the figure is then a dash. */
  nTickers: number | null;
  /** The run's coverage threshold. Null until the run resolves — the ring is then simply absent. */
  tau: number | null;
}) {
  const router = useRouter();
  const state = useAnchorDetail(anchor);

  if (state.kind === "loading") {
    return <LoadingState rows={6} label={`Đang tải nhóm ${anchor}`} />;
  }
  if (state.kind === "error") {
    return <ErrorState code={state.code} message={state.message} />;
  }

  const { anchor: row, members } = state.data;

  return (
    <section className="as-section" aria-label={`Nhóm được đại diện bởi ${row.anchor_ticker}`}>
      <div className="as-section__head">
        <h2 className="as-section__title">
          {row.anchor_ticker}
          {row.company_name ? ` — ${row.company_name}` : ""}
        </h2>
        <span className="as-section__note">
          {row.sector ?? "Khác"}
          {row.in_published_set && row.size !== null
            ? ` · nhóm ${formatInt(row.size)}${nTickers === null ? "" : ` / ${formatInt(nTickers)}`} mã`
            : ""}
        </span>
      </div>

      {/* An anchor past the published cut has no group: `model_groups` holds no row for it, so
          size/f_j/rho2_* are null and the member list is empty. That is the truth, not a missing
          join, and it must not read as a group of size zero. The roster no longer offers steps
          past the cut, so this is reached only by a typed URL — and it still has to be honest. */}
      {!row.in_published_set ? (
        <DocPanel>
          <p className="as-caption">
            Mã này được thuật toán chọn ở bước thứ <strong>{formatInt(row.step_k)}</strong>, ngoài
            tập điểm neo được công bố — nên chưa có nhóm nào được gán cho nó.
          </p>
        </DocPanel>
      ) : members.length === 0 ? (
        <EmptyState scope="Nhóm" message="Chưa có mã nào được gán vào nhóm này." />
      ) : (
        <>
          <DocPanel label={`Độ phủ quanh ${row.anchor_ticker}`}>
            <h3 className="as-panel__title">Độ phủ quanh {row.anchor_ticker}</h3>
            {/* No micro note over this one. The orbit's own foot already reads "càng gần tâm, độ
                phủ càng cao" while nothing is pointed at, and repeating it in the head would put
                the same sentence twice in one panel. */}
            <div className={styles.orbit}>
              <CoverageOrbit
                anchor={row.anchor_ticker}
                threshold={tau}
                onSelect={(t) => router.push(`/tickers/?t=${t}`)}
                members={members.map((m) => ({
                  ticker: m.ticker,
                  coverage: m.coverage_c,
                  sector: m.sector,
                }))}
              />
              <p className="as-caption">
                Khoảng cách tới tâm là độ phủ c_i, không phải khoảng cách về giá. Mỗi chấm là một
                mã trong nhóm; điểm neo ở tâm vì nó tự phủ chính nó ở mức 1 và không bao giờ là một
                chấm.
                {tau === null
                  ? " Chưa đọc được ngưỡng τ của lần chạy, nên hình không vẽ vòng ngưỡng."
                  : ` Vòng nét đứt là ngưỡng τ = ${formatDecimal(tau, 2)}; mã nằm ngoài nó được điểm neo đại diện yếu.`}
              </p>
            </div>
          </DocPanel>

          <SectorComposition members={members} />
          <MemberTable members={members} />
        </>
      )}

      <GroupStats row={row} nTickers={nTickers} />
    </section>
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
 * check into a circular argument. Hence the note above the bars, verbatim.
 *
 * The bars are the accent, never green or red: this is composition, and colour on a figure in
 * this product means the direction a price moved.
 */
function SectorComposition({ members }: { members: AnchorMember[] }) {
  const counts = new Map<string, number>();
  for (const m of members) {
    const key = m.sector ?? "Khác";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const rows: CompositionRow[] = [...counts.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));

  return (
    <DocPanel label="Thành phần ngành">
      <h3 className="as-panel__title">Thành phần ngành</h3>
      <span className="as-section__note">
        Đối chiếu độc lập — ngành không tham gia vào việc chọn điểm neo
      </span>
      <CompositionBars rows={rows} total={members.length} />
    </DocPanel>
  );
}

/**
 * The group's members, in the coverage order the API returns them in.
 *
 * `coverage_c` takes the magnitude bar because the table IS sorted by it and because c_i is a
 * fraction in [0,1] — the one figure on this screen a proportional bar can honestly draw. The bar
 * is the accent: coverage has no direction, and a green one would say the price rose.
 */
function MemberTable({ members }: { members: AnchorMember[] }) {
  return (
    <DataTable
      doc
      rankedKey="cov"
      barTone="neutral"
      getRowKey={(r) => String(r.ticker)}
      rows={members.map((m) => ({
        ticker: m.ticker,
        isAnchor: m.is_anchor === true,
        underTau: m.under_tau === true,
        company: m.company_name ?? DASH,
        sector: m.sector ?? "Khác",
        cov: formatDecimal(m.coverage_c, 3),
        cov__n: m.coverage_c,
        d1: formatPercent(m.ret_1d),
        d1__tone: signClass(m.ret_1d),
        d5: formatPercent(m.ret_5d),
        d5__tone: signClass(m.ret_5d),
        d20: formatPercent(m.ret_20d),
        d20__tone: signClass(m.ret_20d),
        turnover: formatBillion(m.turnover_value),
      }))}
      columns={[
        {
          key: "ticker",
          header: "Mã",
          cell: "as-ticker",
          render: (r) => (
            <>
              <Link className="as-link" href={`/tickers/?t=${r.ticker}`}>
                {String(r.ticker)}
              </Link>
              {r.isAnchor === true && (
                <>
                  {" "}
                  <Badge tone="anchor">Điểm neo</Badge>
                </>
              )}
            </>
          ),
        },
        { key: "company", header: "Tên công ty", cell: "as-company" },
        { key: "sector", header: "Ngành" },
        {
          key: "cov",
          header: "Độ phủ",
          align: "num",
          render: (r) => (
            <>
              {String(r.cov)}
              {r.underTau === true && (
                <>
                  {" "}
                  <Badge
                    tone="warn"
                    title="Độ phủ dưới ngưỡng τ của mô hình — điểm neo đại diện yếu cho mã này"
                  >
                    thấp
                  </Badge>
                </>
              )}
            </>
          ),
        },
        { key: "d1", header: "1 phiên", align: "num" },
        { key: "d5", header: "5 phiên", align: "num" },
        { key: "d20", header: "20 phiên", align: "num" },
        { key: "turnover", header: "GT GD (tỷ đ)", align: "num" },
      ]}
    />
  );
}

/**
 * The model's own figures for this group, kept behind a disclosure (D-24, S3).
 *
 * `f_j`, `coverage_f` and `marginal_gain` are sums of per-ticker coverage over a set larger than
 * one, so they are NOT fractions and are not bounded by 1 — F(S) reads 22.35 on the active run.
 * They are shown as plain decimals for exactly that reason: **a percentage bar on any of them
 * would draw a fraction that does not exist.** Only `rho2_mean`, `rho2_min`, F̄ and F̄_adj are in
 * [0,1], and only the members' c_i is drawn as one.
 *
 * **Two of these figures carry a tautology, and both are annotated rather than quietly shown.**
 * Because `P_jj = 1`, every anchor covers itself at exactly 1, so F contains one such term per
 * anchor and Δ contains exactly one for the candidate being added. The consequence is not
 * cosmetic: at the last steps Δ still reads near 1 while almost none of it is coverage of *other*
 * tickers. F̄_adj (D-26) removes the terms from the coverage figure, and it sits immediately
 * beside F̄ — never instead of it, and never without it: F̄ alone overstates coverage by about 60%
 * (0.2629 against 0.1646 on the active run). Δ keeps its published value; the label says what it
 * includes and the caption says how to read it.
 *
 * Δ is **not** shown as Δ − 1. That quantity is F_excl's own marginal gain and it goes negative
 * at the late steps (the selected row leaves the sum), which is correct on that scale and reads
 * as a bug on screen. The honest decomposition — Δ = (1 − c_v) + real cover — needs `c_v` as it
 * stood *before* the step, which neither the API nor the artifact serves; it lives in
 * `data/research/diagonal_curve_*.csv` and stays there.
 */
function GroupStats({ row, nTickers }: { row: AnchorRow; nTickers: number | null }) {
  return (
    <Disclosure summary="Chỉ số nhóm">
      <DefinitionList
        items={[
          { label: "Bước chọn", value: formatInt(row.step_k) },
          { label: "Số mã trong nhóm", value: formatInt(row.size) },
          { label: "f_j", value: formatDecimal(row.f_j, 4) },
          { label: "ρ² trung bình", value: formatDecimal(row.rho2_mean, 4) },
          { label: "ρ² nhỏ nhất", value: formatDecimal(row.rho2_min, 4) },
          { label: "Lợi ích biên Δ (gồm tự phủ)", value: formatDecimal(row.marginal_gain, 4) },
          { label: "F(S) tại bước này", value: formatDecimal(row.coverage_f, 4) },
          { label: "F̄(S) tại bước này", value: formatDecimal(row.coverage_fbar, 4) },
          // step_k, not the run's published k: at step j the sum carries j tautological terms
          // and averages over N − j non-anchors.
          {
            label: "F̄_adj tại bước này",
            value: formatDecimal(fbarAdjusted(row.coverage_f, row.step_k, nTickers), 4),
          },
        ]}
      />
      <p className="as-caption">
        Δ gồm đúng một đơn vị mà mã được chọn tự phủ chính nó, nên Δ xấp xỉ 1 có nghĩa là phần phủ
        thêm cho các mã <em>khác</em> gần bằng 0. Tương tự, F(S) chứa một số hạng tự phủ cho mỗi
        điểm neo; F̄_adj là F̄ sau khi trừ hết chúng.
      </p>
    </Disclosure>
  );
}
