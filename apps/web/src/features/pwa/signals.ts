/**
 * M7e-E1: what `public/sw-register.js` leaves on `window`, and the small checks that decide
 * whether there is anything to offer. Kept apart from the prompts so the shells load only this.
 */

/** The browser's install prompt (not in TypeScript's DOM types). */
export interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
  readonly userChoice: Promise<{ readonly outcome: "accepted" | "dismissed" }>;
}

export interface MedieaseState {
  install?: InstallPromptEvent | undefined;
  waiting?: ServiceWorker | undefined;
  updating?: boolean;
}

declare global {
  interface Window {
    __mediease?: MedieaseState;
  }
}

/** Remembered on this device once the install offer has been answered (design §3: shown once). */
export const PROMPT_KEY = "me_app_prompt";
export const EVENTS = ["mediease:installable", "mediease:installed", "mediease:update"] as const;

export function appState(): MedieaseState {
  window.__mediease ??= {};
  return window.__mediease;
}

export function isStandalone(): boolean {
  const ios = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

/** iPhone and iPad (an iPad reports itself as a Mac with touch). */
export function isIos(): boolean {
  const ua = navigator.userAgent;
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}

export function answered(): boolean {
  try {
    return window.localStorage.getItem(PROMPT_KEY) !== null;
  } catch {
    return true; // storage blocked: do not nag on every page
  }
}

export function remember(): void {
  try {
    window.localStorage.setItem(PROMPT_KEY, "answered");
  } catch {
    // storage blocked: the offer may show again, which is harmless
  }
}

/** Is there an install offer for this device right now? */
export function installOffer(): "install" | "ios" | "none" {
  if (isStandalone() || answered()) return "none";
  if (appState().install !== undefined) return "install";
  return isIos() ? "ios" : "none";
}

/** Anything at all to show: an install offer or a waiting update. */
export function somethingToOffer(): boolean {
  return installOffer() !== "none" || appState().waiting !== undefined;
}
