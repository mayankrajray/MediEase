import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import { deviceWords } from "@/lib/i18n/push";

import { DevicePush, type PushApi } from "./DevicePush";
import { DEVICE_KEY, keyBytes } from "./push";

/**
 * M7e-E5 (spec web-push R50-R54): the "pop-up alerts on this device" switch, with the browser's
 * push manager and notification permission stubbed (design §7 Q4 A).
 */

const WORDS = deviceWords("en");
const KEY = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM";
const DEVICE = { id: "0192f0a0-0000-7000-8000-00000000d001", label: "Chrome on Android", created_at: "2026-11-13T05:00:00Z", last_success_at: null, active: true };
const ANDROID = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1";

interface Browser {
  permission: NotificationPermission;
  subscription: { toJSON: () => unknown; unsubscribe: ReturnType<typeof vi.fn>; options: { applicationServerKey: ArrayBuffer | null } } | null;
  readonly requestPermission: ReturnType<typeof vi.fn>;
  readonly subscribe: ReturnType<typeof vi.fn>;
}

function fakeSubscription() {
  return {
    toJSON: () => ({ endpoint: "https://fcm.googleapis.com/fcm/send/test-device", expirationTime: null, keys: { p256dh: "BP256", auth: "AUTH" } }),
    unsubscribe: vi.fn(async () => true),
    options: { applicationServerKey: keyBytes(KEY).buffer },
  };
}

function browser(ua = ANDROID): Browser {
  const state: Browser = {
    permission: "default",
    subscription: null,
    requestPermission: vi.fn(async () => {
      state.permission = "granted";
      return "granted";
    }),
    subscribe: vi.fn(async () => {
      state.subscription = fakeSubscription();
      return state.subscription;
    }),
  };
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(ua);
  Object.defineProperty(navigator, "maxTouchPoints", { value: 0, configurable: true });
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
  vi.stubGlobal("PushManager", class {});
  vi.stubGlobal("Notification", {
    get permission() {
      return state.permission;
    },
    requestPermission: state.requestPermission,
  });
  const registration = { pushManager: { getSubscription: vi.fn(async () => state.subscription), subscribe: state.subscribe } };
  Object.defineProperty(navigator, "serviceWorker", { value: { ready: Promise.resolve(registration) }, configurable: true });
  return state;
}

function api(overrides: Partial<PushApi> = {}): PushApi & { [K in keyof PushApi]: ReturnType<typeof vi.fn> } {
  return {
    config: vi.fn(async () => ({ enabled: true, public_key: KEY })),
    list: vi.fn(async () => [DEVICE]),
    add: vi.fn(async () => DEVICE),
    remove: vi.fn(async () => undefined),
    ...overrides,
  } as PushApi & { [K in keyof PushApi]: ReturnType<typeof vi.fn> };
}

