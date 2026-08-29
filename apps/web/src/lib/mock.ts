/**
 * Committed mock fixtures for local development only.
 *
 * Reached ONLY when `resolveApiConfig()` returns `mock` — that is, local/development mode with
 * no `NEXT_PUBLIC_API_BASE_URL`. Every deployed build is production-like and can never render
 * these; there, a missing API is a visible error. `useAsyncResource` labels whatever it serves
 * from here with `isMock: true`, and the screens say so on the page.
 *
 * The figures below are plausible but INVENTED. They are shaped to exercise the cases the real
 * data will eventually contain rather than to look tidy:
 *
 *   - `window_end` (2025-12-31) is far behind `latest_session`, because that gap is the whole
 *     reason the provenance strip exists and it must be visible while developing.
 *   - `advancers + decliners + unchanged` is one short of `n_tickers`, so the "these do not
 *     partition the universe" case is on screen by default rather than only in production.
 *   - One mover carries a null `ret_5d`, so the warm-up rendering path is exercised.
 */

import type {
  ActiveModelRunResponse,
  AnchorDetailResponse,
  AnchorRow,
  AnchorsResponse,
  IndexBar,
  IndexHistoryResponse,
  IndicatorPoint,
  LiquidityResponse,
  MarketOverviewResponse,
  MarketSectorsResponse,
  MoversResponse,
  TickerAnalysisResponse,
  TickerDetailResponse,
  TickerHistoryResponse,
  TickerIndicatorsResponse,
  TickersResponse,
} from "./api";

export const MOCK_ACTIVE_MODEL_RUN: ActiveModelRunResponse = {
  run_id: 1,
  artifact_id: "mock000000000",
  scope: "year",
  scope_label: "2025",
  similarity_measure: "pearson_rho2",
  universe_version: "u00000000",
  index_symbol: "VNINDEX",
  window_start: "2025-01-02",
  window_end: "2025-12-31",
  latest_session: "2026-08-18",
  prior_close_date: "2024-12-31",
  n_sessions: 249,
  n_tickers: 85,
  q: 0.341365,
  k: 10,
  k_max: 15,
  tau: 0.1,
  coverage_f: 22.349002,
  coverage_fbar: 0.262929,
  n_under_tau: 33,
  is_primary: true,
  created_at: "2026-01-01T00:00:00Z",
  loaded_at: "2026-01-01T00:00:00Z",
};

export const MOCK_MARKET_OVERVIEW: MarketOverviewResponse = {
  session_date: "2026-08-18",
  n_tickers: 85,
  // Deliberately 84, not 85: one ticker has no ret_1d and is in none of the three counts.
  n_with_return: 84,
  advancers: 32,
  decliners: 40,
  unchanged: 12,
  total_turnover: 8352129774,
  total_volume: 272811000,
  index_symbol: "VNINDEX",
  index_close: 1732.02,
  index_ret_1d: 0.00264,
};

export const MOCK_TOP_GAINERS: MoversResponse = {
  direction: "up",
  horizon: "1d",
  limit: 10,
  count: 3,
  movers: [
    {
      ticker: "AAA",
      company_name: "Mock Company A",
      sector: "Công nghiệp",
      bar_date: "2026-08-18",
      close_price: 24.5,
      volume: 4210000,
      turnover_value: 103145000,
      ret_1d: 0.0687,
      ret_5d: 0.0412,
      ret_20d: 0.1103,
      ret_60d: 0.2417,
      ret_252d: 0.5183,
    },
    {
      ticker: "BBB",
      company_name: "Mock Company B",
      sector: "Ngân hàng",
      bar_date: "2026-08-18",
      close_price: 31.2,
      volume: 2870000,
      turnover_value: 89544000,
      // Warm-up: fewer than five sessions of history, so this is null and not zero.
      ret_5d: null,
      ret_1d: 0.0541,
      ret_20d: 0.0298,
      ret_60d: 0.0912,
      // Fewer than 253 sessions of history: no one-year return exists, and null
      // is the truth. A 0 here would claim the stock finished the year flat.
      ret_252d: null,
    },
    {
      ticker: "CCC",
      company_name: "Mock Company C",
      sector: "Bất động sản và Xây dựng",
      bar_date: "2026-08-18",
      close_price: 18.75,
      volume: 6120000,
      turnover_value: 114750000,
      ret_1d: 0.0489,
      ret_5d: -0.0121,
      ret_20d: 0.0654,
      ret_60d: -0.0338,
      ret_252d: 0.1042,
    },
  ],
};

