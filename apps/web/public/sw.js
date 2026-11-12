/*
 * MediEase service worker (M7e-E1, docs/milestones/M7e-pwa-push.md §3, §5).
 *
 * What it caches: only files that are the same for everyone and change name when they change:
 * the build's static assets (/_next/static/), the logo files (/brand/), the app icons (/icons/),
 * and the offline page. Nothing else is ever stored: no API response, no page, nothing about a
 * patient or a clinic. A page is always fetched from the network; when the network fails, the
 * offline page is shown instead, and nothing is queued or pretended.
 *
 * Updates: a new version waits until the person chooses "Update" (the page posts SKIP_WAITING),
 * then takes over and old caches are removed. Plain JavaScript on purpose: no build step, no
 * library, and the tests load this very file (src/features/pwa/sw.test.ts).
 *
 * M7e-E5: it also shows pop-up alerts (web push) and opens the notice's page when one is tapped.
 */

const VERSION = "v1";
const CACHE = `mediease-static-${VERSION}`;
const OFFLINE_URL = "/offline.html";
// Only what the offline page needs: it must show with nothing else cached. Kept small, because a
// phone downloads it on its first visit (NFR-02).
const PRECACHE = [OFFLINE_URL, "/brand/mediease-icon.svg"];
const STATIC_PREFIXES = ["/_next/static/", "/brand/", "/icons/"];

/** True only for same-origin GETs of a path whose content never changes under one name. */
function isStaticAsset(request) {
  if (request.method !== "GET") return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  return STATIC_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith("mediease-") && key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data !== null && typeof event.data === "object" && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

async function cacheFirst(request) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(request);
  if (hit !== undefined) return hit;
  const response = await fetch(request);
  // Only a complete, same-origin answer is kept (never an error page or a redirect).
  if (response.ok && response.type === "basic") await cache.put(request, response.clone());
  return response;
}

async function pageOrOffline(request) {
  try {
    return await fetch(request);
  } catch {
    const offline = await caches.match(OFFLINE_URL);
    return offline ?? Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (isStaticAsset(request)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  // Same-origin page loads only; everything else (the API, other sites) goes to the network
  // untouched, as if there were no service worker.
  if (request.mode === "navigate" && request.method === "GET" && new URL(request.url).origin === self.location.origin) {
    event.respondWith(pageOrOffline(request));
  }
});

/*
 * M7e-E5 (spec web-push R55-R57): pop-up alerts. The server sends only fixed words per kind and
 * the notice's path (R32), and nothing here adds to them. A message that is not the expected JSON
 * still shows a plain "MediEase" alert, because a push the browser receives must be shown.
 * Tapping it opens the path on this site only; a signed-out person signs in first and lands on it
 * (the proxy's ?next=, validated by the sign-in pages).
 */
const ALERT_ICON = "/icons/icon-192.png";
const FALLBACK = { title: "MediEase", body: "Open MediEase to see it." };

/** A path on this site, or "/": never another origin, a protocol-relative URL or a backslash. */
function samePath(value) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/";
  try {
    const url = new URL(value, self.location.origin);
    return url.origin === self.location.origin ? `${url.pathname}${url.search}${url.hash}` : "/";
  } catch {
    return "/";
  }
}

function text(value, fallback, max) {
  return typeof value === "string" && value.trim() !== "" ? value.slice(0, max) : fallback;
}

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  if (data === null || typeof data !== "object") data = {};
  const tag = typeof data.tag === "string" && data.tag !== "" ? data.tag.slice(0, 64) : undefined;
  const options = {
    body: text(data.body, FALLBACK.body, 200),
    icon: ALERT_ICON,
    data: { url: samePath(data.url) },
  };
  // A newer notice of the same kind replaces the older one on the screen, and still alerts.
  if (tag !== undefined) Object.assign(options, { tag, renotify: true });
  event.waitUntil(self.registration.showNotification(text(data.title, FALLBACK.title, 100), options));
});

async function openPath(path) {
  const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const client of windows) {
    if (new URL(client.url).origin !== self.location.origin) continue;
    try {
      const shown = await client.navigate(path);
      if (shown) return shown.focus();
    } catch {
      // Not controlled by this worker: open a new window below instead.
    }
  }
  return self.clients.openWindow(path);
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data;
  event.waitUntil(openPath(samePath(data !== null && typeof data === "object" ? data.url : undefined)));
});
