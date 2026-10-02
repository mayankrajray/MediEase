// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  REQUEST_ID_HEADER,
  WEB_API_BAD_RESPONSE,
  WEB_API_UNREACHABLE,
  apiBaseUrl,
  apiGet,
} from "./client";

const API = "http://api.internal:8000";

function jsonResponse(status: number, body: unknown, requestId?: string): Response {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (requestId) headers.set(REQUEST_ID_HEADER, requestId);
  return new Response(JSON.stringify(body), { status, headers });
}

function fakeFetch(response: Response) {
  return vi.fn<typeof fetch>().mockResolvedValue(response);
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected an ApiError");
}

describe("apiGet", () => {
  it("NFR-12: sends X-Request-ID to API_INTERNAL_URL and returns the echoed ID", async () => {
    vi.stubEnv("API_INTERNAL_URL", `${API}/`);
    const fetchImpl = fakeFetch(jsonResponse(200, { status: "ok" }, "echoed-1"));

    const result = await apiGet("/health", { requestId: "sent-1", fetchImpl });

    expect(result).toEqual({ data: { status: "ok" }, status: 200, requestId: "echoed-1" });
    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(url).toBe(`${API}/health`);
    const headers = new Headers(init?.headers);
    expect(headers.get(REQUEST_ID_HEADER)).toBe("sent-1");
    expect(headers.get("Accept")).toBe("application/json");
    expect(init?.cache).toBe("no-store");
  });

  it("NFR-12: generates a request ID when none is given", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const fetchImpl = fakeFetch(jsonResponse(200, { status: "ok" }));

    const result = await apiGet("/health", { fetchImpl });

    const sent = new Headers(fetchImpl.mock.calls[0]?.[1]?.headers).get(REQUEST_ID_HEADER);
    expect(sent).toMatch(/^[0-9a-f-]{36}$/);
    expect(result.requestId).toBe(sent); // API echoed nothing, so ours is kept
  });

  it("NFR-12: turns the error envelope into an ApiError with the API's code and ID", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const envelope = {
      error: {
        code: "READY_DB_UNAVAILABLE",
        message: "The database is not reachable.",
        request_id: "api-ref-9",
        details: {},
      },
    };

    const error = await caught(
      apiGet("/ready", { fetchImpl: fakeFetch(jsonResponse(503, envelope, "api-ref-9")) }),
    );

    expect(error.code).toBe("READY_DB_UNAVAILABLE");
    expect(error.message).toBe("The database is not reachable.");
    expect(error.status).toBe(503);
    expect(error.requestId).toBe("api-ref-9");
  });

  it("NFR-12: a network failure is WEB_API_UNREACHABLE with our request ID", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed"));

    const error = await caught(apiGet("/health", { requestId: "ours-1", fetchImpl }));

    expect(error.code).toBe(WEB_API_UNREACHABLE);
    expect(error.status).toBe(0);
    expect(error.requestId).toBe("ours-1");
    expect(error.details).toEqual({ reason: "network" });
  });

  it("NFR-12: a slow API is WEB_API_UNREACHABLE with reason timeout", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const neverAnswers = vi.fn<typeof fetch>(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
        }),
    );

    const error = await caught(apiGet("/health", { fetchImpl: neverAnswers, timeoutMs: 20 }));

    expect(error.code).toBe(WEB_API_UNREACHABLE);
    expect(error.details).toEqual({ reason: "timeout" });
  });

  it("NFR-12: a non-envelope error body (e.g. a proxy's HTML 502) is WEB_API_BAD_RESPONSE", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const html = new Response("<html>Bad Gateway</html>", { status: 502 });

    const error = await caught(apiGet("/ready", { fetchImpl: fakeFetch(html) }));

    expect(error.code).toBe(WEB_API_BAD_RESPONSE);
    expect(error.status).toBe(502);
  });

  it("NFR-12: a 200 without a JSON body is WEB_API_BAD_RESPONSE", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const empty = new Response("", { status: 200 });

    const error = await caught(apiGet("/health", { fetchImpl: fakeFetch(empty) }));

    expect(error.code).toBe(WEB_API_BAD_RESPONSE);
  });
});

describe("apiBaseUrl", () => {
  it("fails clearly on the server when API_INTERNAL_URL is missing", () => {
    vi.stubEnv("API_INTERNAL_URL", "");
    expect(() => apiBaseUrl()).toThrow(/API_INTERNAL_URL is not set/);
  });

  it("uses the same origin in the browser, so calls go through the /api rewrite", () => {
    vi.stubGlobal("window", {});
    expect(apiBaseUrl()).toBe("");
  });
});
