import { describe, expect, it } from "vitest";
import { nearestPane, type ChartPane } from "@/components/charts/ChartHover";

/**
 * `nearestPane` is the seam that lets a multi-pane chart keep its crosshair and tooltip on the
 * pane the pointer is over, instead of projecting them across every band. Its answer is the one
 * thing in P11's hover work that is right or wrong independently of how it looks, so it is worth
 * pinning: the exact band under the pointer, and the "no dead zones" rule that a cursor in a
 * gutter or the label row still resolves to the pane it borders.
 */

/** The four plot bands of the combined indicator chart, top-to-bottom. */
const PANES: ChartPane[] = [
  { key: "price", top: 8, bottom: 208 },
  { key: "rsi", top: 236, bottom: 296 },
  { key: "macd", top: 324, bottom: 384 },
  { key: "volume", top: 412, bottom: 462 },
];

describe("nearestPane", () => {
  it("is null when there are no panes", () => {
    expect(nearestPane(10, [])).toBeNull();
  });

  it("resolves the pane containing the y", () => {
    expect(nearestPane(100, PANES)).toBe("price");
    expect(nearestPane(260, PANES)).toBe("rsi");
    expect(nearestPane(350, PANES)).toBe("macd");
    expect(nearestPane(440, PANES)).toBe("volume");
  });

  it("maps a gutter to the pane it borders — no dead zones", () => {
    // Between price (bottom 208) and rsi (top 236).
    expect(nearestPane(224, PANES)).toBe("rsi");
    // Between rsi and macd.
    expect(nearestPane(312, PANES)).toBe("macd");
  });

  it("maps above the first band to the first pane", () => {
    expect(nearestPane(0, PANES)).toBe("price");
    expect(nearestPane(-20, PANES)).toBe("price");
  });

  it("maps below the last band (the axis/date row) to the last pane", () => {
    expect(nearestPane(490, PANES)).toBe("volume");
    expect(nearestPane(1000, PANES)).toBe("volume");
  });
});