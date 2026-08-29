"use client";

import { useEffect, useRef, useState } from "react";
import type { MarketSectorsResponse, SectorRow } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { squarify } from "@/components/charts/treemap";
import { ChartTooltip } from "@/components/charts/ChartHover";
import panel from "./MarketHome.module.css";
import styles from "./Market.module.css";
import { DASH, formatInt, formatPercent, formatTurnoverTy } from "./format";

/**
 * The treemap's coordinate space is its MEASURED pixel box, not a fixed viewBox.
 *
 * Every other chart here uses a fixed viewBox scaled by CSS, and that is right for them: a line
 * chart has a shape it wants to keep. A treemap has no intrinsic aspect ratio — it fills a
 * rectangle by construction — and a fixed one left it 90px short of the chart panel beside it in
 * the 1.72:1 split, with dead space under the tiles. Measuring instead makes it fill the panel at
 * every width, and has a second effect worth naming: viewBox units are now CSS pixels, so the
 * label tiers below compare tile size against font size directly rather than through a scale
 * factor that had to be tracked separately.
 *
 * The fallback box is used for the single frame before the ResizeObserver reports, and whenever
 * the element is unmeasurable (jsdom, a display:none ancestor).
 */
const FALLBACK_W = 640;
const FALLBACK_H = 360;

/** Where the colour ramp saturates: ±3% in a session is already a strong move on HOSE. */
const FULL_SCALE = 0.03;

/**
 * What a tile is big enough to say, in **rendered pixels** — which, since the viewBox is now the
 * measured box, is also what the tile geometry is in.
 *
 * The predecessor to this table gated on viewBox width alone (`MIN_LABEL_W = 54`), which asked
 * whether the tile was wide, never whether the label fitted. "Bất động sản và Xây dựng" at 13px
 * is ~150px wide; in a 55px tile it overhung by ~100 and was then half-painted-over by the next
 * tile's rect, so it read as a label belonging to the wrong sector. Tiers plus the
 * `overflow: hidden` on each label box replace that guess with a rule.
 */
const TIERS = [
  { minW: 140, minH: 64, name: 14, pct: 13, lines: 2 },
  { minW: 80, minH: 44, name: 12, pct: 12, lines: 1 },
  { minW: 48, minH: 26, name: 0, pct: 11, lines: 0 },
] as const;

type Tier = (typeof TIERS)[number] | null;

function tierFor(wPx: number, hPx: number): Tier {
  return TIERS.find((t) => wPx >= t.minW && hPx >= t.minH) ?? null;
}

/**
 * Colour for one sector's mean move.
 *
 * `null` is NOT 0. A sector where no member holds a return today has no average to report, and
 * painting it the colour of "unchanged" would claim a measurement that was never made — the exact
 * failure D-13 names as the most likely way this system lies on screen. It gets the neutral token
 * and a dash, and reads as absent rather than flat.
 */
function tileFill(mean: number | null): string {
  if (mean === null || !Number.isFinite(mean)) return "var(--data-neutral)";
  if (mean === 0) return "var(--data-neutral)";
  const intensity = Math.min(1, Math.abs(mean) / FULL_SCALE);
  // 0.22 floor: the weakest non-zero move must still read as directional, not as neutral.
  const alpha = 0.22 + 0.78 * intensity;
  return mean > 0
    ? `color-mix(in srgb, var(--data-pos-mark) ${Math.round(alpha * 100)}%, transparent)`
    : `color-mix(in srgb, var(--data-neg-mark) ${Math.round(alpha * 100)}%, transparent)`;
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
 * Two things the API publishes are deliberately carried into the tooltip rather than dropped:
 * `n_with_return` (the actual denominator of `mean_ret_1d`, so a two-stock average is not read
 * with the same weight as a twenty-four-stock one) and the turnover the area encodes.
 */
export function SectorTreemap({ state }: { state: ResourceState<MarketSectorsResponse> }) {
  return (
    <section className={panel.panel} aria-label="Diễn biến ngành">
      <div className={panel.panelHead}>
        <h2 className={panel.panelTitle}>Diễn biến ngành</h2>
        <span className={panel.panelNote}>Diện tích: GT · Màu: ±%</span>
      </div>

      <div className={panel.panelBody}>
        {state.kind === "loading" && <LoadingState rows={4} label="Đang tải diễn biến ngành" />}
        {state.kind === "error" && <ErrorState code={state.code} message={state.message} />}

        {state.kind === "data" && <TreemapBody sectors={state.data.sectors} />}
      </div>
    </section>
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
    return (
      <EmptyState scope="Ghi chú" message="Chưa có giá trị giao dịch nào cho phiên này." />
    );
  }

  const bySector = new Map(sectors.map((s) => [sectorLabel(s.sector), s]));
  const hoveredTile = hovered ? tiles.find((t) => t.key === hovered) : undefined;
  const hoveredRow = hovered ? bySector.get(hovered) : undefined;

  const pctOf = (s: SectorRow): string =>
    s.mean_ret_1d === null ? DASH : formatPercent(s.mean_ret_1d);

  return (
    <div className={styles.treemapWrap} ref={wrapRef}>
      <svg
        className={styles.treemap}
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
              className={styles.treemapTile}
              tabIndex={0}
              role="img"
              aria-label={`${t.key} ${pctOf(s)}, giá trị giao dịch ${formatTurnoverTy(
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

      {/* Labels are HTML over the SVG, not <text> inside it (P11 S5). Each sits in its own box
          with `overflow: hidden`, so a label physically cannot paint outside its tile — the
          defect this replaces was structural, and so is the fix. The layer ignores the pointer so
          the rect underneath still receives hover. */}
      <div className={styles.treemapLabels} aria-hidden="true">
        {tiles.map((t) => {
          const s = bySector.get(t.key);
          if (!s) return null;
          // viewBox units ARE pixels now, so the tier test needs no scale factor.
          const tier = tierFor(t.w, t.h);
          if (!tier) return null;
          return (
            <div
              key={t.key}
              className={styles.tileLabel}
              style={{
                left: `${(t.x / VW) * 100}%`,
                top: `${(t.y / VH) * 100}%`,
                width: `${(t.w / VW) * 100}%`,
                height: `${(t.h / VH) * 100}%`,
              }}
            >
              {tier.lines > 0 && (
                <span
                  className={styles.tileName}
                  style={{ fontSize: `${tier.name}px`, WebkitLineClamp: tier.lines }}
                >
                  {t.key}
                </span>
              )}
              <span className={styles.tilePct} style={{ fontSize: `${tier.pct}px` }}>
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
            {
              label: "GT giao dịch",
              value: `${formatTurnoverTy(hoveredRow.total_turnover)} tỷ đ`,
            },
            { label: "Số mã", value: formatInt(hoveredRow.n_tickers) },
            { label: "Mã có TSSL", value: formatInt(hoveredRow.n_with_return) },
          ]}
        />
      )}
    </div>
  );
}
