"use client";

import { useState } from "react";
import type { TickersResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import {
  useTickerAnalysis,
  useTickerDetail,
  useTickerHistory,
  useTickerIndicators,
} from "@/hooks/dashboard";
import { KpiCard, KpiGrid, DocPanel, RangeTabs } from "@/components/ds";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ChartFrame, ChartNotice, CombinedIndicatorChart, PriceHistoryChart } from "@/components/charts";
import {
  formatBillion,
  formatDecimal,
  formatInt,
  formatPercent,
  formatSession,
  signClass,
} from "@/components/market/format";
import { TickerGroup } from "./TickerGroup";
import styles from "./Tickers.module.css";

/**
 * The window tabs.
 *
 * **These slice the loaded series; they do not refetch.** `/history` and `/indicators` with no
 * bounds return the most recent 252 sessions, so every option here is a TAIL of what is already
 * in memory.
 *
 * A refetch could not do better, and would do worse: the routes are bounded by `from`/`to`
 * CALENDAR dates, and this axis counts SESSIONS. "The last 60 sessions" is not a date range —
 * asking for ~90 calendar days back would return however many sessions the exchange happened to
 * hold, so the tab would say 3M and mean something slightly different for every ticker. A tail
 * slice returns exactly 60 sessions, which is what the label claims.
 *
 * What that argument does NOT license is a window LONGER than the 252 sessions loaded, which is
 * a genuinely different request. That is why no such option exists here: a "3N" tab drawn from
 * 252 sessions would be a label making a claim the loaded data cannot support.
 */
const RANGES = [
  { value: "60", label: "3M" },
  { value: "126", label: "6M" },
  { value: "252", label: "1N" },
];

/**
 * `/tickers/?t=X` — one ticker, read top to bottom.
 *
 * **The four hooks are called side by side, and that is the whole performance design.** Each owns
 * its own `useEffect`, so React issues four overlapping requests when the ticker changes. P9.6
 * measured these routes at 872 + 948 + 1187 + 857 ms from Render: ~3.9 s in sequence, ~1.2 s
 * overlapping. Nothing in the framework enforces the overlap — rendering the charts only after
 * the detail resolves would quietly restore the 3.9 s version — so the calls stay together at the
 * top of one component, and no block waits on another's state.
 *
 * The universe list and the run parameters are NOT fetched here: they belong to the screen, are
 * fetched once per visit, and must not run again every time the reader picks another ticker.
 */
