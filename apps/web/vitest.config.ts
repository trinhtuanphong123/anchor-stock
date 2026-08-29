import { fileURLToPath } from "node:url";
import { defineConfig, type ViteUserConfig } from "vitest/config";

/**
 * Frontend runtime test-harness prerequisite (P13-S01, gate 3). This runner is
 * test infrastructure only — it never changes production behavior or the Next.js
 * build. Discovery is limited to `tests/`; execution is one-shot via `vitest run`
 * (`npm run test`); no browser automation.
 *
 * `envFile: false` disables `.env` / `.env.local` loading (apps/web/.env.local
 * sets NEXT_PUBLIC_API_BASE_URL) so the tests control the environment explicitly
 * via `vi.stubEnv` / `vi.unstubAllEnvs` and no ambient value can leak in.
 */
export default defineConfig({
  envFile: false,
  resolve: {
    alias: {
      // Match tsconfig `@/*` -> `src/*` for the ESM/bundler project.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    setupFiles: ["tests/setup.ts"],
  },
  // `envFile: false` is a valid Vite option (typed on InlineConfig, not
  // UserConfig), so assert the config to ViteUserConfig to keep the property
  // while satisfying defineConfig's parameter type.
} as ViteUserConfig);
