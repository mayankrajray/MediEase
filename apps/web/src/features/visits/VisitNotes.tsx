"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useRxApi, type Visit, type VisitChange, type Vitals } from "@/features/prescriptions/api";

import { saveText, useAutosave } from "./useAutosave";

type VitalKey = keyof Vitals;

/** The vitals (FR-VIS-02): the unit is fixed by the key; the bounds only catch typing slips. */
export const VITALS: readonly { key: VitalKey; label: string; unit: string; low: number; high: number; whole: boolean }[] = [
  { key: "bp_systolic", label: "BP systolic", unit: "mmHg", low: 40, high: 300, whole: true },
  { key: "bp_diastolic", label: "BP diastolic", unit: "mmHg", low: 20, high: 200, whole: true },
  { key: "pulse", label: "Pulse", unit: "/min", low: 20, high: 250, whole: true },
  { key: "temp_c", label: "Temperature", unit: "°C", low: 25, high: 45, whole: false },
  { key: "spo2", label: "SpO₂", unit: "%", low: 50, high: 100, whole: true },
  { key: "resp_rate", label: "Breathing", unit: "/min", low: 4, high: 80, whole: true },
  { key: "weight_kg", label: "Weight", unit: "kg", low: 0.3, high: 400, whole: false },
  { key: "height_cm", label: "Height", unit: "cm", low: 20, high: 260, whole: false },
];

const TEXTS = [
  { key: "chief_complaint", label: "Chief complaint", rows: 1, max: 500 },
  { key: "findings", label: "Findings", rows: 3, max: 5000 },
  { key: "diagnosis", label: "Diagnosis", rows: 1, max: 1000 },
  { key: "notes", label: "Notes", rows: 3, max: 5000 },
] as const;

type TextKey = (typeof TEXTS)[number]["key"];
type Notes = Record<TextKey, string> & { readonly vitals: Readonly<Record<VitalKey, string>> };

export function vitalProblem(spec: (typeof VITALS)[number], raw: string): string | undefined {
  const text = raw.trim();
  if (text === "") return undefined;
  const value = Number(text);
  if (!Number.isFinite(value) || (spec.whole && !Number.isInteger(value)) || value < spec.low || value > spec.high) {
    return `${spec.whole ? "A whole number" : "A number"} from ${spec.low} to ${spec.high}`;
  }
  return undefined;
}

function notesOf(visit: Visit): Notes {
  const vitals = Object.fromEntries(
    VITALS.map((v) => [v.key, visit.vitals[v.key] === undefined ? "" : String(visit.vitals[v.key])]),
  ) as Record<VitalKey, string>;
  return {
    chief_complaint: visit.chief_complaint ?? "",
    findings: visit.findings ?? "",
    diagnosis: visit.diagnosis ?? "",
    notes: visit.notes ?? "",
    vitals,
  };
}

/** The change to send: every text, and the vitals only when all of them read as numbers in range. */
export function changeOf(notes: Notes): Omit<VisitChange, "revision"> {
  const text = (s: string) => (s.trim() === "" ? null : s.trim());
  const vitalsOk = VITALS.every((v) => vitalProblem(v, notes.vitals[v.key]) === undefined);
  const vitals: Record<string, number> = {};
  for (const v of VITALS) {
    const raw = notes.vitals[v.key].trim();
    if (raw !== "") vitals[v.key] = Number(raw);
  }
  return {
    chief_complaint: text(notes.chief_complaint),
    findings: text(notes.findings),
    diagnosis: text(notes.diagnosis),
    notes: text(notes.notes),
    ...(vitalsOk ? { vitals } : {}),
  };
}

/**
 * The visit's notes and vitals (FR-VIS-02), saved as the doctor types (decision 2A) with the
 * revision guard (VIS_STALE). Read only once locked (FR-VIS-05) or for anyone but its doctor.
 */
