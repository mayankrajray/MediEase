"use client";

import { TextField } from "@/components/TextField";

import {
  LANGUAGE_LABELS,
  SEX_LABELS,
  draftIsMinor,
  type AgeMode,
  type Language,
  type PatientDraft,
  type Sex,
} from "./fields";

/**
 * The demographic fields shared by registration and editing (spec patients §6).
 * The guardian field appears, and the phone label changes, as soon as the age is
 * under 18 on the clinic's date (R3, D1): the phone is then the guardian's.
 */
export function PatientFields({
  idPrefix,
  draft,
  onChange,
  today,
  problems,
}: {
  idPrefix: string;
  draft: PatientDraft;
  onChange: (draft: PatientDraft) => void;
  today: string;
  problems: Readonly<Record<string, string>>;
}) {
  const set = <K extends keyof PatientDraft>(key: K, value: PatientDraft[K]) => onChange({ ...draft, [key]: value });
  // A guardian already on record, or one the API asked for, keeps the field visible.
  const minor = draftIsMinor(draft, today) || draft.guardian_name !== "" || problems["guardian_name"] !== undefined;
  const id = (name: string) => `${idPrefix}-${name}`;

  return (
    <div className="space-y-4">
      <TextField
        id={id("name")}
        label="Full name"
        required
        maxLength={200}
        autoComplete="off"
        value={draft.full_name}
        error={problems["full_name"]}
        onChange={(value) => set("full_name", value)}
      />

      <fieldset className="space-y-2">
        <legend className="font-medium">Age</legend>
        <div className="flex gap-4">
          {(["dob", "age"] as const satisfies readonly AgeMode[]).map((mode) => (
            <label key={mode} className="flex items-center gap-2">
              <input
                type="radio"
                name={id("age-mode")}
                value={mode}
                checked={draft.ageMode === mode}
                onChange={() => set("ageMode", mode)}
              />
              {mode === "dob" ? "Date of birth known" : "Only the age is known"}
            </label>
          ))}
        </div>
        {draft.ageMode === "dob" ? (
          <TextField
            id={id("dob")}
            label="Date of birth"
            type="date"
            value={draft.date_of_birth}
            error={problems["date_of_birth"]}
            onChange={(value) => set("date_of_birth", value)}
          />
        ) : (
          <TextField
            id={id("age")}
            label="Age in years"
            inputMode="numeric"
            maxLength={3}
            value={draft.age_years}
            hint="When the date of birth is not known. The age shown advances each year."
            error={problems["age_years"]}
            onChange={(value) => set("age_years", value)}
          />
        )}
      </fieldset>

      {minor && (
        <TextField
          id={id("guardian")}
          label="Parent or guardian's name"
          required
          maxLength={200}
          value={draft.guardian_name}
          hint="Under 18: the guardian is the contact, and answers for consent."
          error={problems["guardian_name"]}
          onChange={(value) => set("guardian_name", value)}
        />
      )}

      <TextField
        id={id("phone")}
        label={minor ? "Parent or guardian's phone" : "Phone"}
        required
        type="tel"
        inputMode="tel"
        maxLength={20}
        value={draft.phone}
        hint="A 10-digit mobile or a number with its country code."
        error={problems["phone"]}
        onChange={(value) => set("phone", value)}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor={id("sex")} className="block font-medium">
            Sex
          </label>
          <select
            id={id("sex")}
            value={draft.sex}
            aria-invalid={problems["sex"] !== undefined ? true : undefined}
            onChange={(event) => set("sex", event.target.value as Sex | "")}
            className="w-full rounded border border-slate-500 px-3 py-2"
          >
            <option value="">Not recorded</option>
            {(Object.keys(SEX_LABELS) as Sex[]).map((sex) => (
              <option key={sex} value={sex}>
                {SEX_LABELS[sex]}
              </option>
            ))}
          </select>
          {problems["sex"] !== undefined && <p className="text-sm font-medium text-red-900">{problems["sex"]}</p>}
        </div>
        <div className="space-y-1">
          <label htmlFor={id("language")} className="block font-medium">
            Message language
          </label>
          <select
            id={id("language")}
            value={draft.language}
            onChange={(event) => set("language", event.target.value as Language)}
            className="w-full rounded border border-slate-500 px-3 py-2"
          >
            {(Object.keys(LANGUAGE_LABELS) as Language[]).map((language) => (
              <option key={language} value={language}>
                {LANGUAGE_LABELS[language]}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
