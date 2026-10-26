"use client";

import { useState, type FormEvent } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/Field";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { clinicToday } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatPaise, parseRupees, rupeesInput } from "@/lib/format/money";
import { formatDateTime } from "@/lib/format/time";

import { MODE_LABELS, useBillsApi, type Bill, type Payment, type PaymentMode } from "./api";

const MODES = (Object.keys(MODE_LABELS) as PaymentMode[]).map((value) => ({ value, label: MODE_LABELS[value] }));

/**
 * Payments on an issued bill (M6d-P3; FR-BIL-03; billing R31-R36). The amount starts at the
 * balance; a refund is offered only when the bill is overpaid after a credit note. A payment is
 * voided only on the day it was taken (the API decides; the button shows only then).
 */
export function PaymentsPanel({ bill, onChange }: Readonly<{ bill: Bill; onChange: (bill: Bill) => void }>) {
  const api = useBillsApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const balance = bill.balance_paise ?? 0;
  const refund = balance < 0;
  const [mode, setMode] = useState<PaymentMode>("CASH");
  const [amount, setAmount] = useState(rupeesInput(Math.abs(balance)));
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState("");
  const [voiding, setVoiding] = useState<Payment | null>(null);
  const [reason, setReason] = useState("");
  const parsed = parseRupees(amount);
  const amountError = !parsed.ok || parsed.paise === null || parsed.paise === 0 ? "Enter the amount in rupees." : undefined;
  const today = clinicToday(clinic.timezone);
  const open = balance !== 0 && (bill.status === "ISSUED" || refund);

  async function run(work: () => Promise<Bill>, done: (next: Bill) => string) {
    setBusy(true);
    setError(null);
    try {
      const next = await work();
      onChange(next);
      setStatus(done(next));
      setAmount(rupeesInput(Math.abs(next.balance_paise ?? 0)));
      setReference("");
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (amountError !== undefined || !parsed.ok || parsed.paise === null) return;
    const paise = parsed.paise;
    void run(
      () => api.pay(bill.id, { kind: refund ? "REFUND" : "PAYMENT", mode, amount_paise: paise, reference: reference.trim() === "" ? null : reference.trim() }),
      (next) => `${refund ? "Refund" : "Payment"} of ${formatPaise(paise)} recorded. ${next.balance_paise === 0 ? "The bill is settled." : ""}`.trim(),
    );
  }

  return (
    <section aria-labelledby="payments-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4">
      <h2 id="payments-heading" className="text-lg font-semibold">
        Payments
      </h2>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {status}
      </p>
      {error !== null && <ErrorNotice error={error} />}
      {bill.payments.length === 0 ? (
        <p>No payments yet.</p>
      ) : (
        <ul className="space-y-2">
          {bill.payments.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-2">
              <span className={p.voided_at !== null ? "line-through" : "font-medium"}>
                {p.kind === "REFUND" ? "Refund" : "Payment"} · {MODE_LABELS[p.mode]} · {formatPaise(p.amount_paise)}
              </span>
              <span className="text-sm text-slate-700">
                {formatDateTime(p.received_at, clinic.timezone)}
                {p.received_by !== null && ` · ${p.received_by}`}
                {p.reference !== null && ` · ${p.reference}`}
              </span>
              {p.voided_at !== null && <StatusBadge tone="missed">Voided: {p.void_reason}</StatusBadge>}
              {p.voided_at === null && p.local_date === today && (
                <Button size="sm" disabled={busy} onClick={() => setVoiding(p)}>
                  Void <span className="sr-only">{`the ${formatPaise(p.amount_paise)} ${p.kind === "REFUND" ? "refund" : "payment"}`}</span>
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {open && (
        <form onSubmit={submit} className="space-y-2 border-t border-slate-200 pt-3" noValidate>
          <p className="font-medium">{refund ? `Refund ${formatPaise(-balance)} to the patient` : `Take a payment (${formatPaise(balance)} due)`}</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <SelectField id={`mode-${bill.id}`} label="Mode" value={mode} onChange={(v) => setMode(v as PaymentMode)} options={MODES} />
            <TextField id={`amount-${bill.id}`} label="Amount in rupees" inputMode="numeric" value={amount} onChange={setAmount} error={amountError} required />
            {mode !== "CASH" && <TextField id={`reference-${bill.id}`} label="Reference (optional)" value={reference} onChange={setReference} maxLength={40} />}
          </div>
          <Button type="submit" variant="primary" disabled={busy || amountError !== undefined}>
            {refund ? "Record refund" : "Record payment"}
          </Button>
        </form>
      )}
      {voiding !== null && (
        <Dialog title="Void this payment?" onClose={() => setVoiding(null)}>
          <p>Only a payment taken today can be voided. Its amount goes back on the bill.</p>
          <TextField id={`void-reason-${voiding.id}`} label="Reason" value={reason} onChange={setReason} maxLength={200} required />
          <div className="mt-4 flex gap-2">
            <Button
              variant="danger"
              disabled={busy || reason.trim() === ""}
              onClick={() => {
                const target = voiding;
                setVoiding(null);
                void run(
                  () => api.voidPayment(bill.id, target.id, reason.trim()),
                  () => `The ${formatPaise(target.amount_paise)} ${target.kind === "REFUND" ? "refund" : "payment"} was voided.`,
                );
                setReason("");
              }}
            >
              Void
            </Button>
            <Button onClick={() => setVoiding(null)}>Keep it</Button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
