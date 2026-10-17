"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

import { Drawer } from "@/components/Drawer";
import { useFocusOnError } from "@/components/useFocusOnError";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { usePatientApi } from "./api";
import { DuplicateCandidates } from "./DuplicateCandidates";
import {
  EMPTY_DRAFT,
  newPatientBody,
  patientFieldErrors,
  phoneCandidates,
  type PatientDraft,
} from "./fields";
import { PatientFields } from "./PatientFields";

export interface RegisterPrefill {
  readonly phone?: string;
  readonly full_name?: string;
}

/** Where a patient's profile lives. */
export const patientPath = (id: string) => `/patients/${id}`;

/**
 * Register a patient (FR-PAT-01, 02, 06). A phone the clinic already has comes
 * back as candidates; "Register as a new family member" resends the same details
 * with `confirm_new: true`. The button is disabled while a request is in flight,
 * so a double click cannot register twice.
 */
export function RegisterPatientDrawer({
  prefill,
  today,
  onClose,
}: {
  prefill: RegisterPrefill;
  today: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const { endSession } = useSession();
  const api = usePatientApi();
  const [draft, setDraft] = useState<PatientDraft>({ ...EMPTY_DRAFT, ...prefill });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error, container);

  const candidates = phoneCandidates(error);
  const problems = patientFieldErrors(error);
  const alertError = error !== null && candidates === undefined && Object.keys(problems).length === 0;

  async function submit(confirmNew: boolean) {
    if (submitting) return;
    setSubmitting(true);
    try {
      const patient = await api.register(newPatientBody(draft, confirmNew));
      onClose();
      router.push(patientPath(patient.id));
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    void submit(false);
  }

  return (
    <Drawer title="Register patient" onClose={onClose}>
      <div ref={container} className="space-y-4">
        {candidates !== undefined ? (
          <DuplicateCandidates
            candidates={candidates}
            submitting={submitting}
            onUse={(candidate) => {
              onClose();
              router.push(patientPath(candidate.id));
            }}
            onRegisterNew={() => void submit(true)}
            onBack={() => setError(null)}
          />
        ) : (
          <>
            {alertError && <ErrorNotice error={error} />}
            <form onSubmit={onSubmit} noValidate className="space-y-4">
              <PatientFields idPrefix="register" draft={draft} onChange={setDraft} today={today} problems={problems} />
              <button
                type="submit"
                disabled={submitting}
                className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900 disabled:cursor-not-allowed disabled:bg-slate-500"
              >
                {submitting ? "Registering…" : "Register patient"}
              </button>
            </form>
          </>
        )}
      </div>
    </Drawer>
  );
}
