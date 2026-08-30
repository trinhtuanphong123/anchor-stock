"use client";

import { useEffect, useRef, useState } from "react";
import type { MarketSectorsResponse, SectorRow } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { Panel } from "@/components/ds";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { squarify } from "@/components/charts/treemap";
import { ChartTooltip } from "@/components/charts/ChartHover";
import { DASH, formatBillion, formatInt, formatPercent } from "./format";

/**
 * The treemap is THE EXCEPTION to this package's fixed-viewBox rule, and deliberately so.
 *
 * Every other chart here uses a fixed `viewBox` scaled by CSS, which is right for them: a line
 * chart has a shape it wants to keep. A treemap has no intrinsic aspect ratio — it fills whatever
 * rectangle it is given by construction — and a fixed one left it 90px short of the chart panel
 * beside it in the 1.72 : 1 split, with dead space under the tiles. Measuring the real pixel box
 * makes it fill the panel at every width, and has a second effect that the tier table below
 * depends on: viewBox units ARE CSS pixels, so a tile's size can be compared against a FONT SIZE
 * directly rather than through a scale factor nothing was tracking.
 *
 * The fallback box covers the single frame before the ResizeObserver reports, and any environment
 * where the element is unmeasurable (jsdom, a `display: none` ancestor).
 */
const FALLBACK_W = 640;
const FALLBACK_H = 360;

/**
 * Where the colour ramp saturates: a SECTOR MEAN of ±0.9% in one session.
 *
 * Not the ±3% that would be right for a single ticker. This colours an average over every member
 * of a sector, and averages of twenty names do not travel 3% in a day — scaling to a single
 * stock's range would leave every tile in the palest step on all but the most violent sessions.
 */
const FULL_SCALE = 0.009;

/**
 * Four saturated steps per direction, rather than a wash of one hue across the panel. The weakest
 * step is still a legible tint and the strongest is the -700 ink; only the top two are dark
 * enough to carry white labels, which is what `isDeep` below decides.
 */
const RAMP = {
  pos: ["var(--pos-500)", "var(--pos-600)", "var(--pos-700)", "color-mix(in srgb, var(--pos-700) 88%, black)"],
  neg: ["var(--neg-500)", "var(--neg-600)", "var(--neg-700)", "color-mix(in srgb, var(--neg-700) 88%, black)"],
} as const;

/**
 * What a tile is big enough to SAY, in rendered pixels — which, since the viewBox is the measured
 * box, is also what the tile geometry is in.
 *
 * The predecessor to this table gated on width alone, which asked whether the tile was wide and
 * never whether the label fitted. "Bất động sản và Xây dựng" at 14px is ~150px; in a 55px tile it
 * overhung by ~100 and was then half-painted-over by the next tile, so it read as a label
 * belonging to the wrong sector. Tiers plus `overflow: hidden` on each label box replace that
 * guess with a rule. Below the last tier a tile carries only its ±%, and its name lives in the
 * tooltip.
 */
const TIERS = [
  { minW: 132, minH: 58, name: 14, pct: 13, lines: 2, pad: "6px 8px" },
  { minW: 84, minH: 40, name: 11.5, pct: 12, lines: 2, pad: "5px 6px" },
  { minW: 52, minH: 28, name: 9.5, pct: 10.5, lines: 3, pad: "3px 4px" },
  { minW: 38, minH: 18, name: 0, pct: 10, lines: 0, pad: "2px 3px" },
] as const;

type Tier = (typeof TIERS)[number];

function tierFor(wPx: number, hPx: number): Tier | null {
  return TIERS.find((t) => wPx >= t.minW && hPx >= t.minH) ?? null;
}

/** A mean with a direction to colour: measured, finite, and not exactly zero. */
function directional(mean: number | null): mean is number {
  return mean !== null && Number.isFinite(mean) && mean !== 0;
}

/** Ramp step 0–3 for a directional mean. */
function tileLevel(mean: number): number {
  const t = Math.min(1, Math.abs(mean) / FULL_SCALE);
  return t < 0.3 ? 0 : t < 0.6 ? 1 : t < 0.85 ? 2 : 3;
}

/**
 * Colour for one sector's mean move.
 *
 * Two different neutrals, and the difference is the point. A sector whose members all finished
 * exactly level HAS a measurement and it is zero, so it takes `--data-neutral`. A sector where no
 * member holds a return today has NO average to report, so it takes a visibly paler wash and a
 * dash — painting it the colour of 0% would claim a measurement nobody made, which is the most
 * likely way this system could lie on screen.
 */
function tileFill(mean: number | null): string {
  if (directional(mean)) return RAMP[mean > 0 ? "pos" : "neg"][tileLevel(mean)];
  if (mean === 0) return "var(--data-neutral)";
  return "color-mix(in srgb, var(--data-neutral) 42%, var(--surface-card))";
}

/** Only the -700 step and darker can carry white text at these sizes. */
function isDeep(mean: number | null): boolean {
  return directional(mean) && tileLevel(mean) >= 2;
}

/** NULL sector is a real group — tickers with no assigned sector — not an error. */
function sectorLabel(sector: string | null): string {
  return sector ?? "Khác";
}

