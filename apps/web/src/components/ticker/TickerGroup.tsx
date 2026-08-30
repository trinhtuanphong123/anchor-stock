"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { TickerAssignment, TickerListRow } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import type { TickersResponse } from "@/lib/api";
import { Badge, DocPanel } from "@/components/ds";
import { CoverageOrbit } from "@/components/charts";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { formatDecimal } from "@/components/market/format";
import styles from "./Tickers.module.css";

/**
 * "Nhóm cổ phiếu liên quan tới X" — the one place a stock on this screen touches the model.
 *
 * It used to be a single sentence carrying one number, which undersold the only contribution the
 * product actually makes. The orbit draws coverage as DISTANCE from the anchor, so the group's
 * shape — who is close, who is out past τ, how uneven the spread is — is readable at a glance,
 * and the sentence beside it stays as the thing that says what the picture means.
 *
 * **Whether the ticker sits in the hub or on the rim is the model's answer, not a display
 * choice.** An anchor is the hub of its own group; a member orbits the anchor that represents it
 * and is marked, never promoted to the middle. The middle means "represents".
 *
 * The members come from the universe list this screen already holds — every row carries its
 * `anchor_ticker` and `coverage_c` — so the picture costs no request of its own.
 */
export function TickerGroup({
  ticker,
  assignment,
  universe,
  tau,
}: {
  ticker: string;
  assignment: TickerAssignment;
  /** The 85-row universe, fetched once by the screen. */
  universe: ResourceState<TickersResponse>;
  /** The run's coverage threshold. Null until the run resolves — the ring is then simply absent. */
  tau: number | null;
}) {
  const router = useRouter();
  const isAnchor = assignment.is_anchor === true;
  const hub = isAnchor ? ticker : assignment.anchor_ticker;

  const members: TickerListRow[] =
    hub === null || universe.kind !== "data"
      ? []
      : universe.data.tickers.filter((r) => r.anchor_ticker === hub);

  return (
    <section className="as-section" aria-label={`Nhóm cổ phiếu liên quan tới ${ticker}`}>
      <div className="as-section__head">
        <h2 className="as-section__title">Nhóm cổ phiếu liên quan tới {ticker}</h2>
        {members.length > 0 && (
          <span className="as-section__note">{members.length} mã trong nhóm</span>
        )}
      </div>

      <DocPanel>
        {hub === null ? (
          // Not an anchor and assigned to none: the run represents this ticker with nothing, and
          // that is a fact about the model rather than a missing join.
          <p className="as-caption">Mã này chưa được gán vào nhóm nào trong lần chạy đang phục vụ.</p>
        ) : (
          <div className={styles.group}>
            <div>
              {universe.kind === "loading" && (
                <LoadingState rows={5} label={`Đang tải nhóm của ${hub}`} />
              )}
              {universe.kind === "error" && (
                <ErrorState code={universe.code} message={universe.message} />
              )}
              {universe.kind === "data" &&
                (members.length === 0 ? (
                  <EmptyState
                    scope="Nhóm điểm neo"
                    message={`Chưa có mã nào được gán cho ${hub} trong lần chạy đang phục vụ.`}
                  />
                ) : (
                  <CoverageOrbit
                    anchor={hub}
                    threshold={tau}
                    focus={isAnchor ? null : ticker}
                    members={members.map((m) => ({
                      ticker: m.ticker,
                      coverage: m.coverage_c,
                      sector: m.sector,
                    }))}
                    onSelect={(t) => router.push(`/tickers/?t=${t}`)}
                  />
                ))}
            </div>

            <div className={styles.groupText}>
              {isAnchor ? (
                <p className="as-caption">
                  <strong>{ticker}</strong> là một trong các mã điểm neo được công bố, nên nó ở
                  tâm: các mã quanh nó là nhóm mà nó đại diện.{" "}
                  <Link className="as-link" href={`/anchors/?a=${ticker}`}>
                    Xem nhóm được đại diện →
                  </Link>
                </p>
              ) : (
                <p className="as-caption">
                  Mã này được đại diện bởi{" "}
                  <Link className="as-link" href={`/anchors/?a=${hub}`}>
                    {hub}
                  </Link>
                  , độ phủ <strong>{formatDecimal(assignment.coverage_c, 3)}</strong>
                  {assignment.under_tau === true && (
                    <>
                      {" "}
                      <Badge
                        tone="warn"
                        title="Độ phủ dưới ngưỡng τ của mô hình — điểm neo đại diện yếu cho mã này"
                      >
                        độ phủ thấp
                      </Badge>
                    </>
                  )}
                  . Nó là một điểm trên vành, không phải tâm.
                </p>
              )}

              {/* Content, not a footnote to trim: the distance is the one thing a reader can
                  misread here, and both sentences say what it is not. */}
              <p className="as-caption">
                Khoảng cách tới tâm là độ phủ c_i, không phải khoảng cách về giá.
                {tau !== null
                  ? ` Vòng nét đứt là ngưỡng τ = ${formatDecimal(tau, 2)}; mã nằm ngoài nó được điểm neo đại diện yếu.`
                  : " Chưa đọc được ngưỡng τ của lần chạy, nên hình không vẽ vòng ngưỡng."}
              </p>
            </div>
          </div>
        )}
      </DocPanel>
    </section>
  );
}
