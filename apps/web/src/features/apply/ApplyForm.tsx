"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { CheckboxField, ERROR, HINT, INPUT, LABEL, SelectField, TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ApiError, apiPostForm } from "@/lib/api/client";

import {
  CERTIFICATE_ACCEPT,
  COUNCILS,
  MAX_CERTIFICATE_BYTES,
  MAX_DOCTORS,
  MAX_SPECIALTIES,
  MAX_SUBMISSION_BYTES,
  REPLY_PROMISE,
  SPECIALTIES,
} from "./lists";

type Kind = "CLINIC" | "SOLO_DOCTOR";
type Step = "kind" | "clinic" | "owner" | "doctors" | "review";
const STEPS: readonly Step[] = ["kind", "clinic", "owner", "doctors", "review"];
const STEP_TITLES: Record<Step, string> = {
  kind: "Who is applying",
  clinic: "The clinic",
  owner: "The owner",
  doctors: "The doctors",
  review: "Check and send",
};

export interface DoctorDraft {
  name: string;
  qualification: string;
  council: string;
  registration_number: string;
  is_owner: boolean;
  file: File | null;
}

export interface Draft {
  kind: Kind;
  clinic_name: string;
  address_line: string;
  city: string;
  state: string;
  pincode: string;
  clinic_phone: string;
  specialties: string[];
  owner_name: string;
  owner_phone: string;
  owner_email: string;
  owner_practises: boolean;
  doctors: DoctorDraft[];
}

/** Field name (as the API names it, doctors from 1) -> message. */
export type Problems = Readonly<Record<string, string>>;

const EMPTY_DOCTOR: DoctorDraft = { name: "", qualification: "", council: "", registration_number: "", is_owner: false, file: null };

export function emptyDraft(): Draft {
  return {
    kind: "CLINIC",
    clinic_name: "",
    address_line: "",
    city: "",
    state: "",
    pincode: "",
    clinic_phone: "",
    specialties: [],
    owner_name: "",
    owner_phone: "",
    owner_email: "",
    owner_practises: false,
    doctors: [{ ...EMPTY_DOCTOR }],
  };
}

const PINCODE = /^[1-9]\d{5}$/;
const MOBILE = /^(?:\+?91|0)?[6-9]\d{9}$/;
const PHONE = /^[+\d][\d\s\-()]{7,19}$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const FILE_TYPE = /\.(pdf|jpe?g|png)$/i;

const req = (value: string) => value.trim() === "";

/** The checks the form can make before sending; the API makes them all again (R2-R7). */
export function problemsFor(step: Step, d: Draft): Problems {
  const p: Record<string, string> = {};
  if (step === "clinic") {
    if (req(d.clinic_name)) p["clinic_name"] = "Enter the clinic's name.";
    if (req(d.address_line)) p["address_line"] = "Enter the address.";
    if (req(d.city)) p["city"] = "Enter the city.";
    if (req(d.state)) p["state"] = "Enter the state.";
    if (!PINCODE.test(d.pincode.trim())) p["pincode"] = "Enter the six-digit PIN code.";
    if (!PHONE.test(d.clinic_phone.trim())) p["clinic_phone"] = "Enter the clinic's phone number.";
    if (d.specialties.length === 0) p["specialties"] = "Choose at least one specialty.";
  }
  if (step === "owner") {
    if (req(d.owner_name)) p["owner_name"] = "Enter the owner's name.";
    if (!MOBILE.test(d.owner_phone.replace(/[\s-]/g, ""))) p["owner_phone"] = "Enter an Indian mobile number, 10 digits.";
    if (!EMAIL.test(d.owner_email.trim())) p["owner_email"] = "Enter an email address.";
  }
  if (step === "doctors") {
    if (d.owner_practises && d.doctors.filter((x) => x.is_owner).length !== 1) p["doctors"] = "Mark which doctor is the owner.";
    d.doctors.forEach((x, i) => {
      const at = `doctors.${i + 1}`;
      if (req(x.name)) p[`${at}.name`] = "Enter the doctor's name.";
      if (req(x.qualification)) p[`${at}.qualification`] = "Enter the qualification.";
      if (req(x.council)) p[`${at}.council`] = "Choose the council.";
      if (req(x.registration_number)) p[`${at}.registration_number`] = "Enter the registration number.";
      if (x.file === null) p[`${at}.certificate`] = "Add the registration certificate.";
      else if (!FILE_TYPE.test(x.file.name)) p[`${at}.certificate`] = "Use a PDF, JPEG or PNG file.";
      else if (x.file.size > MAX_CERTIFICATE_BYTES) p[`${at}.certificate`] = "The file must be at most 5 MB.";
    });
    const total = d.doctors.reduce((sum, x) => sum + (x.file?.size ?? 0), 0);
    if (total > MAX_SUBMISSION_BYTES) p["doctors"] = "The files together must be at most 30 MB.";
  }
  return p;
}

