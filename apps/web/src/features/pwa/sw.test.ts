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

interface FakeWindow {
  readonly url: string;
  readonly navigate: (url: string) => Promise<FakeWindow | null>;
  readonly focus: () => Promise<FakeWindow>;
}

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
    clients: {
      claim: vi.fn(async () => undefined),
      matchAll: vi.fn(async (): Promise<FakeWindow[]> => []),
      openWindow: vi.fn<(url: string) => Promise<null>>(async () => null),
    },
    registration: { showNotification: vi.fn<(title: string, options: Record<string, unknown>) => Promise<void>>(async () => undefined) },
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
  async function fire(type: "push" | "notificationclick", event: Record<string, unknown>): Promise<void> {
    let work: Promise<unknown> = Promise.resolve();
    listeners.get(type)?.({ ...event, waitUntil: (p: Promise<unknown>) => (work = p) });
    await work;
  }
  return { listeners, stores, network, self, fetchEvent, lifecycle, stored, fire };
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

describe("pop-up alerts (M7e-E5, spec web-push R55-R57)", () => {
  let sw: ReturnType<typeof load>;
  beforeEach(() => {
    sw = load();
  });

  const pushed = (payload: unknown) => ({
    data: {
      json: () => {
        if (typeof payload === "string") throw new SyntaxError("not JSON");
        return payload;
      },
    },
  });

  it("shows exactly the server's words, with the app icon and the notice's path", async () => {
    await sw.fire(
      "push",
      pushed({ title: "Appointment reminder", body: "You have an upcoming appointment. Open MediEase to see it.", url: "/portal/appointments", tag: "appointment.reminder" }),
    );
    expect(sw.self.registration.showNotification).toHaveBeenCalledWith("Appointment reminder", {
      body: "You have an upcoming appointment. Open MediEase to see it.",
      icon: "/icons/icon-192.png",
      data: { url: "/portal/appointments" },
      tag: "appointment.reminder",
      renotify: true,
    });
  });

  it("still shows a plain alert for a message that is not the expected JSON", async () => {
    for (const payload of ["garbage", null, 42, { title: "", body: 7 }]) await sw.fire("push", pushed(payload));
    await sw.fire("push", { data: null });
    expect(sw.self.registration.showNotification).toHaveBeenCalledTimes(5);
    for (const [title, options] of sw.self.registration.showNotification.mock.calls) {
      expect(title).toBe("MediEase");
      expect(options).toEqual({ body: "Open MediEase to see it.", icon: "/icons/icon-192.png", data: { url: "/" } });
    }
  });

  it("never keeps a link to another site, whatever the message says", async () => {
    for (const url of ["https://evil.example/x", "//evil.example/x", "/\\evil.example", "javascript:alert(1)", 5]) {
      await sw.fire("push", pushed({ title: "MediEase", body: "x", url }));
    }
    const urls = sw.self.registration.showNotification.mock.calls.map(([, o]) => (o.data as { url: string }).url);
    expect(urls).toEqual(["/", "/", "/", "/", "/"]);
  });

  it("opens the notice's page in a new window when MediEase is not open", async () => {
    const close = vi.fn();
    await sw.fire("notificationclick", { notification: { data: { url: "/portal/appointments?x=1" }, close } });
    expect(close).toHaveBeenCalled();
    expect(sw.self.clients.openWindow).toHaveBeenCalledWith("/portal/appointments?x=1");
  });

  it("reuses an open MediEase window, and leaves other sites' windows alone", async () => {
    const focus = vi.fn(async () => mine);
    const mine: FakeWindow = { url: `${ORIGIN}/today`, navigate: vi.fn(async () => mine), focus };
    const other: FakeWindow = { url: "https://other.example/", navigate: vi.fn(async () => other), focus: vi.fn(async () => other) };
    sw.self.clients.matchAll.mockResolvedValueOnce([other, mine]);
    await sw.fire("notificationclick", { notification: { data: { url: "/booking-requests" }, close: vi.fn() } });
    expect(other.navigate).not.toHaveBeenCalled();
    expect(mine.navigate).toHaveBeenCalledWith("/booking-requests");
    expect(focus).toHaveBeenCalled();
    expect(sw.self.clients.openWindow).not.toHaveBeenCalled();
  });

  it("opens a new window when the open one cannot be steered, and goes home for a bad link", async () => {
    const stuck: FakeWindow = {
      url: `${ORIGIN}/portal`,
      navigate: vi.fn(async () => {
        throw new TypeError("not controlled");
      }),
      focus: vi.fn(async () => stuck),
    };
    sw.self.clients.matchAll.mockResolvedValueOnce([stuck]);
    await sw.fire("notificationclick", { notification: { data: { url: "https://evil.example/" }, close: vi.fn() } });
    expect(sw.self.clients.openWindow).toHaveBeenCalledWith("/");
  });
});