function show(calls: PushApi, onSaved = vi.fn()) {
  render(<DevicePush owner="patient" words={WORDS} api={calls} onSessionError={() => false} onSaved={onSaved} />);
  return onSaved;
}

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("pop-up alerts on this device (M7e-E5)", () => {
  it("R50, R51: asks for permission only after Turn on, then saves this browser", async () => {
    const b = browser();
    const calls = api();
    const saved = show(calls);
    await screen.findByText(WORDS.off);
    expect(b.requestPermission).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: WORDS.turnOn }));
    await screen.findByText(WORDS.on);
    expect(b.requestPermission).toHaveBeenCalledTimes(1);
    expect(b.subscribe).toHaveBeenCalledWith({ userVisibleOnly: true, applicationServerKey: keyBytes(KEY) });
    expect(calls.add).toHaveBeenCalledWith({
      endpoint: "https://fcm.googleapis.com/fcm/send/test-device",
      expirationTime: null,
      keys: { p256dh: "BP256", auth: "AUTH" },
    });
    expect(JSON.parse(window.localStorage.getItem(DEVICE_KEY) ?? "{}")).toEqual({ id: DEVICE.id, owner: "patient" });
    expect(saved).toHaveBeenCalledWith(WORDS.turnedOn);
  });

  it("R54: shows on when the server still lists this browser, and Turn off forgets it everywhere", async () => {
    const b = browser();
    b.permission = "granted";
    b.subscription = fakeSubscription();
    window.localStorage.setItem(DEVICE_KEY, JSON.stringify({ id: DEVICE.id, owner: "patient" }));
    const calls = api();
    show(calls);
    await screen.findByText(WORDS.on);
    fireEvent.click(screen.getByRole("button", { name: WORDS.turnOff }));
    await screen.findByText(WORDS.off);
    expect(calls.remove).toHaveBeenCalledWith(DEVICE.id);
    expect(b.subscription?.unsubscribe).toHaveBeenCalled();
    expect(window.localStorage.getItem(DEVICE_KEY)).toBeNull();
  });

  it("R54: shows off when the device expired, moved to someone else, or is another person's here", async () => {
    const b = browser();
    b.permission = "granted";
    b.subscription = fakeSubscription();
    window.localStorage.setItem(DEVICE_KEY, JSON.stringify({ id: DEVICE.id, owner: "patient" }));
    show(api({ list: vi.fn(async () => [{ ...DEVICE, active: false }]) }));
    await screen.findByText(WORDS.off);
    expect(window.localStorage.getItem(DEVICE_KEY)).toBeNull();
  });

  it("R52: a browser that blocks alerts says how to allow them, with no switch", async () => {
    const b = browser();
    b.permission = "denied";
    show(api());
    await screen.findByText(WORDS.blocked);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("R52: refusing the permission prompt explains it too", async () => {
    const b = browser();
    b.requestPermission.mockImplementationOnce(async () => {
      b.permission = "denied";
      return "denied";
    });
    const calls = api();
    show(calls);
    fireEvent.click(await screen.findByRole("button", { name: WORDS.turnOn }));
    await screen.findByText(WORDS.blocked);
    expect(calls.add).not.toHaveBeenCalled();
  });

  it("R52: an iPhone outside the installed app is told to add it to the Home Screen first", async () => {
    browser(IPHONE);
    const calls = api();
    show(calls);
    await screen.findByText(WORDS.iosInstall);
    expect(calls.config).not.toHaveBeenCalled();
  });

  it("R52: a browser without push, or a server without a key, offers nothing", async () => {
    browser();
    vi.stubGlobal("PushManager", undefined);
    // jsdom: deleting the stub's property is how "not in window" looks.
    delete (window as { PushManager?: unknown }).PushManager;
    const { unmount } = render(<DevicePush owner="staff" words={WORDS} api={api()} onSessionError={() => false} onSaved={vi.fn()} />);
    await screen.findByText(WORDS.unsupported);
    unmount();
    browser();
    show(api({ config: vi.fn(async () => ({ enabled: false, public_key: null })) }));
    await screen.findByText(WORDS.notOffered);
  });

  it("R52: a browser that cannot subscribe says what to check, and a refused one is 'blocked'", async () => {
    const b = browser();
    b.subscribe.mockRejectedValueOnce(Object.assign(new Error("push service error"), { name: "AbortError" }));
    const calls = api();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    show(calls);
    fireEvent.click(await screen.findByRole("button", { name: WORDS.turnOn }));
    await screen.findByText(WORDS.failed);
    expect(calls.add).not.toHaveBeenCalled();
    expect(screen.getByText(WORDS.off)).toBeTruthy();

    b.subscribe.mockRejectedValueOnce(Object.assign(new Error("denied"), { name: "NotAllowedError" }));
    fireEvent.click(screen.getByRole("button", { name: WORDS.turnOn }));
    await screen.findByText(WORDS.blocked);
  });

  it("R19: ten devices already says so in plain words", async () => {
    browser();
    show(api({ add: vi.fn(async () => Promise.reject(new ApiError("PSH_TOO_MANY_DEVICES", "Too many", 409, "rid", {}))) }));
    fireEvent.click(await screen.findByRole("button", { name: WORDS.turnOn }));
    await screen.findByText(WORDS.tooMany);
    await waitFor(() => expect(screen.getByText(WORDS.off)).toBeTruthy());
  });
});
