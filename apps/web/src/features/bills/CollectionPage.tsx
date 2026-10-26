"use client";

import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { INPUT, LABEL } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { clinicToday } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatPaise } from "@/lib/format/money";
import { formatClock } from "@/lib/format/time";

import { MODE_LABELS, useBillsApi, type CollectionDay } from "./api";

function Table({ caption, head, rows }: Readonly<{ caption: string; head: readonly string[]; rows: readonly (readonly string[])[] }>) {
  return (
    <div className={TABLE_WRAP}>
      <table className={TABLE} role="table">
        <caption className="sr-only">{caption}</caption>
        <thead role="rowgroup">
          <tr role="row">
            {head.map((h) => (
              <th key={h} role="columnheader" scope="col" className={TH}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup">
          {rows.map((r, i) => (
            <tr key={i} role="row" className={TR}>
              {r.map((cell, j) => (
                <td key={j} role="cell" data-label={head[j] ?? ""} className={`${TD} ${j > 0 ? "tabular-nums" : ""}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * *Collection* (M6d-P5; FR-BIL-06; billing R55-R62): one clinic-local day's payments and refunds,
 * by mode and by doctor, with the net and the list behind it; *Export CSV* downloads the same list.
 * Voided entries are listed, struck through, and never counted.
 */
export function CollectionPage() {
  const api = useBillsApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const today = clinicToday(clinic.timezone);
  const [day, setDay] = useState(today);
  const [data, setData] = useState<CollectionDay | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  const dayId = useId();

  useEffect(() => {
    let cancelled = false;
    api.collection(day).then(
      (result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, day, endSession]);

  async function exportCsv() {
    setExporting(true);
    try {
      const url = URL.createObjectURL(await api.collectionCsv(day));
      const a = document.createElement("a");
      a.href = url;
      a.download = `collection-${day}.csv`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setExporting(false);
    }
  }

  const money = (t: { payments_paise: number; refunds_paise: number; net_paise: number }) => [
    formatPaise(t.payments_paise),
    formatPaise(t.refunds_paise),
    formatPaise(t.net_paise),
  ];

  return (
    <section className="space-y-5">
      <PageHeader
        title="Collection"
        description="Payments and refunds taken on one day. A day's figures stop changing when it ends."
        actions={
          <Button onClick={() => void exportCsv()} disabled={exporting || data === undefined}>
            {exporting ? "Preparing…" : "Export CSV"}
          </Button>
        }
      />
      <div className="max-w-xs space-y-1">
        <label htmlFor={dayId} className={LABEL}>
          Day
        </label>
        <input id={dayId} type="date" value={day} max={today} onChange={(e) => e.target.value !== "" && setDay(e.target.value)} className={INPUT} />
      </div>
      {error !== null && <ErrorNotice error={error} />}
      {data === undefined && error === null && <p role="status">Loading the collection…</p>}
      {data !== undefined && (
        <>
          <p className="text-2xl font-bold" aria-live="polite">
            Net {formatPaise(data.total.net_paise)}
            <span className="block text-base font-normal text-slate-700">
              {formatPaise(data.total.payments_paise)} taken, {formatPaise(data.total.refunds_paise)} refunded, {data.total.count}{" "}
              {data.total.count === 1 ? "entry" : "entries"}
              {data.voided.count > 0 && ` · ${data.voided.count} voided, not counted`}
            </span>
          </p>
          <h2 className="text-lg font-semibold">By mode</h2>
          <Table caption="Collection by mode" head={["Mode", "Taken", "Refunded", "Net"]} rows={data.by_mode.map((r) => [MODE_LABELS[r.mode], ...money(r)])} />
          <h2 className="text-lg font-semibold">By doctor</h2>
          {data.by_doctor.length === 0 ? (
            <p>Nothing taken on this day.</p>
          ) : (
            <Table
              caption="Collection by doctor"
              head={["Doctor", "Taken", "Refunded", "Net"]}
              rows={data.by_doctor.map((r) => [r.doctor?.display_name ?? "No doctor", ...money(r)])}
            />
          )}
          {data.items.length > 0 && (
            <>
              <h2 className="text-lg font-semibold">Entries</h2>
              <Table
                caption="Every payment and refund of the day"
                head={["Time", "Entry", "Bill", "Patient", "Amount", "Taken by"]}
                rows={data.items.map((i) => [
                  formatClock(i.received_at, data.timezone),
                  `${i.kind === "REFUND" ? "Refund" : "Payment"} · ${MODE_LABELS[i.mode]}${i.reference ? ` · ${i.reference}` : ""}${i.voided ? " · voided" : ""}`,
                  i.bill_number ?? "–",
                  i.patient === null ? "–" : `${i.patient.full_name} · ${i.patient.code}`,
                  formatPaise(i.amount_paise),
                  i.received_by ?? "–",
                ])}
              />
            </>
          )}
        </>
      )}
    </section>
  );
}
