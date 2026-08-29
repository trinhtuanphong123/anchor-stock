import { describe, expect, it } from "vitest";
import {
  classifyRuntimeMode,
  resolveApiConfig,
  validateApiBaseUrl,
  joinApiUrl,
} from "@/lib/api";

/**
 * The production no-mock guard.
 *
 * `next build` sets `NODE_ENV=production`, so every deployed build classifies as production-like
 * and must NEVER serve a fixture: a misconfigured deployment has to look broken rather than look
 * real. The classifier fails closed for exactly that reason, and this is the test that keeps it
 * failing closed.
 *
 * These functions take their environment as an argument, so nothing here needs `vi.stubEnv`.
 */

describe("classifyRuntimeMode", () => {
  it("treats a hosted build as production-like", () => {
    expect(classifyRuntimeMode({ VERCEL_ENV: "production" })).toBe("production-like");
    expect(classifyRuntimeMode({ VERCEL_ENV: "preview" })).toBe("production-like");
    expect(classifyRuntimeMode({ NODE_ENV: "production" })).toBe("production-like");
  });

  it("treats an explicit local build as local", () => {
    expect(classifyRuntimeMode({ VERCEL_ENV: "development" })).toBe("local");
    expect(classifyRuntimeMode({ NODE_ENV: "development" })).toBe("local");
    expect(classifyRuntimeMode({ NODE_ENV: "test" })).toBe("local");
  });

  it("fails closed on anything it does not recognise", () => {
    expect(classifyRuntimeMode({})).toBe("production-like");
    expect(classifyRuntimeMode({ NODE_ENV: "staging" })).toBe("production-like");
    expect(classifyRuntimeMode({ VERCEL_ENV: "something-new" })).toBe("production-like");
    // VERCEL_ENV wins over NODE_ENV: a Vercel preview sets NODE_ENV=production while being a
    // non-production deployment.
    expect(classifyRuntimeMode({ VERCEL_ENV: "development", NODE_ENV: "production" })).toBe("local");
  });
});

describe("resolveApiConfig", () => {
  it("errors rather than mocking when a production-like build has no API URL", () => {
    const cfg = resolveApiConfig({ NODE_ENV: "production", NEXT_PUBLIC_API_BASE_URL: "" });
    expect(cfg.kind).toBe("error");
    expect(cfg).toMatchObject({ code: "api_not_configured" });
  });

  it("serves the mock only in local mode with no URL configured", () => {
    expect(resolveApiConfig({ NODE_ENV: "development", NEXT_PUBLIC_API_BASE_URL: "" })).toEqual({
      kind: "mock",
    });
  });

  it("validates an explicitly configured URL in every mode", () => {
    expect(
      resolveApiConfig({ NODE_ENV: "development", NEXT_PUBLIC_API_BASE_URL: "not a url" }),
    ).toMatchObject({ kind: "error", code: "api_misconfigured" });

    expect(
      resolveApiConfig({
        NODE_ENV: "production",
        NEXT_PUBLIC_API_BASE_URL: "https://api.example.com/",
      }),
    ).toEqual({ kind: "live", baseUrl: "https://api.example.com" });
  });
});

describe("validateApiBaseUrl", () => {
  it("requires an absolute http(s) URL", () => {
    expect(validateApiBaseUrl("https://api.example.com").ok).toBe(true);
    expect(validateApiBaseUrl("http://localhost:8000").ok).toBe(true);
    // A bare host:port parses with protocol "localhost:", which is not http(s).
    expect(validateApiBaseUrl("localhost:3000").ok).toBe(false);
    expect(validateApiBaseUrl("ftp://example.com").ok).toBe(false);
    expect(validateApiBaseUrl("  ").ok).toBe(false);
  });

  // P15/D2: a same-origin deploy proxies /api/* to the API service (render.yaml's rewrite), so
  // the site is configured with a root-relative value instead of the API's own absolute URL.
  it("accepts a root-relative value as same-origin, normalized to an empty base", () => {
    expect(validateApiBaseUrl("/")).toEqual({ ok: true, baseUrl: "" });
    expect(validateApiBaseUrl("/api")).toEqual({ ok: true, baseUrl: "" });
  });

  it("still fails closed on an empty value -- same-origin must be requested explicitly", () => {
    expect(validateApiBaseUrl("")).toMatchObject({ ok: false, code: "api_not_configured" });
    expect(validateApiBaseUrl(undefined)).toMatchObject({ ok: false, code: "api_not_configured" });
  });

  it("strips trailing slashes so the join stays deterministic", () => {
    expect(validateApiBaseUrl("https://api.example.com///")).toEqual({
      ok: true,
      baseUrl: "https://api.example.com",
    });
  });

  // The message reaches the browser on a misconfigured deploy, so it names the variable, never
  // its value. Both rejection paths are checked: unsupported protocol, and unparseable.
  it("never echoes the offending value back in the message", () => {
    for (const bad of ["ftp://secret-host.internal", "http://[secret-host"]) {
      const result = validateApiBaseUrl(bad);
      if (result.ok) throw new Error(`expected a rejection for ${bad}`);
      expect(result.message).not.toContain("secret-host");
      expect(result.message).toContain("NEXT_PUBLIC_API_BASE_URL");
    }
  });
});

describe("joinApiUrl", () => {
  it("joins without doubling or dropping a slash", () => {
    expect(joinApiUrl("https://api.example.com", "/api/tickers")).toBe(
      "https://api.example.com/api/tickers",
    );
    expect(joinApiUrl("https://api.example.com/", "/api/tickers", "?limit=10")).toBe(
      "https://api.example.com/api/tickers?limit=10",
    );
  });

  // P15/D2: an empty base -- what a root-relative NEXT_PUBLIC_API_BASE_URL normalizes to --
  // must resolve to a same-origin path, not a broken "undefined/api/x".
  it("resolves an empty (same-origin) base to a bare path", () => {
    expect(joinApiUrl("", "/api/x")).toBe("/api/x");
  });
});

describe("resolveApiConfig — same-origin proxy (P15/D2)", () => {
  it("treats a root-relative NEXT_PUBLIC_API_BASE_URL as live, same-origin", () => {
    expect(
      resolveApiConfig({ NODE_ENV: "production", NEXT_PUBLIC_API_BASE_URL: "/" }),
    ).toEqual({ kind: "live", baseUrl: "" });
  });
});
