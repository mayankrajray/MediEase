"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatClock, formatDayTime } from "@/lib/format/time";

import { AcceptDrawer, DECLINE_LABELS, DeclineDialog, ProposeDrawer } from "./AnswerRequest";
import { useAppointmentApi, type BookingInbox, type StaffBookingRequest } from "./api";

type State = "open" | "answered";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly inbox: BookingInbox }
  | { readonly status: "failed"; readonly error: unknown };

type Open =
  | { readonly kind: "accept"; readonly request: StaffBookingRequest }
  | { readonly kind: "propose"; readonly request: StaffBookingRequest }
  | { readonly kind: "decline"; readonly request: StaffBookingRequest };

const SEX: Readonly<Record<NonNullable<StaffBookingRequest["sex"]>, string>> = {
  FEMALE: "Female",
  MALE: "Male",
  OTHER: "Other",
  UNDISCLOSED: "Prefers not to say",
};

const OUTCOME: Readonly<Record<StaffBookingRequest["status"], string>> = {
  PENDING: "Waiting",
  PROPOSED: "Another time offered",
  ACCEPTED: "Accepted",
  DECLINED: "Declined",
  EXPIRED: "Expired",
};

/**
 * The inbox of online booking requests (M6b-P4, P5; spec R22, R31-R47): **Open** (oldest first,
 * reply-by time and hold) with *Accept*, *Propose another time* and *Decline*; **Answered** (the
 * last 7 days: outcome, by whom, when). A proposal waits for the patient; the desk may still
 * decline it. An expired request cannot be answered.
 */
