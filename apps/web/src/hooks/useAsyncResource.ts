"use client";

import { useEffect, useState } from "react";
import { ApiError, resolveApiConfig } from "@/lib/api";

export type ResourceState<T> =
  | { kind: "loading" }
  | { kind: "data"; data: T; isMock: boolean }
  | { kind: "error"; code: string; message: string };

/**
 * Generic data-layer hook shared by every dashboard resource. In local/development
 * mode with no API configured it serves a clearly-labeled mock (`isMock: true`)
 * instead of fetching — it never pretends the mock is live-API verification. In
 * production-like mode (Vercel production or preview) it NEVER serves a mock: a
 * missing/invalid configuration or a fetch/contract failure becomes a visible
 * `error` state (a rejection is never converted into a mock `success`). On error
 * it surfaces the stable envelope code/message via {@link ApiError}.
 *
 * `deps` is a caller-controlled dependency list (same role as useEffect deps);
 * the fetcher/mock closures are intentionally excluded, so the hook refetches
 * only when the resource arguments change.
 */
export function useAsyncResource<T>(
  fetcher: () => Promise<T>,
  mock: T,
  deps: ReadonlyArray<unknown> = [],
): ResourceState<T> {
  const [state, setState] = useState<ResourceState<T>>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    const cfg = resolveApiConfig();
    if (cfg.kind === "mock") {
      // Local/development explicit mock only — production-like never reaches here.
      setState({ kind: "data", data: mock, isMock: true });
      return;
    }
    if (cfg.kind === "error") {
      // Production-like missing/invalid config → visible error, not mock success.
      setState({ kind: "error", code: cfg.code, message: cfg.message });
      return;
    }
    setState({ kind: "loading" });
    fetcher()
      .then((data) => {
        if (!cancelled) setState({ kind: "data", data, isMock: false });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) {
          setState({ kind: "error", code: err.code, message: err.message });
        } else {
          setState({
            kind: "error",
            code: "unknown",
            message: err instanceof Error ? err.message : "Unknown error",
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // fetcher/mock are intentional closures; refetch is driven by `deps`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
