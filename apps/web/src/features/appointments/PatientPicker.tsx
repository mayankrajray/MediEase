"use client";

import { Search, SearchX } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { INPUT, LABEL } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { usePatientApi } from "@/features/patients/api";
import { ageText, type Patient } from "@/features/patients/fields";
import { maskPhone } from "@/lib/format/phone";

export const PICK_DEBOUNCE_MS = 250;

/**
 * Find a patient to book (M3-P5): focused when it appears, a phone, code or name, up to 20
 * matches as buttons. Choosing one is a single interaction (AC6). Phones are masked.
 * M7c-P7 (M6): a search icon, initials and 44 px rows, a spinner while searching.
 */
export function PatientPicker({
  onPick,
  debounceMs = PICK_DEBOUNCE_MS,
  inputId,
  hideLabel = false,
}: {
  onPick: (patient: Patient) => void;
  debounceMs?: number;
  /** Lets the parent move focus back here (the booking drawer's Confirm without a patient). */
  inputId?: string;
  /** The label for screen readers only, where a heading already says "Patient". */
  hideLabel?: boolean;
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
  const ownId = useId();
  const id = inputId ?? ownId;

  // Outside a modal this focuses at once; inside Drawer/Dialog, data-autofocus does it again
  // after the modal opens, which is what sticks.
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
      <label htmlFor={id} className={hideLabel ? "sr-only" : LABEL}>
        Patient
      </label>
      <div className="relative">
        <input
          id={id}
          ref={input}
          data-autofocus
          type="search"
          autoComplete="off"
          spellCheck={false}
          placeholder="Phone, code or name"
          value={text}
          onChange={(event) => setText(event.target.value)}
          className={`${INPUT} pl-9`}
        />
        <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-3 size-4 text-slate-500" />
      </div>
      {q !== "" && current === null && (
        <p role="status" className="flex items-center gap-2 text-sm text-slate-700">
          <Spinner /> Searching…
        </p>
      )}
      {current?.error !== undefined && <ErrorNotice error={current.error} />}
      {current?.items !== undefined &&
        (current.items.length === 0 ? (
          <p role="status" className="flex items-start gap-2 rounded-lg border border-dashed border-slate-300 px-3 py-3 text-sm text-slate-700">
            <SearchX aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
            No patient matches. Register them from the header first.
          </p>
        ) : (
          <ul aria-label="Matching patients" className="max-h-72 divide-y divide-line overflow-y-auto rounded-lg border border-line bg-surface">
            {current.items.map((patient) => (
              <li key={patient.id}>
                <button
                  type="button"
                  onClick={() => onPick(patient)}
                  className="flex min-h-11 w-full items-center gap-3 px-3 py-2 text-left transition-colors duration-150 hover:bg-slate-50 focus-visible:bg-brand-50 motion-reduce:transition-none"
                >
                  <Avatar name={patient.full_name} size="sm" />
                  <span className="min-w-0">
                    <span className="block break-words font-semibold text-slate-900">{patient.full_name}</span>{" "}
                    <span className="block text-sm tabular-nums text-slate-700">
                      {patient.code} · {ageText(patient)} · {maskPhone(patient.phone_e164)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