export const MOCK_TOP_LOSERS: MoversResponse = {
  direction: "down",
  horizon: "1d",
  limit: 10,
  count: 3,
  movers: [
    {
      ticker: "DDD",
      company_name: "Mock Company D",
      sector: "Bất động sản và Xây dựng",
      bar_date: "2026-08-18",
      close_price: 11.05,
      volume: 10569900,
      turnover_value: 116797395,
      ret_1d: -0.03913,
      ret_5d: 0.0,
      ret_20d: 0.004545,
      ret_60d: -0.1875,
      ret_252d: -0.4126,
    },
    {
      ticker: "EEE",
      company_name: "Mock Company E",
      sector: "Tiêu dùng",
      bar_date: "2026-08-18",
      close_price: 11.8,
      volume: 2957500,
      turnover_value: 34898500,
      ret_1d: -0.032787,
      ret_5d: -0.036735,
      ret_20d: -0.052209,
      ret_60d: -0.0941,
      ret_252d: 0.0217,
    },
    {
      ticker: "FFF",
      company_name: "Mock Company F",
      sector: "Năng lượng",
      // A stale date: this ticker stopped trading and is shown as such rather than
      // silently ranked beside the current session.
      bar_date: "2026-07-30",
      close_price: 8.4,
      volume: 331000,
      turnover_value: 2780400,
      ret_1d: -0.031963,
      ret_5d: -0.041,
      ret_20d: -0.118,
      ret_60d: -0.2264,
      ret_252d: -0.3508,
    },
  ],
};

// ---------------------------------------------------------------------------
// P10 fixtures — the eight routes P9 added.
//
// The series fixtures are GENERATED rather than written out. A 252-point chart cannot be
// hand-authored, and a 20-point stand-in would hide every bug that only appears at real density:
// label collision, polyline decimation, and the 200-day average being null for four fifths of the
// window. The generator is a seeded LCG, so the fixture is byte-identical on every reload and a
// visual change is a real regression rather than new noise.
// ---------------------------------------------------------------------------

/** Deterministic [0,1) — a plain LCG. Not random enough for anything but a chart shape. */
function makeRng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function round(value: number, digits: number): number {
  const f = 10 ** digits;
  return Math.round(value * f) / f;
}

/** `count` weekday session dates ending at `endIso`, oldest first. Holidays are not modelled. */
function sessionDates(endIso: string, count: number): string[] {
  const [y, m, d] = endIso.split("-").map(Number);
  const out: string[] = [];
  const cur = new Date(Date.UTC(y, m - 1, d));
  while (out.length < count) {
    const dow = cur.getUTCDay();
    if (dow !== 0 && dow !== 6) out.push(cur.toISOString().slice(0, 10));
    cur.setUTCDate(cur.getUTCDate() - 1);
  }
  return out.reverse();
}

/** Trailing mean over `window` closes, null until there are enough — never 0. */
function sma(values: number[], i: number, window: number): number | null {
  if (i + 1 < window) return null;
  let total = 0;
  for (let j = i + 1 - window; j <= i; j += 1) total += values[j];
  return round(total / window, 2);
}

const MOCK_SESSIONS = 252;
const MOCK_END = "2026-08-18";

