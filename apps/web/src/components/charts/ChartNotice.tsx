import type { ReactNode } from "react";
import styles from "./charts.module.css";

/**
 * Static inline note container for later use by charts that must present
 * caller-supplied text alongside the figure. It renders `children` unchanged and
 * has no dismiss control. The optional `label` is a short caller-supplied prefix
 * and defaults to nothing, so this primitive contributes no copy of its own.
 */
export function ChartNotice({
  children,
  label,
  className,
}: {
  children: ReactNode;
  label?: string;
  className?: string;
}) {
  return (
    <aside
      className={[styles.notice, className].filter(Boolean).join(" ")}
      role="note"
    >
      {label && <span className={styles.noticeLabel}>{label}</span>}
      {children}
    </aside>
  );
}
