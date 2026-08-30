import { Notice } from "./Notice";

/**
 * A day the exchange did not trade. The latest valid snapshot is served; no live-market
 * recomputation is implied, and the absence of movement is the calendar, not the market.
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
    <Notice tone="muted" label="Ghi chú:">
      Không phải phiên giao dịch{dayType ? ` (${dayType})` : ""} — đang hiển thị ảnh chụp hợp lệ
      gần nhất.
    </Notice>
  );
}
