"use client";

import { TABLE, TD, TH, TR } from "@/components/ui/table";
import { useEffect, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import type { Patient } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatPhone } from "@/lib/format/phone";
import { formatDateTime } from "@/lib/format/time";

import { useReminderApi, type PatientMessage } from "./api";
import { CHANNEL_LABELS, MESSAGE_STATUS_LABELS, explainFailure, shouldCall, templateLabel } from "./labels";

/** The latest time the message reached, for the "when" column. */
function lastTime(m: PatientMessage): string {
  return m.read_at ?? m.delivered_at ?? m.failed_at ?? m.sent_at ?? m.created_at;
}

/**
 * What we have sent the patient (M5-P6 decision 1A; R16; FR-MSG-04), newest first: which
 * message, the channel, its status and when. Status only: the text and the number are never sent
 * to the browser. A message that did not arrive says why and offers a call.
 */
export function PatientMessages({ patient }: Readonly<{ patient: Patient }>) {
  const clinic = useClinic();
  const api = useReminderApi();
  const { endSession } = useSession();
  const [items, setItems] = useState<readonly PatientMessage[] | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api.messages(patient.id).then(
      (found) => {
        if (cancelled) return;
        setItems(found);
        setError(undefined);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, patient.id, reload, endSession]);

  const anyFailed = items?.some((m) => shouldCall(m.status)) ?? false;

  return (
    <section aria-labelledby="message-history-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <h2 id="message-history-heading" className="text-lg font-bold">
        Message history
      </h2>
      {error !== undefined && <ErrorNotice error={error} onRetry={() => setReload((n) => n + 1)} />}
      {items === undefined && error === undefined && <p className="text-slate-700">Loading messages…</p>}
      {items !== undefined && items.length === 0 && <p className="text-slate-700">No messages sent yet.</p>}
      {items !== undefined && items.length > 0 && (
        <table role="table" className={TABLE}>
          <caption className="sr-only">Messages sent to the patient, newest first</caption>
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader" scope="col" className={TH}>Message</th>
              <th role="columnheader" scope="col" className={TH}>Channel</th>
              <th role="columnheader" scope="col" className={TH}>Status</th>
              <th role="columnheader" scope="col" className={TH}>When</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {items.map((m) => {
              const why = explainFailure(m.status, m.error_code);
              return (
                <tr role="row" key={m.id} className={TR}>
                  <th role="rowheader" scope="row" className={`${TD} font-medium`}>
                    {templateLabel(m.template_key)}
                  </th>
                  <td role="cell" data-label="Channel" className={TD}>{CHANNEL_LABELS[m.channel]}</td>
                  <td role="cell" data-label="Status" className={TD}>
                    {MESSAGE_STATUS_LABELS[m.status]}
                    {why !== null && <span className="block text-sm text-slate-800">{why}</span>}
                  </td>
                  <td role="cell" data-label="When" className={TD}>{formatDateTime(lastTime(m), clinic.timezone)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {anyFailed && (
        <p>
          <a href={`tel:${patient.phone_e164}`} className="font-medium text-brand-800 underline">
            Call patient{" "}<span className="sr-only">on {formatPhone(patient.phone_e164)}</span>
          </a>{" "}
          if a message that did not arrive mattered.
        </p>
      )}
    </section>
  );
}
