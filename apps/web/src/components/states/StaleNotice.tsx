import { Notice } from "./Notice";

/**
 * Rows whose latest bar is older than the current session.
 *
 * It states which snapshot is on screen and stops there: nothing was recomputed, nothing is
 * live, and the as-of date is the whole content of the notice.
 */
export function StaleNotice({ isStale, asOfDate }: { isStale: boolean; asOfDate?: string | null }) {
  if (!isStale) return null;
  return (
    <Notice tone="stale" label="Dữ liệu cũ:">
      Đang hiển thị ảnh chụp hợp lệ gần nhất{asOfDate ? `, đến ${asOfDate}` : ""}.
    </Notice>
  );
}
