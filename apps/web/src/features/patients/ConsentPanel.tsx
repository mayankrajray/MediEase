"use client";

import { MessageSquareQuote } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { CHOICE_CARD, CHOICE_INPUT } from "@/components/ui/Field";
import { StatusBadge } from "@/components/ui/StatusBadge";

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
  const summary = consentSummary(patient);
  const tone = patient.opted_out ? "missed" : patient.consent_recorded_at === null ? "waiting" : summary === "Declined" ? "neutral" : "done";

  return (
    <section aria-labelledby="consent-heading" className="space-y-3 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
      <h2 id="consent-heading" className="heading-6 text-slate-900">
        Messages
      </h2>
      {/* M7c-P7 (M5): the consent state as a badge in words; when it was recorded under it. */}
      <p data-testid="consent-summary">
        <StatusBadge tone={tone}>{summary}</StatusBadge>
      </p>
      {patient.opted_out && patient.opted_out_at !== null && (
        <p className="text-sm text-slate-700">Opted out on {formatDateTime(patient.opted_out_at, timeZone)}.</p>
      )}
      {!patient.opted_out && patient.consent_recorded_at !== null && (
        <p className="text-sm text-slate-700">Recorded {formatDateTime(patient.consent_recorded_at, timeZone)}.</p>
      )}

      {error !== null && <ErrorNotice error={error} />}

      {mode === "record" || mode === "opt-in" ? (
        <form onSubmit={onSubmit} className="space-y-3">
          <p className="flex gap-2 rounded-lg border border-line bg-surface-muted p-3 text-slate-800">
            <MessageSquareQuote aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
            <span>
              Ask {who}: “May the clinic send you appointment and prescription messages on WhatsApp? And by SMS?
              You can ask us to stop at any time.”
            </span>
          </p>
          <label className={CHOICE_CARD}>
            <input type="checkbox" className={CHOICE_INPUT} checked={whatsapp} onChange={(event) => setWhatsapp(event.target.checked)} />
            <span className="font-medium">WhatsApp: yes</span>
          </label>
          <label className={CHOICE_CARD}>
            <input type="checkbox" className={CHOICE_INPUT} checked={sms} onChange={(event) => setSms(event.target.checked)} />
            <span className="font-medium">SMS: yes</span>
          </label>
          <p className="text-sm text-slate-700">Leave both unticked if the answer is no: that is recorded as declined.</p>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" loading={submitting}>
              {submitting ? "Saving…" : mode === "opt-in" ? "Opt back in" : "Save answer"}
            </Button>
            <Button onClick={() => setMode("view")} disabled={submitting}>
              Cancel
            </Button>
          </div>
        </form>
      ) : mode === "confirm-opt-out" ? (
        <div className="space-y-3 rounded-lg border border-danger-line bg-danger-soft p-3">
          <p className="font-medium text-slate-900">
            Stop all messages to this {patient.is_minor ? "patient's guardian" : "patient"}? They can opt back in later.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" loading={submitting} onClick={() => void act(() => api.optOut(patient.id))}>
              {submitting ? "Saving…" : "Yes, opt out"}
            </Button>
            <Button onClick={() => setMode("view")} disabled={submitting} data-autofocus>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {patient.opted_out ? (
            <Button
              onClick={() => {
                setWhatsapp(false);
                setSms(false);
                setMode("opt-in");
              }}
            >
              Opt back in
            </Button>
          ) : (
            <>
              <Button
                onClick={() => {
                  setWhatsapp(patient.whatsapp_consent);
                  setSms(patient.sms_consent);
                  setMode("record");
                }}
              >
                {patient.consent_recorded_at === null ? "Record consent" : "Change consent"}
              </Button>
              <Button variant="ghost" onClick={() => setMode("confirm-opt-out")} className="text-danger hover:bg-danger-soft hover:text-danger">
                Opt out of all messages
              </Button>
            </>
          )}
        </div>
      )}
    </section>
  );
}