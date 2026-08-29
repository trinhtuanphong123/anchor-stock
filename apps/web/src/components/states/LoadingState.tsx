/**
 * In-card loading skeleton (UI_SPEC Global States: Loading). A subtle placeholder
 * within the owning region; chrome (header, tab bar) renders immediately.
 */
export function LoadingState({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="status-rows" aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="status-row skeleton skeleton-row" />
      ))}
    </div>
  );
}
