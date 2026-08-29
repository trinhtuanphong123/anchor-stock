import { describe, expect, it } from "vitest";
import { coverageFbarAdjusted, fbarAdjusted, type ActiveModelRunResponse } from "@/lib/api";
import { formatDecimal, DASH } from "@/components/market/format";

/**
 * F̄_adj = (F − k) / (N − k), the coverage figure with the tautological self-cover removed.
 *
 * Every anchor covers itself at ρ²(j,j) = 1, so F(S) carries exactly k terms equal to 1 that
 * carry no information — 44.7 %–54.3 % of the published F across the ten research artifacts.
 * D-26 keeps the objective unchanged and requires the two numbers to be displayed together,
 * so this is derived on the client from fields the API already serves rather than stored.
 *
 * The expected values below are not invented: they are `fbar_adjusted` as computed by
 * `pipelines/research/diagonal.py` and published in
 * `data/research/diagonal_comparison_pearson_rho2.csv`. If this test and that CSV ever
 * disagree, the client is wrong.
 */

function run(over: Partial<ActiveModelRunResponse> = {}): ActiveModelRunResponse {
  return {
    run_id: 1,
    artifact_id: "ae2010a4ad426",
    scope: "year",
    scope_label: "2025",
    similarity_measure: "pearson_rho2",
    universe_version: "v1",
    index_symbol: "VNINDEX",
    window_start: "2025-01-02",
    window_end: "2025-12-31",
    latest_session: "2025-12-31",
    prior_close_date: "2024-12-31",
    n_sessions: 249,
    n_tickers: 85,
    q: 0.3414,
    k: 10,
    k_max: 15,
    tau: 0.1,
    coverage_f: 22.349002,
    coverage_fbar: 0.262929,
    n_under_tau: 33,
    is_primary: true,
    created_at: null,
    loaded_at: null,
    ...over,
  };
}

describe("coverageFbarAdjusted", () => {
  it("reproduces the published fbar_adjusted for the 2025 pearson artifact", () => {
    // diagonal_comparison_pearson_rho2.csv, 2025: fbar_adjusted = 0.16465336153906876
    expect(coverageFbarAdjusted(run())).toBeCloseTo(0.164653, 6);
  });

  it("is materially below the raw F̄ — the gap is the tautology, not rounding", () => {
    const r = run();
    const adj = coverageFbarAdjusted(r)!;
    expect(adj).toBeLessThan(r.coverage_fbar!);
    // k of the F is identity: 10 / 22.349 = 44.7 % of the published figure.
    expect(1 - adj / r.coverage_fbar!).toBeCloseTo(0.3737, 3);
  });

  it("matches every published research year", () => {
    // (year, coverage_f, expected fbar_adjusted) from diagonal_comparison_pearson_rho2.csv
    const cases: Array<[string, number, number]> = [
      ["2021", 0.23304263743057899 * 85, 0.1307816557546562],
      ["2022", 0.26316376232691435 * 85, 0.16491893063716964],
      ["2023", 0.23783808320848343 * 85, 0.1362164943029479],
      ["2024", 0.22351956291915379 * 85, 0.11998883797504097],
      ["2025", 0.2629294366521195 * 85, 0.16465336153906876],
    ];
    for (const [label, f, expected] of cases) {
      const got = coverageFbarAdjusted(run({ scope_label: label, coverage_f: f }));
      expect(got, `year ${label}`).toBeCloseTo(expected, 10);
    }
  });

  it("returns null rather than a wrong number when the inputs cannot support one", () => {
    expect(coverageFbarAdjusted(run({ coverage_f: null }))).toBeNull();
    // N === k would divide by zero; N < k is incoherent. Both must decline, not produce Infinity.
    expect(coverageFbarAdjusted(run({ n_tickers: 10 }))).toBeNull();
    expect(coverageFbarAdjusted(run({ n_tickers: 5 }))).toBeNull();
  });
});