/** One synthetic price path plus every indicator the two series routes publish. */
function buildSeries() {
  const rng = makeRng(20260818);
  const dates = sessionDates(MOCK_END, MOCK_SESSIONS);

  const closes: number[] = [];
  const highs: number[] = [];
  const lows: number[] = [];
  const opens: number[] = [];
  const volumes: number[] = [];

  let price = 21.5;
  for (let i = 0; i < MOCK_SESSIONS; i += 1) {
    // Mild upward drift plus a slow cycle, so the moving averages actually cross each other.
    const drift = 0.0006 + 0.004 * Math.sin(i / 34);
    price = Math.max(4, price * (1 + drift + (rng() - 0.5) * 0.031));
    const close = round(price, 2);
    const open = round(close * (1 + (rng() - 0.5) * 0.012), 2);
    closes.push(close);
    opens.push(open);
    highs.push(round(Math.max(open, close) * (1 + rng() * 0.011), 2));
    lows.push(round(Math.min(open, close) * (1 - rng() * 0.011), 2));
    volumes.push(Math.round(2_000_000 + rng() * 7_000_000));
  }

  const ema = (period: number): (number | null)[] => {
    const k = 2 / (period + 1);
    const out: (number | null)[] = [];
    let prev: number | null = null;
    closes.forEach((c, i) => {
      if (i + 1 < period) {
        out.push(null);
      } else if (prev === null) {
        prev = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
        out.push(round(prev, 2));
      } else {
        prev = c * k + prev * (1 - k);
        out.push(round(prev, 2));
      }
    });
    return out;
  };

  const ema12 = ema(12);
  const ema26 = ema(26);
  const macd = closes.map((_, i) =>
    ema12[i] !== null && ema26[i] !== null ? round(ema12[i]! - ema26[i]!, 2) : null,
  );

  const macdSignal: (number | null)[] = [];
  let sigPrev: number | null = null;
  macd.forEach((v) => {
    if (v === null) {
      macdSignal.push(null);
      return;
    }
    sigPrev = sigPrev === null ? v : v * 0.2 + sigPrev * 0.8;
    macdSignal.push(round(sigPrev, 2));
  });

  const rsi = closes.map((_, i) => {
    if (i < 14) return null;
    let gain = 0;
    let loss = 0;
    for (let j = i - 13; j <= i; j += 1) {
      const diff = closes[j] - closes[j - 1];
      if (diff >= 0) gain += diff;
      else loss -= diff;
    }
    if (loss === 0) return 100;
    return round(100 - 100 / (1 + gain / loss), 2);
  });

  // A two-session hole in the middle of the window. Leading nulls (sma_200 before bar 200, rsi_14
  // before bar 14) only ever exercise a gap at the START of a series, which every renderer gets
  // right by accident. A hole in the middle is what breaks a chart: it is where a naive line
  // joins across missing data, or substitutes 0 and draws a crash that never happened.
  const GAP_AT = Math.floor(MOCK_SESSIONS / 2);
  const inGap = (i: number) => i === GAP_AT || i === GAP_AT + 1;

  const indicators: IndicatorPoint[] = dates.map((bar_date, i) => {
    if (inGap(i)) {
      return {
        bar_date,
        close: null,
        volume: null,
        sma_20: null,
        sma_50: null,
        sma_200: null,
        ema_12: null,
        ema_26: null,
        macd: null,
        macd_signal: null,
        macd_hist: null,
        rsi_14: null,
        stoch_k_14: null,
        stoch_d_14: null,
        atr_14: null,
        bb_mid_20: null,
        bb_upper_20: null,
        bb_lower_20: null,
        bb_width_20: null,
        realized_vol_20d: null,
        realized_vol_60d: null,
        obv: null,
        volume_sma_20: null,
        turnover_value: null,
        ret_1d: null,
        ret_5d: null,
        ret_20d: null,
        ret_60d: null,
        ret_ytd: null,
        dist_from_sma_200_pct: null,
        high_252d: null,
        low_252d: null,
        drawdown_from_252d_high: null,
      };
    }
    const mid = sma(closes, i, 20);
    let sd: number | null = null;
    if (mid !== null) {
      let acc = 0;
      for (let j = i - 19; j <= i; j += 1) acc += (closes[j] - mid) ** 2;
      sd = Math.sqrt(acc / 20);
    }
    const upper = mid !== null && sd !== null ? round(mid + 2 * sd, 2) : null;
    const lower = mid !== null && sd !== null ? round(mid - 2 * sd, 2) : null;
    const sma200 = sma(closes, i, 200);
    const window = closes.slice(Math.max(0, i - 251), i + 1);
    const high252 = round(Math.max(...window), 2);
    const low252 = round(Math.min(...window), 2);
    const volSma =
      i >= 19
        ? Math.round(volumes.slice(i - 19, i + 1).reduce((a, b) => a + b, 0) / 20)
        : null;

    const ret = (n: number): number | null =>
      i >= n ? round(closes[i] / closes[i - n] - 1, 6) : null;

    return {
      bar_date,
      close: closes[i],
      volume: volumes[i],
      sma_20: mid,
      sma_50: sma(closes, i, 50),
      sma_200: sma200,
      ema_12: ema12[i],
      ema_26: ema26[i],
      macd: macd[i],
      macd_signal: macdSignal[i],
      macd_hist:
        macd[i] !== null && macdSignal[i] !== null
          ? round(macd[i]! - macdSignal[i]!, 2)
          : null,
      rsi_14: rsi[i],
      stoch_k_14: i >= 14 ? round(30 + rng() * 55, 2) : null,
      stoch_d_14: i >= 16 ? round(32 + rng() * 50, 2) : null,
      atr_14: i >= 14 ? round(0.4 + rng() * 0.5, 2) : null,
      bb_mid_20: mid,
      bb_upper_20: upper,
      bb_lower_20: lower,
      bb_width_20:
        mid !== null && upper !== null && lower !== null
          ? round((upper - lower) / mid, 6)
          : null,
      realized_vol_20d: i >= 20 ? round(0.18 + rng() * 0.14, 6) : null,
      realized_vol_60d: i >= 60 ? round(0.2 + rng() * 0.1, 6) : null,
      obv: Math.round(volumes.slice(0, i + 1).reduce((a, b) => a + b, 0) / 1000),
      volume_sma_20: volSma,
      turnover_value: round(closes[i] * volumes[i], 2),
      ret_1d: ret(1),
      ret_5d: ret(5),
      ret_20d: ret(20),
      ret_60d: ret(60),
      ret_ytd: ret(160),
      dist_from_sma_200_pct: sma200 !== null ? round(closes[i] / sma200 - 1, 6) : null,
      high_252d: high252,
      low_252d: low252,
      drawdown_from_252d_high: round(closes[i] / high252 - 1, 6),
    };
  });

  return { dates, opens, highs, lows, closes, volumes, indicators, inGap };
}

