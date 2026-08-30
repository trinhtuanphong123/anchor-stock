"use client";

import { useState } from "react";
import {
  MOVER_RET_FIELD,
  type LiquidityResponse,
  type MoverDirection,
  type MoverHorizon,
  type MoverRow,
  type MoversResponse,
} from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { DataTable, Panel, RangeTabs, SegmentedControl, type DataTableColumn } from "@/components/ds";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import {
  DASH,
  formatBillion,
  formatDecimal,
  formatInt,
  formatPercent,
  formatSession,
  formatShare,
  signClass,
} from "./format";

/**
 * The session's two ranked boards, in ONE panel with a tab.
 *
 * They were two stacked panels, and the merge is about what the reader is actually doing: both
 * rank the same 85 names over the same session, with seven of ten columns identical. Stacked,
 * comparing "biggest mover" against "most traded" meant scrolling past a full ten-row table and
 * losing the first one off the top. Tabbed, the two answers occupy the same rectangle and the
 * comparison is one click.
 *
 * **The tab is display state and lives here, not on the page.** That distinction is load-bearing:
 * the range, horizon and direction live on the page because each one selects what its hook
 * FETCHES, and a panel owning those would have to fetch inside itself. This one selects nothing —
 * BOTH hooks run in parallel from the page whichever tab is showing, so switching never waits on
 * a request and a slow liquidity response cannot blank the movers table.
 */

const BOARDS = [
  { value: "movers", label: "Biến động" },
  { value: "liquidity", label: "Thanh khoản" },
];

/**
 * The five horizons, with the SESSION COUNT each one actually means.
 *
 * The subtitle carries that count rather than hiding it. "1M" is 20 sessions and "1N" is 252 —
 * trading conventions, not calendar arithmetic — and a reader checking this table against a
 * broker's own screen deserves to know which convention produced the number.
 */
const HORIZONS: Array<{ value: MoverHorizon; label: string; sessions: string }> = [
  { value: "1d", label: "1D", sessions: "1 phiên" },
  { value: "5d", label: "5D", sessions: "5 phiên" },
  { value: "1m", label: "1M", sessions: "20 phiên" },
  { value: "3m", label: "3M", sessions: "60 phiên" },
  { value: "1y", label: "1N", sessions: "252 phiên" },
];

/** The identity columns both boards open with, in the order both use them. */
const IDENTITY: DataTableColumn[] = [
  { key: "__rank", header: "#" },
  {
    key: "ticker",
    header: "Mã",
    cell: "as-ticker",
    render: (r) => (
      <>
        {r.ticker as string}
        {r.stale ? (
          <span className="as-stale" title={r.staleTitle as string}>
            {" "}
            ⚠
          </span>
        ) : null}
      </>
    ),
  },
  { key: "company", header: "Tên công ty", cell: "as-company" },
  { key: "sector", header: "Ngành", cell: "as-sector" },
  { key: "price", header: "Giá", align: "num" },
  { key: "vol", header: "KL", align: "num" },
  { key: "gt", header: "GT (tỷ)", align: "num" },
];

/**
 * The shared head of a row: identity, the stale mark, and the three unsigned figures.
 *
 * A ticker that stopped trading keeps its last indicator date. Marking that is the difference
 * between a stale row and a row that looks like today's, which is why `sessionDate` is threaded
 * this far down instead of being assumed equal to every row's own `bar_date`.
 */
function identityCells(r: MoverRow, rank: number, sessionDate: string | null) {
  const stale = sessionDate !== null && r.bar_date < sessionDate;
  return {
    __rank: rank,
    ticker: r.ticker,
    stale,
    staleTitle: stale ? `Dữ liệu cũ hơn phiên hiện tại — đến ${formatSession(r.bar_date)}` : "",
    company: r.company_name ?? DASH,
    sector: r.sector ?? "Khác",
    price: formatDecimal(r.close_price, 2),
    vol: formatInt(r.volume),
    gt: formatBillion(r.turnover_value),
  };
}

