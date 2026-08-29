/**
 * Non-trading-day notice (UI_SPEC Global States: Non-trading day). The latest
 * valid snapshot is served; no live-market recomputation is implied.
 */
export function NonTradingDayNotice({
  isTradingDay = true,
  dayType,
}: {
  isTradingDay?: boolean;
  dayType?: string | null;
}) {
  if (isTradingDay) return null;
  return (
    <p className="status-notice">
      <span className="status-notice__label">Ghi chú:</span>
      Non-trading day{dayType ? ` (${dayType})` : ""} — latest valid snapshot served.
    </p>
  );
}
