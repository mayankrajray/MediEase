"use client";

import { useId, useState } from "react";

import { Drawer } from "@/components/Drawer";

import type { Frequency, PreparationPhrase, StoragePhrase, Timing } from "./api";
import type { Line } from "./draft";
import { FREQUENCIES, PREPARATIONS, STORAGES, TIMINGS } from "./vocabulary";

const text = (value: string) => (value.trim() === "" ? null : value.trim());

/**
 * "More" on a line (FR-RX-01, FR-RX-02): every field of the medicine, including form, strength,
 * quantity, the structured preparation and storage phrases (shown to the patient in their
 * language, R20), warnings and notes (shown as written). Done applies; Close discards.
 */
export function LineEditor({
  line,
  number,
  onDone,
  onClose,
}: Readonly<{ line: Line; number: number; onDone: (line: Line) => void; onClose: () => void }>) {
  const base = useId();
  const [draft, setDraft] = useState<Line>(line);
  const [duration, setDuration] = useState(line.duration_days === null || line.duration_days === undefined ? "" : String(line.duration_days));
  const [tried, setTried] = useState(false);
  const set = (patch: Partial<Line>) => setDraft((d) => ({ ...d, ...patch }));
  const id = (name: string) => `${base}-${name}`;
  const preparation = draft.preparation ?? [];
  const storage = draft.storage ?? [];

  const problems: Record<string, string> = {};
  if (draft.medicine_name.trim() === "") problems["name"] = "The medicine is required";
  if (draft.frequency === "CUSTOM" && (draft.frequency_text ?? "").trim() === "") problems["custom"] = "Say how often";
  if (duration.trim() !== "" && !(/^\d+$/.test(duration.trim()) && Number(duration) >= 1 && Number(duration) <= 365)) {
    problems["duration"] = "Whole days, 1 to 365";
  }
  for (const p of preparation) {
    if ((p.code === "DILUTE_IN_WATER" || p.code === "CUSTOM") && (p.text ?? "").trim() === "") problems[`prep-${p.code}`] = "Required";
  }
  for (const s of storage) {
    if (s.code === "DISCARD_AFTER_DAYS" && !(s.days !== null && s.days !== undefined && s.days >= 1 && s.days <= 365)) {
      problems[`store-${s.code}`] = "Days, 1 to 365";
    }
  }
  const err = (key: string) => (tried ? problems[key] : undefined);

  function togglePrep(code: PreparationPhrase["code"], on: boolean) {
    set({ preparation: on ? [...preparation, { code, text: null }] : preparation.filter((p) => p.code !== code) });
  }
  function prepText(code: PreparationPhrase["code"], value: string) {
    set({ preparation: preparation.map((p) => (p.code === code ? { ...p, text: value } : p)) });
  }
  function toggleStore(code: StoragePhrase["code"], on: boolean) {
    set({ storage: on ? [...storage, { code, days: null }] : storage.filter((s) => s.code !== code) });
  }
  function storeDays(code: StoragePhrase["code"], value: string) {
    const days = /^\d+$/.test(value) ? Number(value) : null;
    set({ storage: storage.map((s) => (s.code === code ? { ...s, days } : s)) });
  }

  function done() {
    if (Object.keys(problems).length > 0) {
      setTried(true);
      return;
    }
    onDone({
      ...draft,
      medicine_name: draft.medicine_name.trim(),
      form: text(draft.form ?? ""),
      strength: text(draft.strength ?? ""),
      dose: text(draft.dose ?? ""),
      frequency_text: draft.frequency === "CUSTOM" ? text(draft.frequency_text ?? "") : null,
      duration_days: duration.trim() === "" ? null : Number(duration),
      quantity: text(draft.quantity ?? ""),
      preparation: preparation.map((p) => ({ code: p.code, text: p.code === "DILUTE_IN_WATER" || p.code === "CUSTOM" ? text(p.text ?? "") : null })),
      warnings: text(draft.warnings ?? ""),
      notes: text(draft.notes ?? ""),
    });
  }

  const field = "w-full rounded-lg border border-slate-400 px-2 py-1.5";
  const labelCss = "block font-medium";
  const short = (name: "form" | "strength" | "dose" | "quantity", label: string) => (
    <div>
      <label htmlFor={id(name)} className={labelCss}>
        {label}
      </label>
      <input id={id(name)} value={draft[name] ?? ""} maxLength={100} onChange={(e) => set({ [name]: e.target.value } as Partial<Line>)} className={field} />
    </div>
  );
  const error = (key: string) =>
    err(key) === undefined ? null : (
      <p id={id(`${key}-error`)} className="text-sm font-medium text-red-900">
        {err(key)}
      </p>
    );
  const invalid = (key: string) => (err(key) === undefined ? {} : { "aria-invalid": true, "aria-describedby": id(`${key}-error`) });

  return (
    <Drawer title={`Line ${number}: ${line.medicine_name}`} onClose={onClose}>
      <div>
        <label htmlFor={id("name")} className={labelCss}>
          Medicine
        </label>
        <input
          id={id("name")}
          data-autofocus
          value={draft.medicine_name}
          maxLength={200}
          onChange={(e) => set({ medicine_name: e.target.value })}
          className={field}
          {...invalid("name")}
        />
        {error("name")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {short("form", "Form (e.g. syrup)")}
        {short("strength", "Strength")}
        {short("dose", "Dose")}
        {short("quantity", "Quantity")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={id("frequency")} className={labelCss}>
            Frequency
          </label>
          <select
            id={id("frequency")}
            value={draft.frequency ?? ""}
            onChange={(e) => set({ frequency: e.target.value === "" ? null : (e.target.value as Frequency) })}
            className={field}
          >
            <option value="">—</option>
            {FREQUENCIES.map((f) => (
              <option key={f.code} value={f.code}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={id("timing")} className={labelCss}>
            Timing
          </label>
          <select
            id={id("timing")}
            value={draft.timing ?? ""}
            onChange={(e) => set({ timing: e.target.value === "" ? null : (e.target.value as Timing) })}
            className={field}
          >
            <option value="">—</option>
            {TIMINGS.map((t) => (
              <option key={t.code} value={t.code}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        {draft.frequency === "CUSTOM" && (
          <div className="col-span-2">
            <label htmlFor={id("custom")} className={labelCss}>
              How often (custom)
            </label>
            <input
              id={id("custom")}
              value={draft.frequency_text ?? ""}
              maxLength={100}
              onChange={(e) => set({ frequency_text: e.target.value })}
              className={field}
              {...invalid("custom")}
            />
            {error("custom")}
          </div>
        )}
        <div>
          <label htmlFor={id("duration")} className={labelCss}>
            Days
          </label>
          <input
            id={id("duration")}
            value={duration}
            inputMode="numeric"
            maxLength={3}
            onChange={(e) => setDuration(e.target.value)}
            className={field}
            {...invalid("duration")}
          />
          {error("duration")}
        </div>
      </div>

      <fieldset className="space-y-2">
        <legend className="font-medium">How to prepare or take it (shown to the patient in their language)</legend>
        {PREPARATIONS.map((p) => {
          const chosen = preparation.find((x) => x.code === p.code);
          return (
            <div key={p.code} className="space-y-1">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={chosen !== undefined} onChange={(e) => togglePrep(p.code, e.target.checked)} />
                {p.label}
              </label>
              {chosen !== undefined && p.text !== undefined && (
                <div className="pl-6">
                  <label htmlFor={id(`prep-${p.code}`)} className="block text-sm font-medium">
                    {p.text}
                  </label>
                  <input
                    id={id(`prep-${p.code}`)}
                    value={chosen.text ?? ""}
                    maxLength={100}
                    onChange={(e) => prepText(p.code, e.target.value)}
                    className={field}
                    {...invalid(`prep-${p.code}`)}
                  />
                  {error(`prep-${p.code}`)}
                </div>
              )}
            </div>
          );
        })}
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="font-medium">Storage</legend>
        {STORAGES.map((s) => {
          const chosen = storage.find((x) => x.code === s.code);
          return (
            <div key={s.code} className="space-y-1">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={chosen !== undefined} onChange={(e) => toggleStore(s.code, e.target.checked)} />
                {s.label}
              </label>
              {chosen !== undefined && s.code === "DISCARD_AFTER_DAYS" && (
                <div className="pl-6">
                  <label htmlFor={id(`store-${s.code}`)} className="block text-sm font-medium">
                    Discard after how many days
                  </label>
                  <input
                    id={id(`store-${s.code}`)}
                    value={chosen.days === null || chosen.days === undefined ? "" : String(chosen.days)}
                    inputMode="numeric"
                    maxLength={3}
                    onChange={(e) => storeDays(s.code, e.target.value)}
                    className={field}
                    {...invalid(`store-${s.code}`)}
                  />
                  {error(`store-${s.code}`)}
                </div>
              )}
            </div>
          );
        })}
      </fieldset>

      <div>
        <label htmlFor={id("warnings")} className={labelCss}>
          Warnings (as written)
        </label>
        <textarea id={id("warnings")} rows={2} maxLength={500} value={draft.warnings ?? ""} onChange={(e) => set({ warnings: e.target.value })} className={field} />
      </div>
      <div>
        <label htmlFor={id("notes")} className={labelCss}>
          Notes (as written)
        </label>
        <textarea id={id("notes")} rows={2} maxLength={1000} value={draft.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} className={field} />
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-4 py-2 font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none">
          Cancel
        </button>
        <button type="button" onClick={done} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none">
          Done
        </button>
      </div>
    </Drawer>
  );
}
