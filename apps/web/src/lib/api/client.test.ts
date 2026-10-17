// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  REQUEST_ID_HEADER,
  WEB_API_BAD_RESPONSE,
  WEB_API_UNREACHABLE,
  CLINIC_HEADER,
  CSRF_HEADER,
  apiBaseUrl,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  newRequestId,
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

  it("reports missing API_INTERNAL_URL as itself, not as WEB_API_UNREACHABLE", async () => {
    vi.stubEnv("API_INTERNAL_URL", "");
    const fetchImpl = vi.fn<typeof fetch>();

    const failure = await apiGet("/health", { fetchImpl }).catch((error: unknown) => error);

    expect(failure).not.toBeInstanceOf(ApiError);
    expect(String(failure)).toMatch(/API_INTERNAL_URL is not set/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("uses the same origin in the browser, so calls go through the /api rewrite", () => {
    vi.stubGlobal("window", {});
    expect(apiBaseUrl()).toBe("");
  });
});


describe("apiPost", () => {
  const SIGN_IN = "/api/v1/auth/sign-in" as const;
  const REFRESH = "/api/v1/auth/refresh" as const;
  const credentials = { identifier: "owner@sample-clinic.example", password: "x" };

  it("FR-AUTH-01: sends the JSON body and the CSRF header copied from the me_csrf cookie", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    vi.stubGlobal("document", { cookie: "theme=dark; me_csrf=csrf-abc_123; other=1" });
    const fetchImpl = fakeFetch(jsonResponse(200, { user: {}, memberships: [], session: {} }, "r-1"));

    const result = await apiPost(SIGN_IN, credentials, { fetchImpl });

    expect(result.status).toBe(200);
    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(url).toBe(`${API}${SIGN_IN}`);
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(credentials));
    expect(init?.credentials).toBe("same-origin");
    const headers = new Headers(init?.headers);
    expect(headers.get(CSRF_HEADER)).toBe("csrf-abc_123");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("FR-AUTH-01: sends no CSRF header when there is no me_csrf cookie (signed out)", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    vi.stubGlobal("document", { cookie: "theme=dark" });
    const fetchImpl = fakeFetch(jsonResponse(200, { user: {}, memberships: [], session: {} }));

    await apiPost(SIGN_IN, credentials, { fetchImpl });

    expect(new Headers(fetchImpl.mock.calls[0]?.[1]?.headers).has(CSRF_HEADER)).toBe(false);
  });

  it("FR-AUTH-01: a body-less operation sends no body and no Content-Type", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const fetchImpl = fakeFetch(jsonResponse(200, { user: {}, memberships: [], session: {} }));

    await apiPost(REFRESH, undefined, { fetchImpl });

    const init = fetchImpl.mock.calls[0]?.[1];
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });

  it("FR-AUTH-01: sign-out's 204 resolves with no data instead of a bad-response error", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const fetchImpl = fakeFetch(new Response(null, { status: 204, headers: { [REQUEST_ID_HEADER]: "out-1" } }));

    const result = await apiPost("/api/v1/auth/sign-out", undefined, { fetchImpl });

    expect(result).toEqual({ data: undefined, status: 204, requestId: "out-1" });
  });

  it("FR-AUTH-04: Retry-After reaches the ApiError on a locked account", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const locked = jsonResponse(423, {
      error: { code: "AUTH_LOCKED", message: "Account temporarily locked", request_id: "lk-1" },
    });
    locked.headers.set("Retry-After", "840");

    const error = await caught(apiPost(SIGN_IN, credentials, { fetchImpl: fakeFetch(locked) }));

    expect(error.code).toBe("AUTH_LOCKED");
    expect(error.status).toBe(423);
    expect(error.retryAfterSeconds).toBe(840);
  });

  it("FR-AUTH-04: falls back to details.retry_after_seconds when the header is missing", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const locked = jsonResponse(423, {
      error: {
        code: "AUTH_LOCKED",
        message: "Account temporarily locked",
        request_id: "lk-2",
        details: { retry_after_seconds: 120 },
      },
    });

    const error = await caught(apiPost(SIGN_IN, credentials, { fetchImpl: fakeFetch(locked) }));

    expect(error.retryAfterSeconds).toBe(120);
  });

  it("other errors carry no retry hint", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const wrong = jsonResponse(401, {
      error: { code: "AUTH_INVALID_CREDENTIALS", message: "Wrong login details", request_id: "w-1" },
    });

    const error = await caught(apiPost(SIGN_IN, credentials, { fetchImpl: fakeFetch(wrong) }));

    expect(error.retryAfterSeconds).toBeUndefined();
  });

  it("fills and URL-encodes path parameters", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const fetchImpl = fakeFetch(jsonResponse(200, { user: {}, memberships: [], session: {} }));

    await apiPost(
      "/api/v1/auth/invites/{token}/accept",
      { password: "a-long-synthetic-password" },
      { fetchImpl, pathParams: { token: "ab/c d" } },
    );

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(`${API}/api/v1/auth/invites/ab%2Fc%20d/accept`);
  });

  it("fails loudly, not as WEB_API_UNREACHABLE, when a path parameter is missing", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const fetchImpl = vi.fn<typeof fetch>();

    const failure = await apiPost(
      "/api/v1/auth/invites/{token}/accept",
      { password: "a-long-synthetic-password" },
      { fetchImpl },
    ).catch((error: unknown) => error);

    expect(failure).not.toBeInstanceOf(ApiError);
    expect(String(failure)).toMatch(/Missing path parameter "token"/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe("clinic header (spec R6)", () => {
  it("FR-AUTH-03: X-Clinic-ID is sent only when a clinic is given", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const clinicId = "0192f0a0-0000-7000-8000-000000000001";
    const withClinic = fakeFetch(jsonResponse(200, { id: clinicId }));
    const without = fakeFetch(jsonResponse(200, { id: clinicId }));

    await apiGet("/api/v1/clinic", { fetchImpl: withClinic, clinicId });
    await apiGet("/api/v1/clinic", { fetchImpl: without });

    expect(new Headers(withClinic.mock.calls[0]?.[1]?.headers).get(CLINIC_HEADER)).toBe(clinicId);
    expect(new Headers(without.mock.calls[0]?.[1]?.headers).has(CLINIC_HEADER)).toBe(false);
  });

  it("GET requests never carry the CSRF header", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    vi.stubGlobal("document", { cookie: "me_csrf=should-not-be-sent" });
    const fetchImpl = fakeFetch(jsonResponse(200, { status: "ok" }));

    await apiGet("/health", { fetchImpl });

    expect(new Headers(fetchImpl.mock.calls[0]?.[1]?.headers).has(CSRF_HEADER)).toBe(false);
  });
});

