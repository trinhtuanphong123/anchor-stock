"use client";

import Link from "next/link";
import type { AnchorsResponse } from "@/lib/api";
import type { ResourceState } from "@/hooks/dashboard";

/**
 * The way back, and the way across.
 *
 * Shown only while a group is open. The roster folds away when one is picked — the group starts
 * at the top of the screen rather than below a table the reader is done with — so this row is
 * what keeps switching anchors to one click, and it is the only place the ten symbols appear as
 * chips. On the roster itself the table is the list.
 *
 * `next/link`, not the DS `Chip`'s plain anchor, and that is load-bearing: a full navigation
 * would refetch `/api/anchors` and the active run on every switch. A client transition changes
 * `?a=` and nothing else, so only the group's own call runs again.
 */
export function AnchorCrumbs({
  state,
  selected,
}: {
  state: ResourceState<AnchorsResponse>;
  selected: string;
}) {
  const published =
    state.kind === "data" ? state.data.anchors.filter((a) => a.in_published_set) : [];

  return (
    <div className="as-crumbs">
      <Link className="as-link" href="/anchors/">
        ← Tất cả điểm neo
      </Link>
      <div className="as-chips">
        {published.map((a) => (
          <Link
            key={a.anchor_ticker}
            href={`/anchors/?a=${a.anchor_ticker}`}
            className={`as-chip${a.anchor_ticker === selected ? " as-chip--active" : ""}`}
            aria-current={a.anchor_ticker === selected ? "page" : undefined}
            title={a.company_name ?? undefined}
          >
            {a.anchor_ticker}
          </Link>
        ))}
      </div>
    </div>
  );
}
