/**
 * Pure helpers for the patient screens: labels, ages on the clinic's own date, the
 * form draft and its request bodies, and reading the API's patient errors.
 * Input hints only (apps/web/CLAUDE.md): the API decides every rule again.
 */

import { ApiError } from "@/lib/api/client";
import { fieldErrors, REQ_VALIDATION_FAILED } from "@/lib/api/field-errors";
import type { components } from "@/lib/api/schema";

export type Patient = components["schemas"]["Patient"];
export type NewPatient = components["schemas"]["NewPatient"];
export type PatientUpdate = components["schemas"]["PatientUpdate"];
export type PatientCandidate = components["schemas"]["PatientCandidate"];
export type Sex = components["schemas"]["Sex"];
export type Language = components["schemas"]["Language"];

export const PAT_PHONE_INVALID = "PAT_PHONE_INVALID";
export const PAT_PHONE_EXISTS = "PAT_PHONE_EXISTS";
export const PAT_GUARDIAN_REQUIRED = "PAT_GUARDIAN_REQUIRED";
export const PAT_OPTED_OUT = "PAT_OPTED_OUT";
export const PAT_NOT_OPTED_OUT = "PAT_NOT_OPTED_OUT";
export const REQ_NOT_FOUND = "REQ_NOT_FOUND";

export const SEX_LABELS: Readonly<Record<Sex, string>> = {
  FEMALE: "Female",
  MALE: "Male",
  OTHER: "Other",
  UNDISCLOSED: "Prefer not to say",
};

export const LANGUAGE_LABELS: Readonly<Record<Language, string>> = {
  en: "English",
  hi: "Hindi",
};

const ADULT_AGE = 18;

/** Today's date (YYYY-MM-DD) in the clinic's zone, never the browser's. Unknown zones fall back to UTC. */
export function clinicToday(timeZone: string, now: Date = new Date()): string {
  const format = (zone: string) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  try {
    return format(timeZone);
  } catch {
    return format("UTC");
  }
}

/** Completed years from a date of birth to `today` (both YYYY-MM-DD); undefined if unreadable. */
export function ageOn(dateOfBirth: string, today: string): number | undefined {
  const born = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateOfBirth);
  const now = /^(\d{4})-(\d{2})-(\d{2})$/.exec(today);
  if (born === null || now === null) return undefined;
  const [, by, bm, bd] = born.map(Number) as [number, number, number, number];
  const [, ny, nm, nd] = now.map(Number) as [number, number, number, number];
  const hadBirthday = nm > bm || (nm === bm && nd >= bd);
  return ny - by - (hadBirthday ? 0 : 1);
}

/** "6 years", "1 year", "about 47 years" (only an age was recorded). */
export function ageText(patient: Pick<Patient, "age_years" | "age_is_estimated">): string {
  const years = `${patient.age_years} ${patient.age_years === 1 ? "year" : "years"}`;
  return patient.age_is_estimated ? `about ${years}` : years;
}

/** Whether a lookup text reads as a phone (7 or more digits), as the API reads it (spec R5). */
export function looksLikePhone(text: string): boolean {
  return /^\d{7,}$/.test(text.replace(/[\s\-+()]/g, ""));
}

export type AgeMode = "dob" | "age";

/** The registration and edit form, as text the person typed. */
export interface PatientDraft {
  readonly full_name: string;
  readonly phone: string;
  readonly sex: Sex | "";
  readonly ageMode: AgeMode;
  readonly date_of_birth: string;
  readonly age_years: string;
  readonly guardian_name: string;
  readonly language: Language;
}

export const EMPTY_DRAFT: PatientDraft = {
  full_name: "",
  phone: "",
  sex: "",
  ageMode: "dob",
  date_of_birth: "",
  age_years: "",
  guardian_name: "",
  language: "en",
};

export function draftFromPatient(patient: Patient): PatientDraft {
  return {
    full_name: patient.full_name,
    phone: patient.phone_e164,
    sex: patient.sex,
    ageMode: patient.date_of_birth === null ? "age" : "dob",
    date_of_birth: patient.date_of_birth ?? "",
    age_years: patient.date_of_birth === null ? String(patient.age_years) : "",
    guardian_name: patient.guardian_name ?? "",
    language: patient.language,
  };
}

