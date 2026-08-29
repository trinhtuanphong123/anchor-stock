import { describe, expect, it } from "vitest";
import { squarify, type TreemapItem } from "@/components/charts/treemap";

/**
 * The treemap layout is the one piece of P10 with an answer that is right or wrong independently
 * of how it looks. On real data every sector has a different size, so a mis-sized tile just looks
 * like a big sector — the tiling property is exactly what the eye cannot check.
 */

/** Do two tiles overlap? Touching edges do not count. */
function overlaps(
  a: { x: number; y: number; w: number; h: number },
  b: { x: number; y: number; w: number; h: number },
): boolean {
  const eps = 1e-9;
  return (
    a.x < b.x + b.w - eps &&
    b.x < a.x + a.w - eps &&
    a.y < b.y + b.h - eps &&
    b.y < a.y + a.h - eps
  );
}

const SECTORS: TreemapItem[] = [
  { key: "Ngân hàng", size: 3120450000 },
  { key: "Bất động sản và Xây dựng", size: 2015880000 },
  { key: "Tài chính", size: 1204330000 },
  { key: "Công nghiệp", size: 872140000 },
  { key: "Tiêu dùng", size: 640910000 },
  { key: "Năng lượng", size: 388270000 },
  { key: "Khác", size: 109800000 },
];

describe("squarify", () => {
  it("returns one tile per positive-size item", () => {
    expect(squarify(SECTORS, 640, 300)).toHaveLength(SECTORS.length);
  });

  it("fills the rectangle exactly", () => {
    const tiles = squarify(SECTORS, 640, 300);
    const total = tiles.reduce((acc, t) => acc + t.w * t.h, 0);
    expect(total).toBeCloseTo(640 * 300, 6);
  });

  it("gives each tile an area proportional to its size", () => {
    const tiles = squarify(SECTORS, 640, 300);
    const totalSize = SECTORS.reduce((acc, s) => acc + s.size, 0);
    for (const item of SECTORS) {
      const tile = tiles.find((t) => t.key === item.key);
      expect(tile).toBeDefined();
      const expected = (item.size / totalSize) * 640 * 300;
      expect(tile!.w * tile!.h).toBeCloseTo(expected, 6);
    }
  });

  it("produces no overlapping tiles", () => {
    const tiles = squarify(SECTORS, 640, 300);
    for (let i = 0; i < tiles.length; i += 1) {
      for (let j = i + 1; j < tiles.length; j += 1) {
        expect(overlaps(tiles[i], tiles[j])).toBe(false);
      }
    }
  });

  it("keeps every tile inside the rectangle", () => {
    for (const t of squarify(SECTORS, 640, 300)) {
      expect(t.x).toBeGreaterThanOrEqual(-1e-9);
      expect(t.y).toBeGreaterThanOrEqual(-1e-9);
      expect(t.x + t.w).toBeLessThanOrEqual(640 + 1e-9);
      expect(t.y + t.h).toBeLessThanOrEqual(300 + 1e-9);
    }
  });

  it("is deterministic — equal sizes break ties by key, not by input order", () => {
    const a = squarify(
      [
        { key: "b", size: 10 },
        { key: "a", size: 10 },
      ],
      100,
      100,
    );
    const b = squarify(
      [
        { key: "a", size: 10 },
        { key: "b", size: 10 },
      ],
      100,
      100,
    );
    expect(a.map((t) => t.key)).toEqual(b.map((t) => t.key));
  });

  // A sector with no turnover has no place on a turnover treemap. Emitting a zero-area tile
  // would put an invisible, un-hoverable rectangle in the DOM for it instead.
  it("drops non-positive and non-finite sizes rather than drawing slivers", () => {
    const tiles = squarify(
      [
        { key: "real", size: 100 },
        { key: "zero", size: 0 },
        { key: "negative", size: -5 },
        { key: "nan", size: Number.NaN },
      ],
      200,
      100,
    );
    expect(tiles.map((t) => t.key)).toEqual(["real"]);
    expect(tiles[0].w * tiles[0].h).toBeCloseTo(200 * 100, 6);
  });

  it("returns nothing when there is nothing to draw", () => {
    expect(squarify([], 640, 300)).toEqual([]);
    expect(squarify([{ key: "a", size: 0 }], 640, 300)).toEqual([]);
    expect(squarify(SECTORS, 0, 300)).toEqual([]);
    expect(squarify(SECTORS, 640, -1)).toEqual([]);
  });

  it("handles a single item by filling the whole rectangle", () => {
    const tiles = squarify([{ key: "only", size: 42 }], 640, 300);
    expect(tiles).toEqual([{ key: "only", x: 0, y: 0, w: 640, h: 300 }]);
  });
});
