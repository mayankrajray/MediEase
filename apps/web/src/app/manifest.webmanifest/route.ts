import { webManifest } from "@/lib/pwa/manifest";

/**
 * M7e-E1: `/manifest.webmanifest`. A route rather than Next's `app/manifest.ts`, which would link
 * the manifest from every page, including the landing page that has no room for it (NFR-02);
 * the staff and portal layouts link it instead (`PWA_METADATA`).
 */
export function GET(): Response {
  return new Response(JSON.stringify(webManifest()), {
    headers: { "Content-Type": "application/manifest+json; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
