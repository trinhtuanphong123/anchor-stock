/**
 * Display formatting for the market screen. Vietnamese locale throughout.
 *
 * One rule governs this file: **null is not zero.** Every formatter maps a null/undefined to an
 * em dash rather than to "0" or "0,00%". A missing indicator means the history was too short to
 * compute it; rendering 0 there would state that the price did not move, which is a claim the
 * data does not make.
 *
 * The second rule: the API sends ratios as FRACTIONS (0.07 = +7%). The conversion to a percent
 * sign happens here and nowhere else, so there is exactly one place it can be wrong.
 */

/** What a null renders as. */
export const DASH = "—";

const INT_FMT = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

/** Decimal formatters, cached per width — constructing an Intl formatter is not cheap. */
const DEC_FMTS = new Map<number, Intl.NumberFormat>();
function decFmt(digits: number): Intl.NumberFormat {
  let fmt = DEC_FMTS.get(digits);
  if (!fmt) {
    fmt = new Intl.NumberFormat("vi-VN", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    DEC_FMTS.set(digits, fmt);
  }
  return fmt;
}
const PCT_FMT = new Intl.NumberFormat("vi-VN", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});

/** A fraction (0.0712) as a signed percent ("+7,12%"). Null → dash. */
export function formatPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return DASH;
  return PCT_FMT.format(fraction);
}

/** A whole number with Vietnamese grouping. Null → dash. */
export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return INT_FMT.format(value);
}

/**
 * Turnover, converted from the stored unit to **tỷ đồng**.
 *
 * The unit chain, written down because nothing in the schema declares it and the next person to
 * read `turnover_value` will have the same question:
 *
 *   `daily_bars.close` is in **nghìn đồng** (thousands of VND) — the vnstock convention, and
 *   why VCB reads 92,40 rather than 92.400. `technical_indicators_daily.turnover_value` is
 *   `close * volume` (`00004_indicators.sql:54`), so it inherits that unit: it is in nghìn
 *   đồng, not đồng.
 *
 * Therefore tỷ đồng = nghìn đồng / 1e6. Confirmed by the project owner, not inferred from the
 * magnitudes — an earlier pass deliberately refused to guess and labelled the figure "theo đơn
 * vị nguồn" instead.
 *
 * This conversion lives here and nowhere else, so there is exactly one place it can be wrong.
 * It applies to `turnover_value` and `total_turnover` ONLY. It must never be applied to
 * `index_close`, which is an index level in points and carries no currency unit at all.
 */
const THOUSAND_VND_PER_TY = 1_000_000;

export function formatTurnoverTy(thousandVnd: number | null | undefined): string {
  if (thousandVnd === null || thousandVnd === undefined || !Number.isFinite(thousandVnd)) {
    return DASH;
  }
  return decFmt(2).format(thousandVnd / THOUSAND_VND_PER_TY);
}

/**
 * A fixed-width decimal with Vietnamese grouping. Null → dash.
 *
 * `digits` is explicit for model figures. Two decimals is right for a price and wrong for a
 * coverage: F̄(S) ranges roughly 0.22–0.27 across the five research years, so rendering it as
 * "0,26" collapses distinctions the API deliberately keeps at six decimals.
 */
export function formatDecimal(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return decFmt(digits).format(value);
}

/**
 * An ISO date as `dd/mm/yyyy`. Parsed by hand rather than through `new Date(...)`, which would
 * apply a timezone shift and can move a session date by a day.
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const [, y, m, d] = match;
  return `${d}/${m}/${y}`;
}

/** Sign class for a fraction: positive, negative, or neutral (also used for null). */
export function signClass(
  fraction: number | null | undefined,
): "pos" | "neg" | "flat" {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return "flat";
  if (fraction > 0) return "pos";
  if (fraction < 0) return "neg";
  return "flat";
}
