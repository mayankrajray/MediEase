/**
 * The structured vocabulary for staff (spec §3), in English. These are how the doctor picks a
 * code; what the patient reads comes from the API's phrasebook (R20), never from here.
 */

import type { Frequency, PreparationPhrase, StoragePhrase, Timing } from "./api";

export const FREQUENCIES: readonly { readonly code: Frequency; readonly label: string }[] = [
  { code: "1-0-0", label: "1-0-0 · morning" },
  { code: "0-1-0", label: "0-1-0 · afternoon" },
  { code: "0-0-1", label: "0-0-1 · night" },
  { code: "1-0-1", label: "1-0-1 · morning and night" },
  { code: "1-1-1", label: "1-1-1 · three times" },
  { code: "1-1-1-1", label: "1-1-1-1 · four times" },
  { code: "SOS", label: "SOS · when needed" },
  { code: "ONCE", label: "Once only" },
  { code: "CUSTOM", label: "Custom…" },
];

export const TIMINGS: readonly { readonly code: Timing; readonly label: string }[] = [
  { code: "AFTER_FOOD", label: "After food" },
  { code: "BEFORE_FOOD", label: "Before food" },
  { code: "WITH_FOOD", label: "With food" },
  { code: "EMPTY_STOMACH", label: "Empty stomach" },
  { code: "BEDTIME", label: "At bedtime" },
  { code: "ANY", label: "Any time" },
];

export const PREPARATIONS: readonly { readonly code: PreparationPhrase["code"]; readonly label: string; readonly text?: string }[] = [
  { code: "SHAKE_WELL", label: "Shake well" },
  { code: "DILUTE_IN_WATER", label: "Mix in water", text: "Amount of water, e.g. 10 ml" },
  { code: "DISSOLVE", label: "Dissolve in water" },
  { code: "CHEW", label: "Chew" },
  { code: "DO_NOT_CRUSH", label: "Do not crush" },
  { code: "CUSTOM", label: "Other instruction", text: "The instruction" },
];

export const STORAGES: readonly { readonly code: StoragePhrase["code"]; readonly label: string }[] = [
  { code: "ROOM_TEMP", label: "Room temperature" },
  { code: "REFRIGERATE", label: "Refrigerate" },
  { code: "AWAY_FROM_LIGHT", label: "Away from light" },
  { code: "DISCARD_AFTER_DAYS", label: "Discard after days" },
];

const BY_DIGITS: Readonly<Record<string, Frequency>> = {
  "100": "1-0-0",
  "010": "0-1-0",
  "001": "0-0-1",
  "101": "1-0-1",
  "111": "1-1-1",
  "1111": "1-1-1-1",
};

/**
 * What the doctor typed in the frequency field (spec §6, keyboard-first): `101`, `1-0-1`,
 * `s`/`sos`, `o`/`once`, `c`/`custom`. Anything else is not a code (the field shows a hint).
 */
export function parseFrequency(typed: string): Frequency | undefined {
  const text = typed.trim().toLowerCase();
  if (text === "") return undefined;
  const digits = text.replace(/[\s-]/g, "");
  if (BY_DIGITS[digits] !== undefined) return BY_DIGITS[digits];
  if (text === "s" || text === "sos") return "SOS";
  if (text === "o" || text === "once") return "ONCE";
  if (text === "c" || text === "custom") return "CUSTOM";
  return FREQUENCIES.find((f) => f.code.toLowerCase() === text)?.code;
}

export function frequencyLabel(code: Frequency | null, custom: string | null): string {
  if (code === null) return "";
  if (code === "CUSTOM") return custom ?? "Custom";
  return FREQUENCIES.find((f) => f.code === code)?.label ?? code;
}

export function timingLabel(code: Timing | null): string {
  return code === null ? "" : (TIMINGS.find((t) => t.code === code)?.label ?? code);
}

/** "Syrup X · 5 ml · 1-0-1 · after food · 5 days", for lists and history. */
export function lineSummary(item: {
  readonly medicine_name: string;
  readonly dose?: string | null | undefined;
  readonly frequency?: Frequency | null | undefined;
  readonly frequency_text?: string | null | undefined;
  readonly timing?: Timing | null | undefined;
  readonly duration_days?: number | null | undefined;
}): string {
  const parts = [
    item.medicine_name,
    item.dose ?? "",
    item.frequency ? (item.frequency === "CUSTOM" ? (item.frequency_text ?? "") : item.frequency) : "",
    item.timing ? timingLabel(item.timing).toLowerCase() : "",
    item.duration_days ? `${item.duration_days} ${item.duration_days === 1 ? "day" : "days"}` : "",
  ];
  return parts.filter((p) => p !== "").join(" · ");
}
