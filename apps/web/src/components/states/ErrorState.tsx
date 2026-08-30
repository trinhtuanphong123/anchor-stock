import { Notice } from "./Notice";

/**
 * The API's `{code, message}` envelope as a scoped failure, rendered inside the panel that
 * failed rather than over the whole page.
 *
 * A code meaning "there is no valid snapshot" gets neutral wording instead of the transport
 * message, which would say nothing a reader can act on. Missing configuration lands here too:
 * a deployed build shows this and never invents figures to fill the space.
 *
 * No action vocabulary — nothing here tells the reader to retry, check their connection, or
 * contact anyone.
 */
const NO_SNAPSHOT_CODES = new Set([
  "no_data",
  "database_unavailable",
  "http_503",
  "api_not_configured",
]);

export function ErrorState({ code, message }: { code?: string; message?: string }) {
  const text =
    code !== undefined && NO_SNAPSHOT_CODES.has(code)
      ? "Chưa có dữ liệu hợp lệ."
      : message || "Đã xảy ra lỗi khi tải dữ liệu.";
  return (
    <Notice tone="error" label="Lỗi:">
      {text}
    </Notice>
  );
}
