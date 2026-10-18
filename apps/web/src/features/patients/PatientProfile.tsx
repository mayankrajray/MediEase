"use client";

import { useEffect, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { PatientAppointments } from "@/features/appointments/PatientAppointments";
import { PrintablePrescriptions } from "@/features/prescriptions/PrintablePrescriptions";
import { useClinic } from "@/features/shell/ClinicGate";
import { PatientVisits } from "@/features/visits/PatientVisits";
import { formatPhone } from "@/lib/format/phone";

import { usePatientApi } from "./api";
import { ConsentPanel } from "./ConsentPanel";
import { EditPatientForm } from "./EditPatientForm";
import { ageText, clinicToday, isNotFound, LANGUAGE_LABELS, SEX_LABELS, type Patient } from "./fields";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly patient: Patient }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * One patient (FR-PAT-03): the code, demographics with the phone in full (staff
 * dial it), an in-place edit, and the message consent. Another clinic's patient
 * and an unknown ID read the same "Patient not found" (NFR-08, AC7).
 */
export function PatientProfile({ patientId }: { patientId: string }) {
  const clinic = useClinic();
  const { clinic: choice, endSession } = useSession();
  const permissions = choice.kind === "active" ? choice.membership.permissions : [];
  const canViewClinical = permissions.includes("CLINICAL_VIEW");
  const canPrint = permissions.includes("RX_PRINT");
  const api = usePatientApi();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [editing, setEditing] = useState(false);

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

  if (load.status === "loading") {
    return (
      <p role="status" className="text-slate-700">
        Loading patient…
      </p>
    );
  }
  if (load.status === "failed") {
    return isNotFound(load.error) ? (
      <section className="space-y-2">
        <h1 className="text-2xl font-bold">Patient not found</h1>
        <p>This patient is not registered in {clinic.name}. Search again with the phone number or code.</p>
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
    <article aria-labelledby="patient-heading" className="space-y-6">
      <header className="space-y-1">
        <p className="font-mono text-lg font-semibold text-slate-800">{patient.code}</p>
        <h1 id="patient-heading" className="text-2xl font-bold">
          {patient.full_name}
        </h1>
        <p className="text-slate-800">
          {ageText(patient)} · {SEX_LABELS[patient.sex]}
          {patient.is_minor && " · under 18"}
        </p>
      </header>

      <section aria-labelledby="details-heading" className="space-y-3 rounded border border-slate-300 p-4">
        <div className="flex items-center justify-between">
          <h2 id="details-heading" className="text-lg font-bold">
            Details
          </h2>
          {!editing && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100"
            >
              Edit details
            </button>
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
            }}
          />
        ) : (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2">
            <dt className="font-medium">{patient.is_minor ? "Parent or guardian's phone" : "Phone"}</dt>
            <dd>
              <a href={`tel:${patient.phone_e164}`} className="text-blue-900 underline">
                {formatPhone(patient.phone_e164)}
              </a>
            </dd>
            {patient.guardian_name !== null && (
              <>
                <dt className="font-medium">Parent or guardian</dt>
                <dd>{patient.guardian_name}</dd>
              </>
            )}
            <dt className="font-medium">Date of birth</dt>
            <dd>{patient.date_of_birth ?? "Not known (age recorded instead)"}</dd>
            <dt className="font-medium">Message language</dt>
            <dd>{LANGUAGE_LABELS[patient.language]}</dd>
          </dl>
        )}
      </section>

      <ConsentPanel patient={patient} timeZone={clinic.timezone} onChange={show} />

      <PatientAppointments patient={patient} />

      {canViewClinical && <PatientVisits patientId={patient.id} />}
      {canPrint && <PrintablePrescriptions patientId={patient.id} />}
    </article>
  );
}
