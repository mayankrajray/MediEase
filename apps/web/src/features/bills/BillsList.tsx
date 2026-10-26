"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { INPUT, LABEL } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { PatientPicker } from "@/features/appointments/PatientPicker";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { formatPaise } from "@/lib/format/money";

import { BILL_STATUS_LABELS, BILL_STATUS_TONES, billPath, useBillsApi, type BillStatus, type BillSummary } from "./api";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly BillSummary[]; readonly next: string | null }
  | { readonly status: "failed"; readonly error: unknown };

/** "No balance", "₹300.00 due" or "₹50.00 to refund": what the desk needs at a glance. */
export function balanceText(bill: Pick<BillSummary, "balance_paise">): string {
  const b = bill.balance_paise;
  if (b === null) return "–";
  if (b === 0) return "Settled";
  return b > 0 ? `${formatPaise(b)} due` : `${formatPaise(-b)} to refund`;
}

/**
 * *Bills* (M6d-P2; FR-BIL-02; spec billing R22): the clinic's bills, newest first, 50 at a time,
 * by state; a doctor sees only their own (the API decides). *New bill* picks a patient and opens
 * the draft.
 */
export function BillsList() {
  const api = useBillsApi();
  const router = useRouter();
  const { endSession } = useSession();
  const [status, setStatus] = useState<BillStatus | "">("");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [more, setMore] = useState(false);
  const [picking, setPicking] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const statusId = useId();

  useEffect(() => {
    let cancelled = false;
    api.list(status === "" ? {} : { status }).then(
      (page) => {
        if (!cancelled) setLoad({ status: "ready", items: page.items, next: page.next_cursor });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, status, endSession]);

  async function loadMore(cursor: string, items: readonly BillSummary[]) {
    setMore(true);
    try {
      const page = await api.list({ ...(status === "" ? {} : { status }), cursor });
      setLoad({ status: "ready", items: [...items, ...page.items], next: page.next_cursor });
    } catch (failure) {
      if (!endSession(failure)) setActionError(failure);
    } finally {
      setMore(false);
    }
  }

  async function start(patientId: string) {
    setActionError(null);
    try {
      const bill = await api.draft(patientId);
      router.push(billPath(bill.id));
    } catch (failure) {
      if (!endSession(failure)) setActionError(failure);
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader
        title="Bills"
        description="Draft, issue and correct bills. An issued bill never changes: correct it with a credit note."
        actions={
          <Button variant="primary" onClick={() => setPicking((p) => !p)} aria-expanded={picking}>
            New bill
          </Button>
        }
      />
      {picking && (
        <div className="space-y-2 rounded-card border border-slate-200 bg-white p-4">
          <p className="font-medium">Who is the bill for?</p>
          <PatientPicker onPick={(patient) => void start(patient.id)} />
        </div>
      )}
      {actionError !== null && <ErrorNotice error={actionError} />}
      <div className="max-w-xs space-y-1">
        <label htmlFor={statusId} className={LABEL}>
          Show
        </label>
        <select id={statusId} value={status} onChange={(e) => setStatus(e.target.value as BillStatus | "")} className={INPUT}>
          <option value="">All bills</option>
          {(Object.keys(BILL_STATUS_LABELS) as BillStatus[]).map((s) => (
            <option key={s} value={s}>
              {BILL_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
      {load.status === "loading" && <p role="status">Loading bills…</p>}
      {load.status === "failed" && <ErrorNotice error={load.error} />}
      {load.status === "ready" && load.items.length === 0 && <p>No bills yet.</p>}
      {load.status === "ready" && load.items.length > 0 && <BillTable items={load.items} />}
      {load.status === "ready" && load.next !== null && (
        <Button disabled={more} onClick={() => void loadMore(load.next as string, load.items)}>
          Show more
        </Button>
      )}
    </section>
  );
}

export function BillTable({ items, caption = "Bills" }: Readonly<{ items: readonly BillSummary[]; caption?: string }>) {
  return (
    <div className={TABLE_WRAP}>
      <table className={TABLE} role="table">
        <caption className="sr-only">{caption}</caption>
        <thead role="rowgroup">
          <tr role="row">
            {["Bill", "Date", "Patient", "Doctor", "Total", "Balance", "State"].map((h) => (
              <th key={h} role="columnheader" scope="col" className={TH}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup">
          {items.map((b) => (
            <tr key={b.id} role="row" className={TR}>
              <td role="cell" data-label="Bill" className={TD}>
                <Link href={billPath(b.id)} className="font-semibold text-brand-800 underline">
                  {b.number ?? "Draft"}
                </Link>
              </td>
              <td role="cell" data-label="Date" className={TD}>
                {b.bill_date ?? "–"}
              </td>
              <td role="cell" data-label="Patient" className={TD}>
                {b.patient === null ? "–" : `${b.patient.full_name} · ${b.patient.code}`}
              </td>
              <td role="cell" data-label="Doctor" className={TD}>
                {b.doctor?.display_name ?? "–"}
              </td>
              <td role="cell" data-label="Total" className={`${TD} tabular-nums`}>
                {formatPaise(b.total_paise)}
              </td>
              <td role="cell" data-label="Balance" className={`${TD} tabular-nums`}>
                {balanceText(b)}
              </td>
              <td role="cell" data-label="State" className={TD}>
                <StatusBadge tone={BILL_STATUS_TONES[b.status]}>{BILL_STATUS_LABELS[b.status]}</StatusBadge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
