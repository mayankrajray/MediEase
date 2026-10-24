"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";

import type { Favourite, Frequency, Suggestion, Timing, Vocabulary } from "./api";
import { toLine, type Line } from "./draft";
import { MedicineCombobox } from "./MedicineCombobox";
import { TIMINGS, frequencyLabel, parseDuration, parseFrequency } from "./vocabulary";

const FREQUENCY_HINT = "Use 0 and 1 for each time of day (101, 110, 1-0-1-1), S for SOS, O for once, C for custom. Anything else: C and write it.";
const DURATION_HINT = "Days 1 to 365, R for until review, G for ongoing, or leave it empty";

interface Entry {
  readonly name: string;
  readonly dose: string;
  readonly frequency: string;
  readonly custom: string;
  readonly timing: Timing | "";
  readonly duration: string;
}

const EMPTY: Entry = { name: "", dose: "", frequency: "", custom: "", timing: "", duration: "" };

/** What is wrong with the entry, by field; empty when it can be added. */
export function entryProblems(entry: Entry, vocabulary: Vocabulary | undefined): Partial<Record<keyof Entry, string>> {
  const problems: Partial<Record<keyof Entry, string>> = {};
  if (entry.name.trim() === "") problems.name = "Type the medicine first";
  const code = parseFrequency(entry.frequency, vocabulary);
  if (entry.frequency.trim() !== "" && code === undefined) problems.frequency = FREQUENCY_HINT;
  if (code === "CUSTOM" && entry.custom.trim() === "") problems.custom = "Say how often";
  if (parseDuration(entry.duration) === undefined) problems.duration = DURATION_HINT;
  return problems;
}

function lineOf(entry: Entry, vocabulary: Vocabulary | undefined): Line {
  const frequency: Frequency | null = parseFrequency(entry.frequency, vocabulary) ?? null;
  const duration = parseDuration(entry.duration) ?? { kind: null, days: null };
  return toLine({
    medicine_name: entry.name.trim(),
    dose: entry.dose.trim() === "" ? null : entry.dose.trim(),
    frequency,
    frequency_text: frequency === "CUSTOM" ? entry.custom.trim() : null,
    timing: entry.timing === "" ? null : entry.timing,
    duration_days: duration.days,
    duration_kind: duration.kind,
  });
}

/**
 * The one entry row of the builder (spec §6, keyboard-first): medicine, Tab, dose, Tab,
 * frequency, Tab, timing, Tab, duration, Enter — the line is added and the cursor is back on the
 * medicine for the next one. Picking a favourite adds its whole line at once (FR-RX-05).
 */