const SERIES = buildSeries();
const LAST = SERIES.indicators[SERIES.indicators.length - 1];

export const MOCK_MARKET_SECTORS: MarketSectorsResponse = {
  count: 7,
  sectors: [
    { sector: "Ngân hàng", n_tickers: 17, n_with_return: 17, mean_ret_1d: 0.0081, total_turnover: 3120450000, total_volume: 91230000 },
    { sector: "Bất động sản và Xây dựng", n_tickers: 21, n_with_return: 21, mean_ret_1d: -0.0043, total_turnover: 2015880000, total_volume: 74110000 },
    { sector: "Tài chính", n_tickers: 9, n_with_return: 9, mean_ret_1d: 0.0117, total_turnover: 1204330000, total_volume: 38940000 },
    { sector: "Công nghiệp", n_tickers: 14, n_with_return: 13, mean_ret_1d: 0.0009, total_turnover: 872140000, total_volume: 31220000 },
    { sector: "Tiêu dùng", n_tickers: 12, n_with_return: 12, mean_ret_1d: -0.0062, total_turnover: 640910000, total_volume: 22870000 },
    { sector: "Năng lượng", n_tickers: 8, n_with_return: 8, mean_ret_1d: 0.0025, total_turnover: 388270000, total_volume: 12140000 },
    // A real group, not an error: tickers with no assigned sector. The treemap labels it "Khác".
    // Its mean is null because none of its members holds a return today — it must be drawn
    // neutral, never in the colour of 0%.
    { sector: null, n_tickers: 4, n_with_return: 0, mean_ret_1d: null, total_turnover: 109800000, total_volume: 2200000 },
  ],
};

/**
 * The session's liquidity ranking. Same row shape as the movers tables because the API serves it
 * from the same view — so these rows are deliberately the SAME six tickers reordered by turnover
 * rather than a fresh invented set. A mock where the two tables shared no names would hide the
 * one thing worth seeing while developing: that a stock can top the turnover table and sit
 * nowhere near the top of the movers table.
 */
export const MOCK_MARKET_LIQUIDITY: LiquidityResponse = {
  session_date: "2026-08-18",
  limit: 10,
  count: 5,
  stocks: [
    MOCK_TOP_LOSERS.movers[0],   // DDD — biggest turnover, and a faller
    MOCK_TOP_GAINERS.movers[2],  // CCC
    MOCK_TOP_GAINERS.movers[0],  // AAA
    MOCK_TOP_GAINERS.movers[1],  // BBB
    MOCK_TOP_LOSERS.movers[1],   // EEE
  ],
};

