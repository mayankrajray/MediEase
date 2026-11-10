"use client";

import { Building2, ChevronLeft, ChevronRight, Download, FileText, Paperclip, Receipt } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";

import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { PrescriptionView } from "@/features/patient-link/PrescriptionView";
import { stringsFor } from "@/features/patient-link/strings";
import { ApiError } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { portalGet, portalPdf, portalPdfAt } from "@/lib/auth/portal-session";
import { formatPaise } from "@/lib/format/money";
import { type PortalLanguage, portalDate } from "@/lib/i18n/portal";

import { DEFAULT_ZONE, type PortalPrescription, portalErrorText, usePortalLoad, zonesOf } from "./data";
import { PORTAL_LINK, PortalCard, PortalTitle, ScreenLoading, usePortal } from "./PortalShell";

/** A download action that reads as a small secondary button (44 px). */
const DOWNLOAD = `${buttonClasses("secondary", "md")} min-h-11 shrink-0`;

type Page = components["schemas"]["PatientPrescriptionPage"];

async function loadList() {
  const [links, items, bills, reports] = await Promise.all([
    portalGet("/api/v1/portal/links"),
    portalGet("/api/v1/portal/prescriptions"),
    // M6d-P4: the bills card is extra; a failure there must not hide the prescriptions.
    portalGet("/api/v1/portal/bills").then(
      (r) => r.data,
      () => ({ items: [] as PortalBill[] }),
    ),
    // M6d-P6: the same for the reports the doctor shared.
    portalGet("/api/v1/portal/attachments").then(
      (r) => r.data.items,
      () => [] as PortalReport[],
    ),
  ]);
  return { zones: zonesOf(links.data.items), items: items.data.items, bills: bills.items, reports };
}

/** *My prescriptions* (M6b-P2; spec R19): each linked clinic's current prescriptions, by clinic. */
export function PortalPrescriptions() {
  const { s } = usePortal();
  const loaded = usePortalLoad(loadList);

  let groups: [string, PortalPrescription[]][] = [];
  if (loaded.status === "ready") {
    const byClinic = new Map<string, PortalPrescription[]>();
    for (const p of loaded.data.items) byClinic.set(p.clinic_id, [...(byClinic.get(p.clinic_id) ?? []), p]);
    groups = [...byClinic.entries()];
  }

  return (
    <div className="space-y-5">
      <PortalTitle>{s.prescriptions.title}</PortalTitle>
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" && groups.length === 0 && <EmptyState title={s.prescriptions.empty} icon={<FileText className="size-5" />} />}
      {loaded.status === "ready" &&
        groups.map(([clinicId, items]) => (
          <PortalCard key={clinicId} id={`rx-${clinicId}`} title={items[0]?.clinic_name ?? ""} icon={<Building2 />}>
            <ul className="-mx-2 space-y-1">
              {items.map((p) => (
                <li
                  key={p.id}
                  className="relative flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors duration-200 ease-brand focus-within:bg-brand-50 hover:bg-slate-50 motion-reduce:transition-none"
                >
                  <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
                    <FileText className="size-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    {/* The doctor names the link; the whole row is its target (the after: layer). */}
                    <Link
                      href={`/portal/prescriptions/${p.id}`}
                      className="block font-semibold text-slate-900 outline-none after:absolute after:inset-0 after:rounded-lg after:content-['] focus-visible:after:ring-2 focus-visible:after:ring-brand-600 [overflow-wrap:anywhere]"
                    >
                      {p.doctor_name}
                    </Link>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-700">
                      {s.prescriptions.issued(portalDate(p.issued_at, loaded.data.zones.get(clinicId) ?? DEFAULT_ZONE, s))}
                      {p.version > 1 && <StatusBadge tone="active">{s.prescriptions.updated}</StatusBadge>}
                    </span>
                  </span>
                  <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-slate-500" />
                </li>
              ))}
            </ul>
          </PortalCard>
        ))}
      {loaded.status === "ready" && loaded.data.reports.length > 0 && <PortalReports reports={loaded.data.reports} zones={loaded.data.zones} />}
      {loaded.status === "ready" && loaded.data.bills.length > 0 && <PortalBills bills={loaded.data.bills} />}
    </div>
  );
}

type PortalBill = components["schemas"]["PortalBillList"]["items"][number];
type PortalReport = components["schemas"]["PortalAttachmentList"]["items"][number];

/** M6d-P6 (visit-attachments R11, R12): reports the doctor shared, each saved under its name. */
function PortalReports({ reports, zones }: Readonly<{ reports: readonly PortalReport[]; zones: ReadonlyMap<string, string> }>) {
  const { s, leave } = usePortal();
  const [error, setError] = useState<unknown>(null);

  async function download(report: PortalReport) {
    setError(null);
    try {
      const url = URL.createObjectURL(await portalPdfAt(`/api/v1/portal/attachments/${encodeURIComponent(report.id)}/file`));
      const link = document.createElement("a");
      link.href = url;
      link.download = report.filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    }
  }

  return (
    <PortalCard id="reports" title={s.reports.title} icon={<Paperclip />}>
      {error !== null && <ErrorNotice error={error} />}
      <ul>
        {reports.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
            <span className="min-w-0 flex-1">
              <span className="block break-all font-semibold text-slate-900">{r.filename}</span>
              <span className="text-sm text-slate-700">
                {r.clinic_name} · {s.reports.visitOn(portalDate(r.visit_date, zones.get(r.clinic_id) ?? DEFAULT_ZONE, s))}
              </span>
            </span>
            <button type="button" onClick={() => void download(r)} className={DOWNLOAD}>
              <Download aria-hidden="true" className="size-4" />
              {s.reports.open} <span className="sr-only">{r.filename}</span>
            </button>
          </li>
        ))}
      </ul>
    </PortalCard>
  );
}