function parseYears(text: string): number | null {
  const trimmed = text.trim();
  return /^\d{1,3}$/.test(trimmed) ? Number(trimmed) : null;
}

/** The hint for the guardian field: is the person under 18 on the clinic's date? */
export function draftIsMinor(draft: PatientDraft, today: string): boolean {
  if (draft.ageMode === "age") {
    const years = parseYears(draft.age_years);
    return years !== null && years < ADULT_AGE;
  }
  const years = draft.date_of_birth === "" ? undefined : ageOn(draft.date_of_birth, today);
  return years !== undefined && years >= 0 && years < ADULT_AGE;
}

/** The registration body. Exactly one of date of birth and age is sent; blanks are left for the API to refuse. */
export function newPatientBody(draft: PatientDraft, confirmNew: boolean): NewPatient {
  const guardian = draft.guardian_name.trim();
  return {
    full_name: draft.full_name.trim(),
    phone: draft.phone.trim(),
    sex: draft.sex === "" ? "UNDISCLOSED" : draft.sex,
    ...(draft.ageMode === "dob"
      ? { date_of_birth: draft.date_of_birth === "" ? null : draft.date_of_birth }
      : { age_years: parseYears(draft.age_years) }),
    guardian_name: guardian === "" ? null : guardian,
    language: draft.language,
    confirm_new: confirmNew,
  };
}

/** Only what changed (R7: the code never changes; a blank guardian clears it). */
export function patientChanges(before: PatientDraft, after: PatientDraft): PatientUpdate {
  const changes: { -readonly [K in keyof PatientUpdate]: PatientUpdate[K] } = {};
  if (after.full_name.trim() !== before.full_name) changes.full_name = after.full_name.trim();
  if (after.phone.trim() !== before.phone) changes.phone = after.phone.trim();
  if (after.sex !== before.sex && after.sex !== "") changes.sex = after.sex;
  if (after.language !== before.language) changes.language = after.language;
  if (after.guardian_name.trim() !== before.guardian_name) changes.guardian_name = after.guardian_name.trim();
  const ageChanged =
    after.ageMode !== before.ageMode ||
    (after.ageMode === "dob" ? after.date_of_birth !== before.date_of_birth : after.age_years.trim() !== before.age_years);
  if (ageChanged) {
    if (after.ageMode === "dob") changes.date_of_birth = after.date_of_birth === "" ? null : after.date_of_birth;
    else changes.age_years = parseYears(after.age_years);
  }
  return changes;
}

/**
 * Problems the API reported against a field, keyed by the form's field names:
 * validation failures and an invalid phone carry `details.fields`; a missing
 * guardian is the guardian field's problem.
 */
export function patientFieldErrors(error: unknown): Readonly<Record<string, string>> {
  const fields = { ...fieldErrors(error, [REQ_VALIDATION_FAILED, PAT_PHONE_INVALID]) };
  if (error instanceof ApiError && error.code === PAT_GUARDIAN_REQUIRED) {
    fields["guardian_name"] ??= error.message;
  }
  if (error instanceof ApiError && error.code === PAT_PHONE_INVALID) {
    fields["phone"] ??= error.message;
  }
  return fields;
}

/** The existing patients on a phone, from a 409 `PAT_PHONE_EXISTS`; undefined for any other error. */
export function phoneCandidates(error: unknown): readonly PatientCandidate[] | undefined {
  if (!(error instanceof ApiError) || error.code !== PAT_PHONE_EXISTS) return undefined;
  const raw: unknown = error.details["candidates"];
  if (!Array.isArray(raw)) return [];
  return (raw as unknown[]).filter(
    (c): c is PatientCandidate =>
      typeof c === "object" &&
      c !== null &&
      "id" in c &&
      typeof c.id === "string" &&
      "code" in c &&
      typeof c.code === "string" &&
      "full_name" in c &&
      typeof c.full_name === "string" &&
      "age_years" in c &&
      typeof c.age_years === "number",
  );
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
