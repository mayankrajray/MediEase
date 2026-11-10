"use client";

import { Copy, LockOpen, Printer, QrCode } from "lucide-react";
import QRCode from "qrcode";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { useBillsApi, type Bill, type ReceiptLink } from "./api";

/**
 * Print or share an issued bill (M6d-P4; FR-BIL-04; billing R46, R48): the PDF opens in a new tab
 * for the browser to print, and *Show QR for the patient* gives the receipt link to scan or copy.
 * Opening it asks the patient for the last 4 digits of their phone. WhatsApp sending waits for an
 * approved template (D6).
 */
export function ReceiptPanel({ bill }: Readonly<{ bill: Bill }>) {
  const api = useBillsApi();
  const { endSession } = useSession();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<ReceiptLink | undefined>(undefined);
  const [qr, setQr] = useState<string | undefined>(undefined);
  const [copied, setCopied] = useState("");

  function print() {
    const tab = window.open("", "_blank");
    setBusy(true);
    setError(null);
    api.receipt(bill.id).then(
      (blob) => {
        const url = URL.createObjectURL(blob);
        if (tab !== null) tab.location.href = url;
        else {
          const a = document.createElement("a");
          a.href = url;
          a.download = `bill-${bill.number ?? bill.id}.pdf`;
          a.click();
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
        setBusy(false);
      },
      (failure: unknown) => {
        tab?.close();
        setBusy(false);
        if (!endSession(failure)) setError(failure);
      },
    );
  }

  async function share(reset = false) {
    setError(null);
    try {
      const info = reset ? await api.resetLink(bill.id) : await api.link(bill.id);
      setLink(info);
      setQr(await QRCode.toDataURL(info.url, { margin: 1, width: 192, errorCorrectionLevel: "M" }));
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    }
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied("Link copied.");
    } catch {
      setCopied("Could not copy here: select the link and copy it.");
    }
  }

  return (
    <section aria-labelledby="receipt-heading" className="space-y-3 rounded-card border border-line bg-white p-4 shadow-card sm:p-5">
      <h2 id="receipt-heading" className="flex items-center gap-2 text-lg font-bold text-slate-900">
        <Printer aria-hidden="true" className="size-5 text-brand-700" />
        Receipt
      </h2>
      {error !== null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy} onClick={print} icon={<Printer className="size-4" />}>
          {busy ? "Preparing…" : "Print bill"}
        </Button>
        {link === undefined && (
          <Button onClick={() => void share()} icon={<QrCode className="size-4" />}>
            Show QR for the patient
          </Button>
        )}
      </div>
      {link !== undefined && (
        <div className="flex flex-wrap items-start gap-4">
          {qr !== undefined && (
            // A data: URL made here; next/image has nothing to optimise.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={qr} width={192} height={192} alt="QR code of the patient's receipt link" className="shrink-0 rounded-lg border border-line bg-white p-1 shadow-card" />
          )}
          <div className="min-w-0 flex-1 basis-56 space-y-2">
            <p className="text-slate-800">The patient scans this, or you send the link. Opening it asks for the last 4 digits of their phone.</p>
            <p className="break-all rounded-lg border border-line bg-slate-50 px-3 py-2 font-mono text-sm text-slate-900" data-testid="receipt-link">
              {link.url}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => void copy(link.url)} icon={<Copy className="size-3.5" />}>
                Copy link
              </Button>
              {link.locked && (
                <Button size="sm" onClick={() => void share(true)} icon={<LockOpen className="size-3.5" />}>
                  Unlock link
                </Button>
              )}
            </div>
            <p role="status" className="text-sm font-medium text-success">
              {copied}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
