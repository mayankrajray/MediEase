/**
 * Liveness for the web server itself: "is this Next.js process serving?".
 *
 * Deliberately calls nothing else. The container healthcheck hits it every few
 * seconds, so it must not touch the API (no log noise there, and a web process
 * that is fine must not look dead because the API is). Whether the whole
 * system works is what /status shows.
 */

export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}
