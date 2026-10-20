import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    // Components render in jsdom; modules that run only on the server opt into
    // `// @vitest-environment node` at the top of their test file.
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./vitest.setup.ts"],
    restoreMocks: true,
    unstubEnvs: true,
    unstubGlobals: true,
    // M6-P1: with one jsdom worker per core minus one (Vitest's default), a 20-core machine
    // oversubscribes the CPU and the first workspace render of a file can miss Testing
    // Library's 1 s wait (PrintAndLink, seen since M5-P2). Half the cores is faster overall and
    // leaves every assertion and timeout as it was (docs/DEBUG_JOURNAL.md, 20 Oct 2026).
    maxWorkers: "50%",
  },
});
