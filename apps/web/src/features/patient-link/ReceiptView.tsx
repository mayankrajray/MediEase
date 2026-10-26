import type { GetResponse } from "@/lib/api/client";
import { formatPaise } from "@/lib/format/money";

type Receipt = GetResponse<"/api/v1/public/links/{token}/receipt">;

/** M6d-P4 (billing R49): the bill's number, date and amounts, and its PDF; nothing clinical. */
export function ReceiptView({ receipt, pdfHref }: Readonly<{ receipt: Receipt; pdfHref: string }>) {
  const balance = receipt.balance_paise;
  const rows: [string, string][] = [
    ["Total", formatPaise(receipt.total_paise)],
    ...(receipt.credited_paise > 0 ? ([["Credited", formatPaise(receipt.credited_paise)]] as [string, string][]) : []),
    ["Paid", formatPaise(receipt.paid_paise)],
    ...(receipt.refunded_paise > 0 ? ([["Refunded", formatPaise(receipt.refunded_paise)]] as [string, string][]) : []),
  ];
  return (
    <main lang="en" className="mx-auto max-w-md space-y-4 px-4 pb-10 pt-4 text-base leading-relaxed text-slate-900">
      <header>
        <p>{receipt.clinic_name}</p>
        <h1 className="text-xl font-bold">Bill {receipt.number}</h1>
        <p>{receipt.bill_date}</p>
        {receipt.cancelled && <p className="font-semibold">This bill was cancelled.</p>}
      </header>
      <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1 tabular-nums">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-medium">{k}</dt>
            <dd className="text-right">{v}</dd>
          </div>
        ))}
        <div className="contents text-lg font-bold">
          <dt>{balance > 0 ? "Balance due" : balance < 0 ? "To be refunded" : "Balance"}</dt>
          <dd className="text-right">{balance === 0 ? "Settled" : formatPaise(Math.abs(balance))}</dd>
        </div>
      </dl>
      <a href={pdfHref} className="inline-flex min-h-11 items-center rounded-lg bg-brand-700 px-4 font-semibold text-white">
        Download the receipt (PDF)
      </a>
    </main>
  );
}
