"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { PrescriptionView } from "@/features/patient-link/PrescriptionView";
import { stringsFor } from "@/features/patient-link/strings";
import { ApiError } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { portalGet, portalPdf } from "@/lib/auth/portal-session";
import { type PortalLanguage, portalDate } from "@/lib/i18n/portal";

import { DEFAULT_ZONE, type PortalPrescription, portalErrorText, usePortalLoad, zonesOf } from "./data";
import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";

type Page = components["schemas"]["PatientPrescriptionPage"];

async function loadList() {
  const [links, items] = await Promise.all([portalGet("/api/v1/portal/links"), portalGet("/api/v1/portal/prescriptions")]);
  return { zones: zonesOf(links.data.items), items: items.data.items };
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
      <h1 className="text-2xl font-bold tracking-tight">{s.prescriptions.title}</h1>
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" && groups.length === 0 && <p>{s.prescriptions.empty}</p>}
      {loaded.status === "ready" &&
        groups.map(([clinicId, items]) => (
          <PortalCard key={clinicId} id={`rx-${clinicId}`} title={items[0]?.clinic_name ?? ""}>
            <ul>
              {items.map((p) => (
                <li key={p.id} className="border-t border-slate-200 py-2 first:border-t-0">
                  <Link href={`/portal/prescriptions/${p.id}`} className="block min-h-11 font-semibold text-brand-800 underline">
                    {p.doctor_name}
                  </Link>
                  <span className="text-sm text-slate-700">
                    {s.prescriptions.issued(portalDate(p.issued_at, loaded.data.zones.get(clinicId) ?? DEFAULT_ZONE, s))}
                    {p.version > 1 && ` · ${s.prescriptions.updated}`}
                  </span>
                </li>
              ))}
            </ul>
          </PortalCard>
        ))}
    </div>
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
    <Link href="/portal/prescriptions" className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
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
            <h1 className="text-2xl font-bold tracking-tight">{s.prescriptions.title}</h1>
            <p role="alert">{s.notFound}</p>
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
      <div className="rounded-card border border-slate-200 bg-white shadow-card">
        <PrescriptionView
          page={page}
          strings={stringsFor(page.language)}
          switchHref={`/portal/prescriptions/${encodeURIComponent(rxId)}?lang=${other}`}
          embedded
        />
      </div>
      {pdfError !== null && <ErrorNotice error={pdfError} {...(pdfText === undefined ? {} : { message: pdfText })} />}
      <button
        type="button"
        onClick={() => void download()}
        disabled={downloading}
        className="inline-flex min-h-12 items-center justify-center rounded-lg border border-brand-700 bg-white px-5 font-semibold text-brand-800 hover:bg-brand-50"
      >
        {downloading ? s.prescriptions.downloading : s.prescriptions.download}
      </button>
    </div>
  );
}
