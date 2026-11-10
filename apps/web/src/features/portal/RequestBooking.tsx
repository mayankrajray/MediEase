"use client";

import { Building2, CalendarClock, CircleAlert, Stethoscope } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { CheckboxField, ErrorSummary, SelectField, TextAreaField, TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ApiError, apiGet, type GetResponse } from "@/lib/api/client";
import { portalPost } from "@/lib/auth/portal-session";
import { bookingWords } from "@/lib/i18n/booking-request";
import { portalDay, portalTime } from "@/lib/i18n/portal";

import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";

type Clinic = GetResponse<"/api/v1/public/clinics/{slug}">;
type Sex = "FEMALE" | "MALE" | "OTHER" | "UNDISCLOSED";
const SEXES: readonly Sex[] = ["FEMALE", "MALE", "OTHER", "UNDISCLOSED"];

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly clinic: Clinic }
  | { readonly status: "gone" }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * Ask a clinic for a time (M6b-P4; FR-PUB-02, 03, FR-BKG-01, 02): the form behind the public
 * page. The chosen time is in the address (`?clinic=&doctor=&session=&slot=`), so signing in
 * brings the patient back to the same time. Phone is always asked; age and sex only when the
 * clinic requires them. The reason is optional, and the patient confirms it is not an emergency.
 */
