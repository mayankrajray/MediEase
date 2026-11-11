"use client";

import { CalendarDays, Check, CircleAlert, Clock, RefreshCw } from "lucide-react";
import { useId, useState } from "react";

import { Skeleton } from "@/components/ui/Skeleton";
import { bookingWords } from "@/lib/i18n/booking-request";
import { portalDay, portalStrings, portalTime, type PortalLanguage } from "@/lib/i18n/portal";

import {
  addDays,
  FEW_PLACES,
  findOffer,
  groupByPart,
  inWindow,
  isChosen,
  nextAvailableAfter,
  offersOn,
  placesOn,
  PREVIEW,
  choiceOf,
  type Choice,
  type Offer,
  type Part,
} from "./availability";
import { DateStrip, noon } from "./DateStrip";
import type { AvailabilityState } from "./useAvailability";

const CHIP =
  "inline-flex min-h-11 w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-2 text-sm font-semibold tabular-nums transition-colors";
const QUIET =
  "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-1 text-sm font-semibold text-brand-800 underline underline-offset-2 hover:text-brand-900";

/**
 * Pick a date, then a time (M7d-P2; design §4 decision 4, §7). Controlled: the screen owns the date
 * and the choice (P3 keeps them in the address, so Back and reload return to them) and the
 * availability (`useAvailability`). Today is the first tile; three more follow, and the browser's
 * own date picker reaches the rest of the 14 days. The chosen date's times are grouped into
 * morning, afternoon and evening, three each until "Show all".
 *
 * States are told apart by words and shape as well as colour: a chosen time is filled and ticked
 * (`aria-pressed`), a date with nothing says "No times", loading is a skeleton with a status line,
 * a failure is an alert with "Try again", and a choice the latest answer no longer offers says so.
 */
