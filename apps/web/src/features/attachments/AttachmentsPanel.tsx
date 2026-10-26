"use client";

import { useCallback, useEffect, useState } from "react";

import { buttonClasses } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { formatDateTime } from "@/lib/format/time";

import { AttachForm } from "./AttachForm";
import { saveBlob, sizeText, useAttachmentsApi, type Attachment } from "./api";

const TYPE_LABELS: Readonly<Record<Attachment["content_type"], string>> = {
  "application/pdf": "PDF",
  "image/jpeg": "JPEG",
  "image/png": "PNG",
};

type Load =
  { readonly status: "loading" } | { readonly status: "ready"; readonly items: readonly Attachment[] } | { readonly status: "failed"; readonly error: unknown };

/**
 * A visit's reports on the consultation screen (M6d-P6; spec visit-attachments R6-R10). Shown to
 * CLINICAL_VIEW; each download is audited on the API. The uploader may delete within 24 hours;
 * the visit's doctor (`canShare`) shows a report in the patient's portal.
 */
export function AttachmentsPanel({ visitId, canShare, timeZone }: Readonly<{ visitId: string; canShare: boolean; timeZone: string }>) {
  const api = useAttachmentsApi();
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [generation, setGeneration] = useState(0);
  const [busy, setBusy] = useState<string | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);

  useEffect(() => {
    let cancelled = false;
    api.list(visitId).then(
      (items) => {
        if (!cancelled) setLoad({ status: "ready", items });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, visitId, generation, endSession]);

  const reload = useCallback(() => setGeneration((n) => n + 1), []);

  async function act(attachment: Attachment, run: () => Promise<unknown>) {
    setBusy(attachment.id);
    setError(undefined);
    try {
      await run();
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <section aria-labelledby="reports-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <h2 id="reports-heading" className="text-lg font-bold">
        Reports
      </h2>
      {load.status === "loading" && <p role="status">Loading the reports…</p>}
      {load.status === "failed" && <ErrorNotice error={load.error} onRetry={reload} />}
      {load.status === "ready" && load.items.length === 0 && <p className="text-slate-700">No reports attached.</p>}
      {error !== undefined && <ErrorNotice error={error} />}
      {load.status === "ready" && load.items.length > 0 && (
        <ul className="divide-y divide-slate-200">
          {load.items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>
                <span className="block break-all font-semibold">{a.filename}</span>
                <span className="text-sm text-slate-700">
                  {TYPE_LABELS[a.content_type]} · {sizeText(a.size_bytes)} · added {formatDateTime(a.uploaded_at, timeZone)}
                  {a.shared_with_patient && " · shared with the patient"}
                </span>
              </span>
              <span className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={busy === a.id}
                  onClick={() => void act(a, async () => saveBlob(await api.file(visitId, a.id), a.filename))}
                  className={buttonClasses("secondary")}
                >
                  Download <span className="sr-only">{a.filename}</span>
                </button>
                {canShare && (
                  <button
                    type="button"
                    disabled={busy === a.id}
                    aria-pressed={a.shared_with_patient}
                    onClick={() =>
                      void act(a, async () => {
                        await api.share(visitId, a.id, !a.shared_with_patient);
                        reload();
                      })
                    }
                    className={buttonClasses("secondary")}
                  >
                    {a.shared_with_patient ? "Stop sharing" : "Share with patient"} <span className="sr-only">{a.filename}</span>
                  </button>
                )}
                {a.can_delete && (
                  <button
                    type="button"
                    disabled={busy === a.id}
                    onClick={() =>
                      void act(a, async () => {
                        await api.remove(visitId, a.id);
                        reload();
                      })
                    }
                    className={`${buttonClasses("secondary")} text-red-800`}
                  >
                    Delete <span className="sr-only">{a.filename}</span>
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <AttachForm visitId={visitId} onAdded={reload} />
    </section>
  );
}
