"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ROLE_LABELS } from "@/features/auth/labels";
import { useSession } from "@/features/auth/SessionProvider";
import { ApiError, type GetResponse } from "@/lib/api/client";
import { sessionGet } from "@/lib/auth/refresh";

import { ClinicStep, type NewClinicResult } from "./ClinicStep";
import { DoctorsStep, type AddedDoctor } from "./DoctorsStep";
import { ElapsedTimer } from "./ElapsedTimer";
import { InviteStep, type InvitedPerson } from "./InviteStep";

type Detail = GetResponse<"/api/v1/ops/clinics/{clinic_id}">;
type Step = "clinic" | "doctors" | "invite" | "done";

const STEPS: readonly { readonly id: Exclude<Step, "done">; readonly label: string }[] = [
  { id: "clinic", label: "Clinic" },
  { id: "doctors", label: "Doctors" },
  { id: "invite", label: "Owner invitation" },
];

const HEADINGS: Record<Step, string> = {
  clinic: "Step 1 of 3: the clinic",
  doctors: "Step 2 of 3: doctors",
  invite: "Step 3 of 3: invite the owner",
  done: "Clinic created",
};

type Resume =
  | { readonly status: "none" }
  | { readonly status: "loading" }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * The Create clinic wizard (spec §6, FR-OPS-01): clinic → doctors → owner
 * invitation, with the elapsed onboarding time (goal G4). The server is the
 * record of what exists, so a half-finished onboarding is resumed by clinic ID
 * (`?clinic=`) rather than kept in browser storage. The acceptance link is
 * deliberately not recoverable.
 */
export function CreateClinicWizard({ resumeClinicId }: { resumeClinicId?: string }) {
  const { endSession } = useSession();
  const [step, setStep] = useState<Step>("clinic");
  const [clinic, setClinic] = useState<NewClinicResult | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [doctors, setDoctors] = useState<AddedDoctor[]>([]);
  const [earlierDoctors, setEarlierDoctors] = useState(0);
  const [invited, setInvited] = useState<InvitedPerson[]>([]);
  const [resume, setResume] = useState<Resume>(
    resumeClinicId === undefined ? { status: "none" } : { status: "loading" },
  );
  const [timerError, setTimerError] = useState<unknown>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  // Move focus to the step heading whenever the step changes (not on first paint).
  const firstPaint = useRef(true);
  useEffect(() => {
    if (firstPaint.current) {
      firstPaint.current = false;
      return;
    }
    heading.current?.focus();
  }, [step]);

  // Resuming: load what already exists for this clinic.
  useEffect(() => {
    if (resumeClinicId === undefined) return;
    let cancelled = false;
    sessionGet("/api/v1/ops/clinics/{clinic_id}", { pathParams: { clinic_id: resumeClinicId } }).then(
      ({ data }: { data: Detail }) => {
        if (cancelled) return;
        if (data.status !== "ONBOARDING") {
          setResume({
            status: "failed",
            error: new ApiError(
              "WEB_CLINIC_NOT_ONBOARDING",
              `${data.name} is already set up, so it cannot be continued here.`,
              409,
              "",
            ),
          });
          return;
        }
        setClinic(data);
        setStartedAt(data.onboarding?.started_at ?? null);
        setEarlierDoctors(data.doctor_count);
        setInvited(data.staff.filter((person) => person.status === "INVITED"));
        setResume({ status: "none" });
        setStep("doctors");
      },
      (failure: unknown) => {
        if (cancelled || endSession(failure)) return;
        setResume({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [resumeClinicId, endSession]);

  function created(result: NewClinicResult) {
    setClinic(result);
    setStep("doctors");
    // The checklist's start time comes from the server; the clinic response does not carry it.
    sessionGet("/api/v1/ops/clinics/{clinic_id}", { pathParams: { clinic_id: result.id } }).then(
      ({ data }) => setStartedAt(data.onboarding?.started_at ?? null),
      (failure: unknown) => {
        if (!endSession(failure)) setTimerError(failure);
      },
    );
  }

  if (resume.status === "loading") {
    return (
      <p role="status" className="text-slate-700">
        Loading the clinic…
      </p>
    );
  }
  if (resume.status === "failed") {
    return (
      <div className="max-w-xl space-y-3">
        <ErrorNotice error={resume.error} />
        <Link href="/ops" className="text-blue-800 underline">
          Back to the clinics
        </Link>
      </div>
    );
  }

  return (
    <section aria-labelledby="wizard-title" className="space-y-5">
      <h1 id="wizard-title" className="text-2xl font-bold">
        Create clinic
      </h1>

      <ol aria-label="Progress" className="flex flex-wrap gap-x-6 gap-y-1">
        {STEPS.map((item, index) => {
          const current = item.id === step;
          const complete = step === "done" || STEPS.findIndex((s) => s.id === step) > index;
          return (
            <li key={item.id} aria-current={current ? "step" : undefined} className={current ? "font-bold" : ""}>
              {index + 1}. {item.label}
              {complete && <span> (done)</span>}
            </li>
          );
        })}
      </ol>

      {startedAt !== null && <ElapsedTimer startedAt={startedAt} />}
      {timerError !== null && (
        <p className="text-sm text-slate-700">The onboarding timer could not be loaded; the steps still work.</p>
      )}

      <h2 ref={heading} tabIndex={-1} className="text-xl font-semibold">
        {clinic !== null && step !== "clinic" ? `${clinic.name}: ` : ""}
        {HEADINGS[step]}
      </h2>

      {step === "clinic" && <ClinicStep onCreated={created} />}

      {step === "doctors" && clinic !== null && (
        <DoctorsStep
          clinicId={clinic.id}
          doctors={doctors}
          alreadyAdded={earlierDoctors}
          onAdded={(doctor) => setDoctors((list) => [...list, doctor])}
          onContinue={() => setStep("invite")}
        />
      )}

      {step === "invite" && clinic !== null && (
        <InviteStep
          clinicId={clinic.id}
          invited={invited}
          onInvited={(invitation) => setInvited((list) => [...list, invitation])}
          onFinish={() => setStep("done")}
        />
      )}

      {step === "done" && clinic !== null && (
        <div className="max-w-2xl space-y-3">
          <p>
            <strong>{clinic.name}</strong> is created with {doctors.length + earlierDoctors}{" "}
            {doctors.length + earlierDoctors === 1 ? "doctor" : "doctors"} and {invited.length}{" "}
            {invited.length === 1 ? "invitation" : "invitations"}.
          </p>
          {invited.length > 0 && (
            <ul className="list-disc pl-6">
              {invited.map((person) => (
                <li key={person.membership_id}>
                  {person.full_name}, {ROLE_LABELS[person.role]}
                </li>
              ))}
            </ul>
          )}
          <p>
            The clinic becomes <strong>active</strong> when its owner accepts the invitation. Follow it in the clinics
            list.
          </p>
          <Link
            href="/ops"
            className="inline-block rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900"
          >
            Back to the clinics
          </Link>
        </div>
      )}
    </section>
  );
}
