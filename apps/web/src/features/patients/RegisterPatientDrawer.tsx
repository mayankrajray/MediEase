"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/Button";
import { ErrorSummary } from "@/components/ui/Field";
import { useFocusOnError } from "@/components/useFocusOnError";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { usePatientApi } from "./api";
import { DuplicateCandidates } from "./DuplicateCandidates";
import { EMPTY_DRAFT, newPatientBody, patientFieldErrors, phoneCandidates, type PatientDraft } from "./fields";
import { PatientFields, usePatientForm } from "./PatientFields";

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
 *
 * M7c-P7 (M5): fields are checked on leaving them and on submit; a submit with problems lists
 * them at the top, moves focus to the first and sends nothing. The button says "Registering…"
 * while the call runs.
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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error, container);

  const candidates = phoneCandidates(error);
  const apiProblems = patientFieldErrors(error);
  const alertError = error !== null && candidates === undefined && Object.keys(apiProblems).length === 0;
  const form = usePatientForm({ ...EMPTY_DRAFT, ...prefill }, today, "register", apiProblems);
  const change = (next: PatientDraft) => {
    form.setDraft(next);
    // The API's answer was about the old values; the form checks the new ones itself.
    if (error !== null && candidates === undefined) setError(null);
  };

  async function submit(confirmNew: boolean) {
    if (submitting) return;
    setSubmitting(true);
    try {
      const patient = await api.register(newPatientBody(form.draft, confirmNew));
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
    if (!form.check()) return;
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
            <ErrorSummary title="Check these before registering" errors={form.summary.length > 1 ? form.summary : []} />
            <form onSubmit={onSubmit} noValidate className="space-y-5">
              <PatientFields idPrefix="register" form={{ ...form, setDraft: change }} today={today} />
              <div className="flex flex-wrap gap-2 border-t border-line pt-4">
                <Button type="submit" variant="primary" loading={submitting} className="max-sm:w-full">
                  {submitting ? "Registering…" : "Register patient"}
                </Button>
                <Button onClick={onClose} disabled={submitting} className="max-sm:w-full">
                  Cancel
                </Button>
              </div>
            </form>
          </>
        )}
      </div>
    </Drawer>
  );
}
