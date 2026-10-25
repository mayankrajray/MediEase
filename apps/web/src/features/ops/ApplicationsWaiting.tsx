"use client";

import { useEffect, useState } from "react";

import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import type { GetResponse } from "@/lib/api/client";
import { sessionGet } from "@/lib/auth/refresh";
import { formatDateTime } from "@/lib/format/time";

type Applications = GetResponse<"/api/v1/ops/applications">["items"];

const KIND_LABEL: Record<Applications[number]["kind"], string> = {
  CLINIC: "Clinic",
  SOLO_DOCTOR: "Own practice",
};

/**
 * Confirmed clinic applications waiting for MediEase (M6c-P1; spec clinic-onboarding R18): the
 * count and a summary list, oldest first. Read-only until the reviewer's workflow (M6c-P2); no
 * phone, email, registration number or certificate is shown or fetched.
 */
export function ApplicationsWaiting() {
  const { endSession } = useSession();
  const [items, setItems] = useState<Applications | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    sessionGet("/api/v1/ops/applications").then(
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
  }, [endSession]);

  if (error !== null) return <ErrorNotice error={error} />;
  if (items === undefined) return null;
  return (
    <section aria-labelledby="applications-heading" className="space-y-3">
      <h2 id="applications-heading" className="text-lg font-semibold">
        {items.length === 0 ? "No applications waiting" : items.length === 1 ? "1 application waiting" : `${items.length} applications waiting`}
      </h2>
      {items.length > 0 && (
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
                  Kind
                </th>
                <th role="columnheader" scope="col" className={TH}>
                  Doctors
                </th>
                <th role="columnheader" scope="col" className={TH}>
                  Confirmed (IST)
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {items.map((a) => (
                <tr key={a.id} role="row" className={TR}>
                  <td role="cell" className={`${TD} font-mono`} data-label="Reference">
                    {a.reference}
                    {a.possible_duplicate && <span className="ml-2 font-sans text-sm font-medium text-amber-900">Possible duplicate</span>}
                  </td>
                  <td role="cell" className={TD} data-label="Clinic">
                    {a.clinic_name}, {a.city}
                  </td>
                  <td role="cell" className={TD} data-label="Kind">
                    {KIND_LABEL[a.kind]}
                  </td>
                  <td role="cell" className={TD} data-label="Doctors">
                    {a.doctors}
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
