/**
 * Squarified treemap layout — pure geometry, no React and no DOM.
 *
 * Separated from the component that draws it for one reason: this is the only piece of P10 with a
 * correct answer that can be checked without a browser. `apps/web/tests/treemap.test.ts` asserts
 * that the tiles tile — no overlap, no gaps, areas proportional to the inputs — which is exactly
 * the property that is invisible by eye on real data, where every sector has a different size and
 * a wrong tile just looks like a big sector.
 *
 * The algorithm is Bruls, Huizing and van Wijk's squarified treemap: lay items out in rows along
 * the shorter side of the remaining rectangle, extending the current row while doing so improves
 * the worst aspect ratio in it, and starting a new row when it does not. Sorting descending is
 * part of the algorithm, not a presentation choice — it is what keeps the aspect ratios near 1.
 */

export interface TreemapItem {
  /** Stable identity, returned on the tile. Not rendered — the caller owns labelling. */
  key: string;
  /** Area weight. Non-positive and non-finite values are dropped, never drawn as a sliver. */
  size: number;
}

export interface TreemapTile {
  key: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Worst aspect ratio in `areas` if laid across a strip of length `side`.
 *
 * Returns Infinity for an empty row so that the caller's "does adding this improve things?"
 * comparison always admits the first item.
 */
function worstAspect(areas: number[], side: number): number {
  if (areas.length === 0) return Number.POSITIVE_INFINITY;
  let total = 0;
  let max = -Infinity;
  let min = Infinity;
  for (const a of areas) {
    total += a;
    if (a > max) max = a;
    if (a < min) min = a;
  }
  if (total <= 0 || min <= 0) return Number.POSITIVE_INFINITY;
  const s2 = total * total;
  const w2 = side * side;
  return Math.max((w2 * max) / s2, s2 / (w2 * min));
}

/**
 * Lay `items` out over a `width` × `height` rectangle anchored at the origin.
 *
 * Total tile area equals `width * height` (to floating-point tolerance) whenever any item has a
 * positive size; an empty or all-non-positive input returns an empty array rather than a
 * zero-area tile per item, because a sector with no turnover has no place on a turnover treemap.
 */
export function squarify(
  items: readonly TreemapItem[],
  width: number,
  height: number,
): TreemapTile[] {
  if (width <= 0 || height <= 0) return [];

  const usable = items.filter((i) => Number.isFinite(i.size) && i.size > 0);
  const total = usable.reduce((acc, i) => acc + i.size, 0);
  if (total <= 0) return [];

  // Work in output units from the start, so no scaling is needed when a row is placed.
  const scale = (width * height) / total;
  const sorted = usable
    .map((i) => ({ key: i.key, area: i.size * scale }))
    .sort((a, b) => b.area - a.area || (a.key < b.key ? -1 : 1));

  const tiles: TreemapTile[] = [];

  // The free rectangle, shrinking as rows are placed.
  let x = 0;
  let y = 0;
  let w = width;
  let h = height;

  let row: Array<{ key: string; area: number }> = [];

  const placeRow = () => {
    if (row.length === 0) return;
    const rowArea = row.reduce((acc, r) => acc + r.area, 0);

    if (w >= h) {
      // Vertical strip down the left edge of what remains.
      const stripW = rowArea / h;
      let cy = y;
      for (const r of row) {
        const tileH = r.area / stripW;
        tiles.push({ key: r.key, x, y: cy, w: stripW, h: tileH });
        cy += tileH;
      }
      x += stripW;
      w -= stripW;
    } else {
      // Horizontal strip across the top of what remains.
      const stripH = rowArea / w;
      let cx = x;
      for (const r of row) {
        const tileW = r.area / stripH;
        tiles.push({ key: r.key, x: cx, y, w: tileW, h: stripH });
        cx += tileW;
      }
      y += stripH;
      h -= stripH;
    }
    row = [];
  };

  for (const item of sorted) {
    const side = Math.min(w, h);
    const areas = row.map((r) => r.area);
    if (worstAspect(areas, side) >= worstAspect([...areas, item.area], side)) {
      row.push(item);
    } else {
      placeRow();
      row.push(item);
    }
  }
  placeRow();

  return tiles;
}