describe("apiPut and apiPatch (M2-P5)", () => {
  const PATIENT = "0192f0a0-0000-7000-8000-0000000000c1";
  const patient = { id: PATIENT, code: "SC-0001" };

  it("FR-PAT-05: PUT sends the method, JSON body, CSRF and clinic headers and fills the path", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    vi.stubGlobal("document", { cookie: "me_csrf=csrf-put" });
    const fetchImpl = fakeFetch(jsonResponse(200, patient));

    const result = await apiPut(
      "/api/v1/patients/{patient_id}/consent",
      { whatsapp: true, sms: false },
      { fetchImpl, clinicId: "c-1", pathParams: { patient_id: PATIENT } },
    );

    expect(result.data).toEqual(patient);
    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(url).toBe(`${API}/api/v1/patients/${PATIENT}/consent`);
    expect(init?.method).toBe("PUT");
    expect(init?.body).toBe(JSON.stringify({ whatsapp: true, sms: false }));
    const headers = new Headers(init?.headers);
    expect(headers.get(CSRF_HEADER)).toBe("csrf-put");
    expect(headers.get(CLINIC_HEADER)).toBe("c-1");
  });

  it("FR-PAT-01: PATCH sends the method, the partial body and CSRF", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    vi.stubGlobal("document", { cookie: "me_csrf=csrf-patch" });
    const fetchImpl = fakeFetch(jsonResponse(200, patient));

    await apiPatch("/api/v1/patients/{patient_id}", { full_name: "Sample Name" }, {
      fetchImpl,
      pathParams: { patient_id: PATIENT },
    });

    const init = fetchImpl.mock.calls[0]?.[1];
    expect(init?.method).toBe("PATCH");
    expect(init?.body).toBe(JSON.stringify({ full_name: "Sample Name" }));
    expect(new Headers(init?.headers).get(CSRF_HEADER)).toBe("csrf-patch");
  });

  it("an error on PATCH becomes an ApiError with the API's code and details", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const refused = jsonResponse(422, {
      error: {
        code: "PAT_GUARDIAN_REQUIRED",
        message: "A patient under 18 needs a guardian.",
        request_id: "g-1",
        details: { fields: [{ field: "guardian_name", reason: "required" }] },
      },
    });

    const error = await caught(
      apiPatch("/api/v1/patients/{patient_id}", { guardian_name: "" }, {
        fetchImpl: fakeFetch(refused),
        pathParams: { patient_id: PATIENT },
      }),
    );

    expect(error.code).toBe("PAT_GUARDIAN_REQUIRED");
    expect(error.details).toEqual({ fields: [{ field: "guardian_name", reason: "required" }] });
  });
});

describe("query strings and cancellation (M2-P5)", () => {
  it("FR-PAT-04: encodes query values and leaves undefined ones out", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const fetchImpl = fakeFetch(jsonResponse(200, { items: [] }));

    await apiGet("/api/v1/patients", { fetchImpl, query: { q: "90000 00101&x=1", unused: undefined } });

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(`${API}/api/v1/patients?q=90000+00101%26x%3D1`);
  });

  it("a request the caller cancels rejects with the abort, not WEB_API_UNREACHABLE", async () => {
    vi.stubEnv("API_INTERNAL_URL", API);
    const controller = new AbortController();
    const fetchImpl = vi.fn<typeof fetch>((_input, init) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    });

    const pending = apiGet("/api/v1/patients", { fetchImpl, query: { q: "asha" }, signal: controller.signal });
    controller.abort();
    const failure = await pending.catch((error: unknown) => error);

    expect(failure).not.toBeInstanceOf(ApiError);
    expect((failure as DOMException).name).toBe("AbortError");
  });
});

const realCrypto = globalThis.crypto;

describe("newRequestId", () => {
  const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

  it("NFR-12: is a UUID v4 even where randomUUID is missing (plain HTTP on a non-localhost host)", () => {
    vi.stubGlobal("crypto", { getRandomValues: (array: Uint8Array) => realCrypto.getRandomValues(array) });

    const ids = new Set(Array.from({ length: 50 }, () => newRequestId()));

    expect(ids.size).toBe(50);
    for (const id of ids) expect(id).toMatch(UUID_V4);
  });

  it("uses randomUUID where the browser has it", () => {
    expect(newRequestId()).toMatch(UUID_V4);
  });
});