/** Rendered size of an element, tracked across resizes. Drives both the layout and the tiers. */
function useElementSize<T extends HTMLElement>(): [
  React.RefObject<T | null>,
  { w: number; h: number },
] {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    setSize({ w: box.width, h: box.height });
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return [ref, size];
}

/**
 * "Diễn biến ngành" — area by turnover, colour by mean session move.
 *
 * Two figures the API publishes are carried into the tooltip rather than dropped: `n_with_return`
 * (the actual denominator of `mean_ret_1d`, so a two-stock average is not read with the same
 * weight as a twenty-four-stock one) and the turnover the area encodes.
 */
export function SectorTreemap({ state }: { state: ResourceState<MarketSectorsResponse> }) {
  return (
    <Panel title="Diễn biến ngành" note="Diện tích: GT · Màu: ±%">
      {state.kind === "loading" && <LoadingState rows={4} label="Đang tải diễn biến ngành" />}
      {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}
      {state.kind === "data" && <TreemapBody sectors={state.data.sectors} />}
    </Panel>
  );
}

function TreemapBody({ sectors }: { sectors: SectorRow[] }) {
  const [wrapRef, size] = useElementSize<HTMLDivElement>();
  const [hovered, setHovered] = useState<string | null>(null);

  const VW = size.w > 1 ? size.w : FALLBACK_W;
  const VH = size.h > 1 ? size.h : FALLBACK_H;

  const tiles = squarify(
    sectors.map((s) => ({ key: sectorLabel(s.sector), size: s.total_turnover ?? 0 })),
    VW,
    VH,
  );

  if (tiles.length === 0) {
    return <EmptyState scope="Ghi chú" message="Chưa có giá trị giao dịch nào cho phiên này." />;
  }

  const bySector = new Map(sectors.map((s) => [sectorLabel(s.sector), s]));
  const hoveredTile = hovered ? tiles.find((t) => t.key === hovered) : undefined;
  const hoveredRow = hovered ? bySector.get(hovered) : undefined;

  const pctOf = (s: SectorRow): string =>
    s.mean_ret_1d === null ? DASH : formatPercent(s.mean_ret_1d);

  return (
    <div className="as-treemap-wrap" ref={wrapRef}>
      <svg
        className="as-treemap"
        viewBox={`0 0 ${VW} ${VH}`}
        role="img"
        aria-label="Bản đồ nhiệt giá trị giao dịch theo ngành"
      >
        {tiles.map((t) => {
          const s = bySector.get(t.key);
          if (!s) return null;
          return (
            <rect
              key={t.key}
              x={t.x}
              y={t.y}
              width={t.w}
              height={t.h}
              fill={tileFill(s.mean_ret_1d)}
              className="as-treemap__tile"
              tabIndex={0}
              role="img"
              aria-label={`${t.key} ${pctOf(s)}, giá trị giao dịch ${formatBillion(
                s.total_turnover,
              )} tỷ đồng, ${formatInt(s.n_tickers)} mã`}
              onPointerEnter={() => setHovered(t.key)}
              onPointerLeave={() => setHovered(null)}
              onFocus={() => setHovered(t.key)}
              onBlur={() => setHovered(null)}
            />
          );
        })}
      </svg>

      {/* Labels are HTML over the SVG, not <text> inside it. Each sits in its own box with
          `overflow: hidden`, so a label physically CANNOT paint outside the tile it names — the
          defect this replaces was structural, and so is the fix. The layer ignores the pointer so
          the rect underneath still receives hover. */}
      <div className="as-treemap__labels" aria-hidden="true">
        {tiles.map((t) => {
          const s = bySector.get(t.key);
          if (!s) return null;
          // viewBox units ARE pixels here, so the tier test needs no scale factor.
          const tier = tierFor(t.w, t.h);
          if (!tier) return null;
          const deep = isDeep(s.mean_ret_1d);
          return (
            <div
              key={t.key}
              className={`as-treemap__label${deep ? " as-treemap__label--deep" : ""}`}
              style={{
                left: `${(t.x / VW) * 100}%`,
                top: `${(t.y / VH) * 100}%`,
                width: `${(t.w / VW) * 100}%`,
                height: `${(t.h / VH) * 100}%`,
                padding: tier.pad,
              }}
            >
              {tier.lines > 0 && (
                <span
                  className="as-treemap__name"
                  style={{ fontSize: `${tier.name}px`, WebkitLineClamp: tier.lines }}
                >
                  {t.key}
                </span>
              )}
              <span className="as-treemap__pct" style={{ fontSize: `${tier.pct}px` }}>
                {pctOf(s)}
              </span>
            </div>
          );
        })}
      </div>

      {hoveredTile && hoveredRow && (
        <ChartTooltip
          left={(hoveredTile.x + hoveredTile.w / 2) / VW}
          top={(hoveredTile.y + hoveredTile.h / 2) / VH}
          title={hoveredTile.key}
          rows={[
            { label: "% thay đổi", value: pctOf(hoveredRow) },
            { label: "GT giao dịch", value: `${formatBillion(hoveredRow.total_turnover)} tỷ đ` },
            { label: "Số mã", value: formatInt(hoveredRow.n_tickers) },
            { label: "Mã có TSSL", value: formatInt(hoveredRow.n_with_return) },
          ]}
        />
      )}
    </div>
  );
}
