// @vitest-environment node
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const headerValues = new Map<string, string>();
vi.mock("next/headers", () => ({ headers: async () => ({ get: (name: string) => headerValues.get(name) ?? null }) }));

const { nonceFrom, RegisterServiceWorker } = await import("./RegisterServiceWorker");

describe("RegisterServiceWorker (M7e-E1)", () => {
  it("is one async script for /sw-register.js carrying this response's CSP nonce", async () => {
    headerValues.set("Content-Security-Policy", "default-src 'self'; script-src 'self' 'nonce-abc123==' 'strict-dynamic'");
    const html = renderToStaticMarkup(await RegisterServiceWorker());
    expect(html).toBe('<script src="/sw-register.js" async="" nonce="abc123=="></script>');
  });

  it("reads the nonce, or nothing when there is no policy", () => {
    expect(nonceFrom("script-src 'nonce-x+/y=' 'self'")).toBe("x+/y=");
    expect(nonceFrom(null)).toBeUndefined();
    expect(nonceFrom("script-src 'self'")).toBeUndefined();
  });
});