/** The request the API takes: the JSON part and one file per doctor (R1). */
export function formData(d: Draft): FormData {
  const form = new FormData();
  const application = {
    kind: d.kind,
    clinic_name: d.clinic_name,
    address_line: d.address_line,
    city: d.city,
    state: d.state,
    pincode: d.pincode.trim(),
    clinic_phone: d.clinic_phone,
    specialties: d.specialties,
    owner_name: d.owner_name,
    owner_phone: d.owner_phone,
    owner_email: d.owner_email,
    owner_practises: d.owner_practises,
    doctors: d.doctors.map(({ name, qualification, council, registration_number, is_owner }) => ({
      name,
      qualification,
      council,
      registration_number,
      is_owner,
    })),
  };
  form.append("application", JSON.stringify(application));
  d.doctors.forEach((x, i) => {
    if (x.file !== null) form.append(`certificate_${i + 1}`, x.file, x.file.name);
  });
  return form;
}

/** The step a server-named field belongs to, so the form can take the person there. */
export function stepOf(field: string): Step {
  if (field.startsWith("doctors")) return "doctors";
  if (field.startsWith("owner_")) return "owner";
  return "clinic";
}

/** The API's refusal, as field messages (R6, R7); undefined when it is not about a field. */
export function serverProblems(error: unknown): Problems | undefined {
  if (!(error instanceof ApiError)) return undefined;
  if (error.code === "ONB_FILE_REJECTED") {
    const position = String(error.details["position"] ?? "1");
    const reason = error.details["reason"];
    const text =
      reason === "size" ? "The file must be at most 5 MB." : reason === "missing" ? "Add the registration certificate." : "Use a PDF, JPEG or PNG file.";
    return { [`doctors.${position}.certificate`]: text };
  }
  if (error.code === "REQ_VALIDATION_FAILED") {
    const fields = error.details["fields"];
    if (!Array.isArray(fields)) return undefined;
    const p: Record<string, string> = {};
    for (const f of fields as { field?: unknown; reason?: unknown }[]) {
      if (typeof f.field === "string") p[f.field.replace(/^specialties\.\d+$/, "specialties")] = `Check this field: ${String(f.reason ?? "not valid")}.`;
    }
    return p;
  }
  return undefined;
}

/**
 * `/apply` (M6c-P1; FR-ONB-01, spec clinic-onboarding R1-R8, R23): a clinic or a doctor with their
 * own practice applies in five short steps, signed out, English only (D2). Each step checks what it
 * can before going on; the API checks everything again and its field errors bring the person back
 * to the step concerned. Certificates are read from the device only when sent. The promise of a
 * reply within 2 working days (D3) is on the form and on the page after sending.
 */
