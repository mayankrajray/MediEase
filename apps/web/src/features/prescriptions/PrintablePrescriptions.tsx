"use client";

import { useEffect, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatDateTime } from "@/lib/format/time";

import { useRxApi, type Printable } from "./api";
import { LinkPanel, PrintButton } from "./PrintAndLink";

/**
 * The patient's issued prescriptions for the counter (spec D6, M4-P4 decision 2A, M4-P6): the
 * date, the doctor and the version, with Print and the patient link. No clinical content, so
 * front desk may see it (RX_PRINT).
 */
export function PrintablePrescriptions({ patientId }: Readonly<{ patientId: string }>) {
  const api = useRxApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [items, setItems] = useState<readonly Printable[] | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [showing, setShowing] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    api.printable(patientId).then(
      (found) => {
        if (!cancelled) setItems(found);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, patientId, endSession]);

  return (
    <section aria-labelledby="printable-heading" className="space-y-2">
      <h2 id="printable-heading" className="text-lg font-bold">
        Prescriptions to print
      </h2>
      {error !== undefined && <ErrorNotice error={error} />}
      {items === undefined && error === undefined && <p className="text-slate-700">Loading prescriptions…</p>}
      {items !== undefined && items.length === 0 && <p className="text-slate-700">No prescriptions issued yet.</p>}
      {items !== undefined && items.length > 0 && (
        <ul className="space-y-3">
          {items.map((rx) => {
            const when = formatDateTime(rx.issued_at, clinic.timezone);
            const title = `${when} · ${rx.doctor_display_name}${rx.version > 1 ? ` · version ${rx.version}` : ""}`;
            return (
              <li key={rx.id} className="space-y-3 rounded border border-slate-300 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{title}</span>
                  <span className="flex flex-wrap items-start gap-2">
                    <PrintButton rxId={rx.id} name={`Print the prescription of ${when}`} />
                    <button
                      type="button"
                      aria-expanded={showing === rx.id}
                      onClick={() => setShowing(showing === rx.id ? undefined : rx.id)}
                      className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100"
                    >
                      {showing === rx.id ? "Hide link" : "Show link"}
                    </button>
                  </span>
                </div>
                {showing === rx.id && <LinkPanel rxId={rx.id} />}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
