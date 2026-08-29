import type { ReactNode } from "react";
import styles from "./charts.module.css";
import { ChartCaption } from "./ChartCaption";

/**
 * Reusable chart container: a titled surface with an optional subtitle, an
 * optional metadata caption (unit / horizon / as-of, rendered only when
 * supplied), and a stable content area for the chart body. The body simply
 * renders `children`, so callers pass their own loading/empty/error content —
 * this component holds no data and creates no hooks. No metadata is fabricated.
 */
export function ChartFrame({
  title,
  subtitle,
  unit,
  horizon,
  asOf,
  className,
  children,
}: {
  title: string;
  subtitle?: string;
  unit?: string;
  horizon?: string;
  asOf?: string | null;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={[styles.frame, className].filter(Boolean).join(" ")}>
      <div className={styles.frameHead}>
        <h3 className={styles.frameTitle}>{title}</h3>
        {subtitle && <p className={styles.frameSubtitle}>{subtitle}</p>}
        <ChartCaption unit={unit} horizon={horizon} asOf={asOf} />
      </div>
      <div className={styles.frameBody}>{children}</div>
    </section>
  );
}
