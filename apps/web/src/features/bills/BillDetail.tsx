"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";
import { CheckboxField, SelectField, TextAreaField, TextField } from "@/components/ui/Field";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useFeesApi, type FeeService } from "@/features/fees/api";
import { patientPath } from "@/features/patients/RegisterPatientDrawer";
import { formatPaise } from "@/lib/format/money";

import { BILL_STATUS_LABELS, BILL_STATUS_TONES, useBillsApi, type Bill, type BillLineInput, type DiscountKind } from "./api";
import { balanceText } from "./BillsList";
import { discountRow, emptyRow, rowsOf, toDiscount, toLine, type DiscountRow, type LineRow, type RowErrors } from "./form";

type Load = { readonly status: "loading" } | { readonly status: "ready"; readonly bill: Bill } | { readonly status: "failed"; readonly error: unknown };

const DISCOUNT_OPTIONS: readonly { value: DiscountKind; label: string }[] = [
  { value: "NONE", label: "No discount" },
  { value: "AMOUNT", label: "Rupees off" },
  { value: "PERCENT", label: "Percent off" },
];

/**
 * One bill (M6d-P2; FR-BIL-02, 07; billing R13-R30). A draft is edited here and issued, which
 * numbers and freezes it; an issued bill is corrected only by a credit note for some or all of
 * its lines. Totals come from the API. `extra` is where payments and receipts join (P3, P4).
 */
export function BillDetail({ billId, extra }: Readonly<{ billId: string; extra?: (bill: Bill, show: (b: Bill) => void) => ReactNode }>) {
  const api = useBillsApi();
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [message, say] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.get(billId).then(
      (bill) => {
        if (!cancelled) setLoad({ status: "ready", bill });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, billId, endSession]);

  if (load.status === "loading") return <p role="status">Loading the bill…</p>;
  if (load.status === "failed") return <ErrorNotice error={load.error} />;
  const { bill } = load;
  const show = (next: Bill) => setLoad({ status: "ready", bill: next });

  return (
    <article aria-labelledby="bill-heading" className="max-w-4xl space-y-6">
      <header className="space-y-1">
        <p className="text-sm">
          <Link href="/bills" className="font-medium text-brand-800 underline">
            All bills
          </Link>
        </p>
        <h1 id="bill-heading" className="text-2xl font-bold tracking-tight">
          {bill.number === null ? "Draft bill" : `Bill ${bill.number}`}
        </h1>
        <p className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={BILL_STATUS_TONES[bill.status]}>{BILL_STATUS_LABELS[bill.status]}</StatusBadge>
          {bill.patient !== null && (
            <Link href={patientPath(bill.patient.id)} className="font-medium text-brand-800 underline">
              {bill.patient.full_name} · {bill.patient.code}
            </Link>
          )}
          {bill.doctor !== null && <span>· {bill.doctor.display_name}</span>}
          {bill.bill_date !== null && <span>· {bill.bill_date}</span>}
        </p>
      </header>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {message}
      </p>
      {bill.status === "DRAFT" ? <DraftEditor bill={bill} onChange={show} say={say} /> : <IssuedBill bill={bill} onChange={show} say={say} />}
      {extra?.(bill, show)}
    </article>
  );
}

function Totals({ bill }: Readonly<{ bill: Bill }>) {
  const rows: [string, string][] = [
    ["Subtotal", formatPaise(bill.subtotal_paise)],
    ...(bill.discount_paise > 0 ? ([["Bill discount", `− ${formatPaise(bill.discount_paise)}`]] as [string, string][]) : []),
    ["Total", formatPaise(bill.total_paise)],
    ...(bill.credited_paise > 0 ? ([["Credited", `− ${formatPaise(bill.credited_paise)}`]] as [string, string][]) : []),
    ...(bill.paid_paise > 0 ? ([["Paid", `− ${formatPaise(bill.paid_paise)}`]] as [string, string][]) : []),
    ...(bill.refunded_paise > 0 ? ([["Refunded", formatPaise(bill.refunded_paise)]] as [string, string][]) : []),
  ];
  return (
    <dl className="ml-auto grid max-w-xs grid-cols-[1fr_auto] gap-x-6 gap-y-1 tabular-nums">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="font-medium">{k}</dt>
          <dd className="text-right">{v}</dd>
        </div>
      ))}
      {bill.balance_paise !== null && (
        <div className="contents text-lg font-bold">
          <dt>Balance</dt>
          <dd className="text-right">{balanceText(bill)}</dd>
        </div>
      )}
    </dl>
  );
}

