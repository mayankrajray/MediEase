"use client";

import { useRef, useState, type RefObject } from "react";

import { cx } from "@/components/ui/cx";
import { CHOICE_CARD, CHOICE_INPUT, DateField, SelectField, TextField } from "@/components/ui/Field";

import {
  LANGUAGE_LABELS,
  SEX_LABELS,
  draftIsMinor,
  draftProblems,
  type AgeMode,
  type DraftField,
  type Language,
  type PatientDraft,
  type Sex,
} from "./fields";

/** The order fields appear in, for the error summary and for moving focus to the first problem. */
const ORDER: readonly DraftField[] = ["full_name", "date_of_birth", "age_years", "guardian_name", "phone"];

export interface PatientForm {
  readonly draft: PatientDraft;
  readonly setDraft: (draft: PatientDraft) => void;
  /** Problems to show now: the API's for this submit, then the form's own for fields already left. */
  readonly problems: Readonly<Record<string, string>>;
  readonly leave: (field: DraftField) => void;
  /**
   * Checks every field (they all count as left). True when the form may be sent; otherwise focus
   * moves to the first problem and the summary lists them all.
   */
  readonly check: () => boolean;
  /** Each problem with the id of its field, in form order, after a failed check. */
  readonly summary: readonly { readonly id: string; readonly message: string }[];
  readonly fieldRefs: RefObject<Partial<Record<DraftField, HTMLInputElement | null>>>;
}

/**
 * M7c-P7 (M5): the registration and edit form's state with inline checks (DESIGN.md §8a): a field
 * is checked when the person leaves it and re-checked as they fix it; a submit with problems shows
 * them all, moves focus to the first and sends nothing; what was typed is always kept. `apiProblems`
 * are the API's own field answers, which still show under their fields.
 */
export function usePatientForm(
  initial: PatientDraft,
  today: string,
  idPrefix: string,
  apiProblems: Readonly<Record<string, string>>,
): PatientForm {
  const [draft, setDraft] = useState(initial);
  const [left, setLeft] = useState<ReadonlySet<DraftField>>(new Set());
  const [submitted, setSubmitted] = useState(false);
  const fieldRefs = useRef<Partial<Record<DraftField, HTMLInputElement | null>>>({});

  const own = draftProblems(draft, today);
  const shown: Record<string, string> = { ...apiProblems };
  for (const field of ORDER) {
    const message = own[field];
    if (message !== undefined && (submitted || left.has(field))) shown[field] = message;
  }
  const ids: Record<DraftField, string> = {
    full_name: `${idPrefix}-name`,
    date_of_birth: `${idPrefix}-dob`,
    age_years: `${idPrefix}-age`,
    guardian_name: `${idPrefix}-guardian`,
    phone: `${idPrefix}-phone`,
  };
  const summary = submitted
    ? ORDER.filter((f) => own[f] !== undefined).map((f) => ({ id: ids[f], message: own[f] ?? "" }))
    : [];

  return {
    draft,
    setDraft,
    problems: shown,
    leave: (field) => setLeft((current) => (current.has(field) ? current : new Set([...current, field]))),
    check: () => {
      setSubmitted(true);
      const first = ORDER.find((f) => own[f] !== undefined);
      if (first === undefined) return true;
      fieldRefs.current[first]?.focus();
      return false;
    },
    summary,
    fieldRefs,
  };
}

/**
 * The demographic fields shared by registration and editing (spec patients §6).
 * The guardian field appears, and the phone label changes, as soon as the age is
 * under 18 on the clinic's date (R3, D1): the phone is then the guardian's.
 *
 * M7c-P7 (M5): titled groups (who, age, contact, preferences), the age choice as two choice
 * cards, the shared select fields, a character count on names, and checks on leaving a field.
 */
export function PatientFields({
  idPrefix,
  form,
  today,
}: {
  idPrefix: string;
  form: PatientForm;
  today: string;
}) {
  const { draft, setDraft, problems, leave, fieldRefs } = form;
  const set = <K extends keyof PatientDraft>(key: K, value: PatientDraft[K]) => setDraft({ ...draft, [key]: value });
  // A guardian already on record, or one the API asked for, keeps the field visible.
  const minor = draftIsMinor(draft, today) || draft.guardian_name !== "" || problems["guardian_name"] !== undefined;
  const id = (name: string) => `${idPrefix}-${name}`;
  const ref = (field: DraftField) => (el: HTMLInputElement | null) => {
    fieldRefs.current[field] = el;
  };

  return (
    <div className="space-y-5">
      <TextField
        id={id("name")}
        label="Full name"
        required
        maxLength={200}
        counter
        autoComplete="off"
        value={draft.full_name}
        error={problems["full_name"]}
        onChange={(value) => set("full_name", value)}
        onBlur={() => leave("full_name")}
        inputRef={ref("full_name")}
      />

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-semibold text-slate-900">Age</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {(["dob", "age"] as const satisfies readonly AgeMode[]).map((mode) => (
            <label key={mode} className={cx(CHOICE_CARD, "text-sm font-medium")}>
              <input
                type="radio"
                name={id("age-mode")}
                value={mode}
                checked={draft.ageMode === mode}
                onChange={() => set("ageMode", mode)}
                className={CHOICE_INPUT}
              />
              {mode === "dob" ? "Date of birth known" : "Only the age is known"}
            </label>
          ))}
        </div>
        {draft.ageMode === "dob" ? (
          <DateField
            id={id("dob")}
            label="Date of birth"
            value={draft.date_of_birth}
            error={problems["date_of_birth"]}
            onChange={(value) => set("date_of_birth", value)}
            onBlur={() => leave("date_of_birth")}
            inputRef={ref("date_of_birth")}
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
            onBlur={() => leave("age_years")}
            inputRef={ref("age_years")}
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
          onBlur={() => leave("guardian_name")}
          inputRef={ref("guardian_name")}
        />
      )}

      <TextField
        id={id("phone")}
        label={minor ? "Parent or guardian's phone" : "Phone"}
        required
        type="tel"
        inputMode="tel"
        autoComplete="off"
        maxLength={20}
        value={draft.phone}
        hint="A 10-digit mobile or a number with its country code. Spaces and a leading 0 are fine."
        error={problems["phone"]}
        onChange={(value) => set("phone", value)}
        onBlur={() => leave("phone")}
        inputRef={ref("phone")}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          id={id("sex")}
          label="Sex"
          value={draft.sex}
          error={problems["sex"]}
          onChange={(value) => set("sex", value as Sex | "")}
          options={[
            { value: "", label: "Not recorded" },
            ...(Object.keys(SEX_LABELS) as Sex[]).map((sex) => ({ value: sex, label: SEX_LABELS[sex] })),
          ]}
        />
        <SelectField
          id={id("language")}
          label="Message language"
          value={draft.language}
          onChange={(value) => set("language", value as Language)}
          options={(Object.keys(LANGUAGE_LABELS) as Language[]).map((language) => ({ value: language, label: LANGUAGE_LABELS[language] }))}
        />
      </div>
    </div>
  );
}