export function AppointmentPicker({
  availability,
  timezone,
  language,
  today,
  date,
  choice,
  onDate,
  onChoice,
  onRetry,
}: Readonly<{
  availability: AvailabilityState;
  timezone: string;
  language: PortalLanguage;
  /** The clinic's date today (`clinicToday`). */
  today: string;
  date: string;
  choice: Choice | null;
  onDate: (date: string) => void;
  onChoice: (choice: Choice | null) => void;
  onRetry: () => void;
}>) {
  const words = bookingWords(language).picker;
  const s = portalStrings(language);
  const ids = { times: useId() };
  const days = availability.status === "ready" ? availability.days : [];
  const ready = availability.status === "ready";
  const offers = ready ? offersOn(days, date, timezone) : [];
  const chosen = ready ? findOffer(days, date, choice, timezone) : undefined;
  const gone = ready && !availability.refreshing && choice !== null && chosen === undefined;
  const next = ready ? nextAvailableAfter(days, date) : undefined;
  // Nothing later but something earlier (a later date was picked): offer the earliest instead.
  const earliest = ready && next === undefined ? nextAvailableAfter(days, addDays(today, -1)) : undefined;
  const target = next ?? (earliest !== date ? earliest : undefined);
  const fullDay = (d: string) => portalDay(noon(d), "UTC", s);
  const places = ready ? placesOn(days, date) : 0;

  function pickDate(value: string) {
    if (inWindow(value, today) && value !== date) onDate(value);
  }

  return (
    <div className="space-y-5">
      <DateStrip language={language} today={today} date={date} onDate={pickDate} left={ready ? (d) => placesOn(days, d) : undefined} />

      <section aria-labelledby={ids.times} aria-busy={availability.status === "loading" || (ready && availability.refreshing)} className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id={ids.times} className="heading-6 text-slate-900">
            {words.timesOn(fullDay(date))}
          </h2>
          {ready && places > 0 && (
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-1 text-sm font-semibold tabular-nums ${places <= FEW_PLACES ? "bg-warning-soft text-slate-900 ring-1 ring-warning-line" : "bg-success-soft text-slate-900 ring-1 ring-success-line"}`}
            >
              {words.placesOn(places)}
            </span>
          )}
        </div>

        {ready && availability.refreshing && (
          <p role="status" className="flex items-center gap-2 text-sm text-slate-700">
            <RefreshCw aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
            {words.updating}
          </p>
        )}

        {gone && (
          <p role="alert" className="flex gap-2 rounded-xl border border-warning-line bg-warning-soft p-3 font-medium text-slate-900">
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
            <span>{words.gone}</span>
          </p>
        )}

        {availability.status === "loading" && (
          <div>
            <p role="status" className="sr-only">
              {words.loading}
            </p>
            <div aria-hidden="true" className="space-y-2">
              <Skeleton className="h-5 w-24" />
              <div className="grid grid-cols-3 gap-2">
                <Skeleton className="h-11" />
                <Skeleton className="h-11" />
                <Skeleton className="h-11" />
              </div>
            </div>
          </div>
        )}

        {availability.status === "failed" && (
          <div role="alert" className="space-y-3 rounded-xl border border-danger-line bg-danger-soft p-4 text-slate-900">
            <p className="flex gap-2 font-semibold">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
              {words.failed}
            </p>
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg border border-slate-300 bg-surface px-4 text-sm font-semibold text-slate-900 transition-colors hover:border-brand-300 hover:bg-brand-50"
            >
              <RefreshCw aria-hidden="true" className="size-4" />
              {words.retry}
            </button>
          </div>
        )}

        {ready && offers.length === 0 && (
          <div className="space-y-3 rounded-card border border-dashed border-slate-300 bg-surface px-4 py-6 text-center">
            <p className="text-slate-800">{target === undefined ? words.noneInWindow : words.noneOnDate}</p>
            {target !== undefined && (
              <button
                type="button"
                onClick={() => pickDate(target)}
                className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 font-semibold text-white transition-colors hover:bg-brand-800"
              >
                <CalendarDays aria-hidden="true" className="size-4" />
                {next === undefined ? words.firstAvailable(fullDay(target)) : words.nextAvailable(fullDay(target))}
              </button>
            )}
          </div>
        )}

        {ready &&
          groupByPart(offers).map((group) => (
            <PartOfDay
              key={`${date}|${group.part}`}
              part={group.part}
              offers={group.offers}
              choice={choice}
              onChoice={onChoice}
              timezone={timezone}
              language={language}
            />
          ))}

        <p aria-live="polite" className="sr-only">
          {chosen === undefined ? "" : words.yourChoice(`${fullDay(date)}, ${portalTime(chosen.startsAt, timezone, s)}`)}
        </p>
      </section>
    </div>
  );
}

/** One part of the day: three times, then the rest on request. A chosen time is never hidden. */
function PartOfDay({
  part,
  offers,
  choice,
  onChoice,
  timezone,
  language,
}: Readonly<{ part: Part; offers: readonly Offer[]; choice: Choice | null; onChoice: (choice: Choice | null) => void; timezone: string; language: PortalLanguage }>) {
  const words = bookingWords(language).picker;
  const s = portalStrings(language);
  const headingId = useId();
  const listId = useId();
  const chosenAt = offers.findIndex((o) => isChosen(o, choice));
  const [open, setOpen] = useState(chosenAt >= PREVIEW);
  const shown = open || chosenAt >= PREVIEW ? offers : offers.slice(0, PREVIEW);
  const more = offers.length - PREVIEW;
  const name = words.parts[part];
  const slots = offers.every((o) => o.slot !== null);

  return (
    <div role="group" aria-labelledby={headingId} className="space-y-2">
      <h3 id={headingId} className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-slate-700">
        <Clock aria-hidden="true" className="size-4" />
        {name}
      </h3>
      <ul id={listId} className={slots ? "grid grid-cols-3 gap-2 sm:grid-cols-4" : "space-y-2"}>
        {shown.map((offer) => {
          const selected = isChosen(offer, choice);
          const time = portalTime(offer.startsAt, timezone, s);
          if (offer.slot !== null) {
            return (
              <li key={offer.key}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onChoice(selected ? null : choiceOf(offer))}
                  className={`${CHIP} ${selected ? "border-brand-700 bg-brand-700 text-white" : "border-brand-300 bg-brand-50 text-brand-900 hover:border-brand-700 hover:bg-brand-100"}`}
                >
                  {selected && <Check aria-hidden="true" className="size-4 shrink-0" />}
                  {time}
                </button>
              </li>
            );
          }
          const span = words.span(time, portalTime(offer.endsAt, timezone, s));
          const left = offer.session.places_left;
          return (
            <li
              key={offer.key}
              className={`flex items-center gap-3 rounded-lg border px-3 py-2 transition-colors ${selected ? "border-brand-700 bg-brand-50 ring-1 ring-brand-700" : "border-line bg-surface"}`}
            >
              <p className="min-w-0 flex-1 text-sm">
                <span className="font-semibold tabular-nums text-slate-900">{span}</span>
                <span aria-hidden="true" className="text-slate-500">
                  {" · "}
                </span>
                <span className={`font-medium ${left <= FEW_PLACES ? "text-warning" : "text-slate-700"}`}>{bookingWords(language).page.placesLeft(left)}</span>
              </p>
              <button
                type="button"
                aria-pressed={selected}
                aria-label={words.chooseLabel(span)}
                onClick={() => onChoice(selected ? null : choiceOf(offer))}
                className={`inline-flex min-h-11 min-w-24 shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-lg px-4 text-sm font-semibold transition-colors ${
                  selected ? "bg-brand-800 text-white" : "border border-brand-700 bg-surface text-brand-800 hover:bg-brand-50"
                }`}
              >
                {selected && <Check aria-hidden="true" className="size-4 shrink-0" />}
                {selected ? words.chosen : words.choose}
              </button>
            </li>
          );
        })}
      </ul>
      {more > 0 && chosenAt < PREVIEW && (
        <button type="button" aria-expanded={open} aria-controls={listId} onClick={() => setOpen((v) => !v)} className={QUIET}>
          {open ? words.showFewer(name) : words.showAll(name, more)}
        </button>
      )}
    </div>
  );
}