/**
 * The per-step form, used by the anchor screen.
 *
 * `k` here is the size of the set at that step (`AnchorRow.step_k`), not the run's published k:
 * at step j the sum carries j tautological terms and averages over N − j non-anchors. Getting
 * that wrong is the one way to produce a plausible but incorrect column, so it is what these
 * cases pin down.
 *
 * Expected values come from the active artifact itself — `data/artifacts/ae2010a4ad426/
 * manifest.json`, `anchors[].coverage_f` with `run.n_tickers = 85` — not from anything this
 * client computes. Same rule as the block above: if the test and the artifact disagree, the
 * client is wrong.
 */
describe("fbarAdjusted — the per-step form", () => {
  const N = 85;

  // [step_k, coverage_f, expected F̄_adj] — the published selection curve, five sampled steps
  // spanning the published cut (k=10) in both directions.
  const CURVE: Array<[number, number, number]> = [
    [1, 5.800375824479027, 0.05714733124379794],
    [5, 15.785591196643308, 0.13481988995804134],
    [10, 22.349002115430157, 0.16465336153906876],
    [11, 23.49682005232534, 0.16887594665304514],
    [15, 27.581888812440393, 0.17974126874914848],
  ];

  it("reproduces the artifact's own selection curve at every sampled step", () => {
    for (const [k, f, expected] of CURVE) {
      expect(fbarAdjusted(f, k, N), `step ${k}`).toBeCloseTo(expected, 12);
    }
  });

  it("agrees with the headline at k=10, by two independent routes", () => {
    // The step-10 row of the artifact and the run-level figure are the same set, so the per-step
    // helper and the headline wrapper must land on the same number — which is also the
    // `fbar_adjusted` published in diagonal_comparison_pearson_rho2.csv for 2025.
    expect(fbarAdjusted(22.349002115430157, 10, N)).toBeCloseTo(
      coverageFbarAdjusted(run())!,
      6,
    );
    expect(fbarAdjusted(22.349002115430157, 10, N)).toBeCloseTo(0.16465336153906876, 12);
  });

  it("shows why this column exists: raw F̄ rises 23.4 % from k=10 to k=15, F̄_adj only 9.2 %", () => {
    // docs/02 §3d — the tautology grows linearly with k, so raw F̄ overstates the benefit of more
    // anchors by roughly 2.6x. If someone "simplifies" the formula, this is the assertion that
    // explains what broke.
    const rawFbar10 = 0.2629294366521195;
    const rawFbar15 = 0.32449280955812226;
    const adj10 = fbarAdjusted(22.349002115430157, 10, N)!;
    const adj15 = fbarAdjusted(27.581888812440393, 15, N)!;

    expect(rawFbar15 / rawFbar10 - 1).toBeCloseTo(0.234, 3);
    expect(adj15 / adj10 - 1).toBeCloseTo(0.092, 3);
    // The overstatement factor docs/02 quotes.
    expect((rawFbar15 / rawFbar10 - 1) / (adj15 / adj10 - 1)).toBeCloseTo(2.6, 1);
  });

  it("declines rather than guesses when N has not loaded, and renders as a dash", () => {
    // The anchor screen passes null while /api/model/active is in flight or has failed. A
    // coverage figure computed against a guessed N would be worse than no figure at all.
    expect(fbarAdjusted(22.349002115430157, 10, null)).toBeNull();
    expect(formatDecimal(fbarAdjusted(22.349002115430157, 10, null), 4)).toBe(DASH);

    expect(fbarAdjusted(null, 10, N)).toBeNull();
    expect(fbarAdjusted(22.349002115430157, null, N)).toBeNull();
    // N ≤ k: no non-anchors left to average over.
    expect(fbarAdjusted(22.349002115430157, 85, N)).toBeNull();
    expect(fbarAdjusted(Number.POSITIVE_INFINITY, 10, N)).toBeNull();
  });
});
