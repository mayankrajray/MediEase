"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type Ref } from "react";

import { useSession } from "@/features/auth/SessionProvider";

import { useRxApi, type Suggestion } from "./api";

const MIN_QUERY = 2;
const MAX_QUERY = 50;
const DEBOUNCE_MS = 200;

/**
 * The medicine name (FR-RX-10, spec §6): free text, with suggestions from this doctor's
 * favourites first and then this clinic's own history (M4-P3) — never a drug database, never a
 * dose. WAI-ARIA combobox: ArrowDown/ArrowUp move through the list, Enter picks the highlighted
 * one, Escape closes it. With nothing highlighted, Enter belongs to the entry row (adds the line).
 */
export function MedicineCombobox({
  id,
  value,
  onChange,
  onPick,
  inputRef,
  invalid,
  describedBy,
}: Readonly<{
  id: string;
  value: string;
  onChange: (value: string) => void;
  /** A suggestion was chosen: a favourite brings its whole line, a history name only the name. */
  onPick: (suggestion: Suggestion) => void;
  inputRef?: Ref<HTMLInputElement>;
  invalid?: boolean;
  describedBy?: string;
}>) {
  const api = useRxApi();
  const { endSession } = useSession();
  const listId = useId();
  const [items, setItems] = useState<readonly Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const typed = useRef(false);

  useEffect(() => {
    const q = value.trim();
    if (!typed.current || q.length < MIN_QUERY || q.length > MAX_QUERY) {
      setItems([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.suggestions(q, controller.signal).then(
        (found) => {
          setItems(found);
          setActive(-1);
          setOpen(found.length > 0);
        },
        (failure: unknown) => {
          // Suggestions are a help, not a step: a failure leaves the field as plain text.
          if (!controller.signal.aborted) endSession(failure);
        },
      );
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [api, value, endSession]);

  const shown = open && items.length > 0;

  function pick(s: Suggestion) {
    typed.current = false;
    setOpen(false);
    setActive(-1);
    onPick(s);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" && items.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % items.length);
    } else if (event.key === "ArrowUp" && shown) {
      event.preventDefault();
      setActive((i) => (i <= 0 ? items.length - 1 : i - 1));
    } else if (event.key === "Escape" && shown) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      setActive(-1);
    } else if (event.key === "Enter" && shown && active >= 0) {
      const chosen = items[active];
      if (chosen !== undefined) {
        event.preventDefault();
        event.stopPropagation();
        pick(chosen);
      }
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        id={id}
        type="text"
        role="combobox"
        autoComplete="off"
        maxLength={200}
        aria-autocomplete="list"
        aria-expanded={shown}
        aria-controls={listId}
        aria-activedescendant={shown && active >= 0 ? `${listId}-${active}` : undefined}
        aria-invalid={invalid === true ? true : undefined}
        aria-describedby={describedBy}
        value={value}
        onChange={(event) => {
          typed.current = true;
          onChange(event.target.value);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => setOpen(false)}
        className="w-full rounded border border-slate-500 px-2 py-1.5"
      />
      <ul
        id={listId}
        role="listbox"
        aria-label="Suggestions from your favourites and this clinic's prescriptions"
        hidden={!shown}
        className="absolute z-20 mt-1 max-h-64 w-full min-w-64 overflow-y-auto rounded border border-slate-400 bg-white py-1 shadow-lg"
      >
        {items.map((s, i) => (
          <li
            key={`${s.source}-${s.name}-${s.favourite_id ?? ""}`}
            id={`${listId}-${i}`}
            role="option"
            aria-selected={i === active}
            // mousedown, so the input's blur does not close the list before the click lands.
            onMouseDown={(event) => {
              event.preventDefault();
              pick(s);
            }}
            className="cursor-pointer px-3 py-1.5 aria-selected:bg-blue-100"
          >
            {s.name}{" "}
            <span className="ml-1 text-sm text-slate-700">{s.source === "FAVOURITE" ? "· favourite" : "· used before"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
