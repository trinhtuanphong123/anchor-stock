"use client";

import { useActiveModelRun } from "@/hooks/dashboard";
import { coverageFbarAdjusted } from "@/lib/api";
import { DASH, formatDecimal, formatInt, formatSession } from "@/components/market/format";

/**
 * Which run is on screen, and as of when. Rendered once by {@link AppChrome} at the foot of every
 * page.
 *
 * Two rules meet here, and D-24 is where they were reconciled.
 *
 * `docs/04` §5 requires the dashboard to show the universe as of the active run and say so — the
 * anchor set was estimated on one window while the prices beside it run to the latest collected
 * session, currently an eight-month distance, and a reader left to assume those dates agree would
 * be misled about the most consequential thing on the page.
 *
 * But this is a results dashboard, and `docs/03` §5 is explicit that the methodology is not
 * re-argued here. The previous version led with nine fields — `k`, `τ`, `F̄(S)`, `Dưới τ`, `Độ đo`,
 * `Artifact` among them — across the top of the market screen, so every reader met the notation
 * before the first price.
 *
 * The resolution is demotion, not deletion. The summary line carries the as-of date, the universe
 * size and the published anchor count, which is what §5 actually asks for. The run's identity sits
 * one disclosure away, still complete, for the reader reproducing the result.
 *
 * It renders nothing while loading and nothing on error: a footer that cannot name the run is
 * better absent than shouting. The screens above already surface their own failures, and an error
 * card repeated under every one of them would say the same thing twice.
 *
 * Styled by the design system's global `as-*` classes rather than a module of its own — the
 * duplicate rule set this replaced had drifted to `--motion-fast`, a variable no token file has
 * ever declared.
 */
export function ProvenanceStrip() {
  const state = useActiveModelRun();
  if (state.kind !== "data") return null;

  const run = state.data;

  // Model internals only. The summary line carries everything a reader of results needs.
  const details: Array<{ label: string; value: string }> = [
    {
      label: "Cửa sổ ước lượng",
      value: `${formatSession(run.window_start)} – ${formatSession(run.window_end)}`,
    },
    { label: "Số phiên", value: formatInt(run.n_sessions) },
    { label: "τ", value: formatDecimal(run.tau) },
    { label: "F̄(S)", value: formatDecimal(run.coverage_fbar, 4) },
    // Shown beside F̄, never instead of it: F̄ includes k tautological self-cover terms of 1
    // (~45 % of F), F̄_adj removes them. D-26 requires the pair.
    { label: "F̄_adj", value: formatDecimal(coverageFbarAdjusted(run), 4) },
    {
      label: "Dưới τ",
      value: `${formatInt(run.n_under_tau)} / ${formatInt(run.n_tickers)}`,
    },
    { label: "Độ đo", value: run.similarity_measure },
    { label: "Artifact", value: run.artifact_id || DASH },
  ];

  return (
    <section className="as-provenance" aria-label="Thông tin dữ liệu">
      <p className="as-provenance__summary">
        <span>
          Dữ liệu đến <strong>{formatSession(run.latest_session)}</strong>
        </span>
        <span aria-hidden="true" className="as-provenance__dot">
          ·
        </span>
        <span>
          <strong>{formatInt(run.n_tickers)}</strong> mã
        </span>
        <span aria-hidden="true" className="as-provenance__dot">
          ·
        </span>
        <span>
          <strong>{formatInt(run.k)}</strong> điểm neo
        </span>
      </p>

      {/* `.as-details` is the design system's bordered sunken card. Here the disclosure sits
          inside a strip that already has its own rule above it, and a card nested in that would
          be a border inside a border — the one thing the surface rules forbid. Stripping the
          three properties in place is smaller than adding a second class for one use. */}
      <details
        className="as-details"
        style={{ background: "transparent", border: "none", padding: 0 }}
      >
        <summary className="as-details__toggle">Chi tiết mô hình</summary>
        <div className="as-provenance__items">
          {details.map((item) => (
            <div key={item.label} className="as-provenance__item">
              {/* Not uppercased: these labels carry Greek, and `text-transform: uppercase`
                  turns τ into Τ, which reads as a Latin T. */}
              <span className="as-def-term">{item.label}</span>
              <span className="as-def-value">{item.value}</span>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

export default ProvenanceStrip;
