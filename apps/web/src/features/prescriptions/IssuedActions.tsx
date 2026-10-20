"use client";

import { useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { FollowUpReminder } from "@/features/reminders/FollowUpReminder";
import { useClinic } from "@/features/shell/ClinicGate";
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
    <section aria-labelledby="rx-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="rx-heading" className="text-lg font-bold">
          Prescription issued{rx.version > 1 ? ` · version ${rx.version}` : ""}
        </h2>
        <div className="flex flex-wrap items-start gap-2">
          <PrintButton rxId={rx.id} label="Print" name="Print the prescription" />
          {canRevise && (
            <button
              type="button"
              disabled={busy}
              onClick={revise}
              className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100 disabled:text-slate-500"
            >
              Revise
            </button>
          )}
        </div>
      </div>
      {rx.issued_at !== null && <p className="text-slate-800">Issued {formatDateTime(rx.issued_at, clinic.timezone)}. It cannot be changed; Revise makes a new version.</p>}
      {error !== undefined && <ErrorNotice error={error} />}
      <ol aria-label="Medicines issued" className="list-decimal space-y-1 pl-6">
        {rx.items.map((item) => (
          <li key={item.id}>{lineSummary(item)}</li>
        ))}
      </ol>
      {(advice.diet.length > 0 || advice.activity.length > 0 || advice.return_if.length > 0 || advice.notes !== null) && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
          {advice.diet.length > 0 && (
            <>
              <dt className="font-medium">Diet</dt>
              <dd>{advice.diet.join("; ")}</dd>
            </>
          )}
          {advice.activity.length > 0 && (
            <>
              <dt className="font-medium">Activity</dt>
              <dd>{advice.activity.join("; ")}</dd>
            </>
          )}
          {advice.return_if.length > 0 && (
            <>
              <dt className="font-medium">Come back immediately if</dt>
              <dd>{advice.return_if.join("; ")}</dd>
            </>
          )}
          {advice.notes !== null && (
            <>
              <dt className="font-medium">Other advice</dt>
              <dd className="whitespace-pre-line">{advice.notes}</dd>
            </>
          )}
        </dl>
      )}
      {rx.follow_up_date !== null && (
        <div className="flex flex-wrap items-start gap-3">
          <p>Follow-up: {formatDay(rx.follow_up_date)}</p>
          {chainId !== undefined && <FollowUpReminder patientId={rx.patient_id} chainId={chainId} />}
        </div>
      )}
      <h3 className="font-bold">Patient link</h3>
      <LinkPanel rxId={rx.id} />
    </section>
  );
}
