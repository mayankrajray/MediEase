/** Test helpers: a fake API behind `fetch`, speaking the contract's shapes. */

import { vi } from "vitest";

export interface Recorded {
  readonly method: string;
  readonly path: string;
  readonly headers: Headers;
  readonly body: unknown;
}

export type Route = (call: Recorded) => Response | Promise<Response>;

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Request-ID": "test-ref", ...headers },
  });
}

export function noContent(): Response {
  return new Response(null, { status: 204, headers: { "X-Request-ID": "test-ref" } });
}

export function apiError(
  status: number,
  code: string,
  message: string,
  headers: Record<string, string> = {},
  details: Record<string, unknown> = {},
): Response {
  return json(status, { error: { code, message, request_id: "test-ref", details } }, headers);
}

/**
 * Replaces `fetch` with a router keyed by "METHOD /path". A route may be a
 * function (called each time) or a list of responses used in order (the last
 * repeats). An unrouted call fails the test loudly.
 */
export function mockApi(routes: Record<string, Route | readonly (() => Response)[]>) {
  const calls: Recorded[] = [];
  const counters = new Map<string, number>();

  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const key = `${method} ${url.pathname}`;
    const rawBody = init?.body;
    const call: Recorded = {
      method,
      path: url.pathname,
      headers: new Headers(init?.headers),
      body: typeof rawBody === "string" ? (JSON.parse(rawBody) as unknown) : undefined,
    };
    calls.push(call);

    const route = routes[key];
    if (route === undefined) {
      throw new Error(`Unrouted API call in test: ${key}`);
    }
    if (typeof route === "function") {
      return route(call);
    }
    const index = counters.get(key) ?? 0;
    counters.set(key, index + 1);
    const respond = route[Math.min(index, route.length - 1)];
    if (respond === undefined) {
      throw new Error(`No responses listed for ${key}`);
    }
    return respond();
  });
  vi.stubGlobal("fetch", fetchMock);

  return {
    calls,
    count: (key: string) => calls.filter((c) => `${c.method} ${c.path}` === key).length,
    fetchMock,
  };
}

/** Lets pending promise callbacks and React state updates run. */
export const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
