/**
 * Maps the stable API error envelope to a scoped, honest error state (UI_SPEC
 * Global States: Error). A 503 / no-valid-snapshot code renders the neutral
 * "Chua co du lieu hop le." wording rather than fabricated data. No action
 * vocabulary.
 */
const NO_SNAPSHOT_CODES = new Set([
  "no_data",
  "database_unavailable",
  "http_503",
  "api_not_configured",
]);

export function ErrorState({ code, message }: { code?: string; message?: string }) {
  const isNoSnapshot = code !== undefined && NO_SNAPSHOT_CODES.has(code);
  const text = isNoSnapshot
    ? "Chưa có dữ liệu hợp lệ."
    : message || "Đã xảy ra lỗi khi tải dữ liệu.";
  return (
    <p className="status-notice status-notice--error">
      <span className="status-notice__label">Lỗi:</span>
      {text}
    </p>
  );
}
