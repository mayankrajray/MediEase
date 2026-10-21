"use client";

import { useState, type FormEvent } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format/time";

import { usePatientApi } from "./api";
import { PAT_NOT_OPTED_OUT, PAT_OPTED_OUT, type Patient } from "./fields";

type Mode = "view" | "record" | "opt-in" | "confirm-opt-out";

/** "Not asked yet", "Declined", or what was allowed: the three consent states (spec R6). */
export function consentSummary(patient: Patient): string {
  if (patient.opted_out) return "Opted out: no messages";
  if (patient.consent_recorded_at === null) return "Not asked yet";
  if (!patient.whatsapp_consent && !patient.sms_consent) return "Declined";
  const allowed = [patient.whatsapp_consent ? "WhatsApp" : null, patient.sms_consent ? "SMS" : null].filter(Boolean);
  return `Allowed: ${allowed.join(" and ")}`;
}

/**
 * Consent, opt-out and opt-in as three separate actions (FR-PAT-05, FR-MSG-05, AC5).
 * While a patient is opted out there is no consent form at all, only "Opt back in",
 * which takes the new answer: no checkbox can undo an opt-out. For a minor the
 * guardian answers (FR-PAT-06), and the script says so.
 */
export function ConsentPanel({
  patient,
  timeZone,
  onChange,
}: {
  patient: Patient;
  timeZone: string;
  onChange: (patient: Patient) => void;
}) {
  const { endSession } = useSession();
  const api = usePatientApi();
  const [mode, setMode] = useState<Mode>("view");
  const [whatsapp, setWhatsapp] = useState(patient.whatsapp_consent);
  const [sms, setSms] = useState(patient.sms_consent);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function act(call: () => Promise<Patient>) {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await call();
      onChange(updated);
      setMode("view");
    } catch (failure) {
      if (endSession(failure)) return;
      setError(failure);
      // The screen was stale (someone else opted the patient out or in): show the
      // reason and bring the buttons up to date, so the right next action is offered.
      if (failure instanceof ApiError && (failure.code === PAT_OPTED_OUT || failure.code === PAT_NOT_OPTED_OUT)) {
        setMode("view");
        api.get(patient.id).then(onChange, () => undefined);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void act(() =>
      mode === "opt-in" ? api.optIn(patient.id, whatsapp, sms) : api.recordConsent(patient.id, whatsapp, sms),
    );
  }

  const who = patient.is_minor ? "the parent or guardian" : "the patient";
  const button =
    "rounded px-4 py-2 font-semibold disabled:cursor-not-allowed disabled:bg-slate-500";

  return (
    <section aria-labelledby="consent-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <h2 id="consent-heading" className="text-lg font-bold">
        Messages
      </h2>
      <p className="font-medium" data-testid="consent-summary">
        {consentSummary(patient)}
      </p>
      {patient.opted_out && patient.opted_out_at !== null && (
        <p className="text-slate-800">Opted out on {formatDateTime(patient.opted_out_at, timeZone)}.</p>
      )}
      {!patient.opted_out && patient.consent_recorded_at !== null && (
        <p className="text-sm text-slate-700">Recorded {formatDateTime(patient.consent_recorded_at, timeZone)}.</p>
      )}

      {error !== null && <ErrorNotice error={error} />}

      {mode === "record" || mode === "opt-in" ? (
        <form onSubmit={onSubmit} className="space-y-3">
          <p className="rounded-lg bg-slate-100 p-3">
            Ask {who}: “May the clinic send you appointment and prescription messages on WhatsApp? And by SMS?
            You can ask us to stop at any time.”
          </p>
          <label className="flex min-h-10 items-center gap-3 font-medium">
            <input type="checkbox" className="size-5 accent-brand-700" checked={whatsapp} onChange={(event) => setWhatsapp(event.target.checked)} />
            WhatsApp: yes
          </label>
          <label className="flex min-h-10 items-center gap-3 font-medium">
            <input type="checkbox" className="size-5 accent-brand-700" checked={sms} onChange={(event) => setSms(event.target.checked)} />
            SMS: yes
          </label>
          <p className="text-sm text-slate-700">Leave both unticked if the answer is no: that is recorded as declined.</p>
          <div className="flex gap-3">
            <button type="submit" disabled={submitting} className={`${button} bg-brand-700 text-white hover:bg-brand-800`}>
              {submitting ? "Saving…" : mode === "opt-in" ? "Opt back in" : "Save answer"}
            </button>
            <button
              type="button"
              onClick={() => setMode("view")}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-4 py-2 font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : mode === "confirm-opt-out" ? (
        <div className="space-y-3">
          <p>Stop all messages to this {patient.is_minor ? "patient's guardian" : "patient"}? They can opt back in later.</p>
          <div className="flex gap-3">
            <button
              type="button"
              disabled={submitting}
              onClick={() => void act(() => api.optOut(patient.id))}
              className={`${button} bg-red-700 text-white hover:bg-red-800`}
            >
              {submitting ? "Saving…" : "Yes, opt out"}
            </button>
            <button
              type="button"
              onClick={() => setMode("view")}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-4 py-2 font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          {patient.opted_out ? (
            <button
              type="button"
              onClick={() => {
                setWhatsapp(false);
                setSms(false);
                setMode("opt-in");
              }}
              className="rounded-lg border border-brand-700 px-4 py-2 font-medium text-brand-800 hover:bg-brand-50"
            >
              Opt back in
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={() => {
                  setWhatsapp(patient.whatsapp_consent);
                  setSms(patient.sms_consent);
                  setMode("record");
                }}
                className="rounded-lg border border-brand-700 px-4 py-2 font-medium text-brand-800 hover:bg-brand-50"
              >
                {patient.consent_recorded_at === null ? "Record consent" : "Change consent"}
              </button>
              <button
                type="button"
                onClick={() => setMode("confirm-opt-out")}
                className="rounded-lg border border-red-800 px-4 py-2 font-medium text-red-900 hover:bg-red-50"
              >
                Opt out of all messages
              </button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
