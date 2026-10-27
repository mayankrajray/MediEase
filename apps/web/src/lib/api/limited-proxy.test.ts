// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

import { NextRequest } from "next/server";

import { POST as importPost } from "@/app/api/v1/ops/clinics/[clinicId]/patient-imports/route";
import { POST as uploadPost } from "@/app/api/v1/portal/prescription-uploads/route";

import { MAX_IMPORT_BYTES, MAX_UPLOAD_REQUEST_BYTES } from "./limited-proxy";

const ORIGIN = "https://clinic.example.test";

function upload(body: BodyInit, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`${ORIGIN}/api/v1/portal/prescription-uploads`, {
    method: "POST",
    body,
    headers: { "Content-Type": "multipart/form-data; boundary=x", ...headers },
    duplex: "half",
  });
}

function stream(total: number, chunk = 64 * 1024): ReadableStream<Uint8Array> {
  let sent = 0;
  return new ReadableStream({
    pull(controller) {
      if (sent >= total) {
        controller.close();
        return;
      }
      const size = Math.min(chunk, total - sent);
      sent += size;
      controller.enqueue(new Uint8Array(size));
    },
  });
}

function api(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fetchMock = vi.fn<typeof fetch>(
    async () =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("the size-checked upload proxy (issue #30, prescription-uploads R3)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("#30: a declared Content-Length over the limit is the API's 413 envelope, and the API is not called", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const fetchMock = api(500, {});
    const response = await uploadPost(
      upload(new Uint8Array(16), { "Content-Length": String(MAX_UPLOAD_REQUEST_BYTES + 1) }),
    );
    expect(response.status).toBe(413);
    const body = (await response.json()) as { error: { code: string; request_id: string } };
    expect(body.error.code).toBe("REQ_REQUEST_ENTITY_TOO_LARGE");
    expect(body.error.request_id).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("#30: a streamed body with no length is cut off once it passes the limit", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const fetchMock = api(500, {});
    const response = await uploadPost(upload(stream(MAX_UPLOAD_REQUEST_BYTES + 100 * 1024)));
    expect(response.status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a body within the limit goes to the API with the session, CSRF and request ID; the answer comes back", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const fetchMock = api(202, { id: "u1", state: "QUARANTINED" }, { "Cache-Control": "no-store" });
    const response = await uploadPost(
      upload(new Uint8Array(1024), {
        Cookie: "me_pt_access=a; me_pt_csrf=c",
        "X-CSRF-Token": "c",
        "X-Request-ID": "req-1",
        "X-Not-For-The-Api": "dropped",
      }),
    );
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ id: "u1", state: "QUARANTINED" });
    expect(response.headers.get("cache-control")).toBe("no-store");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("http://api:8000/api/v1/portal/prescription-uploads");
    const sent = new Headers(init?.headers);
    expect(sent.get("cookie")).toBe("me_pt_access=a; me_pt_csrf=c");
    expect(sent.get("x-csrf-token")).toBe("c");
    expect(sent.get("x-request-id")).toBe("req-1");
    expect(sent.get("content-type")).toContain("multipart/form-data");
    expect(sent.get("x-not-for-the-api")).toBeNull();
    expect((init?.body as Uint8Array).byteLength).toBe(1024);
  });

  it("the API's own errors pass through, Retry-After included", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    api(429, { error: { code: "UPL_RATE_LIMITED", message: "x", request_id: "r", details: {} } }, { "Retry-After": "120" });
    const response = await uploadPost(upload(new Uint8Array(8)));
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("120");
  });

  it("an unreachable API is WEB_API_UNREACHABLE (503), not a 500", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Promise.reject(new TypeError("down"))));
    const response = await uploadPost(upload(new Uint8Array(8)));
    expect(response.status).toBe(503);
    expect(((await response.json()) as { error: { code: string } }).error.code).toBe("WEB_API_UNREACHABLE");
  });

  it("#30: the ops import over 2 MB is 413; under it the query goes on to the API", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const params = { params: Promise.resolve({ clinicId: "c-1" }) };
    const csv = (size: number) =>
      new NextRequest(`${ORIGIN}/api/v1/ops/clinics/c-1/patient-imports?dry_run=false`, {
        method: "POST",
        body: new Uint8Array(size),
        headers: { "Content-Type": "text/csv" },
      });
    const fetchMock = api(200, { created: 0 });
    expect((await importPost(csv(MAX_IMPORT_BYTES + 1), params)).status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
    expect((await importPost(csv(100), params)).status).toBe(200);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      "http://api:8000/api/v1/ops/clinics/c-1/patient-imports?dry_run=false",
    );
  });
});
