// ESLint flat config: Next.js core-web-vitals + TypeScript rules.
// apps/web/CLAUDE.md: TypeScript strict, no `any`.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
  // schema.d.ts is generated from contracts/openapi.yaml (npm run gen:api); never edited by hand.
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "src/lib/api/schema.d.ts"]),
]);
