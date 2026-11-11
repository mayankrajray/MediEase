/**
 * Addresses of the booking screens (M7d). The chosen date and time live in the address
 * (`?date=&session=&slot=`), so Back, reload and a language switch return to them (design §7).
 */

import type { PortalLanguage } from "@/lib/i18n/portal";

import type { Choice } from "./availability";

export interface Place {
  readonly slug: string;
  readonly language: PortalLanguage;
  /** M6c-P7 (discovery R11, R13): opened from search, the directory's rule applies all the way. */
  readonly viaDirectory: boolean;
}

function query(place: Place, extra: Record<string, string | null | undefined>, language = place.language): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(extra)) if (value !== null && value !== undefined && value !== "") q.set(key, value);
  if (language === "hi") q.set("lang", "hi");
  // Switching to English says so, so the portal's language cookie does not win.
  else if (language !== place.language) q.set("lang", "en");
  if (place.viaDirectory) q.set("via", "directory");
  const text = q.toString();
  return text === "" ? "" : `?${text}`;
}

/** The clinic page, on a chosen date. */
export function clinicHref(place: Place, date?: string, language?: PortalLanguage): string {
  return `/c/${encodeURIComponent(place.slug)}${query(place, { date }, language)}`;
}

/** A doctor's page, with the chosen date and time. */
export function doctorHref(place: Place, doctorId: string, date?: string, choice?: Choice | null, language?: PortalLanguage): string {
  return `/c/${encodeURIComponent(place.slug)}/doctors/${encodeURIComponent(doctorId)}${query(place, { date, session: choice?.session, slot: choice?.slot }, language)}`;
}

/** The request form for a chosen time; sign-in returns to it unchanged (spec R10). */
export function requestHref(place: Place, doctorId: string, choice: Choice): string {
  return `/portal/request${query(place, { clinic: place.slug, doctor: doctorId, session: choice.session, slot: choice.slot })}`;
}
