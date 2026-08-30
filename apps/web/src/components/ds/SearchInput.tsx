/**
 * Client-side filter box, with an optional result count beside it.
 *
 * The whole universe is 85 rows and it is already in memory by the time this renders, so the
 * filtering happens in the browser and no keystroke reaches the API.
 */
export function SearchInput({
  value,
  onChange,
  placeholder = "Tìm mã, tên công ty hoặc ngành…",
  count,
}: {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  /** Result count, already formatted — e.g. "12 / 85". */
  count?: string | number | null;
}) {
  return (
    <div className="as-controls">
      <input
        className="as-search"
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange?.(e.target.value)}
        aria-label={placeholder}
      />
      {count !== undefined && count !== null ? <span className="as-count">{count}</span> : null}
    </div>
  );
}
