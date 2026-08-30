export interface RangeTabOption {
  value: string;
  label: string;
}

/**
 * Bare chip strip answering "which window am I looking at" — no container, no border, only the
 * active chip filled.
 *
 * There is no "1D" option anywhere in this product: the pipeline collects daily bars, so an
 * intraday range would be a label making a claim the data cannot support.
 *
 * Shaped differently from {@link SegmentedControl} on purpose, so "which range" and "which
 * direction" never look like the same question.
 */
export function RangeTabs({
  options = [],
  value,
  onChange,
  label = "Khoảng thời gian",
}: {
  options?: RangeTabOption[];
  value?: string;
  onChange?: (value: string) => void;
  label?: string;
}) {
  return (
    <div className="as-tabs" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`as-tab${value === o.value ? " as-tab--active" : ""}`}
          aria-pressed={value === o.value}
          onClick={() => onChange?.(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
