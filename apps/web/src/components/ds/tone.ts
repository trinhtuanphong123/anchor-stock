/**
 * Directional tone, shared by every primitive that can colour a figure.
 *
 * Colour on a number means the direction the price moved and nothing else — which is why a
 * status badge is teal or amber and a composition bar is the accent. `flat` is the neutral step
 * and is also what a null takes: a missing value must never be drawn in the colour of 0%.
 */
export type Tone = "pos" | "neg" | "flat";

/** The class for a tone, or "" for an untoned figure. */
export function toneClass(tone: Tone | undefined): string {
  if (tone === "pos") return " as-pos";
  if (tone === "neg") return " as-neg";
  if (tone === "flat") return " as-flat";
  return "";
}