export function EntryRow({
  onAdd,
  favourites,
  vocabulary,
  disabled,
}: Readonly<{ onAdd: (line: Line) => void; favourites: readonly Favourite[]; vocabulary: Vocabulary | undefined; disabled: boolean }>) {
  const base = useId();
  const [entry, setEntry] = useState<Entry>(EMPTY);
  const [tried, setTried] = useState(false);
  const [message, setMessage] = useState("");
  const medicine = useRef<HTMLInputElement>(null);
  const problems = entryProblems(entry, vocabulary);
  const shown = tried ? problems : { ...problems, name: undefined };
  const code = parseFrequency(entry.frequency, vocabulary);
  const set = (patch: Partial<Entry>) => setEntry((e) => ({ ...e, ...patch }));

  function reset(text: string) {
    setEntry(EMPTY);
    setTried(false);
    setMessage(text);
    medicine.current?.focus();
  }

  function add() {
    if (disabled) return;
    if (Object.values(problems).some((p) => p !== undefined)) {
      setTried(true);
      return;
    }
    const line = lineOf(entry, vocabulary);
    onAdd(line);
    reset(`${line.medicine_name} added.`);
  }

  function pick(s: Suggestion) {
    const favourite = s.favourite_id === null ? undefined : favourites.find((f) => f.id === s.favourite_id);
    if (favourite !== undefined) {
      onAdd(toLine(favourite.item, favourite.id));
      reset(`${favourite.item.medicine_name} added from your favourites.`);
    } else {
      set({ name: s.name });
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Enter" || event.defaultPrevented) return;
    if (!(event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) return;
    event.preventDefault();
    add();
  }

  const fieldId = (name: string) => `${base}-${name}`;
  const errorOf = (name: keyof Entry) => shown[name];
  const describe = (name: keyof Entry, hint?: boolean) =>
    [hint === true ? `${fieldId(name)}-hint` : "", errorOf(name) !== undefined ? `${fieldId(name)}-error` : ""].filter(Boolean).join(" ") ||
    undefined;
  const label = "block text-sm font-medium";
  const input = "w-full rounded-lg border border-slate-400 px-2 py-1.5";

  return (
    <div role="group" aria-label="New medicine" onKeyDown={onKeyDown} className="space-y-2 rounded-card border border-slate-200 bg-white bg-slate-50 p-3">
      <div className="grid grid-cols-[minmax(12rem,2fr)_minmax(5rem,1fr)_minmax(7rem,1fr)_minmax(8rem,1fr)_minmax(5rem,0.7fr)_auto] items-start gap-2">
        <div>
          <label htmlFor={fieldId("name")} className={label}>
            Medicine
          </label>
          <MedicineCombobox
            id={fieldId("name")}
            inputRef={medicine}
            value={entry.name}
            onChange={(name) => set({ name })}
            onPick={pick}
            invalid={errorOf("name") !== undefined}
            {...(describe("name") === undefined ? {} : { describedBy: describe("name") as string })}
          />
        </div>
        <div>
          <label htmlFor={fieldId("dose")} className={label}>
            Dose
          </label>
          <input id={fieldId("dose")} value={entry.dose} maxLength={100} onChange={(e) => set({ dose: e.target.value })} className={input} />
        </div>
        <div>
          <label htmlFor={fieldId("frequency")} className={label}>
            Frequency
          </label>
          <input
            id={fieldId("frequency")}
            value={entry.frequency}
            maxLength={20}
            aria-invalid={errorOf("frequency") !== undefined ? true : undefined}
            aria-describedby={describe("frequency", true)}
            onChange={(e) => set({ frequency: e.target.value })}
            className={input}
          />
          <p id={`${fieldId("frequency")}-hint`} className="text-xs text-slate-700">
            {code === undefined ? "101, 110, 1-0-1-1, S, O, C" : frequencyLabel(code, null, vocabulary)}
          </p>
          {code === "CUSTOM" && (
            <>
              <label htmlFor={fieldId("custom")} className={label}>
                How often (custom)
              </label>
              <input
                id={fieldId("custom")}
                value={entry.custom}
                maxLength={100}
                aria-invalid={errorOf("custom") !== undefined ? true : undefined}
                aria-describedby={describe("custom")}
                onChange={(e) => set({ custom: e.target.value })}
                className={input}
              />
            </>
          )}
        </div>
        <div>
          <label htmlFor={fieldId("timing")} className={label}>
            Timing
          </label>
          <select id={fieldId("timing")} value={entry.timing} onChange={(e) => set({ timing: e.target.value as Timing | "" })} className={input}>
            <option value="">—</option>
            {TIMINGS.map((t) => (
              <option key={t.code} value={t.code}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={fieldId("duration")} className={label}>
            Days
          </label>
          <input
            id={fieldId("duration")}
            value={entry.duration}
            maxLength={12}
            aria-invalid={errorOf("duration") !== undefined ? true : undefined}
            aria-describedby={describe("duration", true)}
            onChange={(e) => set({ duration: e.target.value })}
            className={input}
          />
          <p id={`${fieldId("duration")}-hint`} className="text-xs text-slate-700">
            5, R, G
          </p>
        </div>
        <button
          type="button"
          disabled={disabled}
          onClick={add}
          className="mt-5 rounded bg-brand-700 px-3 py-1.5 font-semibold text-white hover:bg-brand-800 disabled:bg-slate-400"
        >
          Add line
        </button>
      </div>
      {(["name", "frequency", "custom", "duration"] as const).map((name) =>
        errorOf(name) === undefined ? null : (
          <p key={name} id={`${fieldId(name)}-error`} className="text-sm font-medium text-red-900">
            {errorOf(name)}
          </p>
        ),
      )}
      <p role="status" className="sr-only">
        {message}
      </p>
    </div>
  );
}
