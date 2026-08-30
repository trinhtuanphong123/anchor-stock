/**
 * A call that succeeded and returned no rows. Never a blank region.
 *
 * The scope is the point: an empty date range and a mistyped symbol produce the same zero rows,
 * and a message that does not name what was queried lets a typo read as a quiet market.
 */
export function EmptyState({
  message = "Chưa có dữ liệu để hiển thị.",
  scope = "Ghi chú",
}: {
  message?: string;
  /** What was queried, e.g. "Lịch sử giá". */
  scope?: string;
}) {
  return (
    <div className="as-empty">
      <span className="as-empty__scope">{scope}</span>
      {message}
    </div>
  );
}
