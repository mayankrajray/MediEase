"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { patientPath } from "@/features/patients/RegisterPatientDrawer";
import { formatPaise } from "@/lib/format/money";

import { useBillsApi, type DuesList } from "./api";

/**
 * *Dues* (M6d-P3; FR-BIL-05; billing R39): every patient who owes on an issued bill, the largest
 * first, for owners and the front desk (COLLECTION_VIEW).
 */
export function DuesPage() {
  const api = useBillsApi();
  const { endSession } = useSession();
  const [dues, setDues] = useState<DuesList | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    api.dues().then(
      (list) => {
        if (!cancelled) setDues(list);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  return (
    <section className="space-y-4">
      <PageHeader title="Dues" description={dues === undefined ? undefined : `In all: ${formatPaise(dues.total_paise)}`} />
      {error !== null && <ErrorNotice error={error} />}
      {dues === undefined && error === null && <p role="status">Loading dues…</p>}
      {dues !== undefined && dues.items.length === 0 && <p>Nobody owes the clinic anything.</p>}
      {dues !== undefined && dues.items.length > 0 && (
        <div className={TABLE_WRAP}>
          <table className={TABLE} role="table">
            <caption className="sr-only">Patients who owe the clinic</caption>
            <thead role="rowgroup">
              <tr role="row">
                {["Patient", "Bills", "Owes", "Oldest bill"].map((h) => (
                  <th key={h} role="columnheader" scope="col" className={TH}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody role="rowgroup">
              {dues.items.map((d) => (
                <tr key={d.patient?.id ?? d.oldest_bill_date} role="row" className={TR}>
                  <td role="cell" data-label="Patient" className={TD}>
                    {d.patient === null ? (
                      "–"
                    ) : (
                      <Link href={patientPath(d.patient.id)} className="font-semibold text-brand-800 underline">
                        {d.patient.full_name} · {d.patient.code}
                      </Link>
                    )}
                  </td>
                  <td role="cell" data-label="Bills" className={TD}>
                    {d.bills}
                  </td>
                  <td role="cell" data-label="Owes" className={`${TD} font-medium tabular-nums`}>
                    {formatPaise(d.due_paise)}
                  </td>
                  <td role="cell" data-label="Oldest bill" className={TD}>
                    {d.oldest_bill_date}
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