function DiscountFields({
  id,
  label,
  row,
  onChange,
  error,
}: Readonly<{ id: string; label: string; row: DiscountRow; onChange: (row: DiscountRow) => void; error?: string | undefined }>) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <SelectField
        id={`${id}-kind`}
        label={label}
        value={row.kind}
        options={DISCOUNT_OPTIONS}
        onChange={(kind) => onChange({ kind: kind as DiscountKind, value: kind === "NONE" ? "" : row.value })}
      />
      {row.kind !== "NONE" && (
        <TextField
          id={`${id}-value`}
          label={row.kind === "PERCENT" ? `${label}: percent` : `${label}: rupees`}
          inputMode="numeric"
          value={row.value}
          onChange={(value) => onChange({ ...row, value })}
          error={error}
        />
      )}
    </div>
  );
}

/** R15-R20: a draft's lines (from the fee schedule or typed), discounts and notes. */
function DraftEditor({ bill, onChange, say }: Readonly<{ bill: Bill; onChange: (bill: Bill) => void; say: (text: string) => void }>) {
  const api = useBillsApi();
  const fees = useFeesApi();
  const router = useRouter();
  const { endSession } = useSession();
  const [services, setServices] = useState<readonly FeeService[]>([]);
  const [rows, setRows] = useState<LineRow[]>(() => rowsOf(bill));
  const [discount, setDiscount] = useState<DiscountRow>(() => discountRow(bill.discount));
  const [notes, setNotes] = useState(bill.notes ?? "");
  const [errors, setErrors] = useState<Record<string, RowErrors>>({});
  const [billError, setBillError] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [discarding, setDiscarding] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fees.get().then(
      (schedule) => {
        if (!cancelled) setServices(schedule.services.filter((s) => s.active));
      },
      () => undefined, // typed lines still work without the schedule
    );
    return () => {
      cancelled = true;
    };
  }, [fees]);

  const update = (key: string, change: Partial<LineRow>) => setRows((all) => all.map((r) => (r.key === key ? { ...r, ...change } : r)));

  function pickService(row: LineRow, serviceId: string) {
    const service = services.find((s) => s.id === serviceId);
    const priced = service?.doctor_prices.find((p) => p.doctor_id === bill.doctor?.id)?.price_paise ?? service?.default_price_paise ?? null;
    update(row.key, {
      serviceId,
      description: service?.name ?? row.description,
      price: priced === null ? row.price : (priced / 100).toFixed(priced % 100 === 0 ? 0 : 2),
    });
  }

  function lines(): BillLineInput[] | null {
    const found: Record<string, RowErrors> = {};
    const out: BillLineInput[] = [];
    for (const row of rows) {
      const result = toLine(row);
      if ("errors" in result) found[row.key] = result.errors;
      else out.push(result.line);
    }
    const d = toDiscount(discount);
    setErrors(found);
    setBillError(typeof d === "string" ? d : undefined);
    return Object.keys(found).length > 0 || typeof d === "string" ? null : out;
  }

  async function save(): Promise<Bill | null> {
    const body = lines();
    const d = toDiscount(discount);
    if (body === null || typeof d === "string") return null;
    const next = await api.change(bill.id, { lines: body, discount: d, notes: notes.trim() === "" ? null : notes.trim() });
    onChange(next);
    return next;
  }

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(async () => {
      if ((await save()) !== null) say("Draft saved.");
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error !== null && <ErrorNotice error={error} />}
      <fieldset className="space-y-3">
        <legend className="text-lg font-semibold">Lines</legend>
        {rows.length === 0 && <p>No lines yet. Add one below.</p>}
        {rows.map((row, n) => {
          const e = errors[row.key] ?? {};
          const id = `${bill.id}-${n + 1}`;
          return (
            <div key={row.key} className="space-y-2 rounded-card border border-slate-200 bg-white p-3">
              <div className="grid gap-2 sm:grid-cols-[2fr_2fr_1fr_1fr]">
                <SelectField
                  id={`${id}-service`}
                  label={`Line ${n + 1}: service`}
                  value={row.serviceId}
                  onChange={(v) => pickService(row, v)}
                  options={[{ value: "", label: "Typed line" }, ...services.map((s) => ({ value: s.id, label: s.name }))]}
                />
                <TextField
                  id={`${id}-description`}
                  label={`Line ${n + 1}: description`}
                  value={row.description}
                  onChange={(description) => update(row.key, { description })}
                  maxLength={80}
                  error={e.description}
                />
                <TextField
                  id={`${id}-price`}
                  label={`Line ${n + 1}: price in rupees`}
                  inputMode="numeric"
                  value={row.price}
                  onChange={(price) => update(row.key, { price })}
                  error={e.price}
                />
                <TextField
                  id={`${id}-quantity`}
                  label={`Line ${n + 1}: quantity`}
                  inputMode="numeric"
                  value={row.quantity}
                  onChange={(quantity) => update(row.key, { quantity })}
                  error={e.quantity}
                />
              </div>
              <DiscountFields
                id={`${id}-discount`}
                label={`Line ${n + 1}: discount`}
                row={row.discount}
                onChange={(d) => update(row.key, { discount: d })}
                error={e.discount}
              />
              <Button size="sm" onClick={() => setRows((all) => all.filter((r) => r.key !== row.key))}>
                Remove line {n + 1}
              </Button>
            </div>
          );
        })}
        <Button size="sm" onClick={() => setRows((all) => [...all, emptyRow()])} disabled={rows.length >= 50}>
          Add a line
        </Button>
      </fieldset>
      <DiscountFields id={`${bill.id}-bill-discount`} label="Bill discount" row={discount} onChange={setDiscount} error={billError} />
      <TextAreaField
        id={`${bill.id}-notes`}
        label="Notes on the bill (optional)"
        value={notes}
        onChange={setNotes}
        maxLength={500}
        hint="Printed on the bill. Never write clinical details here."
      />
      {bill.lines.length > 0 && (
        <section aria-label="Saved totals" className="space-y-1">
          <p className="text-sm text-slate-700">As last saved:</p>
          <Totals bill={bill} />
        </section>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          Save draft
        </Button>
        <Button
          variant="primary"
          disabled={busy || rows.length === 0}
          onClick={() =>
            void run(async () => {
              if ((await save()) === null) return;
              onChange(await api.issue(bill.id));
              say("Bill issued. It can no longer change.");
            })
          }
        >
          Issue bill
        </Button>
        <Button variant="danger" disabled={busy} onClick={() => setDiscarding(true)}>
          Discard draft
        </Button>
      </div>
      {discarding && (
        <Dialog title="Discard this draft?" onClose={() => setDiscarding(false)}>
          <p>The draft is deleted. It never had a number, so nothing is lost from the series.</p>
          <div className="mt-4 flex gap-2">
            <Button
              variant="danger"
              onClick={() =>
                void run(async () => {
                  await api.discard(bill.id);
                  router.push("/bills");
                })
              }
            >
              Discard
            </Button>
            <Button onClick={() => setDiscarding(false)}>Keep it</Button>
          </div>
        </Dialog>
      )}
    </form>
  );
}

/** R20, R23-R26: an issued bill's lines, its credit notes, and the credit-note form. */
function IssuedBill({ bill, onChange, say }: Readonly<{ bill: Bill; onChange: (bill: Bill) => void; say: (text: string) => void }>) {
  const api = useBillsApi();
  const { endSession } = useSession();
  const open = bill.lines.filter((l) => !l.credited);
  const [chosen, setChosen] = useState<readonly string[]>([]);
  const [reason, setReason] = useState("");
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const reasonError = tried && reason.trim() === "" ? "Say why the bill is corrected." : undefined;

  async function credit(lineIds: readonly string[] | null) {
    setTried(true);
    if (reason.trim() === "" || (lineIds !== null && lineIds.length === 0)) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.credit(bill.id, lineIds, reason.trim());
      onChange(next);
      setChosen([]);
      setReason("");
      setTried(false);
      say(next.status === "CANCELLED" ? "Credit note issued. The bill is cancelled." : "Credit note issued.");
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className={TABLE_WRAP}>
        <table className={TABLE} role="table">
          <caption className="sr-only">Bill lines</caption>
          <thead role="rowgroup">
            <tr role="row">
              {["Line", "Price", "Qty", "Discount", "Amount", ""].map((h) => (
                <th key={h || "state"} role="columnheader" scope="col" className={TH}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody role="rowgroup">
            {bill.lines.map((line) => (
              <tr key={line.id} role="row" className={TR}>
                <td role="cell" data-label="Line" className={TD}>
                  {line.description}
                </td>
                <td role="cell" data-label="Price" className={`${TD} tabular-nums`}>
                  {formatPaise(line.unit_price_paise)}
                </td>
                <td role="cell" data-label="Qty" className={TD}>
                  {line.quantity}
                </td>
                <td role="cell" data-label="Discount" className={`${TD} tabular-nums`}>
                  {line.discount_paise + line.bill_discount_paise > 0 ? `− ${formatPaise(line.discount_paise + line.bill_discount_paise)}` : "–"}
                </td>
                <td role="cell" data-label="Amount" className={`${TD} tabular-nums font-medium`}>
                  {formatPaise(line.amount_paise)}
                </td>
                <td role="cell" data-label="" className={TD}>
                  {line.credited && <StatusBadge tone="missed">Credited</StatusBadge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Totals bill={bill} />
      {bill.notes !== null && <p>Notes: {bill.notes}</p>}

      {bill.credit_notes.length > 0 && (
        <section aria-labelledby="credit-notes-heading" className="space-y-2">
          <h2 id="credit-notes-heading" className="text-lg font-semibold">
            Credit notes
          </h2>
          <ul className="space-y-2">
            {bill.credit_notes.map((note) => (
              <li key={note.id} className="rounded-card border border-slate-200 bg-white p-3">
                <p className="font-medium">
                  {note.number} · {note.bill_date} · {formatPaise(note.total_paise)}
                </p>
                <p className="text-sm">
                  {note.lines.map((l) => l.description).join(", ")} — {note.reason}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {bill.status === "ISSUED" && open.length > 0 && (
        <section aria-labelledby="credit-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4">
          <h2 id="credit-heading" className="text-lg font-semibold">
            Correct this bill
          </h2>
          <p className="text-sm text-slate-700">
            An issued bill never changes. A credit note reverses the lines you choose; reversing all of them cancels the bill.
          </p>
          {error !== null && <ErrorNotice error={error} />}
          <fieldset>
            <legend className="font-medium">Lines to credit</legend>
            {open.map((line) => (
              <CheckboxField
                key={line.id}
                id={`credit-${line.id}`}
                label={`${line.description} (${formatPaise(line.amount_paise)})`}
                checked={chosen.includes(line.id)}
                onChange={(on) => setChosen(on ? [...chosen, line.id] : chosen.filter((i) => i !== line.id))}
              />
            ))}
          </fieldset>
          <TextField id={`credit-reason-${bill.id}`} label="Reason" value={reason} onChange={setReason} maxLength={200} required error={reasonError} />
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || chosen.length === 0} onClick={() => void credit(chosen)}>
              Credit the chosen lines
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => void credit(null)}>
              Cancel the whole bill
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
