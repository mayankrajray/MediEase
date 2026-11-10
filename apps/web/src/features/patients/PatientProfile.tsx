"use client";

import { Pencil, Phone, SearchX } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatusMessage } from "@/components/ui/StatusMessage";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { PatientAppointments } from "@/features/appointments/PatientAppointments";
import { PatientBills } from "@/features/bills/PatientBills";
import { PrintablePrescriptions } from "@/features/prescriptions/PrintablePrescriptions";
import { PatientMessages } from "@/features/reminders/PatientMessages";
import { PatientReminders } from "@/features/reminders/PatientReminders";
import { useClinic } from "@/features/shell/ClinicGate";
import { PatientVisits } from "@/features/visits/PatientVisits";
import { formatPhone } from "@/lib/format/phone";

import { usePatientApi } from "./api";
import { ConsentPanel } from "./ConsentPanel";
import { EditPatientForm } from "./EditPatientForm";
import { PatientPortalCard } from "./PatientPortalCard";
import { ageText, clinicToday, isNotFound, LANGUAGE_LABELS, SEX_LABELS, type Patient } from "./fields";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly patient: Patient }
  | { readonly status: "failed"; readonly error: unknown };

/** The profile's cards share one surface (DESIGN.md §3). */
export const PROFILE_CARD = "space-y-3 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5";

/**
 * One patient (FR-PAT-03): the code, demographics with the phone in full (staff
 * dial it), an in-place edit, and the message consent. Another clinic's patient
 * and an unknown ID read the same "Patient not found" (NFR-08, AC7).
 *
 * M7c-P7 (M5): a header with who this is (initials, name, code, age and sex, under 18, no
 * messages); on a wide screen the record's working sections (appointments, visits, prescriptions,
 * bills, reminders, messages sent) on the left and the details, consent and patient app on the
 * right; on a phone the details come first. A saved edit is confirmed in words.
 */