export function TickerDetail({
  ticker,
  universe,
  tau,
}: {
  ticker: string;
  universe: ResourceState<TickersResponse>;
  tau: number | null;
}) {
  const detail = useTickerDetail(ticker);
  const history = useTickerHistory(ticker);
  const indicators = useTickerIndicators(ticker);
  const analysis = useTickerAnalysis(ticker);

  const [range, setRange] = useState("252");
  const sessions = Number(range);
  const longRange = sessions > 120;

  const bars = history.kind === "data" ? history.data.bars.slice(-sessions) : [];
  const points = indicators.kind === "data" ? indicators.data.indicators.slice(-sessions) : [];

  // Each block's own as-of line, from the block's own response — the price series and the model
  // assignment are not read from the same session, and this screen must not imply they are.
  const barsAsOf =
    bars.length > 0
      ? `${bars.length} phiên · đến phiên ${formatSession(bars[bars.length - 1].bar_date)}`
      : undefined;
  const pointsAsOf =
    points.length > 0
      ? `${points.length} phiên · đến phiên ${formatSession(points[points.length - 1].bar_date)}`
      : undefined;

  return (
    <>
      <section className="as-section" aria-label={`Tổng quan ${ticker}`}>
        {detail.kind === "loading" && (
          <LoadingState rows={4} label={`Đang tải dữ liệu ${ticker}`} />
        )}
        {detail.kind === "error" && <ErrorState code={detail.code} message={detail.message} />}
        {detail.kind === "data" && (
          <>
            <div className="as-section__head">
              <h2 className="as-section__title">
                {detail.data.identity.ticker}
                {detail.data.identity.company_name
                  ? ` — ${detail.data.identity.company_name}`
                  : ""}
              </h2>
              <span className="as-section__note">
                {detail.data.identity.sector ?? "Khác"}
                {detail.data.identity.industry ? ` · ${detail.data.identity.industry}` : ""}
              </span>
            </div>

            {/* `latest` can be null in every field while identity and assignment are intact — the
                route LEFT JOINs the bar. Every formatter renders that as an em dash; none of them
                turns a missing figure into a zero. */}
            <KpiGrid>
              <KpiCard
                label="Giá đóng cửa (nghìn đ)"
                value={formatDecimal(detail.data.latest.close, 2)}
              />
              <KpiCard
                label="Thay đổi phiên"
                value={formatPercent(detail.data.latest.ret_1d)}
                tone={signClass(detail.data.latest.ret_1d)}
              />
              <KpiCard
                label="GT giao dịch (tỷ đ)"
                value={formatBillion(detail.data.latest.turnover_value)}
              />
              <KpiCard label="KL giao dịch (cp)" value={formatInt(detail.data.latest.volume)} />
              {/* drawdown_from_252d_high is a FRACTION, negative or zero: how far under the
                  252-session high the close sits. Rendered as a percent, never pre-multiplied. */}
              <KpiCard
                label="So với đỉnh 252 phiên"
                value={formatPercent(detail.data.latest.drawdown_from_252d_high)}
                tone={signClass(detail.data.latest.drawdown_from_252d_high)}
              />
              <KpiCard label="Phiên" value={formatSession(detail.data.latest.bar_date)} />
            </KpiGrid>
          </>
        )}
      </section>

      {detail.kind === "data" && (
        <TickerGroup
          ticker={detail.data.identity.ticker}
          assignment={detail.data.assignment}
          universe={universe}
          tau={tau}
        />
      )}

      <section className="as-section" aria-label={`Biểu đồ ${ticker}`}>
        <div className="as-section__head">
          <h2 className="as-section__title">Diễn biến giá</h2>
          <RangeTabs options={RANGES} value={range} onChange={setRange} />
        </div>

        <div className={styles.charts}>
          <ChartFrame title="Giá giao dịch" subtitle={barsAsOf}>
            {history.kind === "loading" && <LoadingState rows={5} label="Đang tải lịch sử giá" />}
            {history.kind === "error" && (
              <ErrorState code={history.code} message={history.message} />
            )}
            {history.kind === "data" &&
              (bars.length < 2 ? (
                <EmptyState
                  scope="Lịch sử giá"
                  message="Chưa đủ phiên trong khoảng này để vẽ đường giá."
                />
              ) : (
                <>
                  <PriceHistoryChart
                    ticker={ticker}
                    pane="price"
                    longRange={longRange}
                    bars={bars.map((b) => ({
                      date: b.bar_date ?? "",
                      close: b.close ?? NaN,
                      volume: b.volume ?? 0,
                    }))}
                  />
                  <ChartNotice>
                    Giá đã điều chỉnh — biểu đồ có thể lệch so với biểu đồ giá thô của công ty
                    chứng khoán quanh ngày giao dịch không hưởng quyền. Vùng tô đóng về mức giá mở
                    đầu khoảng, là đường nét đứt màu hổ phách.
                  </ChartNotice>
                </>
              ))}
          </ChartFrame>

          <ChartFrame title="Khối lượng giao dịch" subtitle={barsAsOf}>
            {history.kind === "loading" && (
              <LoadingState rows={3} label="Đang tải khối lượng giao dịch" />
            )}
            {history.kind === "error" && (
              <ErrorState code={history.code} message={history.message} />
            )}
            {history.kind === "data" &&
              (bars.length < 2 ? (
                <EmptyState
                  scope="Khối lượng"
                  message="Chưa đủ phiên trong khoảng này để vẽ khối lượng."
                />
              ) : (
                <PriceHistoryChart
                  ticker={ticker}
                  pane="volume"
                  longRange={longRange}
                  bars={bars.map((b) => ({
                    date: b.bar_date ?? "",
                    close: b.close ?? NaN,
                    volume: b.volume ?? 0,
                  }))}
                />
              ))}
          </ChartFrame>

          <ChartFrame title="Giá và đường trung bình" subtitle={pointsAsOf}>
            {indicators.kind === "loading" && (
              <LoadingState rows={5} label="Đang tải chỉ báo kỹ thuật" />
            )}
            {indicators.kind === "error" && (
              <ErrorState code={indicators.code} message={indicators.message} />
            )}
            {indicators.kind === "data" &&
              (points.length < 2 ? (
                <EmptyState
                  scope="Chỉ báo"
                  message="Chưa đủ phiên trong khoảng này để vẽ đường trung bình."
                />
              ) : (
                <CombinedIndicatorChart
                  ticker={ticker}
                  pane="price"
                  longRange={longRange}
                  points={points}
                />
              ))}
          </ChartFrame>

          <ChartFrame title="RSI 14" subtitle={pointsAsOf}>
            {indicators.kind === "loading" && <LoadingState rows={3} label="Đang tải RSI" />}
            {indicators.kind === "error" && (
              <ErrorState code={indicators.code} message={indicators.message} />
            )}
            {indicators.kind === "data" &&
              (points.length < 2 ? (
                <EmptyState scope="RSI" message="Chưa đủ phiên trong khoảng này để vẽ RSI." />
              ) : (
                <CombinedIndicatorChart
                  ticker={ticker}
                  pane="rsi"
                  longRange={longRange}
                  points={points}
                />
              ))}
          </ChartFrame>
        </div>
      </section>

      <section className="as-section" aria-label={`Phân tích kỹ thuật ${ticker}`}>
        <div className="as-section__head">
          <h2 className="as-section__title">Phân tích kỹ thuật</h2>
          {analysis.kind === "data" && (
            <span className="as-section__note">
              {analysis.data.statements.length} /{" "}
              {analysis.data.statements.length + analysis.data.skipped.length} quy tắc chạy được
            </span>
          )}
        </div>

        {analysis.kind === "loading" && <LoadingState rows={4} label="Đang tải phân tích" />}
        {analysis.kind === "error" && <ErrorState code={analysis.code} message={analysis.message} />}
        {analysis.kind === "data" && (
          <DocPanel>
            {analysis.data.statements.length === 0 ? (
              // Every rule skipped means the indicators are not computable yet — not an error, and
              // not a neutral verdict either. Say which it is, and never why in the rules' own
              // technical terms.
              <p className="as-caption">
                Chưa đủ dữ liệu lịch sử để đưa ra nhận định cho mã này.
              </p>
            ) : (
              // Verbatim. The wording names a market convention as a convention where it leans on
              // one, so paraphrasing or trimming would break a guarantee the API makes.
              <ul className="as-statements">
                {analysis.data.statements.map((s) => (
                  <li key={s.code}>{s.text}</li>
                ))}
              </ul>
            )}
          </DocPanel>
        )}
      </section>
    </>
  );
}
