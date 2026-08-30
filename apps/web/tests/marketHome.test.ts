import { describe, expect, it } from "vitest";
import { MOVER_RET_FIELD, type MoverHorizon, type MoverRow } from "@/lib/api";
import { axisDate, niceStep, priceTicks } from "@/components/charts/scale";
import { MOCK_INDEX_HISTORY, MOCK_MARKET_LIQUIDITY, MOCK_TOP_GAINERS } from "@/lib/mock";

/**
 * The market home screen's pure logic.
 *
 * Same rule as the other files here: only things with a correct answer that can be checked
 * without a browser. The panels themselves are verified by running them; what is testable is the
 * horizon-to-column map (a wrong entry silently mislabels a whole column), the axis maths, and
 * the fixtures' own shape.
 */

describe("MOVER_RET_FIELD", () => {
  const HORIZONS: MoverHorizon[] = ["1d", "5d", "1m", "3m", "1y"];

  it("maps every horizon to the column the API ranks by", () => {
    // Mirrors `_HORIZON_COLUMN` in services/api/app/routes/market.py. The two tables are the
    // same contract written on both sides of the wire, and this is the assertion that says so:
    // "1m" means twenty sessions, not one month, and the display label is the only thing that
    // says "month" anywhere.
    expect(MOVER_RET_FIELD).toEqual({
      "1d": "ret_1d",
      "5d": "ret_5d",
      "1m": "ret_20d",
      "3m": "ret_60d",
      "1y": "ret_252d",
    });
  });

  it("covers every horizon and names a real field of MoverRow", () => {
    const row: MoverRow = MOCK_TOP_GAINERS.movers[0];
    for (const h of HORIZONS) {
      expect(MOVER_RET_FIELD[h]).toBeDefined();
      // `in` rather than a truthiness check: a legitimately null return must still count as
      // present, and MOCK ret_252d IS null on one fixture row precisely to exercise that.
      expect(MOVER_RET_FIELD[h] in row).toBe(true);
    }
  });

  it("gives each horizon a distinct column", () => {
    const fields = HORIZONS.map((h) => MOVER_RET_FIELD[h]);
    expect(new Set(fields).size).toBe(fields.length);
  });
});

describe("niceStep", () => {
  it("returns 1, 2, 2.5 or 5 times a power of ten", () => {
    for (const span of [3, 17, 128, 1_450, 99_999, 0.04]) {
      const step = niceStep(span, 5);
      const mantissa = step / 10 ** Math.floor(Math.log10(step));
      expect([1, 2, 2.5, 5, 10]).toContainEqual(Math.round(mantissa * 10) / 10);
    }
  });

  it("does not divide by zero or return a non-finite step for a degenerate span", () => {
    // A dead-flat series. The chart must still draw an axis rather than NaN gridlines.
    for (const span of [0, -5, Number.NaN]) {
      expect(niceStep(span, 5)).toBe(1);
    }
  });
});

describe("priceTicks", () => {
  it("covers the band and stays inside it", () => {
    const ticks = priceTicks(1_412.4, 1_896.2);
    expect(ticks.length).toBeGreaterThan(2);
    for (const t of ticks) {
      expect(t).toBeGreaterThanOrEqual(1_412.4);
      expect(t).toBeLessThanOrEqual(1_896.2);
    }
  });

  it("is strictly ascending and evenly spaced", () => {
    const ticks = priceTicks(1_000, 1_500);
    const gaps = ticks.slice(1).map((t, i) => Math.round((t - ticks[i]) * 1e6) / 1e6);
    expect(new Set(gaps).size).toBe(1);
    expect(gaps[0]).toBeGreaterThan(0);
  });

  it("terminates with a bounded tick count on any band, degenerate ones included", () => {
    // The loop increments by `step`, so the property that matters is TERMINATION — a step of 0
    // or NaN would spin forever and hang the render. It is not that a narrow band yields few
    // ticks: `niceStep` scales the step to the span, so 1000.00–1000.05 correctly gets a 0.01
    // step and six ticks. A flat series (lo === hi) is the real degenerate case.
    for (const [lo, hi] of [
      [1_000, 1_000],
      [1_000, 1_000.05],
      [0, 0],
      [-50, 50],
      [1_412.4, 1_896.2],
    ]) {
      const ticks = priceTicks(lo, hi);
      expect(ticks.length).toBeGreaterThanOrEqual(1);
      expect(ticks.length).toBeLessThan(40);
      expect(ticks.every(Number.isFinite)).toBe(true);
    }
  });
});

describe("axisDate", () => {
  it("labels months over a long range and days over a short one", () => {
    expect(axisDate("2026-08-18", true)).toBe("08/26");
    expect(axisDate("2026-08-18", false)).toBe("18/08");
  });

  it("passes an unparseable value through rather than inventing a date", () => {
    expect(axisDate("not-a-date", true)).toBe("not-a-date");
  });

  it("does not shift the date across a timezone", () => {
    // Parsed by regex, never by `new Date(...)`, which would apply a UTC offset and can move a
    // session by a day. Same rule format.ts states for formatDate.
    expect(axisDate("2026-01-01", false)).toBe("01/01");
    expect(axisDate("2026-12-31", false)).toBe("31/12");
  });
});

describe("fixtures", () => {
  it("the index mock is deterministic and ends on the shared session date", () => {
    // A fixture that changed shape on every reload would make a rendering regression
    // indistinguishable from new random data.
    expect(MOCK_INDEX_HISTORY.bars).toHaveLength(252);
    expect(MOCK_INDEX_HISTORY.bars.at(-1)?.bar_date).toBe("2026-08-18");
    // First bar has no previous close, so no return. Null, never 0.
    expect(MOCK_INDEX_HISTORY.bars[0].ret_1d).toBeNull();
    expect(MOCK_INDEX_HISTORY.bars[1].ret_1d).not.toBeNull();
  });

  it("the index mock skips weekends", () => {
    for (const bar of MOCK_INDEX_HISTORY.bars) {
      const day = new Date(`${bar.bar_date}T00:00:00Z`).getUTCDay();
      expect(day).not.toBe(0);
      expect(day).not.toBe(6);
    }
  });

  it("the liquidity mock is ordered by turnover, descending", () => {
    const values = MOCK_MARKET_LIQUIDITY.stocks.map((s) => s.turnover_value ?? 0);
    const sorted = [...values].sort((a, b) => b - a);
    expect(values).toEqual(sorted);
  });

  it("one mover fixture carries a null 1Y return", () => {
    // The warm-up path — a ticker with fewer than 253 sessions — must be on screen in local
    // development by default, not only in production.
    const nulls = MOCK_TOP_GAINERS.movers.filter((m) => m.ret_252d === null);
    expect(nulls.length).toBeGreaterThan(0);
  });
});
