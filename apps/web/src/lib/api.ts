/**
 * API client + response types — reads NEXT_PUBLIC_API_BASE_URL from the browser environment.
 * Only NEXT_PUBLIC_* variables reach the client bundle, so no secret can leak here. Per D-20
 * that is not merely a convention: the Supabase service-role key retains every grant and must
 * never appear in this package.
 *
 * The frontend is a pure reader of precomputed outputs. It never runs a model, and it emits no
 * prediction, recommendation, or trading-signal language.
 *
 * P8 replaced the Leiden contract this file used to carry (15 fetchers against endpoints the API
 * does not implement) with the three routes that existed then. P10 adds the eight P9 landed, so
 * all eleven routes are now covered; the runtime-mode and configuration machinery below is
 * unchanged and is what all three eras share.
 *
 * These types are transcribed BY HAND from the route bodies in `services/api/app/routes/`. That
 * is not laziness: the API annotates every route `-> dict` and builds a dict literal, with no
 * `response_model=` anywhere, so `/openapi.json` publishes an empty response schema and there is
 * nothing to generate from. The route body is the contract. When one changes, this file does not
 * find out on its own.
 */

// ---------------------------------------------------------------------------
// Stable error envelope
// ---------------------------------------------------------------------------

/** Shape of every non-2xx API body (`services/api/app/routes/_errors.py`). */
export interface ApiErrorBody {
  error: { code: string; message: string };
}

/** Error thrown by {@link apiGet}; carries the parsed envelope code/message. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// ---------------------------------------------------------------------------
// Response types
//
// Unit contract, inherited from the views and stated once: RATIOS ARE FRACTIONS.
// `ret_1d = 0.07` means +7%. Formatting to a percent sign happens at the display edge, and
// `null` means "not computed", never zero.
// ---------------------------------------------------------------------------

/** GET /health. `service` is present on the live backend; it is not load-bearing here. */
export interface HealthResponse {
  status: string;
  service?: string;
  database: string;
  time: string;
}

/**
 * GET /api/model/active — the served parameter set.
 *
 * `window_end` and `latest_session` are both here on purpose: the anchors were estimated on one
 * window while the prices beside them run to the collection date, and `docs/04` §5 requires the
 * dashboard to show that rather than let a reader assume the two agree.
 */
export interface ActiveModelRunResponse {
  run_id: number;
  artifact_id: string;
  scope: string;
  scope_label: string;
  similarity_measure: string;
  universe_version: string;
  index_symbol: string;
  window_start: string;
  window_end: string;
  latest_session: string;
  prior_close_date: string;
  n_sessions: number;
  n_tickers: number;
  q: number | null;
  k: number;
  k_max: number;
  tau: number | null;
  coverage_f: number | null;
  coverage_fbar: number | null;
  n_under_tau: number;
  is_primary: boolean;
  created_at: string | null;
  loaded_at: string | null;
}

/**
 * F̄_adj = (F − k) / (N − k) — coverage with the tautological terms removed.
 *
 * Every anchor covers itself at ρ²(j,j) = 1, so F(S) contains exactly k terms equal to 1 that
 * carry no information — 44.7 %–54.3 % of the published F across the ten research artifacts.
 * F̄ = F/N therefore reads about 60 % higher than the coverage the set actually achieves over
 * the tickers it does not contain. D-26 requires the two to be shown together.
 *
 * **`k` is the size of the anchor set the figure belongs to, not always the run's published k.**
 * That is the one way to get this wrong, and both callers exist: the headline passes `run.k`,
 * while the anchor screen's per-step figures pass that row's `step_k`, because at step j the sum
 * carries j tautological terms and averages over N − j non-anchors. Passing `run.k` to a step-11
 * row would subtract 10 terms from a sum that contains 11.
 *
 * Derived on the client rather than served: `coverage_f`, `k`/`step_k` and `n_tickers` are already
 * on the responses, so this needs no schema change, no migration and no API edit.
 *
 * Returns null — never 0, never Infinity — whenever the inputs cannot support a figure: a missing
 * or non-finite F, a missing k, a missing N (the active run has not loaded yet), or N ≤ k. That
 * matches how the API represents an absent figure and how `format.ts` renders one.
 */