/**
 * A synthetic VNINDEX series for the chart, generated rather than typed out.
 *
 * 252 sessions is the 1Y range's own length, so local development exercises the widest fixed
 * window the chart offers. The walk is seeded and deterministic: a mock that changed shape on
 * every reload would make a rendering regression indistinguishable from new random data.
 *
 * Weekends are skipped so the date axis reads like a session calendar rather than a calendar
 * month. Holidays are not modelled — the axis labels months, not individual days, so the
 * difference is invisible and pretending otherwise would be more fiction, not less.
 */
function mockIndexBars(count: number): IndexBar[] {
  // Deterministic LCG. Not a good PRNG; it does not need to be, it needs to be the same twice.
  let seed = 20260818;
  const rand = (): number => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };

  const bars: IndexBar[] = [];
  let level = 1421.6;
  // Walk backwards from the session every other market fixture here uses, then reverse: the
  // chart draws oldest-first, but the fixture must END on the same date as MOCK_MARKET_OVERVIEW
  // or the page would show two different "today"s side by side.
  const cursor = new Date(Date.UTC(2026, 7, 18));
  const dates: string[] = [];
  while (dates.length < count) {
    const day = cursor.getUTCDay();
    if (day !== 0 && day !== 6) dates.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() - 1);
  }
  dates.reverse();

  let prevClose: number | null = null;
  for (const bar_date of dates) {
    // Mild upward drift with occasional shocks — enough shape for the crosshair to have
    // something to land on, not so much that it stops looking like an index.
    const shock = rand() < 0.04 ? (rand() - 0.5) * 0.045 : 0;
    const step = (rand() - 0.47) * 0.011 + shock;
    level = level * (1 + step);
    const close = Math.round(level * 100) / 100;
    const open = Math.round(close * (1 + (rand() - 0.5) * 0.004) * 100) / 100;
    const high = Math.round(Math.max(open, close) * (1 + rand() * 0.004) * 100) / 100;
    const low = Math.round(Math.min(open, close) * (1 - rand() * 0.004) * 100) / 100;
    bars.push({
      bar_date,
      open,
      high,
      low,
      close,
      volume: Math.round(180_000_000 + rand() * 140_000_000),
      // Null on the first bar and nowhere else — the same shape the API returns, so the chart's
      // "no previous close" branch is exercised locally rather than only in production.
      ret_1d: prevClose === null ? null : Math.round((close / prevClose - 1) * 1e6) / 1e6,
    });
    prevClose = close;
  }
  return bars;
}

export const MOCK_INDEX_HISTORY: IndexHistoryResponse = {
  index_symbol: "VNINDEX",
  range: "1y",
  count: 252,
  bars: mockIndexBars(252),
};

const ANCHOR_TICKERS = ["VIC", "PDR", "DCM", "IDI", "CMG", "HCM", "PVT", "VIB", "SZC", "HSG"] as const;

const SECTORS = [
  "Ngân hàng",
  "Bất động sản và Xây dựng",
  "Tài chính",
  "Công nghiệp",
  "Tiêu dùng",
  "Năng lượng",
] as const;

/** 85 rows — the real universe size, so the search screen is exercised at true density. */
export const MOCK_TICKERS: TickersResponse = (() => {
  const rng = makeRng(4242);
  const tickers = Array.from({ length: 85 }, (_, i) => {
    const isAnchor = i < ANCHOR_TICKERS.length;
    const label = `T${String(i).padStart(2, "0")}`;
    const coverage = round(0.04 + rng() * 0.5, 6);
    return {
      position: i,
      ticker: isAnchor ? ANCHOR_TICKERS[i] : label,
      company_name: `Mock Company ${label}`,
      // Four tickers carry no sector, matching the null-sector group in MOCK_MARKET_SECTORS.
      sector: i >= 81 ? null : SECTORS[i % SECTORS.length],
      industry: i >= 81 ? null : `Ngành ${1 + (i % 9)}`,
      anchor_ticker: ANCHOR_TICKERS[i % ANCHOR_TICKERS.length],
      coverage_c: coverage,
      is_anchor: isAnchor,
      under_tau: coverage < 0.1,
      // One ticker has no bar at all: its row must render without inventing a zero.
      bar_date: i === 40 ? null : MOCK_END,
      ret_1d: i === 40 ? null : round((rng() - 0.48) * 0.06, 6),
    };
  });
  return { count: tickers.length, tickers };
})();