export function RequestBooking() {
  const params = useSearchParams();
  const slug = params.get("clinic") ?? "";
  const doctorId = params.get("doctor") ?? "";
  const sessionStart = params.get("session") ?? "";
  const slotStart = params.get("slot");
  // M6c-P7 (discovery R13): from search, the clinic must still be in the directory.
  const via = params.get("via") === "directory";
  const { s, account, leave } = usePortal();
  const words = bookingWords(s.lang);
  const [load, setLoad] = useState<Load>({ status: "loading" });

  const incomplete = slug === "" || doctorId === "" || sessionStart === "";
  useEffect(() => {
    if (incomplete) return;
    let cancelled = false;
    apiGet("/api/v1/public/clinics/{slug}", { pathParams: { slug }, ...(via ? { query: { via: "directory" } } : {}) }).then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", clinic: data });
      },
      (error: unknown) => {
        if (cancelled) return;
        setLoad(error instanceof ApiError && error.status === 404 ? { status: "gone" } : { status: "failed", error });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [incomplete, slug, via]);

  if (!incomplete && load.status === "loading") return <ScreenLoading label={s.loading} />;
  if (load.status === "failed") return <ErrorNotice error={load.error} />;
  const doctor = load.status === "ready" ? load.clinic.doctors.find((d) => d.id === doctorId) : undefined;
  if (incomplete || load.status !== "ready" || doctor === undefined || Number.isNaN(Date.parse(sessionStart))) {
    return (
      <PortalCard id="request-gone" title={words.form.title}>
        <p>{words.form.notAvailable}</p>
        <Link href={slug === "" || via ? "/find" : `/c/${encodeURIComponent(slug)}`} className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
          {words.form.chooseAnother}
        </Link>
      </PortalCard>
    );
  }

  const clinic = load.clinic;
  const at = slotStart ?? sessionStart;
  const when = `${portalDay(at, clinic.timezone, s)}${slotStart === null ? "" : `, ${portalTime(slotStart, clinic.timezone, s)}`}`;
  return (
    <RequestForm
      clinic={clinic}
      doctorName={doctor.display_name}
      doctorId={doctorId}
      sessionStart={sessionStart}
      slotStart={slotStart}
      when={when}
      verified={account.email_verified}
      leave={leave}
    />
  );
}

function RequestForm({
  clinic,
  doctorName,
  doctorId,
  sessionStart,
  slotStart,
  when,
  verified,
  leave,
}: Readonly<{
  clinic: Clinic;
  doctorName: string;
  doctorId: string;
  sessionStart: string;
  slotStart: string | null;
  when: string;
  verified: boolean;
  leave: (error: unknown) => boolean;
}>) {
  const { s } = usePortal();
  const words = bookingWords(s.lang);
  const ids = { phone: useId(), age: useId(), sex: useId(), reason: useId(), ack: useId() };
  const [phone, setPhone] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [reason, setReason] = useState("");
  const [ack, setAck] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const [done, setDone] = useState(false);
  const [left, setLeft] = useState<ReadonlySet<string>>(new Set());
  const [checked, setChecked] = useState(false);
  const required = clinic.requires_age_sex;
  const optional = required ? undefined : ` ${words.form.optional}`;
  const leaveField = (field: string) => setLeft((now) => (now.has(field) ? now : new Set([...now, field])));

  // M7c-P7 (M6): what is missing, checked on leaving a field and on submit; the API decides again.
  const digits = phone.replace(/\D/g, "");
  const own: Record<string, string | undefined> = {
    phone: phone.trim() === "" ? words.form.check.phone : digits.length < 10 ? words.form.check.phoneShort : undefined,
    age: required && !/^\d{1,3}$/.test(age.trim()) ? words.form.check.age : age.trim() !== "" && !/^\d{1,3}$/.test(age.trim()) ? words.form.check.age : undefined,
    sex: required && sex === "" ? words.form.check.sex : undefined,
    ack: ack ? undefined : words.form.check.ack,
  };
  const shown = (field: string) => (checked || left.has(field) ? own[field] : undefined);
  const order = [
    ["phone", ids.phone],
    ["age", ids.age],
    ["sex", ids.sex],
    ["ack", ids.ack],
  ] as const;
  const problems = checked ? order.filter(([f]) => own[f] !== undefined).map(([f, id]) => ({ id, message: own[f] ?? "" })) : [];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending) return;
    setChecked(true);
    const first = order.find(([f]) => own[f] !== undefined);
    if (first !== undefined) {
      document.getElementById(first[1])?.focus();
      return;
    }
    setSending(true);
    setError(undefined);
    try {
      await portalPost("/api/v1/portal/booking-requests", {
        clinic_slug: clinic.slug,
        doctor_id: doctorId,
        session_start: sessionStart,
        ...(slotStart === null ? {} : { slot_start: slotStart }),
        contact_phone: phone.trim(),
        ...(age.trim() === "" ? {} : { age_years: Number.parseInt(age, 10) }),
        ...(sex === "" ? {} : { sex: sex as Sex }),
        ...(reason.trim() === "" ? {} : { reason: reason.trim() }),
        not_emergency_ack: ack,
      });
      setDone(true);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    } finally {
      setSending(false);
    }
  }

  if (done) {
    return (
      <PortalCard id="request-done" title={words.form.doneTitle}>
        <Alert tone="success" role="status">
          {words.form.doneBody(`${doctorName}, ${when}`)}
        </Alert>
        <Link
          href="/portal/appointments"
          className="inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-brand-700 px-4 font-semibold text-white transition-colors hover:bg-brand-800 sm:w-auto"
        >
          {words.form.goAppointments}
        </Link>
      </PortalCard>
    );
  }

  const known = error instanceof ApiError ? words.form.errors[error.code] : undefined;
  const limited = error instanceof ApiError && error.code === "PRT_RATE_LIMITED";
  const message = limited
    ? words.form.rateLimited(error.retryAfterSeconds === undefined ? undefined : String(error.retryAfterSeconds))
    : known;

  return (
    <PortalCard id="request-title" title={words.form.title}>
      {/* What is being asked for, in one glance: doctor, clinic and time. */}
      <p className="sr-only">{words.form.summary(doctorName, clinic.name, when)}</p>
      <dl aria-hidden="true" className="grid gap-2 rounded-lg border border-line bg-surface-muted p-3 text-sm sm:grid-cols-3">
        <div className="flex gap-2">
          <Stethoscope aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
          <div className="min-w-0">
            <dt className="text-slate-600">{words.form.with}</dt>
            <dd className="break-words font-semibold text-slate-900">{doctorName}</dd>
          </div>
        </div>
        <div className="flex gap-2">
          <Building2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
          <div className="min-w-0">
            <dt className="text-slate-600">{words.form.at}</dt>
            <dd className="break-words font-semibold text-slate-900">{clinic.name}</dd>
          </div>
        </div>
        <div className="flex gap-2">
          <CalendarClock aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
          <div className="min-w-0">
            <dt className="text-slate-600">{words.form.when}</dt>
            <dd className="font-semibold tabular-nums text-slate-900">{when}</dd>
          </div>
        </div>
      </dl>
      <p className="text-sm text-slate-700">{words.page.howItWorks}</p>
      {!verified && (
        <div role="note" id={`${ids.phone}-verify`} className="space-y-2 rounded-xl border border-warning-line bg-warning-soft p-3 text-slate-900">
          <p>{words.form.verify}</p>
          <Link href="/portal/account" className="inline-flex min-h-11 items-center font-semibold underline underline-offset-2">
            {words.form.goAccount}
          </Link>
        </div>
      )}
      <ErrorSummary title={words.form.check.title} errors={problems.length > 1 ? problems : []} />
      <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
        <TextField
          id={ids.phone}
          label={words.form.phone}
          hint={words.form.phoneHelp}
          value={phone}
          onChange={setPhone}
          onBlur={() => leaveField("phone")}
          error={shown("phone")}
          required
          requiredMark={false}
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          maxLength={20}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id={ids.age}
            label={`${words.form.age}${optional ?? ""}`}
            value={age}
            onChange={setAge}
            onBlur={() => leaveField("age")}
            error={shown("age")}
            required={required}
            requiredMark={false}
            inputMode="numeric"
            maxLength={3}
          />
          <SelectField
            id={ids.sex}
            label={`${words.form.sex}${optional ?? ""}`}
            value={sex}
            onChange={(v) => {
              setSex(v);
              leaveField("sex");
            }}
            error={shown("sex")}
            required={required}
            requiredMark={false}
            options={[{ value: "", label: words.form.choose }, ...SEXES.map((v) => ({ value: v, label: words.form.sexes[v] }))]}
          />
        </div>
        <TextAreaField
          id={ids.reason}
          label={`${words.form.reason} ${words.form.optional}`}
          hint={words.form.reasonHelp}
          value={reason}
          onChange={setReason}
          maxLength={200}
        />
        <div className="rounded-lg border border-line p-3">
          <CheckboxField id={ids.ack} label={words.form.ack} checked={ack} onChange={setAck} error={shown("ack")} />
        </div>
        <p className="text-sm text-slate-700">{words.form.holdNote}</p>
        {error !== undefined &&
          (message !== undefined ? (
            <p role="alert" className="flex gap-2 rounded-xl border border-danger-line bg-danger-soft p-3 font-medium text-slate-900">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
              <span>{message}</span>
            </p>
          ) : (
            <ErrorNotice error={error} />
          ))}
        {error !== undefined && message !== undefined && !limited && (
          <Link href={`/c/${encodeURIComponent(clinic.slug)}`} className="inline-flex min-h-11 items-center font-semibold text-brand-800 underline underline-offset-2">
            {words.form.chooseAnother}
          </Link>
        )}
        {/* Enabled while anything is missing (the checks say what); disabled only for an unconfirmed
            email, which the note above explains, and while sending. */}
        <Button
          type="submit"
          variant="primary"
          size="lg"
          loading={sending}
          disabled={!verified}
          aria-describedby={verified ? undefined : `${ids.phone}-verify`}
          className="w-full"
        >
          {sending ? words.form.sending : words.form.submit}
        </Button>
      </form>
    </PortalCard>
  );
}