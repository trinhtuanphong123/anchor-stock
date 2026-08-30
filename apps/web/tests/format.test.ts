import { describe, expect, it } from "vitest";
import {
  DASH,
  formatBillion,
  formatCompactVolume,
  formatDecimal,
  formatInt,
  formatParamDate,
  formatPercent,
  formatShare,
  formatSession,
  formatTrillion,
  signClass,
} from "@/components/market/format";

/**
 * Three invariants are worth a test rather than care.
 *
 * **null is not zero.** D-13 names rendering a null as 0 as the single most likely way this
 * system's design turns into a lie on screen: 0 asserts a measurement was made and came out
 * nought, null says nothing was measured. Every formatter must map null to a dash.
 *
 * **The turnover conversion is one-way and applies to one unit.** `close` is in nghìn đồng, so
 * `turnover_value` inherits it and `formatBillion` divides by 1e6 to reach tỷ đồng — 1e9 for
 * `formatTrillion`. Applying either to `index_close` — an index level with no currency unit —
 * would be a units error on the most recognisable number on the market screen, which is why it
 * lives in exactly two functions and nowhere else.
 *
 * **The number form is fixed, not locale-derived.** `1,234.56`: comma groups thousands, dot
 * separates decimals. A locale argument is what would let that flip silently.
 */

const NULLISH = [null, undefined, Number.NaN, Number.POSITIVE_INFINITY] as const;

describe("null is not zero", () => {
  it("maps every absent value to a dash, in every formatter", () => {
    for (const v of NULLISH) {
      expect(formatPercent(v)).toBe(DASH);
      expect(formatInt(v)).toBe(DASH);
      expect(formatDecimal(v)).toBe(DASH);
      expect(formatBillion(v)).toBe(DASH);
      expect(formatTrillion(v)).toBe(DASH);
      expect(formatShare(v)).toBe(DASH);
    }
    for (const iso of [null, undefined, ""] as const) {
      expect(formatSession(iso)).toBe(DASH);
      expect(formatParamDate(iso)).toBe(DASH);
    }
  });

  it("still renders a real zero as zero", () => {
    expect(formatPercent(0)).not.toBe(DASH);
    expect(formatInt(0)).not.toBe(DASH);
    expect(formatDecimal(0)).not.toBe(DASH);
    expect(formatBillion(0)).not.toBe(DASH);
    expect(formatTrillion(0)).not.toBe(DASH);
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

describe("number form", () => {
  it("groups thousands with a comma and separates decimals with a dot", () => {
    expect(formatInt(1_234_567)).toBe("1,234,567");
    expect(formatDecimal(1234.56)).toBe("1,234.56");
    expect(formatInt(-1234)).toBe("-1,234");
    expect(formatDecimal(-1234.5)).toBe("-1,234.50");
  });

  it("does not group below four digits", () => {
    expect(formatInt(999)).toBe("999");
    expect(formatDecimal(0)).toBe("0.00");
  });
});

describe("ratios are fractions", () => {
  // dist_from_sma_200_pct and drawdown_from_252d_high arrive as fractions despite their names.
  // The ×100 happens here and nowhere else, so a caller that pre-multiplies doubles it.
  it("renders 0.07 as +7%, signed", () => {
    expect(formatPercent(0.07)).toBe("+7.00%");
    expect(formatPercent(-0.0325)).toBe("-3.25%");
    expect(formatPercent(0.05)).toBe("+5.00%");
  });

  it("does not sign an exact zero, because it is neither a gain nor a loss", () => {
    expect(formatPercent(0)).toBe("0.00%");
  });

  // A share of turnover cannot be negative, so a leading "+" would read as a gain on a figure
  // that has no direction. Same grouping and decimal point as everything else, so a share and a
  // return still line up in adjacent columns of the liquidity board.
  it("renders a share unsigned, in the same number form as a return", () => {
    expect(formatShare(0.1842)).toBe("18.42%");
    expect(formatShare(1)).toBe("100.00%");
    expect(formatShare(0)).toBe("0.00%");
  });
});

describe("turnover conversion", () => {
  it("divides nghìn đồng by 1e6 to reach tỷ đồng, for a table row", () => {
    // 8,352,129,774 nghìn đồng = 8,352.13 tỷ đồng
    expect(formatBillion(8_352_129_774)).toBe("8,352.13");
    expect(formatBillion(1_000_000)).toBe("1.00");
  });

  it("divides by 1e9 to reach nghìn tỷ đồng, for the basket total", () => {
    expect(formatTrillion(8_352_129_774)).toBe("8.35");
    expect(formatTrillion(18_420_000_000)).toBe("18.42");
  });

  // The guard these tests exist for: an index level must never be routed through a conversion.
  // 1732.02 points would render as "0.00" tỷ đồng — a plausible-looking wrong number.
  it("would visibly destroy an index level, which is why index_close never passes through it", () => {
    expect(formatBillion(1732.02)).toBe("0.00");
    expect(formatTrillion(1732.02)).toBe("0.00");
    expect(formatDecimal(1732.02)).toBe("1,732.02");
  });
});

describe("dates", () => {
  // Parsed by hand rather than through `new Date(...)`, which applies a timezone shift and can
  // move a session date by a day.
  it("renders a session as DD/MM/YY without a timezone shift", () => {
    expect(formatSession("2026-08-18")).toBe("18/08/26");
    expect(formatSession("2025-01-02T00:00:00Z")).toBe("02/01/25");
  });

  it("renders a run parameter as DD/MM/YYYY", () => {
    expect(formatParamDate("2026-08-18")).toBe("18/08/2026");
    expect(formatParamDate("2025-01-02T00:00:00Z")).toBe("02/01/2025");
  });

  it("passes an unparseable value through rather than inventing one", () => {
    expect(formatSession("not-a-date")).toBe("not-a-date");
    expect(formatParamDate("not-a-date")).toBe("not-a-date");
  });
});

describe("formatDecimal width", () => {
  // F̄(S) ranges roughly 0.22–0.27 across the research years; two decimals would collapse
  // distinctions the API deliberately keeps at six.
  it("honours an explicit digit count", () => {
    expect(formatDecimal(0.262929, 4)).toBe("0.2629");
    expect(formatDecimal(0.262929)).toBe("0.26");
  });
});

describe("formatCompactVolume", () => {
  // The volume scale has 64 viewBox units of gutter; a grouped integer does not fit in it.
  it("abbreviates with the unit named in the label", () => {
    expect(formatCompactVolume(12_345_678)).toBe("12.3 tr");
    expect(formatCompactVolume(1_240_000_000)).toBe("1.2 tỷ");
    expect(formatCompactVolume(850_000)).toBe("850 ng");
    expect(formatCompactVolume(742)).toBe("742");
  });

  it("renders a missing count as a dash, never as a zero", () => {
    expect(formatCompactVolume(null)).toBe(DASH);
    expect(formatCompactVolume(undefined)).toBe(DASH);
  });
});
