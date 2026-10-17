// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

import { NextRequest } from "next/server";

import { POST } from "./route";

const TOKEN = "AQFkZXY.claims.mac";

function post(digits: string, lang = "hi"): NextRequest {
  const body = new URLSearchParams({ phone_last4: digits, lang });
  return new NextRequest(`https://clinic.example.test/p/${TOKEN}/verify`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
}

function api(status: number, body: unknown) {
  const fetchMock = vi.fn<typeof fetch>(async () =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const params = { params: Promise.resolve({ token: TOKEN }) };

describe("the last-4 form's route handler (M4-P5, spec R10, decision 3A)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("R10: the right digits set an HttpOnly cookie scoped to this link and redirect with a 303", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const fetchMock = api(200, { view_token: "view.token.mac", view_expires_at: "2026-10-19T05:30:00+00:00" });
    const response = await POST(post("3210"), params);

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(`/p/${TOKEN}?lang=hi`);
    const cookie = response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("me_rx_view=view.token.mac");
    expect(cookie).toContain(`Path=/p/${TOKEN}`);
    expect(cookie).toMatch(/HttpOnly/i);
    expect(cookie).toMatch(/Secure/i); // the request was https
    expect(cookie).toMatch(/SameSite=lax/i);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe(`http://api:8000/api/v1/public/links/${TOKEN}/verify`);
    expect(JSON.parse(String(init?.body))).toEqual({ phone_last4: "3210" });
  });

  it("R10: wrong digits go back with the attempts left, never the digits", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    api(401, { error: { code: "LINK_CHALLENGE_FAILED", message: "no", details: { attempts_left: "3" }, request_id: "r" } });
    const response = await POST(post("0000", "en"), params);
    const location = response.headers.get("location") ?? "";
    expect(response.status).toBe(303);
    expect(location).toBe(`/p/${TOKEN}?lang=en&e=failed&left=3`);
    expect(location).not.toContain("0000");
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it.each([
    ["LINK_LOCKED", 423, "locked"],
    ["LINK_RATE_LIMITED", 429, "rate"],
    ["LINK_INVALID", 404, "invalid"],
    ["LINK_EXPIRED", 410, "expired"],
  ])("AC3: %s goes back as e=%s", async (code, status, problem) => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    api(status, { error: { code, message: "x", details: {}, request_id: "r" } });
    const response = await POST(post("3210"), params);
    expect(new URL(response.headers.get("location") ?? "", "http://x").searchParams.get("e")).toBe(problem);
  });

  it("an unreachable API is 'unavailable'", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Promise.reject(new TypeError("down"))));
    const response = await POST(post("3210"), params);
    expect(new URL(response.headers.get("location") ?? "", "http://x").searchParams.get("e")).toBe("unavailable");
  });
});
