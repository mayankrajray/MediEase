"use client";

import Link from "next/link";

import type { VisitSummary } from "@/features/prescriptions/api";
import { lineSummary } from "@/features/prescriptions/vocabulary";
import { formatDateTime } from "@/lib/format/time";

import { visitPath } from "./paths";

/**
 * The patient's earlier visits (FR-VIS-03, spec §6), newest first: the complaint, the diagnosis
 * and the medicines issued. "Repeat" copies a visit's medicines into the prescription being
 * written; the doctor then edits them like any other line.
 */
export function HistoryTimeline({
  history,
  timeZone,
  onRepeat,
}: Readonly<{ history: readonly VisitSummary[]; timeZone: string; onRepeat?: ((visit: VisitSummary) => void) | undefined }>) {
  return (
    <section aria-labelledby="history-heading" className="space-y-2">
      <h2 id="history-heading" className="text-lg font-bold">
        Earlier visits
      </h2>
      {history.length === 0 && <p className="text-slate-700">This is the first visit.</p>}
      <ol className="space-y-2">
        {history.map((v) => {
          const when = formatDateTime(v.started_at, timeZone);
          return (
            <li key={v.id} className="rounded border border-slate-300 p-2">
              <Link href={visitPath(v.id)} className="font-semibold text-blue-900 underline">
                {when}
              </Link>
              {v.chief_complaint !== null && <p className="text-sm">Complaint: {v.chief_complaint}</p>}
              {v.diagnosis !== null && <p className="text-sm">Diagnosis: {v.diagnosis}</p>}
              {v.prescription !== null && v.prescription.items.length > 0 && (
                <>
                  <ul className="mt-1 list-disc pl-5 text-sm text-slate-800">
                    {v.prescription.items.map((item, i) => (
                      <li key={i}>{lineSummary(item)}</li>
                    ))}
                  </ul>
                  {onRepeat !== undefined && (
                    <button
                      type="button"
                      aria-label={`Repeat the medicines of ${when}`}
                      onClick={() => onRepeat(v)}
                      className="mt-1 rounded border border-slate-600 px-2 py-0.5 text-sm font-medium hover:bg-slate-100"
                    >
                      Repeat
                    </button>
                  )}
                </>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
