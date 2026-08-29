import { describe, expect, it } from "vitest";
import {
  DASH,
  formatDate,
  formatDecimal,
  formatInt,
  formatPercent,
  formatTurnoverTy,
  signClass,
} from "@/components/market/format";

/**
 * Two invariants are worth a test rather than care.
 *
 * **null is not zero.** D-13 names rendering a null as 0 as the single most likely way this
 * system's design turns into a lie on screen: 0 asserts a measurement was made and came out
 * nought, null says nothing was measured. Every formatter must map null to a dash.
 *
 * **The turnover conversion is one-way and applies to one unit.** `close` is in nghìn đồng, so
 * `turnover_value` inherits it and `formatTurnoverTy` divides by 1e6 to reach tỷ đồng. Applying
 * that to `index_close` — an index level with no currency unit — would be a units error on the
 * most recognisable number on the market screen, which is why it lives in exactly one function.
 */

const NULLISH = [null, undefined, Number.NaN, Number.POSITIVE_INFINITY] as const;

describe("null is not zero", () => {
  it("maps every absent value to a dash, in every formatter", () => {
    for (const v of NULLISH) {
      expect(formatPercent(v)).toBe(DASH);
      expect(formatInt(v)).toBe(DASH);
      expect(formatDecimal(v)).toBe(DASH);
      expect(formatTurnoverTy(v)).toBe(DASH);
    }
    expect(formatDate(null)).toBe(DASH);
    expect(formatDate(undefined)).toBe(DASH);
    expect(formatDate("")).toBe(DASH);
  });

  it("still renders a real zero as zero", () => {
    expect(formatPercent(0)).not.toBe(DASH);
    expect(formatInt(0)).not.toBe(DASH);
    expect(formatDecimal(0)).not.toBe(DASH);
    expect(formatTurnoverTy(0)).not.toBe(DASH);
  });

  it("treats a null as neutral for colouring, never as a direction", () => {
    expect(signClass(null)).toBe("flat");
    expect(signClass(undefined)).toBe("flat");
    expect(signClass(Number.NaN)).toBe("flat");
    expect(signClass(0)).toBe("flat");
    expect(signClass(0.01)).toBe("pos");
    expect(signClass(-0.01)).toBe("neg");
  });
});

describe("ratios are fractions", () => {
  it("renders 0.07 as +7%, signed", () => {
    expect(formatPercent(0.07)).toBe("+7,00%");
    expect(formatPercent(-0.0325)).toBe("-3,25%");
  });

  // exceptZero: a genuine 0.00% carries no sign, because it is neither a gain nor a loss.
  it("does not sign an exact zero", () => {
    expect(formatPercent(0)).toBe("0,00%");
  });
});

describe("turnover conversion", () => {
  it("divides nghìn đồng by 1e6 to reach tỷ đồng", () => {
    // 8,352,129,774 nghìn đồng = 8352.13 tỷ đồng
    expect(formatTurnoverTy(8_352_129_774)).toBe("8.352,13");
    expect(formatTurnoverTy(1_000_000)).toBe("1,00");
  });

  // The guard this test exists for: an index level must never be routed through the conversion.
  // 1732.02 points would render as "0,00" tỷ đồng — a plausible-looking wrong number.
  it("would visibly destroy an index level, which is why index_close never passes through it", () => {
    expect(formatTurnoverTy(1732.02)).toBe("0,00");
    expect(formatDecimal(1732.02)).toBe("1.732,02");
  });
});

describe("formatDate", () => {
  // Parsed by hand rather than through `new Date(...)`, which applies a timezone shift and can
  // move a session date by a day.
  it("renders an ISO date as dd/mm/yyyy without a timezone shift", () => {
    expect(formatDate("2026-08-18")).toBe("18/08/2026");
    expect(formatDate("2025-01-02T00:00:00Z")).toBe("02/01/2025");
  });

  it("passes an unparseable value through rather than inventing one", () => {
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });
});

describe("formatDecimal width", () => {
  // F̄(S) ranges roughly 0.22–0.27 across the research years; two decimals would collapse
  // distinctions the API deliberately keeps at six.
  it("honours an explicit digit count", () => {
    expect(formatDecimal(0.262929, 4)).toBe("0,2629");
    expect(formatDecimal(0.262929)).toBe("0,26");
  });
});
