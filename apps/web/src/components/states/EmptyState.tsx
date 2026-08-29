/**
 * Scoped quiet empty state (UI_SPEC Global States: Empty). Never a blank region.
 */
export function EmptyState({
  message = "Chưa có dữ liệu để hiển thị.",
  scope,
}: {
  message?: string;
  scope?: string;
}) {
  return (
    <p className="status-notice">
      <span className="status-notice__label">{scope ? `${scope}:` : "Note:"}</span>
      {message}
    </p>
  );
}