export function fbarAdjusted(
  coverageF: number | null | undefined,
  k: number | null | undefined,
  nTickers: number | null | undefined,
): number | null {
  if (coverageF === null || coverageF === undefined || !Number.isFinite(coverageF)) return null;
  if (k === null || k === undefined || !Number.isFinite(k)) return null;
  if (nTickers === null || nTickers === undefined || !Number.isFinite(nTickers)) return null;
  if (nTickers <= k) return null;
  return (coverageF - k) / (nTickers - k);
}

/**
 * The run's headline F̄_adj — {@link fbarAdjusted} applied to the published anchor set.
 *
 * Kept as its own function because the headline is the one place `k` is unambiguously the run's
 * published k; every other caller has to think about which k it means.
 */
export function coverageFbarAdjusted(run: ActiveModelRunResponse): number | null {
  return fbarAdjusted(run.coverage_f, run.k, run.n_tickers);
}

/**
 * GET /api/market/overview — the KPI row.
 *
 * `advancers + decliners + unchanged` need NOT equal `n_tickers`: a ticker whose first session
 * is the latest one has a null `ret_1d` and is counted in none of the three. `n_with_return` is
 * the actual denominator, so the three must never be rendered as a partition of the universe.
 */
export interface MarketOverviewResponse {
  session_date: string;
  n_tickers: number;
  n_with_return: number;
  advancers: number;
  decliners: number;
  unchanged: number;
  total_turnover: number | null;
  total_volume: number | null;
  /** Null when no run is active — the symbol is resolved from the run, not hard-coded. */
  index_symbol: string | null;
  index_close: number | null;
  index_ret_1d: number | null;
}

export type MoverDirection = "up" | "down";

/**
 * The five horizons the movers table ranks at.
 *
 * These are DISPLAY labels; the columns behind them are session counts, and the API owns the
 * mapping (`_HORIZON_COLUMN` in `routes/market.py`): 1m is 20 sessions, 3m is 60, 1y is 252. The
 * approximation is why `MOVER_RET_FIELD` below exists as a separate, explicit table rather than
 * being derived from the label — nothing here should look like `"1m"` and `ret_20d` are the same
 * string with different spelling.
 */
export type MoverHorizon = "1d" | "5d" | "1m" | "3m" | "1y";

/** Which field of a `MoverRow` a horizon reads. Mirrors the API's own map. */
export const MOVER_RET_FIELD: Record<MoverHorizon, keyof MoverRow> = {
  "1d": "ret_1d",
  "5d": "ret_5d",
  "1m": "ret_20d",
  "3m": "ret_60d",
  "1y": "ret_252d",
};

/** One row of GET /api/market/movers — and of GET /api/market/liquidity, which shares the shape. */
export interface MoverRow {
  ticker: string;
  company_name: string | null;
  sector: string | null;
  /** Per-ticker: a stale date here means the ticker stopped trading, and is shown as such. */
  bar_date: string;
  close_price: number | null;
  volume: number | null;
  turnover_value: number | null;
  ret_1d: number | null;
  ret_5d: number | null;
  /** 20 sessions — the "1M" column. */
  ret_20d: number | null;
  /** 60 sessions — the "3M" column. */
  ret_60d: number | null;
  /**
   * 252 sessions — the "1Y" column. Null for any ticker with fewer than 253 loaded bars, and
   * null is the truth there: a shorter history has no one-year return, and rendering 0 would
   * claim the stock finished the year flat.
   */
  ret_252d: number | null;
}

/** GET /api/market/movers?direction=&horizon=&limit= */
export interface MoversResponse {
  direction: MoverDirection;
  horizon: MoverHorizon;
  limit: number;
  count: number;
  movers: MoverRow[];
}

