import type { ReactNode } from "react";
import type { Tone } from "./tone";

/**
 * A row is a plain record. Two suffixed keys are read off it besides the displayed value:
 *
 *   `<key>__n`    the raw number behind the cell, used to scale the inline magnitude bar
 *   `<key>__tone` "pos" | "neg" | "flat", which colours the cell
 *
 * The suffixes exist because the displayed value is already a formatted string by the time it
 * reaches a table — "+6.84%" cannot be measured, and re-parsing it here would put a second
 * number-reading rule in the product.
 */
export type DataTableRow = Record<string, unknown>;

export interface DataTableColumn {
  /** Row-object key. `"__rank"` is the ordinal column. */
  key: string;
  header: ReactNode;
  /** `"num"` right-aligns the column and switches it to tabular mono. */
  align?: "left" | "num";
  /** Extra class for the cell: `"as-ticker"`, `"as-company"`, `"as-sector"`. */
  cell?: string;
  render?: (row: DataTableRow) => ReactNode;
}

function rawNumber(row: DataTableRow, key: string): number | null {
  const v = row[`${key}__n`];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function rawTone(row: DataTableRow, key: string): Tone | undefined {
  const v = row[`${key}__tone`];
  return v === "pos" || v === "neg" || v === "flat" ? v : undefined;
}

/**
 * Displayed value for a cell with no `render`. Anything that is not already a string or a number
 * is a caller error — markup belongs in `render`, not in the row object.
 */
function cellValue(row: DataTableRow, key: string): ReactNode {
  const v = row[key];
  return typeof v === "string" || typeof v === "number" ? v : null;
}

/**
 * The board table: 11px letter-spaced heads, hairline rows, hover tint, and mono numerics.
 *
 * **Every numeric column carries `as-num`** — `tabular-nums` and right-aligned. That is not a
 * preference: a price column that shifts by a pixel as its digits change is the clearest way a
 * table reads as amateur, and a right edge is what makes two magnitudes comparable at a glance.
 * Pass `align: "num"` and the column gets it on both the head and every cell.
 *
 * One column may be named as the RANKED one. It takes the emphasis step and an inline magnitude
 * bar scaled to the largest absolute value among the VISIBLE rows only, so the bar answers "how
 * big within what I am looking at" rather than against a maximum off screen. Marking it matters:
 * five numeric columns with nothing marked is a table that looks sorted by whichever column the
 * reader happens to read first.
 *
 * `barTone="neutral"` draws the bar in the accent, for unsigned quantities — money traded has no
 * direction, and drawing turnover in green would say it does.
 *
 * `doc` switches to the document density used on `/tickers` and `/anchors`: boxed, sunken heads.
 * The board density and the document density disagree on purpose; do not unify them.
 */
export function DataTable({
  columns = [],
  rows = [],
  rankedKey,
  barTone = "direction",
  getRowKey,
  onRowClick,
  selectedKey,
  doc = false,
}: {
  columns?: DataTableColumn[];
  rows?: DataTableRow[];
  /** Column the rows are ordered by — takes the emphasis step and the magnitude bar. */
  rankedKey?: string;
  /** `"direction"` = the green/red pair; `"neutral"` = accent, for unsigned quantities. */
  barTone?: "direction" | "neutral";
  getRowKey?: (row: DataTableRow, index: number) => string | number;
  onRowClick?: (row: DataTableRow) => void;
  selectedKey?: string | number;
  /** Document density rather than board density. */
  doc?: boolean;
}) {
  // Scaled to the visible rows, deliberately: see the note above.
  let scale = 0;
  if (rankedKey) {
    for (const row of rows) {
      const n = rawNumber(row, rankedKey);
      if (n !== null) scale = Math.max(scale, Math.abs(n));
    }
  }

  return (
    <div className={`as-table-wrap${doc ? " as-table-wrap--boxed" : ""}`}>
      <table className={`as-table${doc ? " as-table--doc" : ""}`}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={
                  [c.align === "num" ? "as-num" : "", c.key === "__rank" ? "as-rank" : ""]
                    .filter(Boolean)
                    .join(" ") || undefined
                }
                aria-sort={rankedKey !== undefined && c.key === rankedKey ? "other" : undefined}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const key = getRowKey ? getRowKey(row, i) : i;
            return (
              <tr
                key={key}
                aria-selected={selectedKey !== undefined && selectedKey === key ? true : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                style={onRowClick ? { cursor: "pointer" } : undefined}
              >
                {columns.map((c) => {
                  const ranked = rankedKey !== undefined && c.key === rankedKey;
                  const tone = rawTone(row, c.key);
                  const n = rawNumber(row, c.key);
                  const width =
                    ranked && scale > 0 && n !== null ? `${(Math.abs(n) / scale) * 100}%` : "0%";
                  const cls = [
                    c.align === "num" ? "as-num" : "",
                    c.key === "__rank" ? "as-rank" : "",
                    c.cell ?? "",
                    tone ? `as-${tone}` : "",
                    ranked ? "as-ranked as-barcell" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <td key={c.key} className={cls || undefined}>
                      {ranked ? (
                        <span
                          aria-hidden="true"
                          className={`as-bar ${
                            barTone === "neutral"
                              ? "as-bar--neutral"
                              : tone === "neg"
                                ? "as-bar--neg"
                                : "as-bar--pos"
                          }`}
                          style={{ width }}
                        />
                      ) : null}
                      <span className={ranked ? "as-barvalue" : undefined}>
                        {c.render ? c.render(row) : cellValue(row, c.key)}
                      </span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
