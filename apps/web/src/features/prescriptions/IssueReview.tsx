"use client";

import { useEffect, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { ApiError } from "@/lib/api/client";

import { useRxApi, type PatientPage, type Prescription } from "./api";

type Lang = "en" | "hi";

/** RX_DOCTOR_INCOMPLETE names the doctor's blank fields (comma-separated, docs/ERRORS.md). */
export function issueMessage(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || error.code !== "RX_DOCTOR_INCOMPLETE") return undefined;
  const raw = error.details["fields"];
  const fields = (typeof raw === "string" ? raw.split(",") : Array.isArray(raw) ? raw.map(String) : [])
    .map((f) => f.trim().replaceAll("_", " "))
    .filter((f) => f !== "");
  return fields.length === 0
    ? `${error.message}. Ask the clinic owner to complete the doctor's profile.`
    : `The doctor's profile is missing: ${fields.join(", ")}. Ask the clinic owner to complete it, then issue again.`;
}

/**
 * Review and issue (spec §6, decision 3A): exactly what the patient will see, from the API's
 * own phrasebook, in English or Hindi, then Issue. Everything waiting is saved first, so the
 * preview and the issue are of the same revision.
 */
export function IssueReview({
  language,
  prepare,
  onIssued,
  onClose,
}: Readonly<{
  language: Lang;
  /** Saves what is waiting; the draft to issue, or undefined when saving failed. */
  prepare: () => Promise<{ readonly rxId: string; readonly revision: number } | undefined>;
  onIssued: (rx: Prescription) => void;
  onClose: () => void;
}>) {
  const api = useRxApi();
  const { endSession } = useSession();
  const [lang, setLang] = useState<Lang>(language);
  const [target, setTarget] = useState<{ rxId: string; revision: number } | null | undefined>(undefined);
  const [pages, setPages] = useState<Partial<Record<Lang, PatientPage>>>({});
  const page = pages[lang];
  const [error, setError] = useState<unknown>(undefined);
  const [issuing, setIssuing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void prepare().then((ready) => {
      if (!cancelled) setTarget(ready ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [prepare]);

  useEffect(() => {
    if (target === undefined || target === null || page !== undefined) return;
    let cancelled = false;
    api.preview(target.rxId, lang).then(
      (found) => {
        if (!cancelled) setPages((p) => ({ ...p, [lang]: found }));
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, target, lang, page, endSession]);

  function issue() {
    if (target === undefined || target === null) return;
    setIssuing(true);
    setError(undefined);
    api.issue(target.rxId, target.revision).then(onIssued, (failure: unknown) => {
      setIssuing(false);
      if (!endSession(failure)) setError(failure);
    });
  }

  const special = issueMessage(error);

  return (
    <Dialog title="Review and issue" onClose={onClose}>
      <div role="group" aria-label="Preview language" className="flex gap-2">
        {(["en", "hi"] as const).map((l) => (
          <button
            key={l}
            type="button"
            {...(l === language ? { "data-autofocus": true } : {})}
            aria-pressed={lang === l}
            onClick={() => setLang(l)}
            className="rounded-lg border border-slate-400 px-3 py-1 aria-pressed:bg-brand-700 aria-pressed:text-white"
          >
            {l === "en" ? "English" : "हिन्दी (Hindi)"}
          </button>
        ))}
      </div>
      {target === null && <p role="alert">The prescription could not be saved, so it cannot be issued yet. Close this and check the message.</p>}
      {target !== null && page === undefined && error === undefined && <p role="status">Preparing the preview…</p>}
      {page !== undefined && <Preview page={page} />}
      {error !== undefined && <ErrorNotice error={error} {...(special === undefined ? {} : { message: special })} />}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-4 py-2 font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none">
          Keep editing
        </button>
        <button
          type="button"
          disabled={page === undefined || issuing}
          onClick={issue}
          className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
        >
          {issuing ? "Issuing…" : "Issue"}
        </button>
      </div>
    </Dialog>
  );
}

/** The patient page's content (the same model as `/p/<token>`), framed as a preview. */
function Preview({ page }: Readonly<{ page: PatientPage }>) {
  return (
    <section lang={page.language} aria-label="What the patient will see" className="max-h-[50vh] space-y-3 overflow-y-auto rounded-card border border-slate-200 bg-white p-3">
      <div>
        <p className="font-bold">{page.clinic_name}</p>
        <p className="font-semibold">{page.doctor_name}</p>
        {page.doctor_lines.map((line) => (
          <p key={line} className="text-sm text-slate-700">
            {line}
          </p>
        ))}
        <p className="text-sm">
          <span className="font-semibold">{page.issued_on.label}:</span> {page.issued_on.value}
        </p>
      </div>
      {page.updated_note !== null && <p className="rounded-lg border border-amber-700 bg-amber-50 p-2 font-semibold">{page.updated_note}</p>}
      {page.medicines.length > 0 && (
        <div>
          <h3 className="font-bold">{page.medicines_heading}</h3>
          <ol className="space-y-2">
            {page.medicines.map((m) => (
              <li key={m.number} className="rounded-lg border border-slate-200 p-2">
                <p className="font-bold">
                  {m.number}. {m.name}
                  {m.form_strength !== null && <span className="font-normal"> ({m.form_strength})</span>}
                </p>
                <dl>
                  {m.fields.map((f) => (
                    <div key={f.label}>
                      <dt className="text-sm font-semibold text-slate-700">{f.label}</dt>
                      <dd>{f.value}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ol>
        </div>
      )}
      {(page.advice.length > 0 || page.advice_notes !== null) && (
        <div>
          <h3 className="font-bold">{page.advice_heading}</h3>
          {page.advice.map((a) => (
            <div key={a.heading}>
              <p className="font-semibold">{a.heading}</p>
              <ul className="list-disc pl-5">
                {a.entries.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          ))}
          {page.advice_notes !== null && (
            <p className="whitespace-pre-line">
              <span className="font-semibold">{page.advice_notes.label}:</span> {page.advice_notes.value}
            </p>
          )}
        </div>
      )}
      {page.follow_up !== null && (
        <p className="font-semibold">
          {page.follow_up.label}: {page.follow_up.value}
        </p>
      )}
    </section>
  );
}
