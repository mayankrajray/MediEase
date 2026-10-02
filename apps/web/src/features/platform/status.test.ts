// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { REQUEST_ID_HEADER } from "@/lib/api/client";

import { getPlatformStatus } from "./status";

type Reply = Response | Error;

/** A fetch that answers per path and records the request ID of every call. */
function apiStub(replies: Record<"/health" | "/ready", Reply>) {
  const sentIds: string[] = [];
  const fetchImpl = vi.fn<typeof fetch>(async (input, init) => {
    sentIds.push(new Headers(init?.headers).get(REQUEST_ID_HEADER) ?? "");
    const path = new URL(String(input)).pathname as "/health" | "/ready";
    const reply = replies[path];
    if (reply instanceof Error) throw reply;
    return reply.clone();
  });
  return { fetchImpl, sentIds };
}

const json = (status: number, body: unknown, id: string) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", [REQUEST_ID_HEADER]: id },
  });

describe("getPlatformStatus", () => {
  it("NFR-12: healthy when /health and /ready both succeed, with one request ID for both", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const { fetchImpl, sentIds } = apiStub({
      "/health": json(200, { status: "ok" }, "ref-1"),
      "/ready": json(200, { status: "ready", checks: { database: "ok" } }, "ref-1"),
    });

    const status = await getPlatformStatus(fetchImpl);

    expect(status).toEqual({ state: "healthy", requestId: "ref-1" });
    expect(new Set(sentIds).size).toBe(1);
  });

  it("NFR-12: degraded with the API's code when the database is not ready", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const envelope = {
      error: {
        code: "READY_DB_UNAVAILABLE",
        message: "The database is not reachable.",
        request_id: "ref-2",
        details: {},
      },
    };
    const { fetchImpl } = apiStub({
      "/health": json(200, { status: "ok" }, "ref-2"),
      "/ready": json(503, envelope, "ref-2"),
    });

    expect(await getPlatformStatus(fetchImpl)).toEqual({
      state: "degraded",
      requestId: "ref-2",
      code: "READY_DB_UNAVAILABLE",
      message: "The database is not reachable.",
    });
  });

  it("NFR-12: down with WEB_API_UNREACHABLE when the API does not answer", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const { fetchImpl, sentIds } = apiStub({
      "/health": new TypeError("fetch failed"),
      "/ready": new TypeError("fetch failed"),
    });

    const status = await getPlatformStatus(fetchImpl);

    expect(status.state).toBe("down");
    expect(status).toMatchObject({ code: "WEB_API_UNREACHABLE", requestId: sentIds[0] });
    expect(fetchImpl).toHaveBeenCalledTimes(1); // /ready is not tried once /health failed
  });

  it("down, not degraded, when the API disappears between /health and /ready", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const { fetchImpl } = apiStub({
      "/health": json(200, { status: "ok" }, "ref-4"),
      "/ready": new TypeError("fetch failed"),
    });

    expect(await getPlatformStatus(fetchImpl)).toMatchObject({
      state: "down",
      code: "WEB_API_UNREACHABLE",
    });
  });

  it("does not hide configuration errors as an API outage", async () => {
    vi.stubEnv("API_INTERNAL_URL", "");
    await expect(getPlatformStatus(vi.fn<typeof fetch>())).rejects.toThrow(/API_INTERNAL_URL/);
  });
});
