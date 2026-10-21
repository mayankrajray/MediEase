"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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
    <section aria-labelledby="visits-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <h2 id="visits-heading" className="text-lg font-bold">
        Visits
      </h2>
      {error !== undefined && <ErrorNotice error={error} />}
      {items === undefined && error === undefined && <p className="text-slate-700">Loading visits…</p>}
      {items !== undefined && items.length === 0 && <p className="text-slate-700">No visits yet.</p>}
      {items !== undefined && items.length > 0 && (
        <ol className="space-y-3">
          {items.map((v) => (
            <li key={v.id} className="rounded-card border border-slate-200 bg-white p-3">
              <p className="flex flex-wrap items-baseline justify-between gap-2">
                <Link href={visitPath(v.id)} className="font-semibold text-brand-800 underline">
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
          className="inline-flex min-h-8 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-3 py-1 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none"
        >
          {loading ? "Loading…" : "Show earlier visits"}
        </button>
      )}
    </section>
  );
}