export function BookingRequests() {
  const api = useAppointmentApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [state, setState] = useState<State>("open");
  const [load, setLoad] = useState<{ key: string; value: Load }>({ key: "", value: { status: "loading" } });
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState<Open | undefined>(undefined);
  const [message, setMessage] = useState("");
  const key = `${state}|${attempt}`;
  const dayTime = (iso: string) => formatDayTime(iso, clinic.timezone);

  useEffect(() => {
    let cancelled = false;
    api.bookingRequests(state).then(
      (inbox) => {
        if (!cancelled) setLoad({ key, value: { status: "ready", inbox } });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ key, value: { status: "failed", error: failure } });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, state, key, endSession]);

  const current: Load = load.key === key ? load.value : { status: "loading" };

  function done(text: string) {
    setOpen(undefined);
    setMessage(text);
    setAttempt((n) => n + 1);
  }

  return (
    <section className="space-y-4">
      <PageHeader
        title="Booking requests"
        description="Times patients asked for on your clinic page. Accept, offer another time or decline before the reply-by time."
      />
      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Which requests" className="inline-flex gap-1 rounded-lg border border-slate-200 bg-white p-1">
          {(["open", "answered"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={state === s}
              onClick={() => setState(s)}
              className={`min-h-9 rounded-md px-3 font-medium ${state === s ? "bg-brand-700 text-white" : "text-slate-700 hover:bg-slate-100"}`}
            >
              {s === "open" ? "Open" : "Answered"}
            </button>
          ))}
        </div>
        {current.status === "ready" && (
          <p className="text-sm text-slate-700">
            {current.inbox.open_count} open · {current.inbox.expired_7d} expired unanswered in the last 7 days
          </p>
        )}
      </div>
      <p role="status" aria-live="polite" className={message === "" ? "sr-only" : "font-medium text-emerald-900"}>
        {current.status === "loading" ? "Loading booking requests." : message}
      </p>
      {current.status === "loading" && <Skeleton className="h-40" />}
      {current.status === "failed" && <ErrorNotice error={current.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {current.status === "ready" && current.inbox.items.length === 0 && (
        <EmptyState title={state === "open" ? "No open requests" : "Nothing answered in the last 7 days"}>
          Requests from your clinic page appear here and in your notifications.
        </EmptyState>
      )}
      {current.status === "ready" && current.inbox.items.length > 0 && (
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <caption className="sr-only">{state === "open" ? "Open booking requests, oldest first" : "Answered booking requests, newest first"}</caption>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>Asked for</th>
                <th role="columnheader" scope="col" className={TH}>Patient</th>
                <th role="columnheader" scope="col" className={TH}>Reason</th>
                <th role="columnheader" scope="col" className={TH}>{state === "open" ? "Hold" : "Outcome"}</th>
                {state === "open" && <th role="columnheader" scope="col" className={`${TH} text-right`}>Actions</th>}
              </tr>
            </thead>
            <tbody role="rowgroup">
              {current.inbox.items.map((r) => (
                <tr key={r.id} role="row" className={TR}>
                  <td role="cell" className={TD} data-label="Asked for">
                    {dayTime(r.starts_at)}
                    <span className="block text-sm text-slate-700">{r.doctor_name}</span>
                    {r.original_starts_at !== null && <span className="block text-sm text-slate-700">First asked: {dayTime(r.original_starts_at)}</span>}
                  </td>
                  <td role="cell" className={TD} data-label="Patient">
                    {r.full_name}
                    {(r.age_years !== null || r.sex !== null) && (
                      <span className="block text-sm text-slate-700">
                        {[r.age_years === null ? null : `${r.age_years} years`, r.sex === null ? null : SEX[r.sex]].filter((p) => p !== null).join(", ")}
                      </span>
                    )}
                    <a href={`tel:${r.phone_e164}`} className="block text-sm text-brand-800 underline">
                      {r.phone_e164}
                    </a>
                    {r.patient_code !== null && <span className="block text-sm text-slate-700">Record {r.patient_code}</span>}
                  </td>
                  <td role="cell" className={TD} data-label="Reason">
                    {r.reason ?? "—"}
                  </td>
                  <td role="cell" className={TD} data-label={state === "open" ? "Hold" : "Outcome"}>
                    {state === "open" ? (
                      <>
                        {r.status === "PROPOSED" ? (
                          <StatusBadge tone="active">Waiting for the patient</StatusBadge>
                        ) : r.holding ? (
                          <StatusBadge tone="waiting">Held until {formatClock(r.hold_expires_at, clinic.timezone)}</StatusBadge>
                        ) : (
                          <StatusBadge tone="neutral">{r.hold_overridden ? "Booked over" : "Hold ended"}</StatusBadge>
                        )}
                        <span className="block text-sm text-slate-700">Reply by {formatClock(r.respond_by, clinic.timezone)}</span>
                      </>
                    ) : (
                      <>
                        <StatusBadge tone={r.status === "ACCEPTED" ? "done" : r.status === "EXPIRED" ? "missed" : "neutral"}>{OUTCOME[r.status]}</StatusBadge>
                        {r.decline_reason !== null && r.decline_reason !== "PATIENT_DECLINED" && r.decline_reason !== "CLINIC_UNAVAILABLE" && (
                          <span className="block text-sm text-slate-700">{DECLINE_LABELS[r.decline_reason]}</span>
                        )}
                        {r.decline_reason === "PATIENT_DECLINED" && <span className="block text-sm text-slate-700">The patient said no thanks</span>}
                        {r.decline_reason === "CLINIC_UNAVAILABLE" && (
                          <span className="block text-sm text-slate-700">Withdrawn while the clinic was suspended</span>
                        )}
                        {r.decline_note !== null && <span className="block text-sm text-slate-700">Note: {r.decline_note}</span>}
                        {(r.answered_by_name !== null || r.decided_at !== null) && (
                          <span className="block text-sm text-slate-700">
                            {r.answered_by_name !== null ? `By ${r.answered_by_name}` : ""}
                            {r.decided_at !== null ? ` · ${dayTime(r.decided_at)}` : ""}
                          </span>
                        )}
                      </>
                    )}
                  </td>
                  {state === "open" && (
                    <td role="cell" className={`${TD} text-right`} data-label="Actions">
                      <div className="flex flex-wrap justify-end gap-2">
                        {r.status === "PENDING" && (
                          <>
                            <Button size="sm" variant="primary" onClick={() => setOpen({ kind: "accept", request: r })} aria-label={`Accept ${r.full_name}'s request`}>
                              Accept
                            </Button>
                            <Button size="sm" onClick={() => setOpen({ kind: "propose", request: r })} aria-label={`Propose another time to ${r.full_name}`}>
                              Propose another time
                            </Button>
                          </>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => setOpen({ kind: "decline", request: r })} aria-label={`Decline ${r.full_name}'s request`}>
                          Decline
                        </Button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open?.kind === "accept" && <AcceptDrawer request={open.request} onDone={done} onClose={() => setOpen(undefined)} />}
      {open?.kind === "propose" && <ProposeDrawer request={open.request} onDone={done} onClose={() => setOpen(undefined)} />}
      {open?.kind === "decline" && <DeclineDialog request={open.request} onDone={done} onClose={() => setOpen(undefined)} />}
    </section>
  );
}
