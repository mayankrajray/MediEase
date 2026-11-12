// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { GET } from "@/app/manifest.webmanifest/route";

import { BACKGROUND_COLOR, MANIFEST_PATH, PWA_METADATA, PWA_VIEWPORT, THEME_COLOR, webManifest } from "./manifest";

const PUBLIC = path.resolve(import.meta.dirname, "../../../public");

/** Width and height from a PNG's IHDR chunk. */
function pngSize(file: string): [number, number] {
  const bytes = readFileSync(file);
  expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
  return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
}

describe("the web app manifest (M7e-E1)", () => {
  const m = webManifest();

  it("Q1: one installable app for staff and patients, opening at / in its own window", () => {
    expect(m).toMatchObject({ id: "/", name: "MediEase", short_name: "MediEase", start_url: "/", scope: "/", display: "standalone" });
    expect(m.theme_color).toBe(THEME_COLOR);
    expect(m.background_color).toBe(BACKGROUND_COLOR);
  });

  it("lists 192 and 512 icons and a maskable one, each a PNG of the size it claims", () => {
    const icons = m.icons ?? [];
    expect(icons.map((i) => `${i.sizes} ${i.purpose}`)).toEqual(["192x192 any", "512x512 any", "512x512 maskable"]);
    for (const icon of icons) {
      const file = path.join(PUBLIC, icon.src);
      expect(existsSync(file), icon.src).toBe(true);
      const [w, h] = pngSize(file);
      expect(`${w}x${h}`).toBe(icon.sizes);
    }
  });

  it("is served as a web app manifest", async () => {
    const response = GET();
    expect(response.headers.get("content-type")).toBe("application/manifest+json; charset=utf-8");
    expect(await response.json()).toEqual(m);
  });

  it("the layouts' tags link it and colour the browser bar", () => {
    expect(PWA_METADATA.manifest).toBe(MANIFEST_PATH);
    expect(MANIFEST_PATH).toBe("/manifest.webmanifest");
    expect(PWA_VIEWPORT.themeColor).toBe(THEME_COLOR);
  });
});
