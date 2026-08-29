"use client";

import Link from "next/link";
import {
  useTickerAnalysis,
  useTickerDetail,
  useTickerHistory,
  useTickerIndicators,
} from "@/hooks/dashboard";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ChartFrame, PriceHistoryChart } from "@/components/charts";
import { CombinedIndicatorChart } from "@/components/charts/CombinedIndicatorChart";
import ui from "@/components/ui.module.css";
import {
  DASH,
  formatDate,
  formatDecimal,
  formatInt,
  formatPercent,
  formatTurnoverTy,
  signClass,
} from "@/components/market/format";

/**
 * `/tickers/?t=X` — one ticker.
 *
 * **The four hooks are called side by side, and that is the whole performance design.** Each owns
 * its own `useEffect`, so React issues four overlapping requests on mount. P9.6 measured these
 * routes at 872 + 948 + 1187 + 857 ms from Render: ~3.9 s in sequence, ~1.2 s overlapping. Nothing
 * in the framework enforces the overlap — rendering the chart only after the detail resolves would
 * quietly restore the 3.9 s version — so the calls stay together at the top of one component.
 *
 * Each panel renders its own loading and error state rather than the screen blocking on all four,
 * which means a slow `/indicators` does not hide a fast `/analysis`.
 */
export function TickerDetail({ ticker }: { ticker: string }) {
  const detail = useTickerDetail(ticker);
  const history = useTickerHistory(ticker);
  const indicators = useTickerIndicators(ticker);
  const analysis = useTickerAnalysis(ticker);

  if (detail.kind === "loading") {
    return <LoadingState rows={6} label={`Đang tải dữ liệu ${ticker}`} />;
  }
  if (detail.kind === "error") {
    return <ErrorState code={detail.code} message={detail.message} />;
  }

  const { identity, assignment, latest } = detail.data;

  return (
    <div className={ui.page}>
      <section className={ui.section}>
        <div className={ui.sectionHead}>
          <h2 className={ui.sectionTitle}>
            {identity.ticker}
            {identity.company_name ? ` — ${identity.company_name}` : ""}
          </h2>
          <span className={ui.sectionNote}>
            {identity.sector ?? "Khác"}
            {identity.industry ? ` · ${identity.industry}` : ""}
          </span>
        </div>

        <div className={ui.kpiGrid}>
          <Kpi label="Giá đóng cửa (nghìn đ)" value={formatDecimal(latest.close)} />
          <Kpi
            label="Thay đổi phiên"
            value={formatPercent(latest.ret_1d)}
            tone={signClass(latest.ret_1d)}
          />
          <Kpi label="GT giao dịch (tỷ đ)" value={formatTurnoverTy(latest.turnover_value)} />
          <Kpi label="KL giao dịch (cp)" value={formatInt(latest.volume)} />
          {/* drawdown_from_252d_high is a FRACTION and is negative or zero: how far under the
              252-session high the close sits. Rendered as a percent, not as a price. */}
          <Kpi
            label="So với đỉnh 252 phiên"
            value={formatPercent(latest.drawdown_from_252d_high)}
            tone={signClass(latest.drawdown_from_252d_high)}
          />
          <Kpi label="Phiên" value={formatDate(latest.bar_date)} />
        </div>
      </section>

      <AnchorCard
        ticker={identity.ticker}
        anchorTicker={assignment.anchor_ticker}
        coverage={assignment.coverage_c}
        isAnchor={assignment.is_anchor}
        underTau={assignment.under_tau}
      />

      <ChartFrame title="Biến động giá & khối lượng" asOf={formatDate(latest.bar_date)}>
        {history.kind === "loading" && <LoadingState rows={4} label="Đang tải lịch sử giá" />}
        {history.kind === "error" && (
          <ErrorState code={history.code} message={history.message} />
        )}
        {history.kind === "data" &&
          (history.data.bars.length === 0 ? (
            <EmptyState scope="Lịch sử giá" message="Chưa có phiên nào trong khoảng này." />
          ) : (
            <PriceHistoryChart
              id={`price-${identity.ticker}`}
              ticker={identity.ticker}
              bars={history.data.bars.map((b) => ({
                date: b.bar_date ?? "",
                close: b.close ?? NaN,
                volume: b.volume ?? 0,
              }))}
            />
          ))}
      </ChartFrame>

      <ChartFrame title="Biểu đồ kỹ thuật tổng hợp" asOf={formatDate(latest.bar_date)}>
        {indicators.kind === "loading" && (
          <LoadingState rows={6} label="Đang tải chỉ báo kỹ thuật" />
        )}
        {indicators.kind === "error" && (
          <ErrorState code={indicators.code} message={indicators.message} />
        )}
        {indicators.kind === "data" &&
          (indicators.data.indicators.length === 0 ? (
            <EmptyState scope="Chỉ báo" message="Chưa có chỉ báo nào cho mã này." />
          ) : (
            <CombinedIndicatorChart
              id={`combined-${identity.ticker}`}
              ticker={identity.ticker}
              points={indicators.data.indicators}
            />
          ))}
      </ChartFrame>

      <section className={ui.section} aria-label="Phân tích kỹ thuật">
        <div className={ui.sectionHead}>
          <h2 className={ui.sectionTitle}>Phân tích kỹ thuật</h2>
        </div>
        {analysis.kind === "loading" && <LoadingState rows={4} label="Đang tải phân tích" />}
        {analysis.kind === "error" && (
          <ErrorState code={analysis.code} message={analysis.message} />
        )}
        {analysis.kind === "data" && (
          <div className={ui.panel}>
            {analysis.data.statements.length === 0 ? (
              // Every rule skipped means the indicators are not computable yet — not an error,
              // and not a neutral verdict either. Say which it is.
              <p className={ui.caption}>
                Chưa đủ dữ liệu lịch sử để đưa ra nhận định cho mã này.
              </p>
            ) : (
              <ul className={ui.statements}>
                {analysis.data.statements.map((s) => (
                  <li key={s.code}>{s.text}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function Kpi({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "flat";
}) {
  return (
    <div className={ui.kpiCard}>
      <span className={ui.kpiLabel}>{label}</span>
      <span className={`${ui.kpiValue} ${tone ? ui[tone] : ""}`}>{value}</span>
    </div>
  );
}

/**
 * "Thẻ điểm neo" — which anchor represents this ticker, and how well.
 *
 * `coverage_c` is the model's own figure for how much of this ticker's residual behaviour its
 * anchor accounts for. `under_tau` says that figure is below the run's rejection threshold, which
 * is the one piece of model vocabulary worth surfacing on a result screen: it is the difference
 * between "this anchor represents the ticker" and "this ticker is not well represented by
 * anything in the published set."
 */
function AnchorCard({
  ticker,
  anchorTicker,
  coverage,
  isAnchor,
  underTau,
}: {
  ticker: string;
  anchorTicker: string | null;
  coverage: number | null;
  isAnchor: boolean | null;
  underTau: boolean | null;
}) {
  return (
    <section className={ui.panel} aria-label="Nhóm điểm neo">
      <h2 className={ui.panelTitle}>Nhóm điểm neo</h2>
      {isAnchor ? (
        <p className={ui.caption}>
          <strong>{ticker}</strong> là một trong các mã điểm neo được công bố.{" "}
          <Link className={ui.link} href={`/anchors/?a=${ticker}`}>
            Xem nhóm được đại diện →
          </Link>
        </p>
      ) : anchorTicker ? (
        <p className={ui.caption}>
          Mã này được đại diện bởi{" "}
          <Link className={ui.link} href={`/anchors/?a=${anchorTicker}`}>
            {anchorTicker}
          </Link>
          , độ phủ <strong>{formatDecimal(coverage, 3)}</strong>
          {underTau && (
            <>
              {" "}
              <span
                className={`${ui.badge} ${ui.badgeWarn}`}
                title="Độ phủ dưới ngưỡng τ của mô hình — điểm neo đại diện yếu cho mã này"
              >
                độ phủ thấp
              </span>
            </>
          )}
          .
        </p>
      ) : (
        <p className={ui.caption}>{DASH} Mã này chưa được gán vào nhóm nào.</p>
      )}
    </section>
  );
}