export function SessionBoard({
  movers,
  liquidity,
  direction,
  horizon,
  onDirectionChange,
  onHorizonChange,
  sessionDate,
  marketTurnover,
}: {
  movers: ResourceState<MoversResponse>;
  liquidity: ResourceState<LiquidityResponse>;
  direction: MoverDirection;
  horizon: MoverHorizon;
  onDirectionChange: (next: MoverDirection) => void;
  onHorizonChange: (next: MoverHorizon) => void;
  /** The session the board ranks, from /overview. Rows older than it are marked stale. */
  sessionDate: string | null;
  /** Total session turnover from /overview, in nghìn đồng. Null while it loads. */
  marketTurnover: number | null;
}) {
  const [board, setBoard] = useState<string>("movers");
  const onMovers = board === "movers";
  const active = HORIZONS.find((h) => h.value === horizon) ?? HORIZONS[0];

  const liquiditySession = liquidity.kind === "data" ? liquidity.data.session_date : null;

  return (
    <Panel
      label={onMovers ? "Top cổ phiếu biến động mạnh" : "Thanh khoản trong phiên"}
      title={
        onMovers ? (
          <>
            Biến động mạnh nhất<span className="as-stat__unit">{active.sessions}</span>
          </>
        ) : (
          <>
            Thanh khoản phiên
            <span className="as-stat__unit">{formatSession(liquiditySession)}</span>
          </>
        )
      }
      controls={
        <div
          style={{
            display: "flex",
            gap: "var(--space-5)",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <SegmentedControl value={board} onChange={setBoard} label="Bảng" options={BOARDS} />
          {onMovers && (
            <>
              <RangeTabs
                value={horizon}
                onChange={(v) => onHorizonChange(v as MoverHorizon)}
                label="Khoảng biến động"
                options={HORIZONS.map((h) => ({ value: h.value, label: h.label }))}
              />
              <SegmentedControl
                tone="direction"
                value={direction}
                onChange={(v) => onDirectionChange(v as MoverDirection)}
                label="Chiều biến động"
                options={[
                  { value: "up", label: "Tăng" },
                  { value: "down", label: "Giảm" },
                ]}
              />
            </>
          )}
        </div>
      }
      flush
      footnote={
        onMovers ? (
          horizon === "1y" && movers.kind === "data" ? (
            <>
              Mã có dưới 253 phiên lịch sử không có TSSL 252 phiên và không được xếp hạng ở mốc
              này — ô trống là “chưa tính được”, không phải 0%.
            </>
          ) : null
        ) : liquidity.kind === "data" && liquidity.data.stocks.length > 0 ? (
          <>
            Xếp theo giá trị giao dịch. <strong>Tỷ trọng</strong> tính trên tổng GT giao dịch toàn
            thị trường trong phiên
            {marketTurnover === null ? " (chưa có tổng — tạm tính trên mười dòng hiển thị)" : ""};{" "}
            <strong>luỹ kế</strong> là tổng tỷ trọng từ đầu bảng xuống dòng đó.
          </>
        ) : null
      }
    >
      {onMovers ? (
        <MoversBoard state={movers} horizon={horizon} active={active} sessionDate={sessionDate} />
      ) : (
        <LiquidityBoard state={liquidity} marketTurnover={marketTurnover} />
      )}
    </Panel>
  );
}

/**
 * Top movers, ranked at one of five horizons in one direction.
 *
 * The ordering and the cut are the API's, not this component's — `v_top_movers` is deliberately
 * unordered and unlimited so "which horizon, which direction, how many" stays the caller's
 * question. This renders what it is given, in the order it is given, and MARKS which column the
 * order came from. That mark is the part worth getting right: five return columns with nothing
 * indicating which one is sorted is a table that looks ranked by whichever column the reader
 * happens to read first.
 */
function MoversBoard({
  state,
  horizon,
  active,
  sessionDate,
}: {
  state: ResourceState<MoversResponse>;
  horizon: MoverHorizon;
  active: (typeof HORIZONS)[number];
  sessionDate: string | null;
}) {
  if (state.kind === "loading") return <LoadingState rows={10} label="Đang tải danh sách" />;
  if (state.kind === "error") return <ErrorState code={state.code} message={state.message} />;
  if (state.data.movers.length === 0) {
    return (
      <EmptyState
        scope="Ghi chú"
        message={`Chưa mã nào có tỷ suất sinh lợi ${active.sessions} để xếp hạng.`}
      />
    );
  }

  const rows = state.data.movers.map((m, i) => {
    const row: Record<string, unknown> = identityCells(m, i + 1, sessionDate);
    for (const h of HORIZONS) {
      // Fractions straight from the API — formatPercent does the ×100, here and nowhere else.
      const v = m[MOVER_RET_FIELD[h.value]] as number | null;
      row[h.value] = formatPercent(v);
      row[`${h.value}__n`] = v;
      row[`${h.value}__tone`] = signClass(v);
    }
    return row;
  });

  const columns: DataTableColumn[] = [
    ...IDENTITY,
    ...HORIZONS.map((h) => ({ key: h.value, header: h.label, align: "num" as const })),
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rankedKey={horizon}
      getRowKey={(r) => r.ticker as string}
    />
  );
}

/**
 * Thanh khoản — the session's most heavily traded names, by turnover value.
 *
 * Two figures are computed here rather than served, and both are shares of a total already on the
 * page, not new measurements: each row's share of session turnover, and the running cumulative
 * share. The denominator is the market total when /overview has arrived and the visible sum when
 * it has not, and the footnote says which is in force so the number is never ambiguous.
 *
 * The magnitude bar sits on the turnover column and is NEUTRAL, not directional: money traded has
 * no sign, and green there would read as "up" on a column that cannot go up or down.
 */
function LiquidityBoard({
  state,
  marketTurnover,
}: {
  state: ResourceState<LiquidityResponse>;
  marketTurnover: number | null;
}) {
  if (state.kind === "loading") return <LoadingState rows={10} label="Đang tải thanh khoản" />;
  if (state.kind === "error") return <ErrorState code={state.code} message={state.message} />;
  if (state.data.stocks.length === 0) {
    return <EmptyState scope="Ghi chú" message="Chưa có giá trị giao dịch nào cho phiên này." />;
  }

  const stocks = state.data.stocks;
  const sessionDate = state.data.session_date;
  const visibleSum = stocks.reduce((acc, r) => acc + (r.turnover_value ?? 0), 0);
  const denominator =
    marketTurnover !== null && Number.isFinite(marketTurnover) && marketTurnover > 0
      ? marketTurnover
      : visibleSum;

  let running = 0;
  const rows = stocks.map((r, i) => {
    const share =
      r.turnover_value !== null && denominator > 0 ? r.turnover_value / denominator : null;
    if (share !== null) running += share;
    return {
      ...identityCells(r, i + 1, sessionDate),
      gt__n: r.turnover_value,
      share: formatShare(share),
      cum: share === null ? DASH : formatShare(running),
      d1: formatPercent(r.ret_1d),
      d1__tone: signClass(r.ret_1d),
    };
  });

  return (
    <DataTable
      rows={rows}
      rankedKey="gt"
      barTone="neutral"
      getRowKey={(r) => r.ticker as string}
      columns={[
        ...IDENTITY,
        { key: "share", header: "Tỷ trọng", align: "num" },
        { key: "cum", header: "Luỹ kế", align: "num" },
        { key: "d1", header: "1D", align: "num" },
      ]}
    />
  );
}
