"use client";

import { useId, useState } from "react";

import { bookingWords } from "@/lib/i18n/booking-request";
import { portalCalendarDate, portalDay, portalDayParts, portalStrings, type PortalLanguage } from "@/lib/i18n/portal";

import { addDays, inWindow, lastDate, stripDates } from "./availability";

const TILE =
  "flex min-h-[4.5rem] w-full cursor-pointer flex-col items-center justify-center gap-0.5 rounded-lg border px-1 py-2 text-center transition-colors";

/** A calendar date as an instant at noon UTC, for the date formatters (no zone shift). */
export const noon = (date: string) => `${date}T12:00:00Z`;

/**
 * Today and the next three dates as tiles, and the browser's own date picker for the rest of the
 * 14 days (M7d-P2, P4; decision 4, design §7). `left` says what is left on a date once known: a
 * tile then shows "N left" or "No times", in words as well as tone. A date outside the window is
 * refused in words and never chosen.
 */
export function DateStrip({
  language,
  today,
  date,
  onDate,
  left,
}: Readonly<{ language: PortalLanguage; today: string; date: string; onDate: (date: string) => void; left: ((date: string) => number) | undefined }>) {
  const words = bookingWords(language).picker;
  const s = portalStrings(language);
  const ids = { heading: useId(), other: useId(), hint: useId() };
  const [outside, setOutside] = useState(false);
  const last = lastDate(today);
  const tiles = stripDates(today);
  const dayName = (d: string) => (d === today ? words.today : d === addDays(today, 1) ? words.tomorrow : portalDayParts(noon(d), "UTC", s).weekday);

  function pick(value: string) {
    if (!inWindow(value, today)) {
      setOutside(true);
      return;
    }
    setOutside(false);
    if (value !== date) onDate(value);
  }

  return (
    <section aria-labelledby={ids.heading} className="space-y-3">
      <h2 id={ids.heading} className="heading-6 text-slate-900">
        {words.chooseDate}
      </h2>
      <ul className="grid grid-cols-4 gap-2">
        {tiles.map((d) => {
          const selected = d === date;
          const n = left?.(d);
          const none = n === 0;
          const parts = portalDayParts(noon(d), "UTC", s);
          return (
            <li key={d}>
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => pick(d)}
                className={`${TILE} ${
                  selected
                    ? "border-brand-700 bg-brand-700 text-white"
                    : none
                      ? "border-dashed border-slate-300 bg-surface text-slate-600 hover:border-slate-400"
                      : "border-line bg-surface text-slate-900 hover:border-brand-300 hover:bg-brand-50"
                }`}
              >
                {/* The name is the full date and what is left; the tile's short parts are for the eye
                    ("Today", "12", "Nov"), so a screen reader hears "Thu, 12 Nov, 40 left". */}
                <span className="sr-only">{`${portalDay(noon(d), "UTC", s)}${n === undefined ? "" : ","}`}</span>
                <span aria-hidden="true" className="text-xs font-medium">
                  {dayName(d)}
                </span>
                <span aria-hidden="true" className="text-lg font-semibold leading-tight tabular-nums">
                  {parts.day}
                </span>
                <span aria-hidden="true" className="text-xs">
                  {parts.month}
                </span>{" "}
                {n !== undefined && (
                  <span className={`text-[0.6875rem] font-medium leading-tight ${selected ? "text-white" : none ? "text-slate-600" : "text-success"}`}>
                    {none ? words.tileNone : words.tileLeft(n)}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      <div>
        <label htmlFor={ids.other} className="block text-sm font-semibold text-slate-900">
          {words.otherDate}
        </label>
        <input
          id={ids.other}
          type="date"
          min={today}
          max={last}
          value={tiles.includes(date) ? "" : date}
          aria-describedby={ids.hint}
          aria-invalid={outside || undefined}
          onChange={(event) => {
            if (event.target.value !== "") pick(event.target.value);
          }}
          className={`mt-1.5 min-h-11 w-full cursor-pointer rounded-lg border bg-white px-3 text-base text-slate-900 transition-colors hover:border-slate-600 focus-visible:border-brand-700 sm:max-w-xs ${
            tiles.includes(date) ? "border-slate-400" : "border-brand-700 ring-1 ring-brand-700"
          }`}
        />
        <p id={ids.hint} className={`mt-1 text-sm ${outside ? "font-medium text-danger" : "text-slate-700"}`} aria-live="polite">
          {outside ? words.outside(portalCalendarDate(today, s), portalCalendarDate(last, s)) : words.otherDateHint(portalCalendarDate(today, s), portalCalendarDate(last, s))}
        </p>
      </div>
    </section>
  );
}
