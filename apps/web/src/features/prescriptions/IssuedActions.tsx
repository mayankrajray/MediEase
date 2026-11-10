"use client";

import { useState } from "react";

import { CalendarClock, CircleCheck, PenLine, QrCode } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { FollowUpReminder } from "@/features/reminders/FollowUpReminder";
import { useClinic } from "@/features/shell/ClinicGate";
import { CARD, CARD_TITLE } from "@/features/visits/card";
import { ApiError } from "@/lib/api/client";
import { formatDateTime, formatDay } from "@/lib/format/time";

import { useRxApi, type Prescription } from "./api";
import { LinkPanel, PrintButton } from "./PrintAndLink";
import { lineSummary } from "./vocabulary";

/**
 * An issued prescription on the consultation screen (journey step 4): what was issued, read only
 * (FR-RX-09), with Print, the patient link as a QR code, and Revise, which starts a new version
 * that supersedes this one when it is issued. M5-P6: beside the follow-up date, the chain's
 * reminder (`chainId` is version 1's ID, which the reminder names).
 */
export function IssuedActions({
  rx,
  canRevise,
  onRevised,
  chainId,
}: Readonly<{ rx: Prescription; canRevise: boolean; onRevised: () => void; chainId?: string }>) {
  const api = useRxApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [error, setError] = useState<unknown>(undefined);
  const [busy, setBusy] = useState(false);

  function revise() {
    setBusy(true);
    setError(undefined);
    api.revise(rx.id).then(onRevised, (failure: unknown) => {
      setBusy(false);
      // A revision another tab started is the one to continue.
      if (failure instanceof ApiError && failure.code === "RX_DRAFT_EXISTS") onRevised();
      else if (!endSession(failure)) setError(failure);
    });
  }

  const advice = rx.advice;
  return (
    <section aria-labelledby="rx-heading" className={`${CARD} border-success-line`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="rx-heading" className={CARD_TITLE}>
          <CircleCheck aria-hidden="true" className="size-5 text-success" />
          Prescription issued{rx.version > 1 ? ` · version ${rx.version}` : ""}
        </h2>
        <div className="flex flex-wrap items-start gap-2">
          <PrintButton rxId={rx.id} label="Print" name="Print the prescription" />
          {canRevise && (
            <Button size="sm" loading={busy} onClick={revise} icon={<PenLine className="size-3.5" />} className="min-h-8">
              Revise
            </Button>
          )}
        </div>
      </div>
      {rx.issued_at !== null && <p className="text-sm text-slate-700">Issued {formatDateTime(rx.issued_at, clinic.timezone)}. It cannot be changed; Revise makes a new version.</p>}
      {error !== undefined && <ErrorNotice error={error} />}
      <ol aria-label="Medicines issued" className="divide-y divide-line rounded-lg border border-line">
        {rx.items.map((item, i) => (
          <li key={item.id} className="flex gap-2.5 px-3 py-2.5">
            <span aria-hidden="true" className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand-800">
              {i + 1}
            </span>
            <span className="min-w-0 [overflow-wrap:anywhere]">{lineSummary(item)}</span>
          </li>
        ))}
      </ol>
      {(advice.diet.length > 0 || advice.activity.length > 0 || advice.return_if.length > 0 || advice.notes !== null) && (
        <dl className="grid gap-x-6 gap-y-1 rounded-lg bg-slate-50 p-3 sm:grid-cols-[max-content_1fr]">
          {advice.diet.length > 0 && (
            <>
              <dt className="text-sm font-semibold text-slate-700">Diet</dt>
              <dd>{advice.diet.join("; ")}</dd>
            </>
          )}
          {advice.activity.length > 0 && (
            <>
              <dt className="text-sm font-semibold text-slate-700">Activity</dt>
              <dd>{advice.activity.join("; ")}</dd>
            </>
          )}
          {advice.return_if.length > 0 && (
            <>
              <dt className="text-sm font-semibold text-slate-700">Come back immediately if</dt>
              <dd>{advice.return_if.join("; ")}</dd>
            </>
          )}
          {advice.notes !== null && (
            <>
              <dt className="text-sm font-semibold text-slate-700">Other advice</dt>
              <dd className="whitespace-pre-line">{advice.notes}</dd>
            </>
          )}
        </dl>
      )}
      {rx.follow_up_date !== null && (
        <div className="flex flex-wrap items-start gap-3">
          <p className="inline-flex min-h-8 items-center gap-1.5 rounded-full bg-brand-50 px-3 text-sm font-semibold text-brand-900">
            <CalendarClock aria-hidden="true" className="size-4" />
            Follow-up: {formatDay(rx.follow_up_date)}
          </p>
          {chainId !== undefined && <FollowUpReminder patientId={rx.patient_id} chainId={chainId} />}
        </div>
      )}
      <h3 className="flex items-center gap-2 border-t border-line pt-4 font-bold text-slate-900">
        <QrCode aria-hidden="true" className="size-4 text-brand-700" />
        Patient link
      </h3>
      <LinkPanel rxId={rx.id} />
    </section>
  );
}
