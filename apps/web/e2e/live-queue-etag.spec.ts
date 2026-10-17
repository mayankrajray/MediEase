/**
 * M3-P4 (FR-QUE-03, spec R12): the live queue's ETag survives the web origin's proxy.
 *
 * Screens poll `/api/v1/queue` through the web app's own origin (next.config rewrites it to
 * the API), so the `ETag` and `If-None-Match` headers must pass through both ways: a repeat
 * request with the tag is a bodiless 304. Uses `make seed` data only (the front desk of
 * sample-clinic); it changes nothing.
 */

import { expect, test } from "@playwright/test";

const DESK = "desk@sample-clinic.example";
const PASSWORD = process.env.E2E_PASSWORD ?? "MediEase-demo-2026";

test("R12: an unchanged queue is a 304 through the web origin", async ({ request }) => {
  const signIn = await request.post("/api/v1/auth/sign-in", {
    data: { identifier: DESK, password: PASSWORD },
  });
  expect(signIn.status()).toBe(200);

  const first = await request.get("/api/v1/queue");
  expect(first.status()).toBe(200);
  const etag = first.headers()["etag"];
  expect(etag).toMatch(/^"[0-9a-f]{32}"$/);
  expect(first.headers()["cache-control"]).toBe("no-store");

  const again = await request.get("/api/v1/queue", { headers: { "If-None-Match": etag ?? "" } });
  expect(again.status()).toBe(304);
  expect(again.headers()["etag"]).toBe(etag);
  expect(await again.body()).toHaveLength(0);
});
