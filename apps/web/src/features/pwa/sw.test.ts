// @vitest-environment node
import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";

import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * M7e-E1 (design §3 E1, §5): the cache rules of the real `public/sw.js`, loaded into a sandbox
 * with fake caches and a fake network. The rule that matters most: no API answer and no page is
 * ever stored, so nothing about a patient can be read from this device's cache.
 */

const ORIGIN = "https://app.mediease.test";
const SOURCE = readFileSync(path.resolve(import.meta.dirname, "../../../public/sw.js"), "utf8");

interface FakeResponse {
  readonly ok: boolean;
  readonly type: string;
  readonly body: string;
  clone(): FakeResponse;
}

function answer(body: string, init: { ok?: boolean; type?: string } = {}): FakeResponse {
  const response: FakeResponse = { ok: init.ok ?? true, type: init.type ?? "basic", body, clone: () => response };
  return response;
}

interface FakeRequest {
  readonly url: string;
  readonly method: string;
  readonly mode: string;
}

const req = (p: string, init: Partial<FakeRequest> = {}): FakeRequest => ({
  url: p.startsWith("http") ? p : `${ORIGIN}${p}`,
  method: "GET",
  mode: "cors",
  ...init,
});

type Listener = (event: Record<string, unknown>) => void;

function load() {
  const listeners = new Map<string, Listener>();
  const stores = new Map<string, Map<string, FakeResponse>>();
  const keyOf = (r: FakeRequest | string) => (typeof r === "string" ? new URL(r, ORIGIN).href : r.url);
  const open = (name: string) => {
    const store = stores.get(name) ?? new Map<string, FakeResponse>();
    stores.set(name, store);
    return {
      match: async (r: FakeRequest | string) => store.get(keyOf(r)),
      put: async (r: FakeRequest | string, response: FakeResponse) => void store.set(keyOf(r), response),
      addAll: async (urls: string[]) => {
        for (const u of urls) store.set(keyOf(u), answer(`precached ${u}`));
      },
    };
  };
  const caches = {
    open: async (name: string) => open(name),
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    match: async (r: FakeRequest | string) => {
      for (const store of stores.values()) {
        const hit = store.get(keyOf(r));
        if (hit !== undefined) return hit;
      }
      return undefined;
    },
  };
  const network = vi.fn<(r: FakeRequest) => Promise<FakeResponse>>(async (r) => answer(`network ${r.url}`));
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, fn: Listener) => listeners.set(type, fn),
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn(async () => undefined) },
  };
  runInNewContext(SOURCE, { self, caches, fetch: network, URL, Response: { error: () => answer("error", { ok: false, type: "error" }) }, Promise });

  async function fetchEvent(request: FakeRequest): Promise<FakeResponse | undefined> {
    let responded: Promise<FakeResponse> | undefined;
    listeners.get("fetch")?.({ request, respondWith: (p: Promise<FakeResponse>) => (responded = p) });
    return responded === undefined ? undefined : await responded;
  }
  async function lifecycle(type: "install" | "activate"): Promise<void> {
    let work: Promise<unknown> = Promise.resolve();
    listeners.get(type)?.({ waitUntil: (p: Promise<unknown>) => (work = p) });
    await work;
  }
  const stored = () => [...stores.values()].flatMap((s) => [...s.keys()].map((k) => new URL(k).pathname));
  return { listeners, stores, network, self, fetchEvent, lifecycle, stored };
}

describe("the service worker's cache rules (M7e-E1)", () => {
  let sw: ReturnType<typeof load>;
  beforeEach(async () => {
    sw = load();
    await sw.lifecycle("install");
  });

  it("precaches only the offline page and the logo it shows", () => {
    expect(sw.stored().sort()).toEqual(["/brand/mediease-icon.svg", "/offline.html"]);
  });

  it("never touches an API call: the browser sends it as if there were no service worker", async () => {
    for (const p of ["/api/v1/portal/me", "/api/v1/portal/appointments", "/api/v1/auth/refresh"]) {
      expect(await sw.fetchEvent(req(p))).toBeUndefined();
      expect(await sw.fetchEvent(req(p, { method: "POST" }))).toBeUndefined();
    }
    expect(sw.network).not.toHaveBeenCalled();
  });

  it("fetches every page from the network and stores none of them", async () => {
    for (const p of ["/portal", "/portal/prescriptions/x", "/p/AQ.token", "/c/sample-clinic", "/today"]) {
      const response = await sw.fetchEvent(req(p, { mode: "navigate" }));
      expect(response?.body).toBe(`network ${ORIGIN}${p}`);
    }
    expect(sw.stored()).not.toEqual(expect.arrayContaining(["/portal"]));
    expect(sw.stored().every((p) => /^\/(offline\.html|icons\/|brand\/)/.test(p))).toBe(true);
  });

  it("shows the offline page when a page cannot load, and sends or queues nothing", async () => {
    sw.network.mockRejectedValueOnce(new TypeError("offline"));
    const response = await sw.fetchEvent(req("/portal/appointments", { mode: "navigate" }));
    expect(response?.body).toBe("precached /offline.html");
    expect(sw.network).toHaveBeenCalledTimes(1);
  });

  it("serves build assets, logos and icons from the cache after the first fetch", async () => {
    const asset = req("/_next/static/chunks/app-1a2b.js");
    expect((await sw.fetchEvent(asset))?.body).toBe(`network ${asset.url}`);
    expect((await sw.fetchEvent(asset))?.body).toBe(`network ${asset.url}`);
    expect(sw.network).toHaveBeenCalledTimes(1);
    expect(sw.stored()).toContain("/_next/static/chunks/app-1a2b.js");
  });

  it("keeps no error or redirected answer for an asset", async () => {
    sw.network.mockResolvedValueOnce(answer("not found", { ok: false }));
    await sw.fetchEvent(req("/_next/static/missing.js"));
    sw.network.mockResolvedValueOnce(answer("opaque", { type: "opaqueredirect" }));
    await sw.fetchEvent(req("/brand/moved.svg"));
    expect(sw.stored()).not.toEqual(expect.arrayContaining(["/_next/static/missing.js", "/brand/moved.svg"]));
  });

  it("leaves other sites alone, even under a static-looking path", async () => {
    expect(await sw.fetchEvent(req("https://cdn.example.com/_next/static/x.js"))).toBeUndefined();
    expect(await sw.fetchEvent(req("https://evil.example/portal", { mode: "navigate" }))).toBeUndefined();
  });

  it("removes old MediEase caches on activate and takes over open pages", async () => {
    sw.stores.set("mediease-static-v0", new Map());
    sw.stores.set("someone-else", new Map());
    await sw.lifecycle("activate");
    expect([...sw.stores.keys()].sort()).toEqual(["mediease-static-v1", "someone-else"]);
    expect(sw.self.clients.claim).toHaveBeenCalled();
  });

  it("waits for the person's Update before a new version takes over", () => {
    const message = sw.listeners.get("message");
    message?.({ data: { type: "something else" } });
    message?.({ data: null });
    expect(sw.self.skipWaiting).not.toHaveBeenCalled();
    message?.({ data: { type: "SKIP_WAITING" } });
    expect(sw.self.skipWaiting).toHaveBeenCalledTimes(1);
  });
});
