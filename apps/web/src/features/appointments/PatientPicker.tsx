"use client";

import { useEffect, useId, useRef, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { usePatientApi } from "@/features/patients/api";
import { ageText, type Patient } from "@/features/patients/fields";
import { maskPhone } from "@/lib/format/phone";

export const PICK_DEBOUNCE_MS = 250;

/**
 * Find a patient to book (M3-P5): focused when it appears, a phone, code or name, up to 20
 * matches as buttons. Choosing one is a single interaction (AC6). Phones are masked.
 */
export function PatientPicker({
  onPick,
  debounceMs = PICK_DEBOUNCE_MS,
}: {
  onPick: (patient: Patient) => void;
  debounceMs?: number;
}) {
  const api = usePatientApi();
  const { endSession } = useSession();
  const [text, setText] = useState("");
  const [answer, setAnswer] = useState<
    | { q: string; items: readonly Patient[]; error?: undefined }
    | { q: string; error: unknown; items?: undefined }
    | null
  >(null);
  const input = useRef<HTMLInputElement>(null);
  const id = useId();

  useEffect(() => input.current?.focus(), []);

  useEffect(() => {
    const q = text.trim();
    if (q === "") return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.lookup(q, controller.signal).then(
        (items) => setAnswer({ q, items }),
        (error: unknown) => {
          if (!controller.signal.aborted && !endSession(error)) setAnswer({ q, error });
        },
      );
    }, debounceMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, api, debounceMs, endSession]);

  const q = text.trim();
  const current = answer !== null && answer.q === q ? answer : null;

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block font-medium">
        Patient
      </label>
      <input
        id={id}
        ref={input}
        type="search"
        autoComplete="off"
        spellCheck={false}
        placeholder="Phone, code or name"
        value={text}
        onChange={(event) => setText(event.target.value)}
        className="w-full rounded border border-slate-500 px-3 py-2"
      />
      {q !== "" && current === null && (
        <p role="status" className="text-slate-700">
          Searching…
        </p>
      )}
      {current?.error !== undefined && <ErrorNotice error={current.error} />}
      {current?.items !== undefined &&
        (current.items.length === 0 ? (
          <p role="status">No patient matches. Register them from the header first.</p>
        ) : (
          <ul aria-label="Matching patients" className="divide-y divide-slate-200 rounded border border-slate-300">
            {current.items.map((patient) => (
              <li key={patient.id}>
                <button
                  type="button"
                  onClick={() => onPick(patient)}
                  className="w-full px-3 py-2 text-left hover:bg-slate-100 focus:bg-blue-100"
                >
                  <span className="font-semibold">{patient.full_name}</span>{" "}
                  <span className="text-sm text-slate-700">
                    {patient.code} · {ageText(patient)} · {maskPhone(patient.phone_e164)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
