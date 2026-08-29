/**
 * Surfaces freshness/stale metadata (UI_SPEC Global States: Stale). Affirms the
 * latest valid snapshot is shown; the as-of chip is always present when known.
 */
export function StaleNotice({
  isStale,
  asOfDate,
}: {
  isStale: boolean;
  asOfDate?: string | null;
}) {
  if (!isStale) return null;
  return (
    <p className="status-notice">
      <span className="status-notice__label">Ghi chú:</span>
      Showing the latest valid snapshot{asOfDate ? ` (as of ${asOfDate})` : ""}.
    </p>
  );
}