/**
 * GET /api/market/liquidity?limit= — the session's most heavily traded names.
 *
 * Same row shape as the movers table because it is literally the same view, ordered by
 * `turnover_value` instead of by a return. `session_date` is the session the ranking is OF;
 * each row's own `bar_date` may be older, which is how a delisted ticker shows as stale rather
 * than sitting unmarked in a table captioned "today".
 */
export interface LiquidityResponse {
  session_date: string | null;
  limit: number;
  count: number;
  stocks: MoverRow[];
}

/** Ranges the index chart offers. Fixed ones are SESSION counts (see `IndexHistoryResponse`). */
export type IndexRange = "1m" | "3m" | "6m" | "ytd" | "1y" | "all";

/** One session of the index series. */
export interface IndexBar {
  bar_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  /** Null on the first session of the whole series — no previous close exists. Never 0. */
  ret_1d: number | null;
}

/**
 * GET /api/market/index-history?range=
 *
 * **One point per SESSION, not per tick.** The pipeline collects daily bars only, so there is no
 * intraday series anywhere in this system and the shortest honest range is 1M. That is why this
 * type has no "1d" and why the chart offers none — a "1D" tab drawn from daily bars would be a
 * label making a claim the data cannot support.
 *
 * `index_symbol` is read off the data. The caller never names it: `v_index_history` resolves it
 * through the active run, so "which index" has one answer and it is the same one /overview gives.
 */
export interface IndexHistoryResponse {
  index_symbol: string;
  range: IndexRange;
  count: number;
  bars: IndexBar[];
}

/**
 * One row of GET /api/market/sectors — the treemap's input.
 *
 * `sector: null` is a REAL GROUP (tickers with no assigned sector), not an error; the display
 * renders it as "Khác". `mean_ret_1d` is deliberately not coalesced: a sector where no ticker
 * holds a return today yields a genuine null, because there is no average to report. It must be
 * drawn as neutral, never as the colour of 0%.
 *
 * `n_with_return` is `mean_ret_1d`'s actual denominator — a two-stock sector average otherwise
 * carries the same visual weight on a treemap as a twenty-four-stock one.
 */
export interface SectorRow {
  sector: string | null;
  n_tickers: number;
  n_with_return: number;
  mean_ret_1d: number | null;
  /** nghìn đồng — `formatTurnoverTy` converts. */
  total_turnover: number | null;
  total_volume: number | null;
}

/** GET /api/market/sectors */
export interface MarketSectorsResponse {
  count: number;
  sectors: SectorRow[];
}

/**
 * One row of GET /api/tickers — the whole 85-ticker universe, in universe order.
 *
 * Served in `position` order rather than alphabetically: the ordered universe pins every position
 * in this system, and re-sorting it here would hide that. Sorting for display is a user action.
 */
export interface TickerListRow {
  position: number;
  ticker: string;
  company_name: string | null;
  sector: string | null;
  industry: string | null;
  /** The anchor representing this ticker. Null when the run assigned none. */
  anchor_ticker: string | null;
  coverage_c: number | null;
  is_anchor: boolean | null;
  /** Coverage below the run's τ — the ticker is poorly represented by its anchor. */
  under_tau: boolean | null;
  bar_date: string | null;
  ret_1d: number | null;
}

/** GET /api/tickers — no pagination; 85 rows is the whole universe. */
export interface TickersResponse {
  count: number;
  tickers: TickerListRow[];
}

/**
 * The indicator fields shared by `/api/tickers/{t}`'s `latest` block and every row of
 * `/api/tickers/{t}/indicators`. Declared once because the two responses genuinely carry the same
 * columns — the series route duplicates them deliberately so each response is self-sufficient and
 * the client never merges two arrays by date.
 *
 * UNITS, and the three that lie about themselves: `bb_width_20`, `realized_vol_20d`,
 * `realized_vol_60d`, `dist_from_sma_200_pct` and `drawdown_from_252d_high` are all FRACTIONS,
 * despite two of them reading as a percent by name. `dist_from_sma_200_pct = 0.05` is +5%.
 * Everything else here is a price in nghìn đồng, an oscillator in [0,100], or a share count.
 */
