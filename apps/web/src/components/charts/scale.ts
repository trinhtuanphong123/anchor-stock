/**
 * Axis arithmetic shared by every hand-drawn chart in this app.
 *
 * Extracted from `market/IndexChart` when the ticker charts needed the same three functions: a
 * gridline algorithm copied into three files is three places for an axis to start disagreeing
 * with itself, and the whole point of a fixed `viewBox` idiom is that every chart in the product
 * measures the same way.
 *
 * Pure and presentational — no tokens, no React, no domain knowledge.
 */

/**
 * A "nice" step for an axis covering `span` in about `count` divisions — 1, 2, 2.5 or 5 times a
 * power of ten. Without it the gridlines land on values like 1417.3, which is a number no reader
 * has ever wanted on an axis.
 */
export function niceStep(span: number, count: number): number {
  if (!(span > 0)) return 1;
  const rough = span / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / mag;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return step * mag;
}

/** Evenly spaced tick VALUES covering [lo, hi] on a nice step. */
export function priceTicks(lo: number, hi: number, count = 5): number[] {
  const step = niceStep(hi - lo, count);
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
    out.push(Math.round(v * 1e6) / 1e6);
  }
  return out;
}

/**
 * Date label for a session, at the granularity the range warrants.
 *
 * Over a year, `dd/MM` on six labels repeats months and reads as noise; over a month, `MM/yy`
 * gives six identical labels. The axis says what changes across the window and nothing else.
 */
export function axisDate(iso: string, longRange: boolean): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const [, y, mo, d] = m;
  return longRange ? `${mo}/${y.slice(2)}` : `${d}/${mo}`;
}

/**
 * The indexes of `count` labels spread across a series of `n` points, first and last included.
 * Duplicates are dropped, so a short series gets fewer labels rather than the same one twice.
 */
export function labelIndexes(n: number, count: number): number[] {
  if (n <= 0) return [];
  return Array.from({ length: count }, (_, k) => Math.round((k / (count - 1)) * (n - 1))).filter(
    (v, k, a) => a.indexOf(v) === k,
  );
}
