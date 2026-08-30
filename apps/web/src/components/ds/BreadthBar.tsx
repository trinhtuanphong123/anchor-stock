/**
 * A 4px proportional rule for advancers / unchanged / decliners.
 *
 * Not a donut: a chart type with an axis would invite the reader to measure it, and the only
 * question this answers is how much of the board is green.
 *
 * The three counts cover only tickers that HAVE a `ret_1d`, so they do not sum to the universe —
 * `note` is where the caller says so, and it is not optional in spirit: 41 + 8 + 30 beside a
 * "85 mã" figure elsewhere on the same bar is a discrepancy the reader has to be told about.
 */
export function BreadthBar({
  up = 0,
  flat = 0,
  down = 0,
  note,
}: {
  up?: number;
  flat?: number;
  down?: number;
  /** Names the denominator. Shown as the bar's title. */
  note?: string;
}) {
  const total = up + flat + down;
  const pct = (n: number): string => (total > 0 ? `${(n / total) * 100}%` : "0%");
  return (
    <div className="as-breadth">
      <div
        className="as-breadth__bar"
        role="img"
        title={note}
        aria-label={`${up} mã tăng, ${flat} mã đứng giá, ${down} mã giảm`}
      >
        <span className="as-breadth__up" style={{ width: pct(up) }} />
        <span className="as-breadth__flat" style={{ width: pct(flat) }} />
        <span className="as-breadth__down" style={{ width: pct(down) }} />
      </div>
      <div className="as-breadth__legend">
        <span className="as-pos">
          <b>{up}</b> tăng
        </span>
        <span className="as-flat">
          <b>{flat}</b> đứng
        </span>
        <span className="as-neg">
          <b>{down}</b> giảm
        </span>
      </div>
    </div>
  );
}
