/**
 * The builder's working copy of a prescription (M4-P6) and its conversions to and from the API.
 * Pure functions only, so the keyboard flow and autosave are tested without a screen. Input
 * hints only: the API checks every rule again.
 */

import type { AdviceInput, ItemInput, PreparationPhrase, Prescription, PrescriptionDraft, RxTemplate, StoragePhrase } from "./api";

/** A medicine line as the builder holds it: the API's input shape plus a key for React. */
export type Line = ItemInput & { readonly key: string };

/** Advice as typed: one entry per line in each box. */
export interface AdviceText {
  readonly diet: string;
  readonly activity: string;
  readonly return_if: string;
  readonly notes: string;
}

export interface Body {
  readonly lines: readonly Line[];
  readonly advice: AdviceText;
  readonly followUp: string;
  readonly templateId: string | null;
  /** M6b-P3 (R24): the first day of the course, YYYY-MM-DD; "" = the day it is issued. */
  readonly startsOn: string;
}

export const EMPTY_ADVICE: AdviceText = { diet: "", activity: "", return_if: "", notes: "" };
export const EMPTY_BODY: Body = { lines: [], advice: EMPTY_ADVICE, followUp: "", templateId: null, startsOn: "" };
export const MAX_LINES = 40;

let counter = 0;
/** A key unique within the page (not an ID: the API gives lines their own on save). */
export const newKey = () => `line-${Date.now().toString(36)}-${(counter++).toString(36)}`;

/** Any line-shaped source: a saved line, a favourite, a template's line, a past visit's medicine. */
export interface LineSource {
  readonly medicine_name: string;
  readonly form?: string | null;
  readonly strength?: string | null;
  readonly dose?: string | null;
  readonly frequency?: ItemInput["frequency"];
  readonly frequency_text?: string | null;
  readonly timing?: ItemInput["timing"];
  readonly duration_days?: number | null;
  readonly duration_kind?: ItemInput["duration_kind"];
  readonly quantity?: string | null;
  readonly preparation?: readonly { readonly code: string; readonly text?: string | null }[];
  readonly storage?: readonly { readonly code: string; readonly days?: number | null }[];
  readonly warnings?: string | null;
  readonly notes?: string | null;
  readonly favourite_id?: string | null;
}

/** Copies a line from any source without its IDs. */
export function toLine(item: LineSource, favouriteId?: string | null): Line {
  const line: ItemInput = {
    medicine_name: item.medicine_name,
    form: item.form ?? null,
    strength: item.strength ?? null,
    dose: item.dose ?? null,
    frequency: item.frequency ?? null,
    frequency_text: item.frequency_text ?? null,
    timing: item.timing ?? null,
    duration_days: item.duration_days ?? null,
    // A line saved before M6b-P3 with days only is a number of days (as the API reads it).
    duration_kind: item.duration_kind ?? (item.duration_days === null || item.duration_days === undefined ? null : "DAYS"),
    quantity: item.quantity ?? null,
    preparation: (item.preparation ?? []).map((p) => ({ code: p.code as PreparationPhrase["code"], text: p.text ?? null })),
    storage: (item.storage ?? []).map((s) => ({ code: s.code as StoragePhrase["code"], days: s.days ?? null })),
    warnings: item.warnings ?? null,
    notes: item.notes ?? null,
    favourite_id: favouriteId === undefined ? (item.favourite_id ?? null) : favouriteId,
  };
  return { ...line, key: newKey() };
}

/** The item without the builder's key, as the API takes it. */
export function toInput(line: Line): ItemInput {
  const { key, ...item } = line;
  void key;
  return item;
}

const entries = (text: string) =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s !== "");

export function adviceInput(advice: AdviceText): AdviceInput {
  return {
    diet: entries(advice.diet),
    activity: entries(advice.activity),
    return_if: entries(advice.return_if),
    notes: advice.notes.trim() === "" ? null : advice.notes.trim(),
  };
}

export function adviceText(advice: Partial<AdviceInput> | undefined): AdviceText {
  return {
    diet: (advice?.diet ?? []).join("\n"),
    activity: (advice?.activity ?? []).join("\n"),
    return_if: (advice?.return_if ?? []).join("\n"),
    notes: advice?.notes ?? "",
  };
}

/** The whole draft for `PUT /prescriptions/{id}` (what is not sent is emptied, P2 decision 3A). */
export function draftBody(body: Body, revision: number): PrescriptionDraft {
  return {
    revision,
    items: body.lines.map(toInput),
    advice: adviceInput(body.advice),
    follow_up_date: body.followUp === "" ? null : body.followUp,
    template_id: body.templateId,
    starts_on: body.startsOn === "" ? null : body.startsOn,
  };
}

export function fromPrescription(rx: Prescription): Body {
  return {
    lines: rx.items.map((item) => toLine(item)),
    advice: adviceText(rx.advice),
    followUp: rx.follow_up_date ?? "",
    templateId: rx.template_id ?? null,
    startsOn: rx.starts_on ?? "",
  };
}

/** A template's whole body replaces the draft's (FR-RX-05); its follow-up counts from today. */
export function fromTemplate(template: RxTemplate, today: string, addDays: (date: string, days: number) => string): Body {
  return {
    lines: template.items.map((item) => toLine(item)),
    advice: adviceText(template.advice),
    followUp: template.follow_up_days === null ? "" : addDays(today, template.follow_up_days),
    templateId: template.id,
    startsOn: "",
  };
}

/** Moves line `index` one place up (-1) or down (+1); out of range leaves the list as it is. */
export function moveLine(lines: readonly Line[], index: number, by: -1 | 1): readonly Line[] {
  const to = index + by;
  if (index < 0 || index >= lines.length || to < 0 || to >= lines.length) return lines;
  const next = [...lines];
  const [moved] = next.splice(index, 1);
  if (moved !== undefined) next.splice(to, 0, moved);
  return next;
}

export function isEmpty(body: Body): boolean {
  const advice = adviceInput(body.advice);
  return (
    body.lines.length === 0 &&
    (advice.diet ?? []).length === 0 &&
    (advice.activity ?? []).length === 0 &&
    (advice.return_if ?? []).length === 0 &&
    advice.notes === null
  );
}

/** Days between two calendar dates (YYYY-MM-DD), for the template's follow-up. */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}
