"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatDateTime } from "@/lib/format/time";

import { useRxApi, type LinkInfo } from "./api";

/**
 * Print a prescription (M4-P4, spec D6): the PDF opens in a new tab, where the browser's own
 * viewer prints it. The tab is opened at the click, before the download, so pop-up blockers
 * allow it; if the browser still refuses, the PDF is offered as a download instead.
 */
export function usePrint(): { readonly print: (rxId: string) => void; readonly printing: boolean; readonly error: unknown } {
  const api = useRxApi();
  const { endSession } = useSession();
  const [printing, setPrinting] = useState(false);
  const [error, setError] = useState<unknown>(undefined);

  function print(rxId: string) {
    const tab = window.open("", "_blank");
    setPrinting(true);
    setError(undefined);
    api.pdf(rxId).then(
      (blob) => {
        const url = URL.createObjectURL(blob);
        if (tab !== null) {
          tab.location.href = url;
        } else {
          const link = document.createElement("a");
          link.href = url;
          link.download = `prescription-${rxId}.pdf`;
          link.click();
        }
        // The tab has its own copy once it has loaded it.
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
        setPrinting(false);
      },
      (failure: unknown) => {
        tab?.close();
        setPrinting(false);
        if (!endSession(failure)) setError(failure);
      },
    );
  }

  return { print, printing, error };
}

export function PrintButton({ rxId, label = "Print", name }: Readonly<{ rxId: string; label?: string; name?: string }>) {
  const { print, printing, error } = usePrint();
  return (
    <span className="inline-flex flex-col items-end gap-2">
      <button
        type="button"
        aria-label={name}
        disabled={printing}
        onClick={() => print(rxId)}
        className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100 disabled:text-slate-500"
      >
        {printing ? "Preparing…" : label}
      </button>
      {error !== undefined && <ErrorNotice error={error} />}
    </span>
  );
}

/** The patient link for the counter (spec D2, M4-P5): a QR code to scan, the link to copy. */
export function LinkPanel({ rxId }: Readonly<{ rxId: string }>) {
  const api = useRxApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [link, setLink] = useState<LinkInfo | undefined>(undefined);
  const [qr, setQr] = useState<string | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [copied, setCopied] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.link(rxId).then(
      (info) => {
        if (cancelled) return;
        setLink(info);
        void QRCode.toDataURL(info.url, { margin: 1, width: 192, errorCorrectionLevel: "M" }).then((data) => {
          if (!cancelled) setQr(data);
        });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, rxId, endSession]);

  if (error !== undefined) return <ErrorNotice error={error} />;
  if (link === undefined) return <p role="status">Getting the patient link…</p>;

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied("Link copied.");
    } catch {
      setCopied("Could not copy here: select the link and copy it.");
    }
  }

  function reset() {
    api.resetLink(rxId).then(setLink, (failure: unknown) => {
      if (!endSession(failure)) setError(failure);
    });
  }

  return (
    <div className="flex flex-wrap items-start gap-4">
      {qr !== undefined && (
        // A data: URL made here; next/image has nothing to optimise.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={qr} width={192} height={192} alt="QR code of the patient's prescription link" className="rounded border border-slate-300" />
      )}
      <div className="min-w-0 flex-1 space-y-2">
        <p>The patient scans this, or you send the link. Opening it asks for the last 4 digits of their phone.</p>
        <p className="break-all font-mono text-sm" data-testid="patient-link">
          {link.url}
        </p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void copy(link.url)} className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100">
            Copy link
          </button>
          {link.locked && (
            <button type="button" onClick={reset} className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100">
              Unlock link
            </button>
          )}
        </div>
        <p role="status" className="text-sm">
          {copied}
        </p>
        <p className="text-sm text-slate-700">
          {link.locked ? "Locked after 5 wrong attempts. " : ""}Opened {link.open_count} {link.open_count === 1 ? "time" : "times"} · valid until{" "}
          {formatDateTime(link.expires_at, clinic.timezone)}
        </p>
      </div>
    </div>
  );
}