export function VisitNotes({
  visit,
  editable,
  register,
  onReload,
}: Readonly<{ visit: Visit; editable: boolean; register: (flush: () => Promise<boolean>) => () => void; onReload: () => void }>) {
  const api = useRxApi();
  const { endSession } = useSession();
  const base = useId();
  const [notes, setNotes] = useState<Notes>(() => notesOf(visit));
  const revision = useRef(visit.revision);

  const save = useCallback(
    async (next: Notes) => {
      const saved = await api.updateVisit(visit.id, { revision: revision.current, ...changeOf(next) });
      revision.current = saved.revision;
    },
    [api, visit.id],
  );
  const autosave = useAutosave<Notes>(save, endSession);
  const { flush } = autosave;
  const stale = autosave.state.kind === "stale";
  useEffect(() => register(flush), [register, flush]);

  function update(next: Notes) {
    setNotes(next);
    autosave.change(next);
  }

  if (!editable) {
    return (
      <section aria-labelledby="notes-heading" className="space-y-2">
        <h2 id="notes-heading" className="text-lg font-bold">
          Notes
        </h2>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
          {TEXTS.map((t) => (
            <div key={t.key} className="contents">
              <dt className="font-medium">{t.label}</dt>
              <dd className="whitespace-pre-line">{notes[t.key] === "" ? "—" : notes[t.key]}</dd>
            </div>
          ))}
          <dt className="font-medium">Vitals</dt>
          <dd>
            {VITALS.filter((v) => notes.vitals[v.key] !== "")
              .map((v) => `${v.label} ${notes.vitals[v.key]} ${v.unit}`)
              .join(" · ") || "—"}
          </dd>
        </dl>
      </section>
    );
  }

  const vitalError = (v: (typeof VITALS)[number]) => vitalProblem(v, notes.vitals[v.key]);
  return (
    <section aria-labelledby="notes-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="notes-heading" className="text-lg font-bold">
          Notes
        </h2>
        <p role="status" aria-live="polite" className="text-sm text-slate-800">
          {stale ? "" : saveText(autosave.state)}
        </p>
      </div>
      {stale && (
        <div role="alert" className="rounded border border-amber-700 bg-amber-50 p-3">
          <p className="font-medium">{saveText(autosave.state)}</p>
          <button type="button" onClick={onReload} className="mt-2 rounded border border-amber-900 bg-white px-3 py-1.5 font-medium">
            Reload
          </button>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        {TEXTS.map((t) => (
          <div key={t.key}>
            <label htmlFor={`${base}-${t.key}`} className="block font-medium">
              {t.label}
            </label>
            {t.rows === 1 ? (
              <input
                id={`${base}-${t.key}`}
                value={notes[t.key]}
                maxLength={t.max}
                disabled={stale}
                onChange={(e) => update({ ...notes, [t.key]: e.target.value })}
                onBlur={() => void flush()}
                className="w-full rounded border border-slate-500 px-2 py-1.5"
              />
            ) : (
              <textarea
                id={`${base}-${t.key}`}
                rows={t.rows}
                value={notes[t.key]}
                maxLength={t.max}
                disabled={stale}
                onChange={(e) => update({ ...notes, [t.key]: e.target.value })}
                onBlur={() => void flush()}
                className="w-full rounded border border-slate-500 px-2 py-1.5"
              />
            )}
          </div>
        ))}
      </div>
      <fieldset>
        <legend className="font-medium">Vitals</legend>
        <div className="grid grid-cols-4 gap-2">
          {VITALS.map((v) => {
            const problem = vitalError(v);
            const id = `${base}-${v.key}`;
            return (
              <div key={v.key}>
                <label htmlFor={id} className="block text-sm font-medium">
                  {v.label} ({v.unit})
                </label>
                <input
                  id={id}
                  value={notes.vitals[v.key]}
                  inputMode="decimal"
                  maxLength={6}
                  disabled={stale}
                  aria-invalid={problem === undefined ? undefined : true}
                  aria-describedby={problem === undefined ? undefined : `${id}-error`}
                  onChange={(e) => update({ ...notes, vitals: { ...notes.vitals, [v.key]: e.target.value } })}
                  onBlur={() => void flush()}
                  className="w-full rounded border border-slate-500 px-2 py-1"
                />
                {problem !== undefined && (
                  <p id={`${id}-error`} className="text-xs font-medium text-red-900">
                    {problem}; vitals not saved until it is fixed
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </fieldset>
      {autosave.state.kind === "failed" && <ErrorNotice error={autosave.state.error} />}
    </section>
  );
}
