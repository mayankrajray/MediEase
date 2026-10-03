"use client";

import { useRef, useState, type FormEvent } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import type { PostResponse } from "@/lib/api/client";
import { sessionPost } from "@/lib/auth/refresh";

import { emptyToNull, fieldErrors } from "./fields";
import { TextField } from "./TextField";
import { useFocusOnError } from "./useFocusOnError";

const PATH = "/api/v1/ops/clinics/{clinic_id}/doctors" as const;

export type AddedDoctor = PostResponse<typeof PATH>;

/**
 * Step 2: add the clinic's doctors (`POST /ops/clinics/{id}/doctors`), one at a
 * time. Qualification, registration number and council are required because
 * every prescription prints them (I3). The step can be skipped: an owner may be
 * the doctor (spec §8), and doctors can be added later.
 */
export function DoctorsStep({
  clinicId,
  doctors,
  alreadyAdded,
  onAdded,
  onContinue,
}: {
  clinicId: string;
  doctors: readonly AddedDoctor[];
  /** Doctors the clinic already had when the wizard resumed (their names are not loaded). */
  alreadyAdded: number;
  onAdded: (doctor: AddedDoctor) => void;
  onContinue: () => void;
}) {
  const { endSession } = useSession();
  const [displayName, setDisplayName] = useState("");
  const [qualification, setQualification] = useState("");
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [council, setCouncil] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error, container);

  const problems = fieldErrors(error);
  const alertError = error !== null && Object.keys(problems).length === 0;
  const total = doctors.length + alreadyAdded;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await sessionPost(
        PATH,
        {
          display_name: displayName.trim(),
          qualification: qualification.trim(),
          registration_number: registrationNumber.trim(),
          registration_council: council.trim(),
          specialty: emptyToNull(specialty),
        },
        { pathParams: { clinic_id: clinicId } },
      );
      onAdded(data);
      setDisplayName("");
      setQualification("");
      setRegistrationNumber("");
      setCouncil("");
      setSpecialty("");
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div ref={container} className="max-w-2xl space-y-5">
      {total > 0 && (
        <section aria-labelledby="added-doctors">
          <h3 id="added-doctors" className="font-semibold">
            Doctors added ({total})
          </h3>
          <ul className="list-disc pl-6">
            {doctors.map((doctor) => (
              <li key={doctor.id}>
                {doctor.display_name}, {doctor.qualification} (registration {doctor.registration_number})
              </li>
            ))}
            {alreadyAdded > 0 && <li>{alreadyAdded} added earlier</li>}
          </ul>
        </section>
      )}

      {alertError && <ErrorNotice error={error} />}
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
        <TextField
          id="doctor-name"
          label="Doctor's name"
          required
          maxLength={200}
          value={displayName}
          error={problems["display_name"]}
          onChange={setDisplayName}
        />
        <TextField
          id="doctor-qualification"
          label="Qualification"
          required
          maxLength={200}
          hint="For example MBBS, MD."
          value={qualification}
          error={problems["qualification"]}
          onChange={setQualification}
        />
        <TextField
          id="doctor-registration"
          label="Registration number"
          required
          maxLength={50}
          hint="Printed on every prescription."
          value={registrationNumber}
          error={problems["registration_number"]}
          onChange={setRegistrationNumber}
        />
        <TextField
          id="doctor-council"
          label="Medical council"
          required
          maxLength={200}
          value={council}
          error={problems["registration_council"]}
          onChange={setCouncil}
        />
        <TextField
          id="doctor-specialty"
          label="Specialty"
          maxLength={100}
          value={specialty}
          error={problems["specialty"]}
          onChange={setSpecialty}
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded border border-blue-800 px-4 py-2 font-semibold text-blue-900 hover:bg-blue-50 disabled:cursor-not-allowed disabled:text-slate-600"
        >
          {submitting ? "Adding…" : "Add doctor"}
        </button>
      </form>

      <div className="border-t border-slate-300 pt-4">
        <button
          type="button"
          onClick={onContinue}
          className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900"
        >
          {total > 0 ? "Continue to owner invitation" : "Skip for now"}
        </button>
        {total === 0 && (
          <p className="mt-2 text-sm text-slate-700">
            Prescriptions need a registered doctor. You can add doctors later from the clinic.
          </p>
        )}
      </div>
    </div>
  );
}