export function PatientProfile({ patientId }: { patientId: string }) {
  const clinic = useClinic();
  const { clinic: choice, endSession } = useSession();
  const permissions = choice.kind === "active" ? choice.membership.permissions : [];
  const canViewClinical = permissions.includes("CLINICAL_VIEW");
  const canPrint = permissions.includes("RX_PRINT");
  const canRemind = permissions.includes("REMINDERS_SCHEDULE");
  const canManage = permissions.includes("PATIENTS_MANAGE");
  const canBill = permissions.includes("BILLING_MANAGE");
  const api = usePatientApi();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.get(patientId).then(
      (patient) => {
        if (!cancelled) setLoad({ status: "ready", patient });
      },
      (error: unknown) => {
        if (!cancelled && !endSession(error)) setLoad({ status: "failed", error });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [patientId, api, attempt, endSession]);

  if (load.status === "loading") return <ProfileSkeleton />;
  if (load.status === "failed") {
    return isNotFound(load.error) ? (
      <section className="space-y-4">
        <h1 className="heading-5 text-slate-900">Patient not found</h1>
        <EmptyState
          icon={<SearchX className="size-5" />}
          title={`This patient is not registered in ${clinic.name}.`}
          action={
            <Link href="/patients" className={buttonClasses("secondary")}>
              Search patients
            </Link>
          }
        >
          Search again with the phone number or code.
        </EmptyState>
      </section>
    ) : (
      <ErrorNotice
        error={load.error}
        onRetry={() => {
          setLoad({ status: "loading" });
          setAttempt((n) => n + 1);
        }}
      />
    );
  }

  const { patient } = load;
  const show = (next: Patient) => setLoad({ status: "ready", patient: next });
  const today = clinicToday(clinic.timezone);

  return (
    <article aria-labelledby="patient-heading" className="space-y-5">
      <Breadcrumbs items={[{ label: "Patients", href: "/patients" }, { label: patient.full_name }]} />
      <header className="flex flex-wrap items-center gap-4 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
        <Avatar name={patient.full_name} size="lg" />
        <div className="min-w-0 flex-1 space-y-1">
          <h1 id="patient-heading" className="heading-5 break-words text-slate-900">
            {patient.full_name}
          </h1>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-slate-700">
            <span className="rounded-md bg-surface-muted px-2 py-0.5 text-sm font-semibold tabular-nums text-slate-800 ring-1 ring-inset ring-line">
              {patient.code}
            </span>
            <span>
              {ageText(patient)} · {SEX_LABELS[patient.sex]}
            </span>
            {patient.is_minor && <StatusBadge tone="active">Under 18</StatusBadge>}
            {patient.opted_out && <StatusBadge tone="missed">No messages</StatusBadge>}
          </p>
        </div>
      </header>

      <StatusMessage message={saved} />

      <div className="grid items-start gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-start-3 lg:row-start-1">
          <section aria-labelledby="details-heading" className={PROFILE_CARD}>
            <div className="flex items-center justify-between gap-2">
              <h2 id="details-heading" className="heading-6 text-slate-900">
                Details
              </h2>
              {!editing && (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Pencil className="size-4" />}
                  onClick={() => {
                    setSaved("");
                    setEditing(true);
                  }}
                >
                  Edit details
                </Button>
              )}
            </div>
            {editing ? (
              <EditPatientForm
                patient={patient}
                today={today}
                onCancel={() => setEditing(false)}
                onSaved={(next) => {
                  show(next);
                  setEditing(false);
                  setSaved(`Details for ${next.full_name} saved.`);
                }}
              />
            ) : (
              <dl className="space-y-3">
                <div>
                  <dt className="text-sm text-slate-700">{patient.is_minor ? "Parent or guardian's phone" : "Phone"}</dt>
                  <dd className="mt-0.5">
                    <a
                      href={`tel:${patient.phone_e164}`}
                      className="inline-flex min-h-11 items-center gap-2 rounded font-semibold tabular-nums text-brand-800 underline underline-offset-2 hover:text-brand-900 sm:min-h-6"
                    >
                      <Phone aria-hidden="true" className="size-4 shrink-0" />
                      {formatPhone(patient.phone_e164)}
                    </a>
                  </dd>
                </div>
                {patient.guardian_name !== null && (
                  <div>
                    <dt className="text-sm text-slate-700">Parent or guardian</dt>
                    <dd className="mt-0.5 break-words font-medium text-slate-900">{patient.guardian_name}</dd>
                  </div>
                )}
                <div>
                  <dt className="text-sm text-slate-700">Date of birth</dt>
                  <dd className="mt-0.5 font-medium tabular-nums text-slate-900">
                    {patient.date_of_birth ?? "Not known (age recorded instead)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-slate-700">Message language</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">{LANGUAGE_LABELS[patient.language]}</dd>
                </div>
              </dl>
            )}
          </section>

          <ConsentPanel patient={patient} timeZone={clinic.timezone} onChange={show} />

          {canManage && <PatientPortalCard patient={patient} />}
        </div>

        <div className="min-w-0 space-y-5 lg:col-span-2 lg:col-start-1 lg:row-start-1">
          <PatientAppointments patient={patient} />
          {canViewClinical && <PatientVisits patientId={patient.id} />}
          {canPrint && <PrintablePrescriptions patientId={patient.id} />}
          {canBill && <PatientBills patientId={patient.id} />}
          {canRemind && <PatientReminders patient={patient} />}
          {canRemind && <PatientMessages patient={patient} />}
        </div>
      </div>
    </article>
  );
}

function ProfileSkeleton() {
  return (
    <div className="space-y-5">
      <p role="status" className="sr-only">
        Loading patient…
      </p>
      <div aria-hidden="true" className="flex items-center gap-4 rounded-card border border-line bg-surface p-5 shadow-card">
        <Skeleton className="size-14 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-4 w-40" />
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Skeleton className="h-64 lg:col-span-2" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}
