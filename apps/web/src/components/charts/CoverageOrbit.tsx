"use client";

import { useState } from "react";
import { formatDecimal } from "@/components/market/format";

export interface OrbitMember {
  ticker: string;
  /** c_i — how much of this ticker's residual behaviour its anchor accounts for. In [0,1]. */
  coverage: number | null;
  sector?: string | null;
}

const VW = 560;
const VH = 420;
/** The hub's clear radius, and the rim the weakest member sits on. */
const R_IN = 54;
const R_OUT = Math.min(VW, VH) / 2 - 34;

/**
 * Coverage as DISTANCE. The anchor sits in the hub; every member of its group is a dot whose
 * distance from the centre is its coverage — high coverage close in, low coverage out at the rim.
 *
 * That is the whole point of the picture: "near the anchor" and "well represented by the anchor"
 * become the same reading, which a column of 0.312s never manages.
 *
 * The dashed ring is τ, the run's rejection threshold. Members outside it are drawn in the warn
 * tone: they are not errors, they are honest low coverage, and the model says so itself. With no
 * τ (the active run has not loaded, or the run publishes none) the ring is simply absent — a
 * threshold guessed from the data would be a number this system invented.
 *
 * `focus` marks the ticker the screen is about when it is a MEMBER rather than the anchor. The
 * hub is always the anchor; a member never moves to the middle, because the middle means
 * "represents", not "is being read".
 */
export function CoverageOrbit({
  members,
  anchor,
  threshold = null,
  focus = null,
  onSelect,
}: {
  members: OrbitMember[];
  /** Anchor ticker, drawn in the hub. */
  anchor: string;
  /** τ. Draws the dashed ring; members outside it take the warn tone. */
  threshold?: number | null;
  /** A member to mark as the one being read. */
  focus?: string | null;
  onSelect?: (ticker: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);

  // The anchor covers itself at ρ² = 1 by construction, so it is never a dot: it is the hub, and
  // a dot at c = 1 would sit under it.
  const rows = members.filter(
    (m): m is OrbitMember & { coverage: number } =>
      m.ticker !== anchor && m.coverage !== null && Number.isFinite(m.coverage),
  );
  if (rows.length === 0) return null;

  const cx = VW / 2;
  const cy = VH / 2;
  const maxCov = Math.max(...rows.map((m) => m.coverage), threshold ?? 0);
  const rAt = (c: number): number =>
    maxCov <= 0 ? R_OUT : R_IN + (1 - Math.min(1, c / maxCov)) * (R_OUT - R_IN);

  // Strongest first, going clockwise from the top; the odd rows are nudged so two adjacent
  // labels at the same radius do not collide.
  const sorted = rows.slice().sort((a, b) => b.coverage - a.coverage);
  const dots = sorted.map((m, i) => {
    const angle = (i / sorted.length) * Math.PI * 2 - Math.PI / 2 + (i % 2 ? 0.14 : 0);
    const r = rAt(m.coverage);
    return {
      ticker: m.ticker,
      coverage: m.coverage,
      sector: m.sector ?? null,
      weak: threshold !== null && m.coverage < threshold,
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
      right: Math.cos(angle) >= 0,
    };
  });

  // Rings labelled with the coverage they stand for, so the picture stays quantitative.
  const rings = [0.25, 0.5, 0.75, 1].map((f) => ({
    f,
    r: rAt(maxCov * f),
    label: formatDecimal(maxCov * f, 2),
  }));

  const read = dots.find((d) => d.ticker === (hover ?? focus)) ?? null;

  return (
    <div className="as-orbit">
      <svg
        viewBox={`0 0 ${VW} ${VH}`}
        className="as-orbit__svg"
        role="img"
        aria-label={`Độ phủ của ${rows.length} mã quanh điểm neo ${anchor} — càng gần tâm thì độ phủ càng cao`}
      >
        {rings.map((g) => (
          <g key={g.f}>
            <circle cx={cx} cy={cy} r={g.r} className="as-orbit__ring" />
            <text x={cx} y={cy - g.r - 4} className="as-orbit__ring-label">
              {g.label}
            </text>
          </g>
        ))}

        {threshold !== null && (
          <>
            <circle cx={cx} cy={cy} r={rAt(threshold)} className="as-orbit__tau" />
            {/* Below its ring, not above: the ring labels all sit at the top, and τ lands on one
                of them whenever the threshold is close to a ring's value. */}
            <text x={cx + 6} y={cy + rAt(threshold) + 14} className="as-orbit__tau-label">
              ngưỡng τ {formatDecimal(threshold, 2)}
            </text>
          </>
        )}

        {dots.map((d) => (
          <line
            key={`spoke-${d.ticker}`}
            x1={cx}
            y1={cy}
            x2={d.x}
            y2={d.y}
            className={`as-orbit__spoke${
              d.ticker === (hover ?? focus) ? " as-orbit__spoke--on" : ""
            }`}
          />
        ))}

        <circle cx={cx} cy={cy} r={R_IN - 14} className="as-orbit__hub" />
        <text x={cx} y={cy - 2} className="as-orbit__hub-ticker">
          {anchor}
        </text>
        <text x={cx} y={cy + 14} className="as-orbit__hub-note">
          điểm neo
        </text>

        {dots.map((d) => {
          const marked = d.ticker === (hover ?? focus);
          return (
            <g
              key={d.ticker}
              className="as-orbit__node"
              tabIndex={0}
              role={onSelect ? "button" : undefined}
              aria-label={`${d.ticker}, độ phủ ${formatDecimal(d.coverage, 3)}`}
              onPointerEnter={() => setHover(d.ticker)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(d.ticker)}
              onBlur={() => setHover(null)}
              onClick={onSelect ? () => onSelect(d.ticker) : undefined}
            >
              <circle
                cx={d.x}
                cy={d.y}
                r={marked ? 7 : 5}
                className={`as-orbit__dot${d.weak ? " as-orbit__dot--weak" : ""}`}
              />
              <text
                x={d.x + (d.right ? 10 : -10)}
                y={d.y + 3.5}
                className={`as-orbit__tag${d.right ? "" : " as-orbit__tag--left"}${
                  marked ? " as-orbit__tag--on" : ""
                }`}
              >
                {d.ticker}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="as-orbit__foot">
        {read ? (
          <span className="as-orbit__readout">
            <strong>{read.ticker}</strong> · độ phủ <strong>{formatDecimal(read.coverage, 3)}</strong>
            {read.sector ? ` · ${read.sector}` : ""}
            {read.weak ? " · dưới ngưỡng τ" : ""}
          </span>
        ) : (
          <span className="as-orbit__hint">
            Càng gần {anchor} thì độ phủ càng cao — quan hệ với điểm neo càng chặt. Trỏ vào một mã
            để xem số.
          </span>
        )}
      </div>
    </div>
  );
}
