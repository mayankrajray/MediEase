"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { formatPaise } from "@/lib/format/money";

import { billPath, useBillsApi, type BillSummary } from "./api";
import { BillTable } from "./BillsList";

/** M6d-P2 (R22): a patient's bills on their profile, and *New bill* for them. */
export function PatientBills({ patientId }: Readonly<{ patientId: string }>) {
  const api = useBillsApi();
  const router = useRouter();
  const { endSession } = useSession();
  const [items, setItems] = useState<readonly BillSummary[] | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const { clinic } = useSession();
  const canSeeDues = clinic.kind === "active" && clinic.membership.permissions.includes("COLLECTION_VIEW");
  const [due, setDue] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (!canSeeDues) return;
    let cancelled = false;
    api.dues(patientId).then(
      (list) => {
        if (!cancelled) setDue(list.total_paise);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [api, patientId, canSeeDues]);

  useEffect(() => {
    let cancelled = false;
    api.list({ patientId }).then(
      (page) => {
        if (!cancelled) setItems(page.items);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, patientId, endSession]);

  async function start() {
    setError(null);
    try {
      router.push(billPath((await api.draft(patientId)).id));
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    }
  }

  return (
    <section aria-labelledby="patient-bills-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <h2 id="patient-bills-heading" className="text-lg font-bold">
          Bills
        </h2>
        <Button size="sm" onClick={() => void start()}>
          New bill
        </Button>
      </div>
      {due !== undefined && due > 0 && <p className="font-semibold text-amber-900">Dues: {formatPaise(due)}</p>}
      {error !== null && <ErrorNotice error={error} />}
      {items === undefined && error === null && <p role="status">Loading bills…</p>}
      {items !== undefined && items.length === 0 && <p>No bills yet.</p>}
      {items !== undefined && items.length > 0 && <BillTable items={items} caption="This patient's bills" />}
    </section>
  );
}