export const MOCK_TICKER_DETAIL: TickerDetailResponse = {
  identity: {
    ticker: "VIC",
    company_name: "Mock Company VIC",
    sector: "Bất động sản và Xây dựng",
    industry: "Bất động sản",
  },
  assignment: {
    position: 80,
    anchor_ticker: "VIC",
    coverage_c: 0.412903,
    is_anchor: true,
    under_tau: false,
    alpha_hat: 0.000214,
    beta_hat: 1.187442,
    sigma_hat: 0.014907,
    r2: 0.503118,
  },
  latest: {
    ...LAST,
    bar_date: MOCK_END,
    open: SERIES.opens[SERIES.opens.length - 1],
    high: SERIES.highs[SERIES.highs.length - 1],
    low: SERIES.lows[SERIES.lows.length - 1],
  },
};

export const MOCK_TICKER_HISTORY: TickerHistoryResponse = {
  ticker: "VIC",
  count: MOCK_SESSIONS,
  // The same two-session hole as the indicator series, so both charts are exercised against it.
  bars: SERIES.dates.map((bar_date, i) => ({
    bar_date,
    open: SERIES.inGap(i) ? null : SERIES.opens[i],
    high: SERIES.inGap(i) ? null : SERIES.highs[i],
    low: SERIES.inGap(i) ? null : SERIES.lows[i],
    close: SERIES.inGap(i) ? null : SERIES.closes[i],
    volume: SERIES.inGap(i) ? null : SERIES.volumes[i],
    is_adjusted: true,
  })),
};

export const MOCK_TICKER_INDICATORS: TickerIndicatorsResponse = {
  ticker: "VIC",
  count: MOCK_SESSIONS,
  indicators: SERIES.indicators,
};

/**
 * Mirrors `narrative.py::_rsi_band`, including its most important property: where the sentence
 * leans on a market convention rather than on something this system computed, it says so ("theo
 * quy ước") instead of asserting it as a fact about the stock.
 */
function rsiSentence(rsi: number | null): string {
  if (rsi === null) return "";
  const v = rsi.toFixed(1);
  if (rsi > 70) {
    return `RSI(14) đang ở mức ${v}, trên ngưỡng 70 thông dụng (vùng quá mua theo quy ước).`;
  }
  if (rsi < 30) {
    return `RSI(14) đang ở mức ${v}, dưới ngưỡng 30 thông dụng (vùng quá bán theo quy ước).`;
  }
  return `RSI(14) đang ở mức ${v}, nằm giữa hai ngưỡng 30 và 70 thông dụng.`;
}

export const MOCK_TICKER_ANALYSIS: TickerAnalysisResponse = {
  ticker: "VIC",
  bar_date: MOCK_END,
  price_basis: "adjusted",
  statements: [
    {
      code: "price_vs_sma_20",
      text: `Giá đóng cửa (${LAST.close?.toFixed(2)}) đang cao hơn đường trung bình 20 phiên (MA20) (${LAST.sma_20?.toFixed(2)}).`,
      inputs: { close: LAST.close ?? 0, sma_20: LAST.sma_20 ?? 0 },
    },
    {
      code: "ma_alignment",
      text: "Các đường trung bình xếp theo thứ tự MA20 > MA50 > MA200, thường được đọc là xu hướng tăng.",
      inputs: { sma_20: LAST.sma_20 ?? 0, sma_50: LAST.sma_50 ?? 0, sma_200: LAST.sma_200 ?? 0 },
    },
    {
      code: "rsi_band",
      // Derived from the generated value rather than hardcoded: an earlier draft said "nằm giữa
      // hai ngưỡng 30 và 70" beside a generated RSI of 77, which is exactly the kind of sentence
      // the real rule engine is built never to emit.
      text: rsiSentence(LAST.rsi_14),
      inputs: { rsi_14: LAST.rsi_14 ?? 0 },
    },
    {
      code: "volume_vs_average",
      text: "Khối lượng phiên gần nhất cao hơn trung bình 20 phiên.",
      inputs: { volume: LAST.volume ?? 0, volume_sma_20: LAST.volume_sma_20 ?? 0 },
    },
    {
      code: "ret_20d",
      text: `Tỷ suất sinh lợi 20 phiên gần nhất là ${((LAST.ret_20d ?? 0) * 100).toFixed(2)}%.`,
      inputs: { ret_20d: LAST.ret_20d ?? 0 },
    },
  ],
  // A rule whose inputs were null emits nothing and is recorded here instead, so that silence is
  // never read as neutrality. The screen does not print the technical reason.
  skipped: [
    { code: "ret_ytd", reason: "missing_inputs", missing: ["ret_ytd"] },
    { code: "bollinger_position", reason: "missing_inputs", missing: ["bb_upper_20"] },
  ],
};