/** M6d-P4 (billing R52): the linked records' issued bills, each with its receipt. */
function PortalBills({ bills }: Readonly<{ bills: readonly PortalBill[] }>) {
  const { s, leave } = usePortal();
  const [error, setError] = useState<unknown>(null);

  async function download(bill: PortalBill) {
    setError(null);
    try {
      const url = URL.createObjectURL(await portalPdfAt(`/api/v1/portal/bills/${encodeURIComponent(bill.id)}/receipt.pdf`));
      const link = document.createElement("a");
      link.href = url;
      link.download = `bill-${bill.number.replaceAll("/", "-")}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    }
  }

  return (
    <PortalCard id="bills" title={s.bills.title} icon={<Receipt />}>
      {error !== null && <ErrorNotice error={error} />}
      <ul>
        {bills.map((b) => (
          <li key={b.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
            <span className="min-w-0 flex-1 space-y-1">
              <span className="block font-semibold text-slate-900 [overflow-wrap:anywhere]">
                {b.clinic_name} · {b.number}
              </span>
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-700">
                <span className="tabular-nums">
                  {b.bill_date} · {formatPaise(b.total_paise)}
                </span>
                <StatusBadge tone={b.cancelled ? "neutral" : b.balance_paise > 0 ? "waiting" : "done"}>
                  {b.cancelled ? s.bills.cancelled : b.balance_paise > 0 ? s.bills.due(formatPaise(b.balance_paise)) : s.bills.settled}
                </StatusBadge>
              </span>
            </span>
            <button type="button" onClick={() => void download(b)} className={DOWNLOAD}>
              <Download aria-hidden="true" className="size-4" />
              {s.bills.download} <span className="sr-only">{b.number}</span>
            </button>
          </li>
        ))}
      </ul>
    </PortalCard>
  );
}

/**
 * One prescription (spec R19, decision 6A): the same page as the prescription link, in the
 * account's language unless `?lang=` asks otherwise, with *Download PDF*.
 */
export function PortalPrescription({ rxId, lang }: Readonly<{ rxId: string; lang?: PortalLanguage }>) {
  const { s, leave } = usePortal();
  const load = useCallback(
    async (): Promise<Page> =>
      (
        await portalGet("/api/v1/portal/prescriptions/{rx_id}", {
          pathParams: { rx_id: rxId },
          ...(lang === undefined ? {} : { query: { lang } }),
        })
      ).data,
    [rxId, lang],
  );
  const loaded = usePortalLoad(load);
  const [downloading, setDownloading] = useState(false);
  const [pdfError, setPdfError] = useState<unknown>(null);

  async function download() {
    if (downloading) return;
    setDownloading(true);
    setPdfError(null);
    try {
      const blob = await portalPdf(rxId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `prescription-${rxId}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      if (!leave(failure)) setPdfError(failure);
    } finally {
      setDownloading(false);
    }
  }

  const back = (
    <Link href="/portal/prescriptions" className={PORTAL_LINK}>
      <ChevronLeft aria-hidden="true" className="size-4" />
      {s.prescriptions.back}
    </Link>
  );
  if (loaded.status === "loading") return <ScreenLoading label={s.loading} />;
  if (loaded.status === "failed") {
    const notFound = loaded.error instanceof ApiError && loaded.error.code === "REQ_NOT_FOUND";
    return (
      <div className="space-y-4">
        {notFound ? (
          <>
            <PortalTitle>{s.prescriptions.title}</PortalTitle>
            <p role="alert" className="rounded-card border border-danger-line bg-danger-soft p-4 text-slate-900">
              {s.notFound}
            </p>
          </>
        ) : (
          <ErrorNotice error={loaded.error} onRetry={loaded.retry} />
        )}
        {back}
      </div>
    );
  }
  const page = loaded.data;
  const other = page.language === "hi" ? "en" : "hi";
  const pdfText = portalErrorText(pdfError, s);
  return (
    <div className="space-y-4">
      {back}
      <div className="overflow-hidden rounded-card border border-line bg-white shadow-card">
        <PrescriptionView
          page={page}
          strings={stringsFor(page.language)}
          switchHref={`/portal/prescriptions/${encodeURIComponent(rxId)}?lang=${other}`}
          embedded
        />
      </div>
      {pdfError !== null && <ErrorNotice error={pdfError} {...(pdfText === undefined ? {} : { message: pdfText })} />}
      <Button size="lg" onClick={() => void download()} disabled={downloading} icon={<Download className="size-5" />} className="w-full sm:w-auto">
        {downloading ? s.prescriptions.downloading : s.prescriptions.download}
      </Button>
    </div>
  );
}
