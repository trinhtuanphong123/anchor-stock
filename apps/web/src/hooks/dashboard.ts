"use client";

/**
 * One hook per implemented API route. Each wires a typed fetcher to its committed mock through
 * {@link useAsyncResource}, which decides between them: it serves the mock only in local mode
 * with no API configured, and in a production-like build it surfaces a visible error instead.
 *
 * All eleven routes are covered — P8's three plus the eight P9 landed.
 *
 * **These hooks are independently concurrent, and that is load-bearing.** Each owns its own
 * `useEffect`, so calling four of them in one component issues four overlapping requests on
 * mount. P9.6 measured the ticker page's four routes at 872 + 948 + 1187 + 857 ms — ~3.9 s if
 * they run in sequence, ~1.2 s if they overlap. Nothing here enforces that: a screen that fetches
 * the detail first and mounts the chart only after it resolves gets the 3.9 s version. Keep the
 * four calls in one component.
 */

import {
  fetchActiveModelRun,
  fetchAnchorDetail,
  fetchAnchors,
  fetchIndexHistory,
  fetchMarketLiquidity,
  fetchMarketOverview,
  fetchMarketSectors,
  fetchTickerAnalysis,
  fetchTickerDetail,
  fetchTickerHistory,
  fetchTickerIndicators,
  fetchTickers,
  fetchTopMovers,
  type ActiveModelRunResponse,
  type AnchorDetailResponse,
  type AnchorsResponse,
  type IndexHistoryResponse,
  type IndexRange,
  type LiquidityResponse,
  type MarketOverviewResponse,
  type MarketSectorsResponse,
  type MoverDirection,
  type MoverHorizon,
  type MoversResponse,
  type TickerAnalysisResponse,
  type TickerDetailResponse,
  type TickerHistoryResponse,
  type TickerIndicatorsResponse,
  type TickersResponse,
} from "@/lib/api";
import {
  MOCK_ACTIVE_MODEL_RUN,
  MOCK_ANCHOR_DETAIL,
  MOCK_ANCHORS,
  MOCK_INDEX_HISTORY,
  MOCK_MARKET_LIQUIDITY,
  MOCK_MARKET_OVERVIEW,
  MOCK_MARKET_SECTORS,
  MOCK_TICKER_ANALYSIS,
  MOCK_TICKER_DETAIL,
  MOCK_TICKER_HISTORY,
  MOCK_TICKER_INDICATORS,
  MOCK_TICKERS,
  MOCK_TOP_GAINERS,
  MOCK_TOP_LOSERS,
} from "@/lib/mock";
import { useAsyncResource, type ResourceState } from "./useAsyncResource";

export type { ResourceState };

/** The served parameter set: identity, estimation window, and published coverage. */
export function useActiveModelRun(): ResourceState<ActiveModelRunResponse> {
  return useAsyncResource(fetchActiveModelRun, MOCK_ACTIVE_MODEL_RUN, []);
}

/** The latest session's breadth, turnover and index move. */
export function useMarketOverview(): ResourceState<MarketOverviewResponse> {
  return useAsyncResource(fetchMarketOverview, MOCK_MARKET_OVERVIEW, []);
}

/**
 * The strongest movers over one horizon in one direction. Refetches when either changes.
 *
 * The mock does NOT vary with `horizon` — it is one fixture per direction, with the horizon
 * echoed onto it so the tab state is still visible locally. Faking five different orderings
 * offline would mean inventing a ranking, and the ranking is the API's answer: local development
 * has no business appearing to produce one.
 */
export function useTopMovers(
  direction: MoverDirection,
  horizon: MoverHorizon = "1d",
  limit = 10,
): ResourceState<MoversResponse> {
  const base = direction === "up" ? MOCK_TOP_GAINERS : MOCK_TOP_LOSERS;
  return useAsyncResource(
    () => fetchTopMovers(direction, horizon, limit),
    { ...base, horizon },
    [direction, horizon, limit],
  );
}

/** Per-sector breadth, mean move and turnover — the treemap. */
export function useMarketSectors(): ResourceState<MarketSectorsResponse> {
  return useAsyncResource(fetchMarketSectors, MOCK_MARKET_SECTORS, []);
}

/** The session's most heavily traded names, by turnover value. */
export function useMarketLiquidity(limit = 10): ResourceState<LiquidityResponse> {
  return useAsyncResource(() => fetchMarketLiquidity(limit), MOCK_MARKET_LIQUIDITY, [limit]);
}

/** Mirrors the API's own window lengths. `ytd` has no fixed length; ~160 sessions stands in for
 *  it and only ever affects local development. */
const MOCK_RANGE_SESSIONS: Record<"1m" | "3m" | "6m" | "ytd", number> = {
  "1m": 20,
  "3m": 60,
  "6m": 126,
  ytd: 160,
};

/**
 * The active run's index series over one range. Refetches when the range changes.
 *
 * The mock is one 252-session series regardless of range, SLICED to length here rather than
 * regenerated: five separately generated walks would disagree with each other at their shared
 * right edge, which is the one place a reader switching tabs would notice.
 */
export function useIndexHistory(range: IndexRange = "1y"): ResourceState<IndexHistoryResponse> {
  const bars =
    range === "all" || range === "1y"
      ? MOCK_INDEX_HISTORY.bars
      : MOCK_INDEX_HISTORY.bars.slice(-MOCK_RANGE_SESSIONS[range]);
  return useAsyncResource(
    () => fetchIndexHistory(range),
    { ...MOCK_INDEX_HISTORY, range, count: bars.length, bars },
    [range],
  );
}

/** The whole 85-ticker universe in one read, filtered client-side. */
export function useTickers(): ResourceState<TickersResponse> {
  return useAsyncResource(fetchTickers, MOCK_TICKERS, []);
}

/** One ticker's identity, model assignment and latest indicator row. */
export function useTickerDetail(ticker: string): ResourceState<TickerDetailResponse> {
  return useAsyncResource(() => fetchTickerDetail(ticker), MOCK_TICKER_DETAIL, [ticker]);
}

/** OHLCV bars, oldest first. Both bounds omitted → the most recent 252 sessions. */
export function useTickerHistory(ticker: string): ResourceState<TickerHistoryResponse> {
  return useAsyncResource(() => fetchTickerHistory(ticker), MOCK_TICKER_HISTORY, [ticker]);
}

/** The full indicator series, oldest first. Same 252-session default as the history. */
export function useTickerIndicators(ticker: string): ResourceState<TickerIndicatorsResponse> {
  return useAsyncResource(() => fetchTickerIndicators(ticker), MOCK_TICKER_INDICATORS, [ticker]);
}

/** The rule-based narrative for the latest indicator row. */
export function useTickerAnalysis(ticker: string): ResourceState<TickerAnalysisResponse> {
  return useAsyncResource(() => fetchTickerAnalysis(ticker), MOCK_TICKER_ANALYSIS, [ticker]);
}

/** All 15 selection steps. Filter on `in_published_set` for the published 10. */
export function useAnchors(): ResourceState<AnchorsResponse> {
  return useAsyncResource(fetchAnchors, MOCK_ANCHORS, []);
}

/** One anchor's selection step plus its group's members. */
export function useAnchorDetail(anchor: string): ResourceState<AnchorDetailResponse> {
  return useAsyncResource(() => fetchAnchorDetail(anchor), MOCK_ANCHOR_DETAIL, [anchor]);
}
