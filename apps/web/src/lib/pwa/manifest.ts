import type { Metadata, MetadataRoute, Viewport } from "next";

/** The brand colours of the installed app (DESIGN.md §1: brand-700 and the canvas). */
export const THEME_COLOR = "#147d72";
export const BACKGROUND_COLOR = "#f5f9f8";
export const MANIFEST_PATH = "/manifest.webmanifest";

/**
 * M7e-E1 (design §3, §7 Q1): the web app manifest. One manifest for staff and patients, who share
 * this origin: the app opens at `/`, which sends a signed-in person on to Today or the portal and
 * anyone else to the landing page. The icons are rendered from the emblem (`src/app/icon.svg`);
 * the maskable one keeps it inside the 80% safe zone.
 */
export function webManifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "MediEase",
    short_name: "MediEase",
    description: "Appointments, prescriptions and reminders from your clinic.",
    lang: "en",
    dir: "ltr",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    theme_color: THEME_COLOR,
    background_color: BACKGROUND_COLOR,
    categories: ["health", "medical"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}

/**
 * The installable app's tags (the manifest link, the iPhone Home Screen tags), for the layouts of
 * the staff and portal pages only, which also register the service worker (design §7 Q2,
 * fallback B). The landing page, search, clinic and token pages leave them out: they have no room
 * in their 200 KB budget (NFR-02).
 */
export const PWA_METADATA: Metadata = {
  manifest: MANIFEST_PATH,
  appleWebApp: { capable: true, title: "MediEase", statusBarStyle: "default" },
};

export const PWA_VIEWPORT: Viewport = { themeColor: THEME_COLOR };
