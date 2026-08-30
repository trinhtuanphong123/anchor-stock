/**
 * Display formatting for the market screen.
 *
 * One rule governs this file: **null is not zero.** Every formatter maps a null/undefined to an
 * em dash rather than to "0" or "0.00%". A missing indicator means the history was too short to
 * compute it; rendering 0 there would state that the price did not move, which is a claim the
 * data does not make.
 *
 * The second rule: the API sends ratios as FRACTIONS (0.07 = +7%). The conversion to a percent
 * sign happens here and nowhere else, so there is exactly one place it can be wrong. That is
 * also why `dist_from_sma_200_pct` and `drawdown_from_252d_high` — fractions despite the names —
 * go through `formatPercent` raw, never pre-multiplied by a caller.
 *
 * Numbers read `1,234.56`: comma for thousands, dot for decimals. The grouping is done by hand
 * rather than through `Intl.NumberFormat` so the output does not depend on a locale argument
 * that a later edit could quietly change, and so a figure looks the same wherever it is read.
 */

/** What a null renders as. */
export const DASH = "—";

/** `1234.5` at 2 digits → `"1,234.50"`. Sign is applied outside the grouping. */
function group(value: number, digits: number): string {
  const [whole, fraction] = Math.abs(value).toFixed(digits).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (value < 0 ? "-" : "") + grouped + (fraction ? "." + fraction : "");
}

function isNum(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value);
}

/** A fraction (0.0712) as a signed percent ("+7.12%"). Null → dash. */
export function formatPercent(fraction: number | null | undefined): string {
  if (!isNum(fraction)) return DASH;
  return (fraction > 0 ? "+" : "") + group(fraction * 100, 2) + "%";
}

/**
 * A fraction as an UNSIGNED percent ("18.42%") — a SHARE of a total, not a return.
 *
 * Separate from {@link formatPercent} because the leading "+" is the whole difference: a share of
 * turnover cannot be negative, and "+18.42%" reads as a gain. The grouping and the decimal point
 * are the same as everywhere else in this file, so a share and a return still line up in adjacent
 * columns. Null → dash.
 */
export function formatShare(fraction: number | null | undefined): string {
  if (!isNum(fraction)) return DASH;
  return group(fraction * 100, 2) + "%";
}

/** A whole number, thousands grouped. Null → dash. */
export function formatInt(value: number | null | undefined): string {
  if (!isNum(value)) return DASH;
  return group(value, 0);
}

/**
 * A fixed-width decimal. Null → dash.
 *
 * `digits` is explicit for model figures. Two decimals is right for a price and wrong for a
 * coverage: F̄(S) ranges roughly 0.22–0.27 across the five research years, so rendering it as
 * "0.26" collapses distinctions the API deliberately keeps at six decimals.
 */
export function formatDecimal(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return DASH;
  return group(value, digits);
}

/**
 * Turnover, converted from the stored unit to a currency the reader can hold in their head.
 *
 * The unit chain, written down because nothing in the schema declares it and the next person to
 * read `turnover_value` will have the same question:
 *
 *   `daily_bars.close` is in **nghìn đồng** (thousands of VND) — the vnstock convention, and
 *   why VCB reads 92.40 rather than 92,400. `technical_indicators_daily.turnover_value` is
 *   `close * volume` (`00004_indicators.sql:54`), so it inherits that unit: it is in nghìn
 *   đồng, not đồng.
 *
 * Therefore tỷ đồng = nghìn đồng / 1e6, and nghìn tỷ đồng = nghìn đồng / 1e9. Confirmed by the
 * project owner, not inferred from the magnitudes — an earlier pass deliberately refused to
 * guess and labelled the figure "theo đơn vị nguồn" instead.
 *
 * Two units coexist on purpose: a table row is read against its neighbours and stays in tỷ đ,
 * while a basket-level total in tỷ đ runs to five digits and stops being a quantity anyone
 * reads. Both conversions live here and nowhere else, so there is exactly one place each can be
 * wrong. They apply to `turnover_value` and `total_turnover` ONLY, and must never be applied to
 * `index_close`, which is an index level in points and carries no currency unit at all.
 */
const THOUSAND_VND_PER_TY = 1_000_000;
const THOUSAND_VND_PER_NGHIN_TY = 1_000_000_000;

/** Per-row turnover in **tỷ đồng**. Null → dash. */
export function formatBillion(thousandVnd: number | null | undefined): string {
  if (!isNum(thousandVnd)) return DASH;
  return group(thousandVnd / THOUSAND_VND_PER_TY, 2);
}

/** Basket-level turnover in **nghìn tỷ đồng**. Null → dash. */
export function formatTrillion(thousandVnd: number | null | undefined): string {
  if (!isNum(thousandVnd)) return DASH;
  return group(thousandVnd / THOUSAND_VND_PER_NGHIN_TY, 2);
}

/**
 * A share count abbreviated for a CHART AXIS, where the tick gutter is 64 viewBox units wide and
 * a grouped integer ("12,345,678") does not fit in it.
 *
 * The unit is named in the label — "1.2 tr", "850 ng" — because an abbreviation with the unit
 * stripped off is the one number on a chart a reader cannot check. Used on the volume scale only;
 * a figure a reader is meant to read exactly still goes through {@link formatInt}. Null → dash.
 */
export function formatCompactVolume(value: number | null | undefined): string {
  if (!isNum(value)) return DASH;
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return group(value / 1_000_000_000, 1) + " tỷ";
  if (abs >= 1_000_000) return group(value / 1_000_000, 1) + " tr";
  if (abs >= 1_000) return group(value / 1_000, 0) + " ng";
  return group(value, 0);
}

/**
 * ISO dates, parsed by hand rather than through `new Date(...)`, which would apply a timezone
 * shift and can move a session date by a day.
 */
function isoParts(iso: string): [string, string, string] | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return match ? [match[1], match[2], match[3]] : null;
}

/** A session date as `DD/MM/YY` — the board form, where the year is context, not information. */
export function formatSession(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const parts = isoParts(iso);
  if (!parts) return iso;
  const [y, m, d] = parts;
  return `${d}/${m}/${y.slice(2)}`;
}

/**
 * A date as `DD/MM/YYYY`, for the run-parameter table on `/about` and nowhere else: that table
 * spans an estimation window measured in years, where a two-digit year is the one digit pair a
 * reader would have to reconstruct.
 */
export function formatParamDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const parts = isoParts(iso);
  if (!parts) return iso;
  const [y, m, d] = parts;
  return `${d}/${m}/${y}`;
}

/** Sign class for a fraction: positive, negative, or neutral (also used for null). */
export function signClass(fraction: number | null | undefined): "pos" | "neg" | "flat" {
  if (!isNum(fraction)) return "flat";
  if (fraction > 0) return "pos";
  if (fraction < 0) return "neg";
  return "flat";
}
