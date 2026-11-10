"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RowsSkeleton } from "@/components/ui/Skeleton";
import { buttonClasses } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useRxApi, type VisitSummary } from "@/features/prescriptions/api";
import { lineSummary } from "@/features/prescriptions/vocabulary";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatDateTime } from "@/lib/format/time";

import { visitPath } from "./paths";

/**
 * A patient's visits on their profile (FR-VIS-03, M4-P6), newest first, ten at a time, each
 * opening its consultation. Only for people who may see clinical content (CLINICAL_VIEW); each
 * page is one audited read on the API (R16).
 */
export function PatientVisits({ patientId }: Readonly<{ patientId: string }>) {
  const api = useRxApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [items, setItems] = useState<readonly VisitSummary[] | undefined>(undefined);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(undefined);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.patientVisits(patientId).then(
      (page) => {
        if (cancelled) return;
        setItems(page.items);
        setNext(page.next_before);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, patientId, endSession]);

  function more(before: string) {
    setLoading(true);
    api.patientVisits(patientId, before).then(
      (page) => {
        setItems((shown) => [...(shown ?? []), ...page.items]);
        setNext(page.next_before);
        setLoading(false);
      },
      (failure: unknown) => {
        setLoading(false);
        if (!endSession(failure)) setError(failure);
      },
    );
  }

  return (
    <section aria-labelledby="visits-heading" className="space-y-3 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
      <h2 id="visits-heading" className="heading-6 text-slate-900">
        Visits
      </h2>
      {error !== undefined && <ErrorNotice error={error} />}
      {items === undefined && error === undefined && <RowsSkeleton label="Loading visits…" />}
      {items !== undefined && items.length === 0 && <p className="rounded-lg border border-dashed border-slate-300 px-3 py-5 text-center text-sm text-slate-700">No visits yet.</p>}
      {items !== undefined && items.length > 0 && (
        <ol className="space-y-3">
          {items.map((v) => (
            <li key={v.id} className="rounded-card border border-line bg-white p-3">
              <p className="flex flex-wrap items-baseline justify-between gap-2">
                <Link href={visitPath(v.id)} className="font-semibold text-brand-800 underline underline-offset-2 hover:text-brand-900">
                  {formatDateTime(v.started_at, clinic.timezone)}
                </Link>
                <span className="text-sm text-slate-800">{v.status === "OPEN" ? "In progress" : "Completed"}</span>
              </p>
              {v.chief_complaint !== null && <p>Complaint: {v.chief_complaint}</p>}
              {v.diagnosis !== null && <p>Diagnosis: {v.diagnosis}</p>}
              {v.prescription !== null && (
                <ul className="mt-1 list-disc pl-5 text-slate-800">
                  {v.prescription.items.map((item, i) => (
                    <li key={i}>{lineSummary(item)}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
      {next !== null && (
        <button
          type="button"
          disabled={loading}
          onClick={() => more(next)}
          className={buttonClasses("secondary", "sm")}
        >
          {loading ? "Loading…" : "Show earlier visits"}
        </button>
      )}
    </section>
  );
}
