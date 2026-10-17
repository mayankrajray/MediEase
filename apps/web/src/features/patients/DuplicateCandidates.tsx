"use client";

import { ageText, type PatientCandidate } from "./fields";

/**
 * The patients already on this phone (409 PAT_PHONE_EXISTS, spec R2): families share
 * phones, so the front desk either picks the person or registers another one on the
 * same number (`confirm_new`, D3). Names and ages are shown to the signed-in staff
 * member only; the list is never stored.
 */
export function DuplicateCandidates({
  candidates,
  onUse,
  onRegisterNew,
  onBack,
  submitting,
}: {
  candidates: readonly PatientCandidate[];
  onUse: (candidate: PatientCandidate) => void;
  onRegisterNew: () => void;
  onBack: () => void;
  submitting: boolean;
}) {
  return (
    <section aria-labelledby="duplicates-heading" className="space-y-4">
      <div role="alert" tabIndex={-1} className="rounded border border-amber-700 bg-amber-50 p-4 text-amber-950">
        <h3 id="duplicates-heading" className="font-semibold">
          This phone number is already registered
        </h3>
        <p className="mt-1">Is the patient one of these? Families often share one phone.</p>
      </div>
      <ul className="divide-y divide-slate-200 rounded border border-slate-300">
        {candidates.map((candidate) => (
          <li key={candidate.id} className="flex items-center justify-between gap-4 p-3">
            <span>
              <span className="font-semibold">{candidate.full_name}</span>{" "}
              <span className="text-slate-700">
                · {candidate.code} · {ageText({ age_years: candidate.age_years, age_is_estimated: false })}
              </span>
            </span>
            <button
              type="button"
              onClick={() => onUse(candidate)}
              aria-label={`Use this patient: ${candidate.full_name}, ${candidate.code}`}
              className="rounded border border-blue-800 px-3 py-1.5 font-medium text-blue-900 hover:bg-blue-50"
            >
              Use this patient
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onRegisterNew}
          disabled={submitting}
          className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900 disabled:cursor-not-allowed disabled:bg-slate-500"
        >
          {submitting ? "Registering…" : "Register as a new family member"}
        </button>
        <button type="button" onClick={onBack} className="rounded border border-slate-500 px-4 py-2 hover:bg-slate-100">
          Back to the form
        </button>
      </div>
    </section>
  );
}
