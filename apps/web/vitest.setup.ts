import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// M7c-P7: next/font is compiled by Next.js at build time and is not callable under Vitest; the
// brand font (src/app/fonts.ts) only contributes class names, so tests get fixed ones.
vi.mock("next/font/local", () => ({
  default: () => ({ className: "font-manrope", variable: "font-manrope-variable", style: { fontFamily: "Manrope" } }),
}));

afterEach(() => {
  cleanup();
});
