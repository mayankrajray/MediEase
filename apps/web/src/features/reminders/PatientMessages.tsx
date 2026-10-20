"use client";

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
    <section aria-labelledby="message-history-heading" className="space-y-2">
      <h2 id="message-history-heading" className="text-lg font-bold">
        Message history
      </h2>
      {error !== undefined && <ErrorNotice error={error} onRetry={() => setReload((n) => n + 1)} />}
      {items === undefined && error === undefined && <p className="text-slate-700">Loading messages…</p>}
      {items !== undefined && items.length === 0 && <p className="text-slate-700">No messages sent yet.</p>}
      {items !== undefined && items.length > 0 && (
        <table className="w-full text-left">
          <caption className="sr-only">Messages sent to the patient, newest first</caption>
          <thead className="text-sm text-slate-700">
            <tr>
              <th scope="col">Message</th>
              <th scope="col">Channel</th>
              <th scope="col">Status</th>
              <th scope="col">When</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => {
              const why = explainFailure(m.status, m.error_code);
              return (
                <tr key={m.id} className="border-t border-slate-200 align-top">
                  <th scope="row" className="py-2 pr-3 font-medium">
                    {templateLabel(m.template_key)}
                  </th>
                  <td className="pr-3">{CHANNEL_LABELS[m.channel]}</td>
                  <td className="pr-3">
                    {MESSAGE_STATUS_LABELS[m.status]}
                    {why !== null && <span className="block text-sm text-slate-800">{why}</span>}
                  </td>
                  <td>{formatDateTime(lastTime(m), clinic.timezone)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {anyFailed && (
        <p>
          <a href={`tel:${patient.phone_e164}`} className="font-medium text-blue-900 underline">
            Call patient{" "}<span className="sr-only">on {formatPhone(patient.phone_e164)}</span>
          </a>{" "}
          if a message that did not arrive mattered.
        </p>
      )}
    </section>
  );
}
