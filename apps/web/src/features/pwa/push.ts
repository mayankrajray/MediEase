/**
 * M7e-E5 (spec web-push R50-R55): this browser's web push, for a patient or a staff member.
 *
 * The browser keeps one push subscription for the whole site (the service worker's scope `/`),
 * so one device belongs to one person at a time (R14): turning push on here moves the device to
 * whoever is signed in. The device's ID is remembered in `localStorage` with its owner, so the
 * switch can show "on" without asking the browser for permission again; the server's list of
 * the person's devices is the truth (a device the push service expired shows as off).
 */

import type { components } from "@/lib/api/schema";

export type PushDevice = components["schemas"]["PushDevice"];
export type PushSubscriptionIn = components["schemas"]["PushSubscriptionIn"];
export type Owner = "patient" | "staff";

/** Where this browser stands, before anyone presses anything. */
export type Support =
  | "supported"
  // No service worker, no push manager, no notifications, or not https.
  | "unsupported"
  // iPhone and iPad deliver web push only to the app added to the Home Screen (iOS 16.4+).
  | "ios-install";

export const DEVICE_KEY = "me_push_device";
const READY_TIMEOUT_MS = 5000;

interface Stored {
  readonly id: string;
  readonly owner: Owner;
}

export function pushSupport(): Support {
  if (typeof window === "undefined") return "unsupported";
  const nav = navigator as Navigator & { standalone?: boolean };
  const ios = /iPhone|iPad|iPod/.test(nav.userAgent) || (/Macintosh/.test(nav.userAgent) && nav.maxTouchPoints > 1);
  const standalone = nav.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
  if (ios && !standalone) return "ios-install";
  const capable = window.isSecureContext && "serviceWorker" in nav && "PushManager" in window && "Notification" in window;
  return capable ? "supported" : "unsupported";
}

export function permission(): NotificationPermission {
  return typeof Notification === "undefined" ? "denied" : Notification.permission;
}

export function storedDevice(owner: Owner): string | null {
  try {
    const raw = window.localStorage.getItem(DEVICE_KEY);
    if (raw === null) return null;
    const value = JSON.parse(raw) as Partial<Stored>;
    return value.owner === owner && typeof value.id === "string" ? value.id : null;
  } catch {
    return null;
  }
}

export function rememberDevice(owner: Owner, id: string | null): void {
  try {
    if (id === null) window.localStorage.removeItem(DEVICE_KEY);
    else window.localStorage.setItem(DEVICE_KEY, JSON.stringify({ id, owner } satisfies Stored));
  } catch {
    // storage blocked: the switch reads the server's list instead
  }
}

/** The service worker's registration, or null if none is active within a few seconds. */
async function registration(): Promise<ServiceWorkerRegistration | null> {
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), READY_TIMEOUT_MS));
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await registration();
  return reg === null ? null : reg.pushManager.getSubscription();
}

/** base64url (the VAPID public key) to the bytes `pushManager.subscribe` wants. */
export function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function sameKey(current: ArrayBuffer | null | undefined, wanted: Uint8Array): boolean {
  if (current === null || current === undefined) return true; // the browser does not say
  const bytes = new Uint8Array(current);
  return bytes.length === wanted.length && bytes.every((b, i) => b === wanted[i]);
}

export type SubscribeResult =
  | { readonly kind: "subscribed"; readonly body: PushSubscriptionIn }
  | { readonly kind: "blocked" }
  | { readonly kind: "unavailable" }
  // The browser refused to subscribe for another reason (its push service failed, the installed
  // app's notifications are off in Android's settings): the DOMException's name, for the console.
  | { readonly kind: "failed"; readonly reason: string };

/** Ask once for permission (only after the person pressed "Turn on", R51) and subscribe. */
export async function subscribe(publicKey: string): Promise<SubscribeResult> {
  const answer = permission() === "granted" ? "granted" : await Notification.requestPermission();
  if (answer !== "granted") return { kind: "blocked" };
  const reg = await registration();
  if (reg === null) return { kind: "unavailable" };
  let existing = await reg.pushManager.getSubscription();
  const key = keyBytes(publicKey);
  if (existing !== null && !sameKey(existing.options.applicationServerKey, key)) {
    // Subscribed under another VAPID key (the pair was rotated): the push service would refuse it.
    await existing.unsubscribe();
    existing = null;
  }
  let subscription: PushSubscription;
  try {
    subscription = existing ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key }));
  } catch (failure) {
    const reason = failure instanceof Error ? failure.name : "Error";
    if (reason === "NotAllowedError") return { kind: "blocked" };
    console.warn("MediEase: the browser did not turn on alerts", reason);
    return { kind: "failed", reason };
  }
  const json = subscription.toJSON();
  const p256dh = json.keys?.p256dh;
  const auth = json.keys?.auth;
  if (json.endpoint === undefined || p256dh === undefined || auth === undefined) return { kind: "unavailable" };
  return { kind: "subscribed", body: { endpoint: json.endpoint, expirationTime: null, keys: { p256dh, auth } } };
}

/** Stop this browser's subscription (after the server forgot the device). */
export async function unsubscribe(): Promise<void> {
  const subscription = await currentSubscription();
  await subscription?.unsubscribe();
}
