/**
 * The six global states, each rendered by the region that owns the request that produced it.
 *
 * Loading, empty and error are the three a panel can be in. Stale, non-trading day and mock are
 * the three that qualify data that DID arrive — they say what the figures below them are, and
 * none of them replaces the figures.
 *
 * All six are built from the design system's `as-*` classes and contribute no CSS of their own.
 */
export { Notice } from "./Notice";
export { LoadingState } from "./LoadingState";
export { EmptyState } from "./EmptyState";
export { ErrorState } from "./ErrorState";
export { StaleNotice } from "./StaleNotice";
export { NonTradingDayNotice } from "./NonTradingDayNotice";
export { MockDataNotice } from "./MockDataNotice";