/** Group sizes over the published anchors. Sum = 85, so the groups partition the universe. */
const GROUP_SIZES = [19, 15, 9, 8, 8, 7, 6, 6, 4, 3];

function anchorRow(i: number, published: boolean, sizeOverride?: number): AnchorRow {
  const rng = makeRng(900 + i * 37);
  const ticker = published ? ANCHOR_TICKERS[i] : `X${String(i).padStart(2, "0")}`;
  return {
    step_k: i + 1,
    anchor_ticker: ticker,
    position: 10 + i * 3,
    company_name: `Mock Company ${ticker}`,
    sector: SECTORS[i % SECTORS.length],
    marginal_gain: round(5.8 / (i + 1) + 0.9, 6),
    coverage_f: round(5.8 + i * 1.9, 6),
    coverage_fbar: round((5.8 + i * 1.9) / 85, 6),
    in_published_set: published,
    // Past the published boundary, model_groups holds no row. Null is the truth, not a join bug.
    size: published ? (sizeOverride ?? GROUP_SIZES[i] ?? 5) : null,
    f_j: published ? round(1.4 + rng() * 3.2, 6) : null,
    rho2_mean: published ? round(0.18 + rng() * 0.2, 6) : null,
    rho2_min: published ? round(0.05 + rng() * 0.08, 6) : null,
    // Empty for every group of the real artifact too — a deferred field, not a placeholder. The
    // anchor screen derives the composition from members[].sector instead.
    sector_composition: published ? {} : null,
  };
}

export const MOCK_ANCHORS: AnchorsResponse = {
  count: 15,
  anchors: Array.from({ length: 15 }, (_, i) => anchorRow(i, i < 10)),
};

const DETAIL_MEMBERS = GROUP_SIZES[0];

export const MOCK_ANCHOR_DETAIL: AnchorDetailResponse = {
  // `size` is passed explicitly so it agrees with the member array below. A fixture whose stated
  // group size contradicts the rows it ships is a fixture that will make a real join bug look
  // normal.
  anchor: anchorRow(0, true, DETAIL_MEMBERS),
  members: (() => {
    const rng = makeRng(77);
    return Array.from({ length: DETAIL_MEMBERS }, (_, i) => {
      const coverage = round(0.52 - i * 0.024, 6);
      return {
        ticker: i === 0 ? "VIC" : `M${String(i).padStart(2, "0")}`,
        company_name: `Mock Member ${i}`,
        // Two members carry no sector, so the derived composition has to handle "Khác".
        sector: i >= 17 ? null : SECTORS[i % SECTORS.length],
        position: 10 + i,
        coverage_c: coverage,
        is_anchor: i === 0,
        under_tau: coverage < 0.1,
        indicator_date: MOCK_END,
        ret_1d: round((rng() - 0.45) * 0.05, 6),
        ret_5d: i === 3 ? null : round((rng() - 0.45) * 0.09, 6),
        ret_20d: round((rng() - 0.45) * 0.16, 6),
        turnover_value: round(40_000_000 + rng() * 180_000_000, 2),
        rsi_14: round(35 + rng() * 40, 2),
        dist_from_sma_200_pct: round((rng() - 0.4) * 0.3, 6),
        drawdown_from_252d_high: round(-rng() * 0.25, 6),
      };
    });
  })(),
};
