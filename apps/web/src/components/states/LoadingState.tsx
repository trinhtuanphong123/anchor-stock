/**
 * In-card skeleton, rendered by the region that owns the request.
 *
 * Every block calls its own endpoint and shows its own state: a slow panel must never blank a
 * panel that has already answered, and the layout must never make one block wait on another. The
 * chrome — header, tab bar — is there from the first paint regardless.
 */
export function LoadingState({ rows = 3, label = "Đang tải" }: { rows?: number; label?: string }) {
  return (
    <div className="as-status-rows" aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="as-skeleton" />
      ))}
    </div>
  );
}
