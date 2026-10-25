"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";
import { CheckboxField, SelectField, TextAreaField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { sessionGet, sessionPost, sessionPut } from "@/lib/auth/refresh";
import { formatDateTime } from "@/lib/format/time";

import { ApproveApplication } from "./ApproveApplication";
import { REJECT_LABELS, STATUS_LABELS, certificateBlob, type ApplicationDetail, type ApplicationDoctor, type RejectReason } from "./api";

const IST = "Asia/Kolkata";

function Row({ label, children }: Readonly<{ label: string; children: ReactNode }>) {
  return (
    <>
      <dt className="font-medium text-slate-700">{label}</dt>
      <dd className="break-words">{children}</dd>
    </>
  );
}

/**
 * One application for a reviewer (M6c-P2; spec clinic-onboarding R26-R34; P3 R41): the clinic,
 * the owner, each doctor's registration with *Open certificate* and the check, then *Take*,
 * *Reject* and, once every doctor is verified, *Approve* (which creates the clinic, P3). Opening
 * the page and each certificate is audited by the API.
 */
export function ReviewApplication({ applicationId }: Readonly<{ applicationId: string }>) {
  const { endSession } = useSession();
  const [detail, setDetail] = useState<ApplicationDetail | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    sessionGet("/api/v1/ops/applications/{application_id}", {
      pathParams: { application_id: applicationId },
    }).then(
      ({ data }) => {
        if (!cancelled) setDetail(data);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [applicationId, endSession]);

  async function act(run: () => Promise<ApplicationDetail>, done: string) {
    setBusy(true);
    setError(null);
    try {
      setDetail(await run());
      setStatus(done);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  const path = { pathParams: { application_id: applicationId } };
  const take = () =>
    act(async () => (await sessionPost("/api/v1/ops/applications/{application_id}/take", undefined, path)).data, "You are reviewing this application.");

  if (detail === undefined) {
    return error !== null ? <ErrorNotice error={error} /> : <p role="status">Loading the application…</p>;
  }
  const reviewing = detail.status === "UNDER_REVIEW";

  return (
    <section aria-labelledby="application-heading" className="max-w-4xl space-y-5">
      <Link href="/ops/applications" className="font-medium text-brand-800 underline">
        All applications
      </Link>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 id="application-heading" className="text-2xl font-bold tracking-tight">
          {detail.clinic_name} <span className="font-mono text-lg text-slate-700">{detail.reference}</span>
        </h1>
        <p className="font-semibold">{STATUS_LABELS[detail.status]}</p>
      </div>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {status}
      </p>
      {error !== null && <ErrorNotice error={error} />}
      {detail.duplicate_of.length > 0 && (
        <p role="note" className="rounded-lg border border-amber-700 bg-amber-50 p-3 text-amber-950">
          Possible duplicate: a registration also appears in {detail.duplicate_of.join(", ")}.
        </p>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
        <Row label="Kind">{detail.kind === "SOLO_DOCTOR" ? "A doctor with their own practice" : "A clinic"}</Row>
        <Row label="Address">
          {detail.address_line}, {detail.city}, {detail.state} {detail.pincode}
        </Row>
        <Row label="Clinic phone">{detail.clinic_phone_e164}</Row>
        <Row label="Specialties">{detail.specialties.join(", ")}</Row>
        <Row label="Owner">
          {detail.owner_name} · {detail.owner_phone_e164} · {detail.owner_email}
          {detail.owner_practises ? " · also sees patients" : ""}
        </Row>
        <Row label="Confirmed">{detail.email_verified_at === null ? "—" : formatDateTime(detail.email_verified_at, IST)}</Row>
        {detail.decided_at !== null && <Row label="Decided">{formatDateTime(detail.decided_at, IST)}</Row>}
        {detail.decision_reason !== null && (
          <Row label="Reason">
            {REJECT_LABELS[detail.decision_reason]}
            {detail.decision_message !== null ? `: ${detail.decision_message}` : ""}
          </Row>
        )}
        {detail.clinic_id !== null && (
          <Row label="Clinic">
            <span className="font-mono">{detail.clinic_id}</span>
          </Row>
        )}
      </dl>

      <h2 className="text-lg font-semibold">Doctors</h2>
      <ol className="space-y-4">
        {detail.doctors.map((doctor) => (
          <li key={doctor.id}>
            <DoctorCard
              applicationId={applicationId}
              doctor={doctor}
              editable={reviewing}
              onChecked={(next) => {
                setDetail(next);
                setStatus(`Doctor ${doctor.position} checked.`);
              }}
            />
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap gap-3">
        {detail.status === "PENDING" && (
          <Button variant="primary" onClick={() => void take()} disabled={busy}>
            Take for review
          </Button>
        )}
        {reviewing && (
          <>
            <Button variant="primary" onClick={() => setApproving(true)} disabled={busy || !detail.all_verified}>
              Approve and create the clinic
            </Button>
            <Button onClick={() => setRejecting(true)} disabled={busy}>
              Reject…
            </Button>
          </>
        )}
      </div>
      {reviewing && !detail.all_verified && <p className="text-sm text-slate-700">Approve is available once every doctor is verified.</p>}

      {rejecting && (
        <RejectDialog
          applicationId={applicationId}
          onClose={() => setRejecting(false)}
          onDone={(next) => {
            setDetail(next);
            setRejecting(false);
            setStatus("Rejected. The applicant has been emailed the reason.");
          }}
        />
      )}
      {approving && (
        <ApproveApplication
          detail={detail}
          onClose={() => setApproving(false)}
          onDone={(next, text) => {
            setDetail(next);
            setApproving(false);
            setStatus(text);
          }}
        />
      )}
    </section>
  );
}

function DoctorCard({
  applicationId,
  doctor,
  editable,
  onChecked,
}: Readonly<{
  applicationId: string;
  doctor: ApplicationDoctor;
  editable: boolean;
  onChecked: (next: ApplicationDetail) => void;
}>) {
  const { endSession } = useSession();
  const [register, setRegister] = useState(doctor.check?.register_checked ?? false);
  const [matches, setMatches] = useState(doctor.check?.certificate_matches ?? false);
  const [note, setNote] = useState(doctor.check?.note ?? "");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function open() {
    setError(null);
    try {
      const blob = await certificateBlob(applicationId, doctor.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    }
  }

  async function save(result: "VERIFIED" | "NOT_VERIFIED") {
    setBusy(true);
    setError(null);
    try {
      const { data } = await sessionPut(
        "/api/v1/ops/applications/{application_id}/doctors/{doctor_id}/check",
        {
          register_checked: register,
          certificate_matches: matches,
          result,
          note: note.trim() === "" ? null : note,
        },
        { pathParams: { application_id: applicationId, doctor_id: doctor.id } },
      );
      onChecked(data);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  const id = `doctor-${doctor.position}`;
  return (
    <article aria-labelledby={`${id}-name`} className="space-y-3 rounded-card border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={`${id}-name`} className="font-semibold">
          {doctor.position}. {doctor.name} {doctor.is_owner && <span className="text-sm font-normal text-slate-700">(owner)</span>}
        </h3>
        <p className="font-medium">{doctor.check === null ? "Not checked" : doctor.check.result === "VERIFIED" ? "Verified" : "Not verified"}</p>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
        <Row label="Qualification">{doctor.qualification}</Row>
        <Row label="Council">{doctor.council}</Row>
        <Row label="Registration">
          <span className="font-mono">{doctor.registration_number}</span>
        </Row>
      </dl>
      <Button size="sm" onClick={() => void open()}>
        Open certificate ({doctor.certificate.content_type === "application/pdf" ? "PDF" : "image"})
      </Button>
      {error !== null && <ErrorNotice error={error} />}
      {editable && (
        <fieldset className="space-y-2">
          <legend className="font-medium">Check</legend>
          <CheckboxField id={`${id}-register`} label="Found on the council's register" checked={register} onChange={setRegister} />
          <CheckboxField id={`${id}-matches`} label="The certificate matches the application" checked={matches} onChange={setMatches} />
          <TextAreaField id={`${id}-note`} label="Note for reviewers (not sent)" value={note} onChange={setNote} maxLength={500} rows={2} />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="primary" onClick={() => void save("VERIFIED")} disabled={busy || !register || !matches}>
              Mark verified
            </Button>
            <Button size="sm" onClick={() => void save("NOT_VERIFIED")} disabled={busy}>
              Mark not verified
            </Button>
          </div>
        </fieldset>
      )}
    </article>
  );
}

function RejectDialog({
  applicationId,
  onClose,
  onDone,
}: Readonly<{
  applicationId: string;
  onClose: () => void;
  onDone: (next: ApplicationDetail) => void;
}>) {
  const { endSession } = useSession();
  const [reason, setReason] = useState<RejectReason | "">("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const needsMessage = reason === "OTHER" && message.trim() === "";

  async function reject() {
    if (reason === "" || needsMessage) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await sessionPost(
        "/api/v1/ops/applications/{application_id}/reject",
        { reason, message: message.trim() === "" ? null : message },
        { pathParams: { application_id: applicationId } },
      );
      onDone(data);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="Reject the application" onClose={onClose}>
      <SelectField
        id="reject-reason"
        label="Reason the applicant will read"
        required
        value={reason}
        onChange={(v) => setReason(v as RejectReason | "")}
        options={[
          { value: "", label: "Choose a reason" },
          ...(Object.keys(REJECT_LABELS) as RejectReason[]).map((r) => ({
            value: r,
            label: REJECT_LABELS[r],
          })),
        ]}
      />
      <TextAreaField
        id="reject-message"
        label="Message to the applicant"
        value={message}
        onChange={setMessage}
        maxLength={500}
        hint="Sent by email with the reason. Required for Other."
        {...(needsMessage ? { error: "Write a message for Other." } : {})}
      />
      {error !== null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={onClose}>Go back</Button>
        <Button variant="danger" onClick={() => void reject()} disabled={busy || reason === "" || needsMessage}>
          Reject and email the applicant
        </Button>
      </div>
    </Dialog>
  );
}
