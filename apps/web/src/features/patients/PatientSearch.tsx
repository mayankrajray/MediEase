"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { maskPhone } from "@/lib/format/phone";

import { usePatientApi } from "./api";
import { ageText, looksLikePhone, type Patient } from "./fields";
import { patientPath } from "./RegisterPatientDrawer";
import { useRegisterPatient } from "./RegisterPatientProvider";

export const SEARCH_DEBOUNCE_MS = 250;
export const RESULTS_PATH = "/patients";

/** The answer for one lookup text; a different text means its answer is still on the way. */
type Answer =
  | { readonly q: string; readonly status: "done"; readonly items: readonly Patient[] }
  | { readonly q: string; readonly status: "failed"; readonly error: unknown };

type Search =
  | { readonly status: "idle" }
  | { readonly status: "loading" }
  | { readonly status: "done"; readonly items: readonly Patient[] }
  | { readonly status: "failed"; readonly error: unknown };

/** True when a key press is typing into something, so "/" must not steal focus. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/**
 * The patient search in the header (FR-PAT-04, spec §6): `/` focuses it from any
 * clinic screen. It follows the WAI-ARIA combobox pattern: arrow keys move through
 * up to 20 matches, Enter opens one, Enter with none chosen opens the results
 * page, Escape closes. Each keystroke waits `debounceMs` and cancels the request
 * before it. Phones in the list are masked; the profile shows them in full.
 */
export function PatientSearch({ debounceMs = SEARCH_DEBOUNCE_MS }: { debounceMs?: number }) {
  const router = useRouter();
  const { endSession } = useSession();
  const api = usePatientApi();
  const openRegister = useRegisterPatient();
  const [text, setText] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const optionId = (index: number) => `${listId}-option-${index}`;

  useEffect(() => {
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !isTyping(event.target)) {
        event.preventDefault();
        input.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const q = text.trim();
    if (q === "") return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.lookup(q, controller.signal).then(
        (items) => {
          setAnswer({ q, status: "done", items });
          setActive(-1);
        },
        (error: unknown) => {
          if (controller.signal.aborted || endSession(error)) return;
          setAnswer({ q, status: "failed", error });
        },
      );
    }, debounceMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, api, debounceMs, endSession]);

  const q = text.trim();
  const search: Search =
    q === ""
      ? { status: "idle" }
      : answer === null || answer.q !== q
        ? { status: "loading" }
        : answer.status === "done"
          ? { status: "done", items: answer.items }
          : { status: "failed", error: answer.error };
  const items = search.status === "done" ? search.items : [];
  const expanded = open && text.trim() !== "";

  function reset() {
    setText("");
    setOpen(false);
    setActive(-1);
  }

  function openPatient(patient: Patient) {
    reset();
    router.push(patientPath(patient.id));
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setOpen(true);
        if (items.length > 0) setActive((i) => (i + 1) % items.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        if (items.length > 0) setActive((i) => (i <= 0 ? items.length - 1 : i - 1));
        break;
      case "Enter": {
        event.preventDefault();
        const chosen = items[active];
        if (chosen !== undefined) {
          openPatient(chosen);
        } else if (text.trim() !== "") {
          const q = text.trim();
          reset();
          router.push(`${RESULTS_PATH}?q=${encodeURIComponent(q)}`);
        }
        break;
      }
      case "Escape":
        if (expanded) setOpen(false);
        else reset();
        break;
    }
  }

  function registerFromSearch() {
    const q = text.trim();
    reset();
    openRegister?.(looksLikePhone(q) ? { phone: q } : { full_name: q });
  }

  return (
    <div className="relative w-full max-w-md">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Find a patient
      </label>
      <input
        id={`${listId}-input`}
        ref={input}
        type="search"
        role="combobox"
        autoComplete="off"
        spellCheck={false}
        placeholder="Find a patient: phone, code or name (press /)"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={expanded && active >= 0 ? optionId(active) : undefined}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
      />
      {expanded && (
        <div
          // Clicks inside the popup must not blur the input before they land.
          onMouseDown={(event) => event.preventDefault()}
          className="absolute z-20 mt-1 max-h-96 w-full overflow-y-auto rounded-lg border border-slate-300 bg-white shadow-lg"
        >
          <ul id={listId} role="listbox" aria-label="Patients" aria-busy={search.status === "loading"}>
            {items.map((patient, index) => (
              <li
                key={patient.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === active}
                onClick={() => openPatient(patient)}
                className="cursor-pointer px-3 py-2 aria-selected:bg-brand-100 hover:bg-slate-100"
              >
                <span className="font-semibold">{patient.full_name}</span>{" "}
                <span className="text-sm text-slate-700">
                  {patient.code} · {ageText(patient)} · {maskPhone(patient.phone_e164)}
                </span>
              </li>
            ))}
          </ul>
          {search.status === "loading" && (
            <p role="status" className="px-3 py-2 text-slate-700">
              Searching…
            </p>
          )}
          {search.status === "done" && items.length === 0 && (
            <div className="space-y-2 px-3 py-2">
              <p role="status">No patient matches.</p>
              {openRegister !== null && (
                <button
                  type="button"
                  onClick={registerFromSearch}
                  className="inline-flex min-h-8 items-center justify-center gap-2 rounded-lg border border-brand-700 bg-white px-3 py-1 text-sm font-medium text-brand-800 transition-colors hover:bg-brand-50 motion-reduce:transition-none"
                >
                  Register patient
                </button>
              )}
            </div>
          )}
          {search.status === "failed" && (
            <div className="p-2">
              <ErrorNotice error={search.error} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
