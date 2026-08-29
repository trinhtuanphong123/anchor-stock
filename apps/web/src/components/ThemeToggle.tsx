"use client";

import { useEffect, useState } from "react";

type Theme = "dark" | "light";

/** One key, shared with the pre-paint script in `app/layout.tsx`. Change both or neither. */
const STORAGE_KEY = "theme";

/**
 * Light/dark switch.
 *
 * Light is the default (P11 S2) and the choice is persisted, which is the whole fix for
 * "choosing light on one page and getting dark on the next": the App Router keeps `<html>` alive
 * across in-app navigation, so the attribute already survived a `<Link>` click — what reverted it
 * was the full page load, and `layout.tsx` now re-applies the stored value before first paint.
 *
 * The initial state must match the server-rendered markup (`data-theme="light"`) or React logs a
 * hydration mismatch; the effect below reads what the pre-paint script actually stamped and
 * corrects the button's label after mount.
 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const current = (document.documentElement.dataset.theme as Theme) ?? "light";
    setTheme(current);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Site data blocked. The theme still applies for this page; it just will not survive a
      // reload, which is strictly better than refusing to switch at all.
    }
    setTheme(next);
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={`Chuyển sang giao diện ${theme === "dark" ? "sáng" : "tối"}`}
    >
      {theme === "dark" ? "Sáng" : "Tối"}
    </button>
  );
}
