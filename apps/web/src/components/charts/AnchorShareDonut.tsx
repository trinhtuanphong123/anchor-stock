"use client";

import { useState } from "react";
import { formatShare } from "@/components/market/format";

export interface DonutSlice {
  /** Identity of the part — also the key the callbacks report back. */
  label: string;
  value: number;
  /** Right-hand text in the legend row. Defaults to the raw value. */
  note?: string;
  /** Override the categorical colour. Leave unset to take the next `--cluster-N`. */
  color?: string;
}

/** The categorical ramp's length. Past it the colours repeat, which is why the donut is capped. */
const CLUSTERS = 12;

/**
 * Composition donut for a small set of named parts.
 *
 * **A pie is honest here for one reason: the parts are a closed partition.** The ten published
 * anchor groups cover all 85 tickers exactly once, so the ring is the whole and each arc is a
 * share of it. Nothing else in this product satisfies that — sector turnover overlaps, breadth
 * omits the tickers with no `ret_1d` — and the shape must not be reused where it does not hold.
 *
 * Colour is IDENTITY, never direction: the `--cluster-*` ramp, so no arc can be read as a price
 * that went up or down.
 *
 * The centre is a readout rather than decoration — the total until an arc is pointed at, then
 * that arc's share. Both the arcs and the legend rows drive it, and both are focusable when
 * `onSelect` is given, so the picture is navigable from the keyboard.
 *
 * Past a dozen slices this becomes unreadable and a ranked bar list is the right shape; the ramp
 * repeating at 13 is the signal, and the guard is the caller's to keep.
 */
export function AnchorShareDonut({
  slices = [],
  size = 300,
  thickness = 34,
  centerLabel = "",
  centerValue = "",
  active = null,
  onSelect,
  onHover,
  gap = 0.012,
}: {
  slices?: DonutSlice[];
  /** Outer diameter in px. */
  size?: number;
  /** Ring width in px. */
  thickness?: number;
  /** Text under the centre value when nothing is pointed at. */
  centerLabel?: string;
  /** Big centre value when nothing is pointed at — usually the total. */
  centerValue?: string;
  /** Label of the slice to keep emphasised. */
  active?: string | null;
  /** Makes arcs and legend rows clickable. */
  onSelect?: (label: string) => void;
  onHover?: (label: string | null) => void;
  /** Radian gap between slices. */
  gap?: number;
}) {
  const [hover, setHover] = useState<string | null>(null);

  const total = slices.reduce((a, s) => a + (s.value || 0), 0);
  // No total means no shares to draw. Not an empty ring: a ring of nothing states a partition
  // that is not there.
  if (!(total > 0)) return null;

  const R = size / 2;
  const rOut = R - 2;
  const rIn = rOut - thickness;
  const current = hover ?? active;

  let acc = 0;
  const arcs = slices.map((s, i) => {
    const frac = s.value / total;
    const a0 = acc * Math.PI * 2 - Math.PI / 2 + gap / 2;
    const a1 = (acc + frac) * Math.PI * 2 - Math.PI / 2 - gap / 2;
    acc += frac;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (r: number, a: number) =>
      `${(R + r * Math.cos(a)).toFixed(2)} ${(R + r * Math.sin(a)).toFixed(2)}`;
    return {
      label: s.label,
      frac,
      value: s.value,
      note: s.note,
      color: s.color ?? `var(--cluster-${(i % CLUSTERS) + 1})`,
      d:
        `M${p(rOut, a0)} A${rOut} ${rOut} 0 ${large} 1 ${p(rOut, a1)}` +
        ` L${p(rIn, a1)} A${rIn} ${rIn} 0 ${large} 0 ${p(rIn, a0)} Z`,
    };
  });

  // Off `arcs`, not off `slices`: the readout shows a SHARE, and the share is computed here.
  const shown = current === null ? null : (arcs.find((a) => a.label === current) ?? null);

  const enter = (label: string) => {
    setHover(label);
    onHover?.(label);
  };
  const leave = () => {
    setHover(null);
    onHover?.(null);
  };

  return (
    <div className="as-donut">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="as-donut__svg"
        style={{ width: size, height: size }}
        role="img"
        aria-label={centerLabel || "Tỷ trọng theo nhóm"}
      >
        {arcs.map((a) => (
          <path
            key={a.label}
            d={a.d}
            fill={a.color}
            className={`as-donut__arc${current !== null && current !== a.label ? " as-donut__arc--dim" : ""}`}
            tabIndex={onSelect ? 0 : undefined}
            role={onSelect ? "button" : undefined}
            aria-label={`${a.label} ${formatShare(a.frac)}`}
            onPointerEnter={() => enter(a.label)}
            onPointerLeave={leave}
            onFocus={() => enter(a.label)}
            onBlur={leave}
            onClick={onSelect ? () => onSelect(a.label) : undefined}
            onKeyDown={
              onSelect
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(a.label);
                    }
                  }
                : undefined
            }
          />
        ))}
        <text x={R} y={R - 4} className="as-donut__center-value">
          {shown ? formatShare(shown.frac) : centerValue}
        </text>
        <text x={R} y={R + 16} className="as-donut__center-label">
          {shown ? shown.label : centerLabel}
        </text>
      </svg>

      <ul className="as-donut__legend">
        {arcs.map((a) => {
          const key = (
            <>
              <span className="as-donut__swatch" style={{ background: a.color }} />
              <span className="as-donut__label">{a.label}</span>
              <span className="as-donut__value">{formatShare(a.frac)}</span>
              <span className="as-donut__note">{a.note ?? a.value}</span>
            </>
          );
          const className = `as-donut__key${current === a.label ? " as-donut__key--on" : ""}`;
          return (
            <li key={a.label}>
              {onSelect ? (
                <button
                  type="button"
                  className={className}
                  onPointerEnter={() => enter(a.label)}
                  onPointerLeave={leave}
                  onFocus={() => enter(a.label)}
                  onBlur={leave}
                  onClick={() => onSelect(a.label)}
                >
                  {key}
                </button>
              ) : (
                <span
                  className={className}
                  onPointerEnter={() => enter(a.label)}
                  onPointerLeave={leave}
                >
                  {key}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