export function ApplyForm() {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [step, setStep] = useState<Step>("kind");
  const [problems, setProblems] = useState<Problems>({});
  const [error, setError] = useState<unknown>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<{ reference: string; email_masked: string } | null>(null);
  const [website, setWebsite] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const summary = useRef<HTMLDivElement>(null);
  const shown = useRef(false);

  useEffect(() => {
    // Move focus to the new step's heading, but not on the first render.
    if (shown.current) heading.current?.focus();
    shown.current = true;
  }, [step, sent]);
  useEffect(() => {
    if (Object.keys(problems).length > 0) summary.current?.focus();
  }, [problems]);

  const set = (change: Partial<Draft>) => setDraft((d) => ({ ...d, ...change }));
  const setDoctor = (index: number, change: Partial<DoctorDraft>) =>
    setDraft((d) => ({ ...d, doctors: d.doctors.map((x, i) => (i === index ? { ...x, ...change } : x)) }));

  function chooseKind(kind: Kind) {
    setDraft((d) =>
      kind === "SOLO_DOCTOR"
        ? { ...d, kind, owner_practises: true, doctors: [{ ...(d.doctors[0] ?? EMPTY_DOCTOR), is_owner: true }] }
        : { ...d, kind, doctors: d.doctors.map((x) => ({ ...x, is_owner: d.owner_practises && x.is_owner })) },
    );
  }

  function go(next: Step) {
    const found = problemsFor(step, draft);
    const index = STEPS.indexOf(next);
    if (index > STEPS.indexOf(step) && Object.keys(found).length > 0) {
      setProblems(found);
      return;
    }
    setProblems({});
    setError(null);
    setStep(next);
  }

  async function send() {
    for (const s of ["clinic", "owner", "doctors"] as const) {
      const found = problemsFor(s, draft);
      if (Object.keys(found).length > 0) {
        setStep(s);
        setProblems(found);
        return;
      }
    }
    setSending(true);
    setError(null);
    try {
      const form = formData(draft);
      if (website !== "") {
        const parsed = JSON.parse(String(form.get("application"))) as Record<string, unknown>;
        form.set("application", JSON.stringify({ ...parsed, website }));
      }
      const { data } = await apiPostForm("/api/v1/public/applications", form, { timeoutMs: 120_000 });
      setSent(data);
    } catch (failure) {
      const fields = serverProblems(failure);
      if (fields !== undefined && Object.keys(fields).length > 0) {
        setStep(stepOf(Object.keys(fields)[0] ?? "clinic"));
        setProblems(fields);
      } else {
        setError(failure);
      }
    } finally {
      setSending(false);
    }
  }

  if (sent !== null) {
    return (
      <section aria-labelledby="apply-sent" className="space-y-4 p-6 sm:p-8">
        <h1 id="apply-sent" ref={heading} tabIndex={-1} className="text-2xl font-bold tracking-tight">
          Check your email
        </h1>
        <p role="status">
          We sent a link to {sent.email_masked} to confirm application <span className="font-semibold">{sent.reference}</span>. The
          application is sent for review only after you open it, within 48 hours.
        </p>
        <p>{REPLY_PROMISE}</p>
      </section>
    );
  }

  const index = STEPS.indexOf(step);
  const err = (field: string) => problems[field];
  const problemList = Object.entries(problems);

  return (
    <section aria-labelledby="apply-heading" className="space-y-5 p-6 sm:p-8">
      <div>
        <p className="text-sm text-slate-700">
          Step {index + 1} of {STEPS.length}
        </p>
        <h1 id="apply-heading" ref={heading} tabIndex={-1} className="text-2xl font-bold tracking-tight">
          {STEP_TITLES[step]}
        </h1>
      </div>

      {problemList.length > 0 && (
        <div ref={summary} tabIndex={-1} role="alert" className="space-y-2 rounded-lg border border-red-800 bg-red-50 p-3 text-red-950">
          <p className="font-semibold">Please check {problemList.length === 1 ? "this field" : `these ${problemList.length} fields`}:</p>
          <ul className="list-disc pl-5">
            {problemList.map(([field, text]) => (
              <li key={field}>{text}</li>
            ))}
          </ul>
        </div>
      )}
      {error !== null && <ErrorNotice error={error} />}

      {step === "kind" && (
        <fieldset className="space-y-3">
          <legend className={LABEL}>Are you applying for a clinic, or for your own practice?</legend>
          {(
            [
              ["CLINIC", "A clinic", "One or more doctors; the owner may also see patients."],
              ["SOLO_DOCTOR", "A doctor with my own practice", "You are the owner and the only doctor."],
            ] as const
          ).map(([value, label, hint]) => (
            <label key={value} className="flex min-h-11 items-start gap-3 rounded-lg border border-slate-300 p-3">
              <input
                type="radio"
                name="kind"
                value={value}
                checked={draft.kind === value}
                onChange={() => chooseKind(value)}
                className="mt-1 size-5 accent-brand-700"
              />
              <span>
                <span className="block font-medium">{label}</span>
                <span className={HINT}>{hint}</span>
              </span>
            </label>
          ))}
          <p className={HINT}>{REPLY_PROMISE}</p>
        </fieldset>
      )}

      {step === "clinic" && (
        <div className="space-y-4">
          <TextField id="clinic_name" label="Clinic name" required value={draft.clinic_name} onChange={(v) => set({ clinic_name: v })} error={err("clinic_name")} maxLength={200} autoComplete="organization" />
          <TextField id="address_line" label="Address" required value={draft.address_line} onChange={(v) => set({ address_line: v })} error={err("address_line")} maxLength={300} autoComplete="street-address" />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField id="city" label="City" required value={draft.city} onChange={(v) => set({ city: v })} error={err("city")} maxLength={100} autoComplete="address-level2" />
            <TextField id="state" label="State" required value={draft.state} onChange={(v) => set({ state: v })} error={err("state")} maxLength={100} autoComplete="address-level1" />
            <TextField id="pincode" label="PIN code" required value={draft.pincode} onChange={(v) => set({ pincode: v })} error={err("pincode")} maxLength={6} inputMode="numeric" autoComplete="postal-code" />
            <TextField id="clinic_phone" label="Clinic phone" required type="tel" value={draft.clinic_phone} onChange={(v) => set({ clinic_phone: v })} error={err("clinic_phone")} maxLength={20} inputMode="tel" />
          </div>
          <fieldset aria-describedby={err("specialties") === undefined ? "specialties-hint" : "specialties-hint specialties-error"} className="space-y-2">
            <legend className={LABEL}>
              Specialties <span className="font-normal text-slate-700">(required)</span>
            </legend>
            <p id="specialties-hint" className={HINT}>
              Choose up to {MAX_SPECIALTIES}.
            </p>
            <div className="grid gap-x-4 sm:grid-cols-2">
              {SPECIALTIES.map((name) => {
                const checked = draft.specialties.includes(name);
                return (
                  <label key={name} className="flex min-h-11 items-center gap-3">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!checked && draft.specialties.length >= MAX_SPECIALTIES}
                      onChange={(e) => set({ specialties: e.target.checked ? [...draft.specialties, name] : draft.specialties.filter((s) => s !== name) })}
                      className="size-5 accent-brand-700"
                    />
                    {name}
                  </label>
                );
              })}
            </div>
            {err("specialties") !== undefined && (
              <p id="specialties-error" className={ERROR}>
                {err("specialties")}
              </p>
            )}
          </fieldset>
        </div>
      )}

      {step === "owner" && (
        <div className="space-y-4">
          <p className={HINT}>The owner gets the email to confirm this application and, once approved, the invitation to set up the clinic.</p>
          <TextField id="owner_name" label="Owner's full name" required value={draft.owner_name} onChange={(v) => set({ owner_name: v })} error={err("owner_name")} maxLength={200} autoComplete="name" />
          <TextField id="owner_phone" label="Owner's mobile number" required type="tel" value={draft.owner_phone} onChange={(v) => set({ owner_phone: v })} error={err("owner_phone")} maxLength={20} inputMode="tel" autoComplete="tel" hint="An Indian mobile number." />
          <TextField id="owner_email" label="Owner's email" required type="email" value={draft.owner_email} onChange={(v) => set({ owner_email: v })} error={err("owner_email")} maxLength={254} inputMode="email" autoComplete="email" />
          {draft.kind === "CLINIC" && (
            <CheckboxField
              id="owner_practises"
              label="The owner also sees patients here"
              checked={draft.owner_practises}
              onChange={(v) => set({ owner_practises: v, doctors: draft.doctors.map((x, i) => ({ ...x, is_owner: v && i === 0 })) })}
              hint="Then the owner is one of the doctors below."
            />
          )}
        </div>
      )}

      {step === "doctors" && (
        <div className="space-y-5">
          <p className={HINT}>For each doctor, the registration details exactly as on the certificate, and the certificate itself (PDF, JPEG or PNG, at most 5 MB).</p>
          {err("doctors") !== undefined && <p className={ERROR}>{err("doctors")}</p>}
          {draft.doctors.map((doctor, i) => {
            const at = `doctors.${i + 1}`;
            const fileId = `doctor-${i + 1}-certificate`;
            const fileError = err(`${at}.certificate`);
            return (
              <fieldset key={i} className="space-y-3 rounded-lg border border-slate-300 p-3">
                <legend className="px-1 font-semibold">Doctor {i + 1}</legend>
                <TextField id={`doctor-${i + 1}-name`} label="Name" required value={doctor.name} onChange={(v) => setDoctor(i, { name: v })} error={err(`${at}.name`)} maxLength={200} />
                <TextField id={`doctor-${i + 1}-qualification`} label="Qualification" required value={doctor.qualification} onChange={(v) => setDoctor(i, { qualification: v })} error={err(`${at}.qualification`)} maxLength={200} hint="For example MBBS, MD (Paediatrics)." />
                <SelectField
                  id={`doctor-${i + 1}-council`}
                  label="Medical council"
                  required
                  value={doctor.council}
                  onChange={(v) => setDoctor(i, { council: v })}
                  error={err(`${at}.council`)}
                  options={[{ value: "", label: "Choose the council" }, ...COUNCILS.map((c) => ({ value: c, label: c }))]}
                />
                <TextField id={`doctor-${i + 1}-registration`} label="Registration number" required value={doctor.registration_number} onChange={(v) => setDoctor(i, { registration_number: v })} error={err(`${at}.registration_number`)} maxLength={80} />
                <div className="space-y-1">
                  <label htmlFor={fileId} className={LABEL}>
                    Registration certificate <span className="font-normal text-slate-700">(required)</span>
                  </label>
                  <input
                    id={fileId}
                    type="file"
                    accept={CERTIFICATE_ACCEPT}
                    aria-invalid={fileError !== undefined ? true : undefined}
                    aria-describedby={fileError !== undefined ? `${fileId}-error` : undefined}
                    onChange={(e) => setDoctor(i, { file: e.target.files?.[0] ?? null })}
                    className={INPUT}
                  />
                  {doctor.file !== null && <p className={HINT}>{doctor.file.name}</p>}
                  {fileError !== undefined && (
                    <p id={`${fileId}-error`} className={ERROR}>
                      {fileError}
                    </p>
                  )}
                </div>
                {draft.kind === "CLINIC" && draft.owner_practises && (
                  <label className="flex min-h-11 items-center gap-3">
                    <input
                      type="radio"
                      name="owner-doctor"
                      checked={doctor.is_owner}
                      onChange={() => set({ doctors: draft.doctors.map((x, j) => ({ ...x, is_owner: j === i })) })}
                      className="size-5 accent-brand-700"
                    />
                    This doctor is the owner
                  </label>
                )}
                {draft.kind === "CLINIC" && draft.doctors.length > 1 && (
                  <Button size="sm" onClick={() => set({ doctors: draft.doctors.filter((_, j) => j !== i) })}>
                    Remove doctor {i + 1}
                  </Button>
                )}
              </fieldset>
            );
          })}
          {draft.kind === "CLINIC" && draft.doctors.length < MAX_DOCTORS && (
            <Button onClick={() => set({ doctors: [...draft.doctors, { ...EMPTY_DOCTOR }] })}>Add another doctor</Button>
          )}
        </div>
      )}

      {step === "review" && (
        <div className="space-y-3">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="font-medium">Clinic</dt>
            <dd>
              {draft.clinic_name}, {draft.city} {draft.pincode}
            </dd>
            <dt className="font-medium">Owner</dt>
            <dd className="break-all">
              {draft.owner_name} · {draft.owner_email}
            </dd>
            <dt className="font-medium">Doctors</dt>
            <dd>{draft.doctors.map((x) => x.name).join(", ")}</dd>
          </dl>
          <p>{REPLY_PROMISE}</p>
          {/* R8: hidden from people and assistive technology; a bot that fills it is dropped. */}
          <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
            <label htmlFor="website">Website</label>
            <input id="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
          </div>
        </div>
      )}

      <div className="flex flex-wrap justify-between gap-3">
        {index > 0 ? (
          <Button onClick={() => go(STEPS[index - 1] as Step)} disabled={sending}>
            Back
          </Button>
        ) : (
          <span />
        )}
        {step === "review" ? (
          <Button variant="primary" onClick={() => void send()} disabled={sending}>
            {sending ? "Sending…" : "Send application"}
          </Button>
        ) : (
          <Button variant="primary" onClick={() => go(STEPS[index + 1] as Step)}>
            Next
          </Button>
        )}
      </div>
    </section>
  );
}
