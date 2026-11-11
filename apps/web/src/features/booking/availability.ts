/**
 * The booking calendar's rules (M7d-P2; FR-PUB-02, FR-BKG-01; design §7): which dates a patient
 * may pick, what is offered on one date, and how those offers are grouped. Pure functions over the
 * availability answer (`GET /public/clinics/{slug}/availability`), so they are tested on a fixed
 * clock; the screens only render what these return.
 *
 * Dates are the clinic's calendar dates (`YYYY-MM-DD`); times are instants shown on the clinic's
 * clock. The API offers today and the next 13 days (`HORIZON_DAYS`), only times at least two hours
 * ahead and not held, and leaves out a day with no place at all.
 */

import type { GetResponse } from "@/lib/api/client";

export type Days = GetResponse<"/api/v1/public/clinics/{slug}/availability">["days"];
export type Day = Days[number];
export type OfferedSession = Day["sessions"][number];

/** Today and the next 13 days: the API's request horizon (`HORIZON_DAYS = 14`). */
export const WINDOW_DAYS = 14;
/** Dates shown as tiles before the calendar (decision 4: "the next 3–4 dates"). */
export const STRIP_DAYS = 4;
/** Times shown per part of the day before "Show all" (decision 4). */
export const PREVIEW = 3;
/** Older answers are fetched again (design §7, P2). */
export const STALE_MS = 60_000;
/** At or below this, a places count is shown in the warning tone. */
export const FEW_PLACES = 3;

export type Part = "morning" | "afternoon" | "evening";
export const PARTS: readonly Part[] = ["morning", "afternoon", "evening"];

/** What the patient chose: a session, and the slot in it when the session has slots. */
export interface Choice {
  readonly session: string;
  readonly slot: string | null;
}

/** One thing that can be chosen: a slot, or a whole token session. */
export interface Offer {
  readonly key: string;
  readonly part: Part;
  readonly session: OfferedSession;
  readonly slot: OfferedSession["slots"][number] | null;
  readonly startsAt: string;
  readonly endsAt: string;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** A calendar date `n` days after `date` (no time zone: plain date arithmetic). */
export function addDays(date: string, n: number): string {
  const at = new Date(`${date}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() + n);
  return at.toISOString().slice(0, 10);
}

/** The clinic's date at `now`. */
export function clinicToday(now: Date, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  } catch {
    return now.toISOString().slice(0, 10);
  }
}

/** The last date a patient may pick. */
export function lastDate(today: string): string {
  return addDays(today, WINDOW_DAYS - 1);
}

/** Whether `date` is a real date from today to the last date (never a past date). */
export function inWindow(date: string, today: string): boolean {
  if (!DATE.test(date) || Number.isNaN(Date.parse(`${date}T00:00:00Z`))) return false;
  // 30 Feb and the like: a real date reads back the same.
  return addDays(date, 0) === date && date >= today && date <= lastDate(today);
}

/** The date tiles: today first, then the next days. */
export function stripDates(today: string): readonly string[] {
  return Array.from({ length: STRIP_DAYS }, (_, n) => addDays(today, n));
}

/** The hour (0–23) of an instant on the clinic's clock. */
function clinicHour(iso: string, timeZone: string): number {
  const at = new Date(iso);
  try {
    const hour = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", hourCycle: "h23" }).format(at);
    return Number.parseInt(hour, 10);
  } catch {
    return at.getUTCHours();
  }
}

/** Morning before 12:00, afternoon 12:00 to before 17:00, evening from 17:00, on the clinic's clock. */
export function partOfDay(iso: string, timeZone: string): Part {
  const hour = clinicHour(iso, timeZone);
  return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
}

/** What can be chosen on one date, in time order: each slot, or each token session. */
export function offersOn(days: Days, date: string, timeZone: string): readonly Offer[] {
  const day = days.find((d) => d.date === date);
  if (day === undefined) return [];
  const offers: Offer[] = [];
  for (const session of day.sessions) {
    if (session.places_left <= 0) continue;
    if (session.mode === "SLOTS") {
      for (const slot of session.slots) {
        offers.push({ key: `${session.starts_at}|${slot.starts_at}`, part: partOfDay(slot.starts_at, timeZone), session, slot, startsAt: slot.starts_at, endsAt: slot.ends_at });
      }
    } else {
      offers.push({ key: session.starts_at, part: partOfDay(session.starts_at, timeZone), session, slot: null, startsAt: session.starts_at, endsAt: session.ends_at });
    }
  }
  return offers.sort((a, b) => Date.parse(a.startsAt) - Date.parse(b.startsAt));
}

/** The offers of a date by part of the day; a part with nothing is left out. */
export function groupByPart(offers: readonly Offer[]): readonly { part: Part; offers: readonly Offer[] }[] {
  return PARTS.map((part) => ({ part, offers: offers.filter((o) => o.part === part) })).filter((g) => g.offers.length > 0);
}

/** The places left on a date (the sum over its sessions); 0 when nothing is offered. */
export function placesOn(days: Days, date: string): number {
  return days.find((d) => d.date === date)?.sessions.reduce((sum, s) => sum + Math.max(0, s.places_left), 0) ?? 0;
}

/** The first date after `date` with something offered, if any. */
export function nextAvailableAfter(days: Days, date: string): string | undefined {
  return days
    .filter((d) => d.date > date && d.sessions.some((s) => s.places_left > 0))
    .map((d) => d.date)
    .sort()[0];
}

/** The choice for an offer. */
export function choiceOf(offer: Offer): Choice {
  return { session: offer.session.starts_at, slot: offer.slot?.starts_at ?? null };
}

/** Whether an offer is the chosen one. */
export function isChosen(offer: Offer, choice: Choice | null): boolean {
  return choice !== null && offer.session.starts_at === choice.session && (offer.slot?.starts_at ?? null) === choice.slot;
}

/** The offer a choice names, if the latest answer still offers it (the stale-data guard). */
export function findOffer(days: Days, date: string, choice: Choice | null, timeZone: string): Offer | undefined {
  if (choice === null) return undefined;
  return offersOn(days, date, timeZone).find((o) => isChosen(o, choice));
}

/** Whether an answer fetched at `fetchedAt` should be fetched again. */
export function isStale(fetchedAt: number, now: number): boolean {
  return now - fetchedAt >= STALE_MS;
}
