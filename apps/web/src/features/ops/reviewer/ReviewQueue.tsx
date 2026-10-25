"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { sessionGet } from "@/lib/auth/refresh";
import { formatDateTime } from "@/lib/format/time";

import { STATUS_LABELS, type ApplicationSummary, type Queue } from "./api";

const QUEUES: readonly { readonly key: Queue; readonly label: string }[] = [
  { key: "waiting", label: "Waiting" },
  { key: "review", label: "Under review" },
  { key: "decided", label: "Decided" },
];

/**
 * The reviewer's queue (M6c-P2; spec clinic-onboarding R25): confirmed applications by state,
 * oldest first, with the duplicate flag. Times in IST, the reviewers' clock.
 */
export function ReviewQueue() {
  const { endSession } = useSession();
  const [queue, setQueue] = useState<Queue>("waiting");
  const [items, setItems] = useState<readonly ApplicationSummary[] | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    sessionGet("/api/v1/ops/applications", { query: { queue } }).then(
      ({ data }) => {
        if (!cancelled) setItems(data.items);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [queue, endSession]);

  return (
    <section aria-labelledby="queue-heading" className="space-y-4">
      <h1 id="queue-heading" className="text-2xl font-bold tracking-tight">
        Clinic applications
      </h1>
      <div role="group" aria-label="Show" className="flex flex-wrap gap-2">
        {QUEUES.map((q) => (
          <button
            key={q.key}
            type="button"
            aria-pressed={queue === q.key}
            onClick={() => {
              if (q.key === queue) return;
              setItems(undefined);
              setError(null);
              setQueue(q.key);
            }}
            className={`min-h-10 rounded-lg border px-3 font-medium ${queue === q.key ? "border-brand-700 bg-brand-50 text-brand-900" : "border-slate-400 bg-white"}`}
          >
            {q.label}
          </button>
        ))}
      </div>
      {error !== null && <ErrorNotice error={error} />}
      {items === undefined && error === null && <p role="status">Loading applications…</p>}
      {items !== undefined && items.length === 0 && <p>No applications here.</p>}
      {items !== undefined && items.length > 0 && (
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>
                  Reference
                </th>
                <th role="columnheader" scope="col" className={TH}>
                  Clinic
                </th>
                <th role="columnheader" scope="col" className={TH}>
                  Doctors
                </th>
                <th role="columnheader" scope="col" className={TH}>
                  Status
                </th>
                <th role="columnheader" scope="col" className={TH}>
                  Confirmed (IST)
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {items.map((a) => (
                <tr key={a.id} role="row" className={TR}>
                  <td role="cell" className={TD} data-label="Reference">
                    <Link href={`/ops/applications/${a.id}`} className="font-mono font-semibold text-brand-800 underline">
                      {a.reference}
                    </Link>
                    {a.possible_duplicate && <span className="ml-2 text-sm font-medium text-amber-900">Possible duplicate</span>}
                  </td>
                  <td role="cell" className={TD} data-label="Clinic">
                    {a.clinic_name}, {a.city}
                  </td>
                  <td role="cell" className={TD} data-label="Doctors">
                    {a.doctors}
                  </td>
                  <td role="cell" className={TD} data-label="Status">
                    {STATUS_LABELS[a.status]}
                  </td>
                  <td role="cell" className={TD} data-label="Confirmed (IST)">
                    {formatDateTime(a.email_verified_at, "Asia/Kolkata")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
