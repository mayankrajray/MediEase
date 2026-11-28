/**
 * M9-P3 (FR-OPS-02, FR-PAT-08; spec patients R8): the words and checks behind the ops patient
 * import screen. The API decides every row; these only describe its report.
 */

import type { components } from "@/lib/api/schema";

export type ImportReport = components["schemas"]["PatientImportReport"];
export type RowError = components["schemas"]["PatientImportRowError"];
export type RowDuplicate = components["schemas"]["PatientImportDuplicate"];

/** The API's limits (delivery/http/ops.py): 2 MB and 5,000 data rows. */
export const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
export const MAX_IMPORT_ROWS = 5_000;
export const COLUMNS = ["name", "phone", "sex", "dob_or_age", "guardian_name", "language"] as const;

export const FIELD_LABEL: Record<RowError["field"], string> = {
  name: "Name",
  phone: "Phone",
  sex: "Sex",
  dob_or_age: "Date of birth or age",
  guardian_name: "Guardian",
  language: "Language",
  row: "Whole row",
};

/** Rows that would become patients: everything valid except those already registered. */
export function importable(report: ImportReport): number {
  return Math.max(0, report.valid - report.already_registered);
}

export function plural(n: number, one: string, many: string = `${one}s`): string {
  return `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
}

/** What one flagged row means for the clinic, in words (never who it matches). */
export function duplicateText(d: RowDuplicate): string {
  switch (d.kind) {
    case "existing_patient":
      return `Will be imported. ${plural(d.matches ?? 1, "patient")} in the clinic already ${d.matches === 1 || d.matches === undefined ? "uses" : "use"} this phone (often family); the desk can check at the next visit.`;
    case "earlier_row":
      return `Will be imported. Same phone as row ${d.same_as_row ?? "above"} (often family).`;
    case "already_registered":
      return d.same_as_row !== undefined
        ? `Left out: same name and phone as row ${d.same_as_row}.`
        : "Left out: this patient is already registered (same name and phone).";
  }
}

/** A problem with the chosen file found before anything is sent, or undefined. */
export function fileProblem(file: File): string | undefined {
  if (!/\.csv$/i.test(file.name)) return "Choose a .csv file. In Excel or Google Sheets, save or download it as CSV UTF-8.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_IMPORT_BYTES) return "This file is over 2 MB. Split it into smaller files and import each one.";
  return undefined;
}

/** One row's problem as a sentence beside its column: "Required for a patient under 18." */
export function problemText(e: RowError): string {
  const reason = e.reason.trim().replace(/^is /, "");
  const sentence = reason.charAt(0).toUpperCase() + reason.slice(1);
  return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
}

/** "ME-0142" and "ME-0153", or the one code, for the confirmation. */
export function codeRange(codes: readonly string[]): string {
  if (codes.length === 0) return "";
  const first = codes[0] ?? "";
  const last = codes[codes.length - 1] ?? "";
  return codes.length === 1 ? first : `${first} to ${last}`;
}

/** An empty file with the header row, to fill in (no patient data). */
export const TEMPLATE_CSV = `${COLUMNS.join(",")}\r\n`;
