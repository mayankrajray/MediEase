"use client";

import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Logo } from "@/components/ui/Logo";
import { apiGetConditional, type GetResponse } from "@/lib/api/client";
import { startPolling } from "@/lib/api/poll";
import { liveWords } from "@/lib/i18n/patient-notifications";
import { type PortalLanguage, portalStrings, portalTime } from "@/lib/i18n/portal";

import { type LiveProblem, liveProblemOf, liveProblemText } from "./problems";

export type LiveQueue = GetResponse<"/api/v1/public/queue/{token}">;

/** R72: the page asks again every 20 s while it is visible. */
export const LIVE_INTERVAL_MS = 20_000;

/**
 * The patient's live place in the queue (M6b-P6; spec R69-R72, AC27): their token or time, how
 * many are still ahead, who is being seen now, and what to do. Only the fields of `LiveQueue`
 * (R70): no names, no phone, no reason. Rendered first on the server; then it polls with the
 * ETag, so an unchanged queue costs a 304. An expired or unknown link stops asking.
 */
export function LiveQueueView({
  token,
  language,
  initial,
  initialEtag,
}: Readonly<{ token: string; language: PortalLanguage; initial: LiveQueue; initialEtag: string | undefined }>) {
  const words = liveWords(language);
  const s = portalStrings(language);
  const [view, setView] = useState(initial);
  const [updatedAt, setUpdatedAt] = useState<string | undefined>(undefined);
  const [problem, setProblem] = useState<LiveProblem | undefined>(undefined);

  useEffect(() => {
    let stopped = false;
    const stop = startPolling<LiveQueue>({
      intervalMs: LIVE_INTERVAL_MS,
      ...(initialEtag === undefined ? {} : { initialEtag }),
      load: (etag, signal) => apiGetConditional("/api/v1/public/queue/{token}", etag, { pathParams: { token }, signal }),
      onData: (next) => {
        setView(next);
        setProblem(undefined);
        setUpdatedAt(new Date().toISOString());
      },
      onError: (error) => {
        const found = liveProblemOf(error);
        setProblem(found);
        if ((found === "expired" || found === "invalid") && !stopped) {
          stopped = true;
          stop();
        }
      },
    });
    return () => {
      stopped = true;
      stop();
    };
  }, [token, initialEtag]);

  const time = (iso: string) => portalTime(iso, view.timezone, s);
  const final = problem === "expired" || problem === "invalid";
  const seeing =
    view.now_seeing_token !== null
      ? words.nowSeeing(words.token(view.now_seeing_token))
      : view.now_seeing_slot !== null
        ? words.nowSeeing(time(view.now_seeing_slot))
        : words.nobodyYet;
  // M7c-P7 (M4): the semantic tones; the words of the state carry it, the colour repeats it.
  const tone =
    view.state === "YOUR_TURN"
      ? "border-success-line bg-success-soft"
      : view.state === "CANCELLED"
        ? "border-danger-line bg-danger-soft"
        : "border-line bg-surface";

  return (
    <main lang={language} className="mx-auto min-h-screen max-w-md space-y-4 bg-canvas px-4 pb-10 pt-4 text-base text-slate-900">
      <div className="flex items-center justify-between gap-3">
        <Logo />
        <a
          href={`?lang=${language === "hi" ? "en" : "hi"}`}
          lang={language === "hi" ? "en" : "hi"}
          aria-label={words.switchLabel}
          className="inline-flex min-h-11 shrink-0 items-center rounded-lg border border-slate-300 bg-surface px-3 text-sm font-semibold text-slate-800 transition-colors hover:border-brand-300 hover:bg-brand-50"
        >
          {words.switchTo}
        </a>
      </div>
      <div>
        <h1 className="heading-4 text-slate-900">{words.heading}</h1>
        <p className="mt-1 text-slate-700">
          {view.clinic_name} · {view.doctor_name}
        </p>
      </div>

      {final ? (
        <Alert tone="danger" role="alert">
          <span className="font-semibold">{liveProblemText(words, problem ?? "unavailable")}</span>
        </Alert>
      ) : (
        <>
          <section aria-labelledby="live-place" className={`space-y-3 rounded-card border p-5 shadow-card ${tone}`}>
            <h2 id="live-place" className="text-3xl font-bold tabular-nums text-slate-900">
              {view.token_number !== null
                ? words.yourToken(view.token_number)
                : view.slot_start !== null
                  ? words.yourSlot(time(view.slot_start))
                  : words.heading}
            </h2>
            {/* Polite: the place changes every few minutes; a screen reader hears it without a jump. */}
            <div aria-live="polite" className="space-y-1">
              <p className="text-xl font-semibold">{words.states[view.state]}</p>
              {view.state === "WAITING" && <p className="text-lg tabular-nums text-slate-800">{words.ahead(view.ahead)}</p>}
              {(view.state === "WAITING" || view.state === "NOT_STARTED") && <p className="text-slate-700">{seeing}</p>}
              {view.state === "NOT_STARTED" && <p className="text-slate-700">{words.startsAt(time(view.session_starts_at))}</p>}
            </div>
          </section>
          {problem !== undefined && (
            <Alert tone="warning" role="status">
              {problem === "rate" ? words.rateLimited : words.offline}
            </Alert>
          )}
          <p className="text-sm text-slate-700">
            {words.refreshNote}
            {updatedAt !== undefined && ` ${words.updated(time(updatedAt))}`}
          </p>
        </>
      )}
    </main>
  );
}
