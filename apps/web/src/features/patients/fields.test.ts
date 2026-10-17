import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import {
  EMPTY_DRAFT,
  ageOn,
  ageText,
  clinicToday,
  draftIsMinor,
  looksLikePhone,
  newPatientBody,
  patientChanges,
  patientFieldErrors,
  phoneCandidates,
  type PatientDraft,
} from "./fields";

describe("clinicToday", () => {
  it("DEBUGGING §5.4: is the clinic's date, not the browser's, across Kolkata midnight", () => {
    const now = new Date("2026-10-16T19:00:00Z"); // 00:30 on 17 Oct in Kolkata
    expect(clinicToday("Asia/Kolkata", now)).toBe("2026-10-17");
    expect(clinicToday("UTC", now)).toBe("2026-10-16");
    expect(clinicToday("Not/AZone", now)).toBe("2026-10-16");
  });
});

describe("ageOn", () => {
  it.each([
    ["2008-10-17", "2026-10-17", 18],
    ["2008-10-18", "2026-10-17", 17],
    ["2020-02-29", "2026-02-28", 5],
    ["2020-02-29", "2026-03-01", 6],
  ])("%s on %s is %i", (born, today, years) => {
    expect(ageOn(born, today)).toBe(years);
  });

  it("is undefined for unreadable dates", () => {
    expect(ageOn("17/10/2008", "2026-10-17")).toBeUndefined();
  });
});

describe("draftIsMinor (FR-PAT-06, R3 hint)", () => {
  const draft = (overrides: Partial<PatientDraft>): PatientDraft => ({ ...EMPTY_DRAFT, ...overrides });

  it("turns at 18 on the clinic's date", () => {
    expect(draftIsMinor(draft({ date_of_birth: "2008-10-18" }), "2026-10-17")).toBe(true);
    expect(draftIsMinor(draft({ date_of_birth: "2008-10-17" }), "2026-10-17")).toBe(false);
  });

  it("reads a recorded age, and is false while nothing usable is typed", () => {
    expect(draftIsMinor(draft({ ageMode: "age", age_years: "6" }), "2026-10-17")).toBe(true);
    expect(draftIsMinor(draft({ ageMode: "age", age_years: "18" }), "2026-10-17")).toBe(false);
    expect(draftIsMinor(draft({ ageMode: "age", age_years: "six" }), "2026-10-17")).toBe(false);
    expect(draftIsMinor(draft({}), "2026-10-17")).toBe(false);
    expect(draftIsMinor(draft({ date_of_birth: "2030-01-01" }), "2026-10-17")).toBe(false);
  });
});

describe("request bodies", () => {
  const filled: PatientDraft = {
    full_name: "  Sample Person ",
    phone: " 90000 00999 ",
    sex: "FEMALE",
    ageMode: "dob",
    date_of_birth: "1990-05-17",
    age_years: "",
    guardian_name: " ",
    language: "hi",
  };

  it("FR-PAT-01: registration sends exactly one age fact, trimmed text and confirm_new", () => {
    expect(newPatientBody(filled, false)).toEqual({
      full_name: "Sample Person",
      phone: "90000 00999",
      sex: "FEMALE",
      date_of_birth: "1990-05-17",
      guardian_name: null,
      language: "hi",
      confirm_new: false,
    });
    expect(newPatientBody({ ...filled, ageMode: "age", age_years: "47", sex: "" }, true)).toMatchObject({
      age_years: 47,
      sex: "UNDISCLOSED",
      confirm_new: true,
    });
    expect(newPatientBody({ ...filled, ageMode: "age", age_years: "x" }, false)).not.toHaveProperty("date_of_birth");
  });

  it("R7: an edit sends only what changed", () => {
    const before: PatientDraft = { ...filled, full_name: "Sample Person", phone: "+919000000999", guardian_name: "" };
    expect(patientChanges(before, before)).toEqual({});
    expect(patientChanges(before, { ...before, full_name: "Sample Persona " })).toEqual({ full_name: "Sample Persona" });
    expect(patientChanges(before, { ...before, ageMode: "age", age_years: "36" })).toEqual({ age_years: 36 });
    expect(patientChanges({ ...before, guardian_name: "Asha" }, { ...before, guardian_name: "" })).toEqual({
      guardian_name: "",
    });
  });
});

describe("reading patient errors", () => {
  const error = (code: string, status: number, details: Record<string, unknown> = {}, message = "msg") =>
    new ApiError(code, message, status, "ref", details);

  it("puts PAT_PHONE_INVALID, PAT_GUARDIAN_REQUIRED and validation failures on their fields", () => {
    expect(patientFieldErrors(error("PAT_PHONE_INVALID", 422, { fields: [{ field: "phone", reason: "not valid" }] }))).toEqual({
      phone: "not valid",
    });
    expect(patientFieldErrors(error("PAT_PHONE_INVALID", 422, {}, "Not a phone"))).toEqual({ phone: "Not a phone" });
    expect(patientFieldErrors(error("PAT_GUARDIAN_REQUIRED", 422, {}, "Guardian needed"))).toEqual({
      guardian_name: "Guardian needed",
    });
    expect(patientFieldErrors(error("REQ_VALIDATION_FAILED", 422, { fields: [{ field: "full_name", reason: "required" }] }))).toEqual({
      full_name: "required",
    });
    expect(patientFieldErrors(error("PAT_PHONE_EXISTS", 409))).toEqual({});
  });

  it("FR-PAT-02: reads the candidates of a PAT_PHONE_EXISTS, dropping malformed ones", () => {
    const good = { id: "p1", code: "SC-0001", full_name: "Asha Rao", age_years: 36 };
    expect(phoneCandidates(error("PAT_PHONE_EXISTS", 409, { candidates: [good, { id: 1 }, null] }))).toEqual([good]);
    expect(phoneCandidates(error("PAT_PHONE_EXISTS", 409))).toEqual([]);
    expect(phoneCandidates(error("PAT_PHONE_INVALID", 422))).toBeUndefined();
  });
});

describe("display helpers", () => {
  it("says when an age was only recorded", () => {
    expect(ageText({ age_years: 47, age_is_estimated: true })).toBe("about 47 years");
    expect(ageText({ age_years: 1, age_is_estimated: false })).toBe("1 year");
  });

  it("R5: reads 7 or more digits as a phone, as the API does", () => {
    expect(looksLikePhone("90000 00101")).toBe(true);
    expect(looksLikePhone("+91-90000-00101")).toBe(true);
    expect(looksLikePhone("0142")).toBe(false);
    expect(looksLikePhone("SC-0142")).toBe(false);
    expect(looksLikePhone("Asha")).toBe(false);
  });
});