export interface IndicatorFields {
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  ema_12: number | null;
  ema_26: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  /** [0,100]. */
  rsi_14: number | null;
  stoch_k_14: number | null;
  stoch_d_14: number | null;
  atr_14: number | null;
  bb_mid_20: number | null;
  bb_upper_20: number | null;
  bb_lower_20: number | null;
  /** Fraction, not a price. */
  bb_width_20: number | null;
  realized_vol_20d: number | null;
  realized_vol_60d: number | null;
  obv: number | null;
  volume_sma_20: number | null;
  /** nghìn đồng. */
  turnover_value: number | null;
  ret_1d: number | null;
  ret_5d: number | null;
  ret_20d: number | null;
  ret_60d: number | null;
  ret_ytd: number | null;
  /** Fraction despite the `_pct` suffix. */
  dist_from_sma_200_pct: number | null;
  high_252d: number | null;
  low_252d: number | null;
  /** Fraction. Negative or zero: how far below the 252-session high the close sits. */
  drawdown_from_252d_high: number | null;
}

/** `identity` block of GET /api/tickers/{t}. */
export interface TickerIdentity {
  ticker: string;
  company_name: string | null;
  sector: string | null;
  industry: string | null;
}

/**
 * `assignment` block of GET /api/tickers/{t} — the frozen model parameters for this ticker.
 *
 * α̂, β̂, σ̂ and r² are outputs of the run, reused to residualise future sessions without
 * refitting. They are model internals: under D-24 they belong behind a disclosure, not in the
 * always-visible layer.
 */
export interface TickerAssignment {
  position: number;
  anchor_ticker: string | null;
  coverage_c: number | null;
  is_anchor: boolean | null;
  under_tau: boolean | null;
  alpha_hat: number | null;
  beta_hat: number | null;
  sigma_hat: number | null;
  r2: number | null;
}

/**
 * `latest` block of GET /api/tickers/{t}.
 *
 * Every field can be null even when `identity` and `assignment` are populated: the route LEFT
 * JOINs the bar, so a ticker with no indicator row yet returns identity and assignment intact and
 * this block entirely null.
 */
