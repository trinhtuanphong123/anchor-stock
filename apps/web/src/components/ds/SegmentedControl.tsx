export interface SegmentOption {
  value: string;
  label: string;
  /** Which side of the directional pair this option tints as, when `tone="direction"`. */
  tone?: "up" | "down";
}

/**
 * Bordered strip for an exclusive choice — up/down, this/that.
 *
 * `tone="direction"` tints the pressed option with the price pair, which is legal here because
 * the option IS the direction: "Tăng" pressed green is naming what it filters, not colouring a
 * measurement. Everything else uses `"accent"`.
 */
export function SegmentedControl({
  options = [],
  value,
  onChange,
  label,
  tone = "accent",
}: {
  options?: SegmentOption[];
  value?: string;
  onChange?: (value: string) => void;
  label?: string;
  tone?: "accent" | "direction";
}) {
  return (
    <div className="as-segment" role="group" aria-label={label}>
      {options.map((o) => {
        const variant =
          tone === "direction"
            ? o.tone === "up" || o.value === "up"
              ? " as-segment__opt--up"
              : " as-segment__opt--down"
            : " as-segment__opt--on";
        return (
          <button
            key={o.value}
            type="button"
            className={`as-segment__opt${variant}`}
            aria-pressed={value === o.value}
            onClick={() => onChange?.(o.value)}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
