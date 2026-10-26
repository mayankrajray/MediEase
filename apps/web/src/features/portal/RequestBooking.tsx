"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { CheckboxField, SelectField, TextAreaField, TextField } from "@/components/ui/Field";
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
  const required = clinic.requires_age_sex;
  const optional = required ? undefined : ` ${words.form.optional}`;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending) return;
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
        <p role="status">{words.form.doneBody(`${doctorName}, ${when}`)}</p>
        <Link href="/portal/appointments" className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
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
      <p className="font-medium">{words.form.summary(doctorName, clinic.name, when)}</p>
      <p className="text-sm text-slate-700">{words.page.howItWorks}</p>
      {!verified && (
        <div role="note" className="space-y-2 rounded-lg border border-amber-700 bg-amber-50 p-3 text-amber-950">
          <p>{words.form.verify}</p>
          <Link href="/portal/account" className="inline-flex min-h-11 items-center font-medium underline">
            {words.form.goAccount}
          </Link>
        </div>
      )}
      <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate={false}>
        <TextField
          id={ids.phone}
          label={words.form.phone}
          hint={words.form.phoneHelp}
          value={phone}
          onChange={setPhone}
          required
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          maxLength={20}
        />
        <TextField
          id={ids.age}
          label={`${words.form.age}${optional ?? ""}`}
          value={age}
          onChange={setAge}
          required={required}
          inputMode="numeric"
          maxLength={3}
        />
        <SelectField
          id={ids.sex}
          label={`${words.form.sex}${optional ?? ""}`}
          value={sex}
          onChange={setSex}
          required={required}
          options={[{ value: "", label: words.form.choose }, ...SEXES.map((v) => ({ value: v, label: words.form.sexes[v] }))]}
        />
        <TextAreaField
          id={ids.reason}
          label={`${words.form.reason} ${words.form.optional}`}
          hint={words.form.reasonHelp}
          value={reason}
          onChange={setReason}
          maxLength={200}
        />
        <CheckboxField id={ids.ack} label={words.form.ack} checked={ack} onChange={setAck} />
        <p className="text-sm text-slate-700">{words.form.holdNote}</p>
        {error !== undefined && (message !== undefined ? <p role="alert" className="rounded-lg border border-red-700 bg-red-50 p-3 font-medium text-red-950">{message}</p> : <ErrorNotice error={error} />)}
        {error !== undefined && message !== undefined && !limited && (
          <Link href={`/c/${encodeURIComponent(clinic.slug)}`} className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
            {words.form.chooseAnother}
          </Link>
        )}
        <Button type="submit" variant="primary" disabled={sending || !ack || phone.trim() === "" || !verified} className="w-full min-h-11">
          {sending ? words.form.sending : words.form.submit}
        </Button>
      </form>
    </PortalCard>
  );
}
