"use client";

import { History, RotateCcw } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import type { VisitSummary } from "@/features/prescriptions/api";
import { lineSummary } from "@/features/prescriptions/vocabulary";
import { formatDateTime } from "@/lib/format/time";

import { CARD, CARD_TITLE } from "./card";
import { visitPath } from "./paths";

/**
 * The patient's earlier visits (FR-VIS-03, spec §6), newest first: the complaint, the diagnosis
 * and the medicines issued. "Repeat" copies a visit's medicines into the prescription being
 * written; the doctor then edits them like any other line. M7c-P7 (M8): a timeline, one dot per
 * visit, the medicines as a quiet list and *Repeat* as a small button.
 */
export function HistoryTimeline({
  history,
  timeZone,
  onRepeat,
}: Readonly<{ history: readonly VisitSummary[]; timeZone: string; onRepeat?: ((visit: VisitSummary) => void) | undefined }>) {
  return (
    <section aria-labelledby="history-heading" className={CARD}>
      <h2 id="history-heading" className={CARD_TITLE}>
        <History aria-hidden="true" className="size-5 text-brand-700" />
        Earlier visits
      </h2>
      {history.length === 0 && <p className="text-slate-700">This is the first visit.</p>}
      {history.length > 0 && (
        <ol className="relative space-y-4 border-l-2 border-line pl-4">
          {history.map((v) => {
            const when = formatDateTime(v.started_at, timeZone);
            return (
              <li key={v.id} className="relative space-y-1">
                <span aria-hidden="true" className="absolute -left-[1.4rem] top-1.5 size-3 rounded-full border-2 border-white bg-brand-600 ring-1 ring-brand-200" />
                <Link href={visitPath(v.id)} className="font-semibold text-brand-800 underline-offset-4 hover:underline">
                  {when}
                </Link>
                {v.chief_complaint !== null && <p className="text-sm text-slate-800 [overflow-wrap:anywhere]">Complaint: {v.chief_complaint}</p>}
                {v.diagnosis !== null && <p className="text-sm text-slate-800 [overflow-wrap:anywhere]">Diagnosis: {v.diagnosis}</p>}
                {v.prescription !== null && v.prescription.items.length > 0 && (
                  <>
                    <ul className="space-y-0.5 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
                      {v.prescription.items.map((item, i) => (
                        <li key={i} className="[overflow-wrap:anywhere]">
                          {lineSummary(item)}
                        </li>
                      ))}
                    </ul>
                    {onRepeat !== undefined && (
                      <Button size="sm" aria-label={`Repeat the medicines of ${when}`} onClick={() => onRepeat(v)} icon={<RotateCcw className="size-3.5" />}>
                        Repeat
                      </Button>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
