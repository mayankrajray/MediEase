"use client";

import { Search as SearchIcon, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { INPUT } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
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
    <div className="relative w-full min-w-0 max-w-md">
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
        className={`${INPUT} pl-9`}
      />
      <SearchIcon aria-hidden="true" className="pointer-events-none absolute left-3 top-3 size-4 text-slate-500" />
      {expanded && (
        <div
          // Clicks inside the popup must not blur the input before they land.
          onMouseDown={(event) => event.preventDefault()}
          className="absolute z-30 mt-1 max-h-96 w-full overflow-y-auto overflow-x-hidden rounded-xl border border-line bg-surface shadow-pop"
        >
          <ul id={listId} role="listbox" aria-label="Patients" aria-busy={search.status === "loading"}>
            {items.map((patient, index) => (
              <li
                key={patient.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === active}
                onClick={() => openPatient(patient)}
                className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 transition-colors duration-150 hover:bg-slate-50 aria-selected:bg-brand-50 motion-reduce:transition-none"
              >
                <Avatar name={patient.full_name} size="sm" />
                <span className="min-w-0">
                  <span className="block break-words font-semibold text-slate-900">{patient.full_name}</span>{" "}
                  <span className="block text-sm tabular-nums text-slate-700">
                    {patient.code} · {ageText(patient)} · {maskPhone(patient.phone_e164)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          {search.status === "loading" && (
            <p role="status" className="flex items-center gap-2 px-3 py-3 text-slate-700">
              <Spinner /> Searching…
            </p>
          )}
          {search.status === "done" && items.length === 0 && (
            <div className="space-y-2 px-3 py-3">
              <p role="status" className="font-medium text-slate-900">No patient matches.</p>
              <p className="text-sm text-slate-700">Try the phone number or the code, or register the patient.</p>
              {openRegister !== null && (
                <Button size="sm" onClick={registerFromSearch} icon={<UserPlus className="size-4" />}>
                  Register patient
                </Button>
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
