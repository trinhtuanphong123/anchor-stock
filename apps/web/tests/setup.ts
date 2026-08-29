/**
 * Vitest setup. `vitest.config.ts` has referenced this file since P13; the directory it lives in
 * was never created, so `npm run test` ran zero tests and reported success — a check that passes
 * because it is empty. P10 makes it a real check.
 *
 * Deliberately minimal: `envFile: false` in the config already stops `.env.local` leaking
 * `NEXT_PUBLIC_API_BASE_URL` into the runtime-mode tests, so there is nothing to undo here. Each
 * test that cares about the environment stubs it explicitly.
 */

import { afterEach, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
});
