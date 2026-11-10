"use client";

import { TriangleAlert, UserPlus } from "lucide-react";

import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";

import { ageText, type PatientCandidate } from "./fields";

/**
 * The patients already on this phone (409 PAT_PHONE_EXISTS, spec R2): families share
 * phones, so the front desk either picks the person or registers another one on the
 * same number (`confirm_new`, D3). Names and ages are shown to the signed-in staff
 * member only; the list is never stored.
 *
 * M7c-P7 (M5): the warning tone with an icon, each person a row with initials and a full-width
 * *Use this patient* on a phone; registering another person stays the primary action below.
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
      <div role="alert" tabIndex={-1} className="flex gap-3 rounded-xl border border-warning-line bg-warning-soft p-4 text-slate-900">
        <TriangleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-warning" />
        <div>
          <h3 id="duplicates-heading" className="font-semibold">
            This phone number is already registered
          </h3>
          <p className="mt-1 text-slate-800">Is the patient one of these? Families often share one phone.</p>
        </div>
      </div>
      <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface">
        {candidates.map((candidate) => (
          <li key={candidate.id} className="flex flex-wrap items-center gap-3 p-3">
            <Avatar name={candidate.full_name} />
            <span className="min-w-0 flex-1">
              <span className="block break-words font-semibold text-slate-900">{candidate.full_name}</span>
              <span className="block text-sm tabular-nums text-slate-700">
                {candidate.code} · {ageText({ age_years: candidate.age_years, age_is_estimated: false })}
              </span>
            </span>
            <Button
              size="sm"
              onClick={() => onUse(candidate)}
              aria-label={`Use this patient: ${candidate.full_name}, ${candidate.code}`}
              className="max-sm:min-h-11 max-sm:w-full"
            >
              Use this patient
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" loading={submitting} onClick={onRegisterNew} icon={<UserPlus className="size-4" />} className="max-sm:w-full">
          {submitting ? "Registering…" : "Register as a new family member"}
        </Button>
        <Button onClick={onBack} className="max-sm:w-full">
          Back to the form
        </Button>
      </div>
    </section>
  );
}
