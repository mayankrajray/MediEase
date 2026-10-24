/**
 * The structured vocabulary for staff (spec §3), in English. These are how the doctor picks a
 * code; what the patient reads comes from the API's phrasebook (R20), never from here.
 *
 * M6b-P3 (prescriptions R21, D8): which slot each digit of a pattern stands for is the API's, read
 * from `GET /rx-vocabulary` (`Vocabulary`). Nothing here keeps a copy of the slot sets, so the
 * editor reads `1-1-0` exactly as the PDF, the patient page and the plan will. The words below
 * only name a slot or a code for the doctor.
 */

import type { DurationKind, Frequency, LineWarning, PreparationPhrase, Slot, StoragePhrase, Timing, Vocabulary } from "./api";

/** The doctor's word for each slot (a label, not the order of a day: that is the API's). */
export const SLOT_WORDS: Readonly<Record<Slot, string>> = {
  MORNING: "morning",
  AFTERNOON: "afternoon",
  EVENING: "evening",
  NIGHT: "night",
};

const SPECIAL_LABELS: Readonly<Record<string, string>> = {
  SOS: "SOS · when needed",
  ONCE: "Once only",
  CUSTOM: "Custom…",
};

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
  { code: "WITH_WATER", label: "Take with water" },
  { code: "WITH_WARM_WATER", label: "Take with warm water" },
  { code: "WITH_MILK", label: "Take with milk" },
  { code: "CUSTOM", label: "Other instruction", text: "The instruction" },
];

export const STORAGES: readonly { readonly code: StoragePhrase["code"]; readonly label: string }[] = [
  { code: "ROOM_TEMP", label: "Room temperature" },
  { code: "REFRIGERATE", label: "Refrigerate" },
  { code: "AWAY_FROM_LIGHT", label: "Away from light" },
  { code: "DISCARD_AFTER_DAYS", label: "Discard after days" },
];

/** Prescriptions R23: how long, as the doctor chooses; "" is not stated. */
export const DURATION_KINDS: readonly { readonly code: DurationKind | ""; readonly label: string }[] = [
  { code: "DAYS", label: "Number of days" },
  { code: "UNTIL_REVIEW", label: "Until review" },
  { code: "ONGOING", label: "Ongoing" },
  { code: "", label: "Not stated" },
];

/** Prescriptions R22: notes for the doctor only; issuing is never refused for them. */
export const WARNING_TEXT: Readonly<Record<LineWarning, string>> = {
  BEDTIME_WITHOUT_NIGHT: "At bedtime, but the frequency has no night dose. It will be shown as written.",
  BEDTIME_WITH_OTHER_SLOTS: "At bedtime, with doses at other times too. It will be shown as written.",
  BEDTIME_UNTIMED: "At bedtime, with no time of day in the frequency. It will be shown as written.",
};

/** The slots a canonical pattern marks, read against the API's slot set for its length. */
export function frequencySlots(code: Frequency | null | undefined, vocabulary: Vocabulary | undefined): readonly Slot[] {
  if (code === null || code === undefined || vocabulary === undefined) return [];
  const digits = code.split("-");
  const set = vocabulary.slot_sets.find((s) => s.length === digits.length);
  if (set === undefined || digits.some((d) => d !== "0" && d !== "1")) return [];
  return set.slots.filter((_, i) => digits[i] === "1");
}

/**
 * What the doctor typed in the frequency field (spec §6, keyboard-first): any pattern of 0 and 1
 * of a length the API publishes, with at least one 1 (`110`, `1-0-1`, `1 0 1 1`), or `s`/`sos`,
 * `o`/`once`, `c`/`custom`. Anything else (`000`, `2-0-2`, `½-0-½`) is not a code: write it as
 * custom. Before the vocabulary has loaded only the three words are read.
 */
export function parseFrequency(typed: string, vocabulary: Vocabulary | undefined): Frequency | undefined {
  const text = typed.trim().toLowerCase();
  if (text === "") return undefined;
  if (text === "s" || text === "sos") return "SOS";
  if (text === "o" || text === "once") return "ONCE";
  if (text === "c" || text === "custom") return "CUSTOM";
  const digits = text.replace(/[\s-]/g, "");
  if (vocabulary === undefined || !/^[01]+$/.test(digits) || !digits.includes("1")) return undefined;
  if (!vocabulary.slot_sets.some((s) => s.length === digits.length)) return undefined;
  return digits.split("").join("-");
}

/** "1-1-0 · morning and afternoon"; a custom one is the doctor's words. */
export function frequencyLabel(code: Frequency | null, custom: string | null, vocabulary: Vocabulary | undefined): string {
  if (code === null) return "";
  if (code === "CUSTOM") return custom ?? "Custom";
  const special = SPECIAL_LABELS[code];
  if (special !== undefined) return special;
  const words = frequencySlots(code, vocabulary).map((s) => SLOT_WORDS[s]);
  if (words.length === 0) return code;
  const joined = words.length === 1 ? (words[0] as string) : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1] as string}`;
  return `${code} · ${joined}`;
}

export function timingLabel(code: Timing | null): string {
  return code === null ? "" : (TIMINGS.find((t) => t.code === code)?.label ?? code);
}

/** Days, "until review", "ongoing" or nothing (not stated), as the line summary says it. */
export function durationLabel(kind: DurationKind | null | undefined, days: number | null | undefined): string {
  if (kind === "UNTIL_REVIEW") return "until review";
  if (kind === "ONGOING") return "ongoing";
  if (days !== null && days !== undefined) return `${days} ${days === 1 ? "day" : "days"}`;
  return "";
}

/**
 * The Days field of the entry row: a number of days, `r`/`review` for until review,
 * `g`/`ongoing` for ongoing, empty for not stated. Undefined when it is none of these.
 */
export function parseDuration(typed: string): { readonly kind: DurationKind | null; readonly days: number | null } | undefined {
  const text = typed.trim().toLowerCase();
  if (text === "") return { kind: null, days: null };
  if (text === "r" || text === "review" || text === "until review") return { kind: "UNTIL_REVIEW", days: null };
  if (text === "g" || text === "ongoing") return { kind: "ONGOING", days: null };
  if (/^\d+$/.test(text) && Number(text) >= 1 && Number(text) <= 365) return { kind: "DAYS", days: Number(text) };
  return undefined;
}

/** "Syrup X · 5 ml · 1-0-1 · after food · 5 days", for lists and history. */
export function lineSummary(item: {
  readonly medicine_name: string;
  readonly dose?: string | null | undefined;
  readonly frequency?: Frequency | null | undefined;
  readonly frequency_text?: string | null | undefined;
  readonly timing?: Timing | null | undefined;
  readonly duration_days?: number | null | undefined;
  readonly duration_kind?: DurationKind | null | undefined;
}): string {
  const parts = [
    item.medicine_name,
    item.dose ?? "",
    item.frequency ? (item.frequency === "CUSTOM" ? (item.frequency_text ?? "") : item.frequency) : "",
    item.timing ? timingLabel(item.timing).toLowerCase() : "",
    durationLabel(item.duration_kind, item.duration_days),
  ];
  return parts.filter((p) => p !== "").join(" · ");
}