export interface TickerLatest extends IndicatorFields {
  bar_date: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

/** GET /api/tickers/{t}. 404 when the ticker is not in the active run's universe. */
export interface TickerDetailResponse {
  identity: TickerIdentity;
  assignment: TickerAssignment;
  latest: TickerLatest;
}

/**
 * One OHLCV bar of GET /api/tickers/{t}/history.
 *
 * `is_adjusted` is on the wire because an adjusted chart will not match a broker's raw chart
 * across an ex-date (D-15) — it is the flag behind the caption the chart owes its reader.
 */
export interface HistoryBar {
  bar_date: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  is_adjusted: boolean | null;
}

/**
 * GET /api/tickers/{t}/history?from&to
 *
 * No bounds → the most recent 252 sessions. Either bound → every row in range, capped at 2000.
 * `from > to` is a 400, not an empty result. An unknown ticker is a 404; a known ticker with no
 * rows in range is a 200 with an empty array — a typo must not look like a quiet market.
 */
export interface TickerHistoryResponse {
  ticker: string;
  count: number;
  bars: HistoryBar[];
}

/** One row of GET /api/tickers/{t}/indicators. Same windowing contract as `/history`. */
export interface IndicatorPoint extends IndicatorFields {
  bar_date: string | null;
  close: number | null;
  volume: number | null;
}

/** GET /api/tickers/{t}/indicators?from&to */
export interface TickerIndicatorsResponse {
  ticker: string;
  count: number;
  indicators: IndicatorPoint[];
}

/**
 * One sentence of GET /api/tickers/{t}/analysis.
 *
 * `text` is finished Vietnamese prose from the API's rule engine and is rendered verbatim. It
 * states a fact about a stored number and is never advisory — no recommendation, no target, no
 * probability. Where a rule leans on a market convention (RSI's 70/30 bands) the wording names it
 * as a convention rather than as a property of the stock, so trimming or paraphrasing it here
 * would break a guarantee the backend makes.
 */
export interface AnalysisStatement {
  code: string;
  text: string;
  inputs: Record<string, number>;
}

/**
 * A rule that produced no sentence because its inputs were null — e.g. a 200-day average on bar
 * 37. Recorded rather than dropped so that silence is never mistaken for neutrality. The UI does
 * not render the technical reason; it renders nothing, or "not enough history" when every rule
 * skipped.
 */
export interface AnalysisSkipped {
  code: string;
  reason: string;
  missing: string[];
}

/**
 * GET /api/tickers/{t}/analysis. `statements.length + skipped.length` is always 13.
 *
 * A ticker with no indicators is a 200 with every rule skipped, not an error.
 */
export interface TickerAnalysisResponse {
  ticker: string;
  bar_date: string | null;
  /** Always "adjusted" (D-15) — the caption saying which price the prose is about. */
  price_basis: string;
  statements: AnalysisStatement[];
  skipped: AnalysisSkipped[];
}

/**
 * One selection step of the greedy algorithm — a row of GET /api/anchors.
 *
 * The route returns ALL `k_max` (15) steps, not the published `k` (10); `in_published_set` marks
 * the cut and the 10-chip selector is a filter at the display edge.
 *
 * `size`, `f_j`, `rho2_mean`, `rho2_min` and `sector_composition` are **null past the published
 * boundary** — `model_groups` holds no row for an unpublished step. That is the truth, not a join
 * bug, and it must render as "not published at k=10", never as 0.
 *
 * `marginal_gain`, `coverage_f` and `f_j` are NOT fractions: they are sums of per-ticker coverage
 * over a set larger than one, so they are not bounded by 1. Only `coverage_fbar`, `rho2_mean` and
 * `rho2_min` are.
 */
export interface AnchorRow {
  step_k: number;
  anchor_ticker: string;
  position: number | null;
  company_name: string | null;
  sector: string | null;
  marginal_gain: number | null;
  coverage_f: number | null;
  coverage_fbar: number | null;
  in_published_set: boolean;
  size: number | null;
  f_j: number | null;
  rho2_mean: number | null;
  rho2_min: number | null;
  /**
   * External validation (`docs/02` §3g), NEVER an input — sector never entered the similarity
   * matrix or the objective.
   *
   * Empirically `{}` for every group of the active artifact: the field is deferred, not computed
   * (`pipelines/artifact/schema.py:186`). The anchor screen therefore derives the composition
   * from `members[].sector` and uses this only when a future run populates it.
   */
  sector_composition: Record<string, number> | null;
}

/** GET /api/anchors — all 15 selection steps, in selection order. */
export interface AnchorsResponse {
  count: number;
  anchors: AnchorRow[];
}

/** One anchored ticker of GET /api/anchors/{a}, ordered by `coverage_c` descending. */
export interface AnchorMember {
  ticker: string;
  company_name: string | null;
  sector: string | null;
  position: number | null;
  coverage_c: number | null;
  is_anchor: boolean | null;
  under_tau: boolean | null;
  indicator_date: string | null;
  ret_1d: number | null;
  ret_5d: number | null;
  ret_20d: number | null;
  turnover_value: number | null;
  rsi_14: number | null;
  dist_from_sma_200_pct: number | null;
  drawdown_from_252d_high: number | null;
}

/**
 * GET /api/anchors/{a}.
 *
 * 404 only when the ticker was never selected at any step — NOT merely "not one of the published
 * ten". A ticker selected at step 11–15 returns 200 here with null group statistics and an empty
 * `members` array, because membership is only ever assigned to a published anchor.
 */
export interface AnchorDetailResponse {
  anchor: AnchorRow;
  members: AnchorMember[];
}

// ---------------------------------------------------------------------------
// Runtime mode + API-base configuration (production no-mock guard)
//
// A production-like build must never fabricate or silently fall back to mock data: a
// missing/invalid NEXT_PUBLIC_API_BASE_URL or a fetch failure becomes a visible error, not a
// mock success. Only explicit local/development mode may use the committed mock path.
// ---------------------------------------------------------------------------

/** Deployment mode. Any hosted build is production-like. */
export type RuntimeMode = "production-like" | "local";

/** Minimal environment shape the classifier reads (kept pure/testable). */
export interface RuntimeEnv {
  VERCEL_ENV?: string | null;
  NODE_ENV?: string | null;
  NEXT_PUBLIC_API_BASE_URL?: string | null;
}

/**
 * Read ambient env. Each field is a LITERAL `process.env.X` member expression so Next.js
 * inlines `NODE_ENV` and the public `NEXT_PUBLIC_API_BASE_URL` into the client bundle.
 *
 * Because the value is inlined AT BUILD TIME, setting it on the host after a successful build
 * changes nothing until a rebuild. On Render it must be a build-time environment variable.
 *
 * `VERCEL_ENV` is a leftover from this app's Vercel era and is absent on Render, where the
 * `NODE_ENV` branch below governs — which is the correct outcome. It is kept rather than
 * deleted because it still classifies a Vercel preview correctly, and preview builds set
 * `NODE_ENV=production` while being a non-production deployment.
 */
function ambientEnv(): RuntimeEnv {
  const hasProcess = typeof process !== "undefined" && !!process.env;
  return {
    VERCEL_ENV: hasProcess ? process.env.VERCEL_ENV : undefined,
    NODE_ENV: hasProcess ? process.env.NODE_ENV : undefined,
    NEXT_PUBLIC_API_BASE_URL: hasProcess ? process.env.NEXT_PUBLIC_API_BASE_URL : undefined,
  };
}

function normalizeEnvToken(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

/**
 * Classify the runtime, fail-closed to production-like. Precedence:
 *   1. VERCEL_ENV=production|preview → production-like; =development → local.
 *   2. VERCEL_ENV present but unrecognized → production-like (fail closed).
 *   3. VERCEL_ENV absent → NODE_ENV=production → production-like;
 *      NODE_ENV=development|test → local.
 *   4. Anything else missing/unrecognized → production-like (fail closed).
 *
 * `next build` sets NODE_ENV=production, so EVERY deployed build is production-like and can
 * never serve mock data. A misconfigured deployment is therefore visibly broken rather than
 * quietly fake, which is the intended trade.
 */
export function classifyRuntimeMode(env: RuntimeEnv = ambientEnv()): RuntimeMode {
  const vercel = normalizeEnvToken(env.VERCEL_ENV);
  if (vercel === "production" || vercel === "preview") return "production-like";
  if (vercel === "development") return "local";
  if (vercel !== "") return "production-like"; // unrecognized: fail closed

  const node = normalizeEnvToken(env.NODE_ENV);
  if (node === "production") return "production-like";
  if (node === "development" || node === "test") return "local";
  return "production-like"; // missing/unrecognized: fail closed
}

/** True when running in a production-like mode. */
export function isProductionLikeMode(env?: RuntimeEnv): boolean {
  return classifyRuntimeMode(env) === "production-like";
}

/** Validation result for a candidate API base URL (no mode logic). */
export type ApiBaseValidation =
  | { ok: true; baseUrl: string }
  | { ok: false; code: string; message: string };

/**
 * Validate a candidate NEXT_PUBLIC_API_BASE_URL: non-empty after trimming, a valid ABSOLUTE
 * URL, and http/https only. Returns a normalized base (trailing slashes stripped) or a typed
 * reason. Rejects blank, malformed, relative, and unsupported-protocol values (a bare
 * `localhost:3000` parses as protocol `localhost:` and is rejected). Never echoes the raw value.
 */
export function validateApiBaseUrl(value: string | null | undefined): ApiBaseValidation {
  const trimmed = (value ?? "").trim();
  if (trimmed === "") {
    return {
      ok: false,
      code: "api_not_configured",
      message: "NEXT_PUBLIC_API_BASE_URL is not set.",
    };
  }
  // P15/D2: render.yaml proxies /api/* to the API service (a same-origin rewrite), so the site
  // no longer needs to know the API's own URL at build time. A root-relative value says exactly
  // that -- normalize it to "" (same origin); joinApiUrl("", "/api/x") already yields "/api/x"
  // with no base to prepend. This is still an explicit, validated configuration, distinct from
  // an EMPTY value: the branch above still fails closed on "" (api_not_configured), unchanged.
  if (trimmed.startsWith("/")) {
    return { ok: true, baseUrl: "" };
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return {
      ok: false,
      code: "api_misconfigured",
      message: "NEXT_PUBLIC_API_BASE_URL must be a valid absolute URL.",
    };
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return {
      ok: false,
      code: "api_misconfigured",
      message: "NEXT_PUBLIC_API_BASE_URL must use http or https.",
    };
  }
  return { ok: true, baseUrl: trimmed.replace(/\/+$/, "") };
}

/** Resolved API configuration for the current mode + environment. */
export type ApiConfig =
  | { kind: "live"; baseUrl: string }
  | { kind: "mock" }
  | { kind: "error"; code: string; message: string };

/**
 * Resolve the API configuration. Production-like builds REQUIRE a valid base URL: a missing
 * value is a typed `error` (never mock, never a localhost default) and an invalid value is a
 * typed `error`. Only local/development mode with no configured URL yields `mock`; any
 * explicitly configured URL is validated in every mode.
 */
export function resolveApiConfig(env: RuntimeEnv = ambientEnv()): ApiConfig {
  const productionLike = classifyRuntimeMode(env) === "production-like";
  const trimmed = (env.NEXT_PUBLIC_API_BASE_URL ?? "").trim();

  if (trimmed === "") {
    if (productionLike) {
      return {
        kind: "error",
        code: "api_not_configured",
        message: "The dashboard has no backend API configured.",
      };
    }
    return { kind: "mock" };
  }

  const validation = validateApiBaseUrl(trimmed);
  if (!validation.ok) {
    return { kind: "error", code: validation.code, message: validation.message };
  }
  return { kind: "live", baseUrl: validation.baseUrl };
}

/** Deterministic endpoint join: base has no trailing slash, path starts with "/". */
export function joinApiUrl(baseUrl: string, path: string, query = ""): string {
  return `${baseUrl.replace(/\/+$/, "")}${path}${query}`;
}

/** Returns the live API base URL, or null when not live (mock/error/unset). */
export function getApiBaseUrl(env?: RuntimeEnv): string | null {
  const cfg = resolveApiConfig(env);
  return cfg.kind === "live" ? cfg.baseUrl : null;
}

/** True when a live API base URL is configured for the current mode. */
export function isApiConfigured(env?: RuntimeEnv): boolean {
  return resolveApiConfig(env).kind === "live";
}

/** Build a query string, skipping undefined/null/empty values. */
function buildQuery(
  params?: Record<string, string | number | undefined | null>,
): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    sp.set(key, String(value));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Typed GET. On a non-2xx response it parses the stable error envelope and throws
 * {@link ApiError}; on success it returns the typed JSON. Throws
 * `ApiError("api_not_configured")` when no base URL is set — it never fabricates mock data,
 * which is the hook's job and only in local mode.
 */
export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | undefined | null>,
): Promise<T> {
  const cfg = resolveApiConfig();
  if (cfg.kind === "error") {
    throw new ApiError(0, cfg.code, cfg.message);
  }
  if (cfg.kind === "mock") {
    throw new ApiError(0, "api_not_configured", "API base URL is not configured.");
  }
  const res = await fetch(joinApiUrl(cfg.baseUrl, path, buildQuery(params)), {
    cache: "no-store",
  }).catch(() => {
    throw new ApiError(0, "network_error", "Could not reach the backend.");
  });
  if (!res.ok) {
    const body = await res
      .json()
      .then((b: unknown) => b as ApiErrorBody)
      .catch(() => null);
    const code = body?.error?.code ?? `http_${res.status}`;
    const message = body?.error?.message ?? `Request failed (HTTP ${res.status}).`;
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

/** Fetch GET /health from the FastAPI backend (used by the shell health card). */
export async function fetchHealth(): Promise<HealthResponse> {
  const cfg = resolveApiConfig();
  if (cfg.kind === "error") {
    throw new ApiError(0, cfg.code, cfg.message);
  }
  if (cfg.kind === "mock") {
    throw new ApiError(0, "api_not_configured", "API base URL is not configured.");
  }

  const res = await fetch(joinApiUrl(cfg.baseUrl, "/health"), { cache: "no-store" }).catch(() => {
    throw new ApiError(0, "network_error", "Could not reach the backend.");
  });
  if (!res.ok) {
    throw new ApiError(
      res.status,
      `http_${res.status}`,
      `Health check failed (HTTP ${res.status}).`,
    );
  }

  return res.json() as Promise<HealthResponse>;
}

// ---------------------------------------------------------------------------
// Typed fetchers — one per implemented route. All eleven are covered.
//
// Ticker paths are uppercased here as well as server-side. The API normalises anyway, but a
// lowercase path would otherwise produce a second cache key for the same resource.
// ---------------------------------------------------------------------------

const seg = (ticker: string): string => encodeURIComponent(ticker.trim().toUpperCase());

export const fetchActiveModelRun = (): Promise<ActiveModelRunResponse> =>
  apiGet<ActiveModelRunResponse>("/api/model/active");

export const fetchMarketOverview = (): Promise<MarketOverviewResponse> =>
  apiGet<MarketOverviewResponse>("/api/market/overview");

export const fetchTopMovers = (
  direction: MoverDirection,
  horizon: MoverHorizon = "1d",
  limit = 10,
): Promise<MoversResponse> =>
  apiGet<MoversResponse>("/api/market/movers", { direction, horizon, limit });

export const fetchMarketSectors = (): Promise<MarketSectorsResponse> =>
  apiGet<MarketSectorsResponse>("/api/market/sectors");

export const fetchMarketLiquidity = (limit = 10): Promise<LiquidityResponse> =>
  apiGet<LiquidityResponse>("/api/market/liquidity", { limit });

export const fetchIndexHistory = (range: IndexRange = "1y"): Promise<IndexHistoryResponse> =>
  apiGet<IndexHistoryResponse>("/api/market/index-history", { range });

export const fetchTickers = (): Promise<TickersResponse> =>
  apiGet<TickersResponse>("/api/tickers");

export const fetchTickerDetail = (ticker: string): Promise<TickerDetailResponse> =>
  apiGet<TickerDetailResponse>(`/api/tickers/${seg(ticker)}`);

/** Omit both bounds for the most recent 252 sessions — the default the chart wants. */
export const fetchTickerHistory = (
  ticker: string,
  from?: string,
  to?: string,
): Promise<TickerHistoryResponse> =>
  apiGet<TickerHistoryResponse>(`/api/tickers/${seg(ticker)}/history`, { from, to });

export const fetchTickerIndicators = (
  ticker: string,
  from?: string,
  to?: string,
): Promise<TickerIndicatorsResponse> =>
  apiGet<TickerIndicatorsResponse>(`/api/tickers/${seg(ticker)}/indicators`, { from, to });

export const fetchTickerAnalysis = (ticker: string): Promise<TickerAnalysisResponse> =>
  apiGet<TickerAnalysisResponse>(`/api/tickers/${seg(ticker)}/analysis`);

export const fetchAnchors = (): Promise<AnchorsResponse> =>
  apiGet<AnchorsResponse>("/api/anchors");

export const fetchAnchorDetail = (anchor: string): Promise<AnchorDetailResponse> =>
  apiGet<AnchorDetailResponse>(`/api/anchors/${seg(anchor)}`);
