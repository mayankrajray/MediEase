"use client";

import { CalendarClock, History, Inbox, Phone } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Segmented } from "@/components/ui/Segmented";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatusMessage } from "@/components/ui/StatusMessage";
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
        <Segmented
          label="Which requests"
          value={state}
          onChange={setState}
          options={[
            { value: "open", label: "Open" },
            { value: "answered", label: "Answered" },
          ]}
        />
        {current.status === "ready" && (
          <p className="text-sm tabular-nums text-slate-700">
            {current.inbox.open_count} open · {current.inbox.expired_7d} expired unanswered in the last 7 days
          </p>
        )}
      </div>
      <StatusMessage message={message} loading={current.status === "loading" ? "Loading booking requests." : undefined} />
      {current.status === "loading" && <ListSkeleton label="" rows={3} />}
      {current.status === "failed" && <ErrorNotice error={current.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {current.status === "ready" && current.inbox.items.length === 0 && (
        <EmptyState
          icon={state === "open" ? <Inbox className="size-5" /> : <History className="size-5" />}
          title={state === "open" ? "No open requests" : "Nothing answered in the last 7 days"}
        >
          {state === "open" ? "You're all caught up. " : ""}Requests from your clinic page appear here and in your notifications.
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
              {current.inbox.items.map((r) => {
                const about = [r.age_years === null ? null : `${r.age_years} years`, r.sex === null ? null : SEX[r.sex]].filter((p) => p !== null).join(", ");
                return (
                  // M7c-P7 (M4 phone fix): one markup. From 768 px a table row; below it a card
                  // built for a phone: who (name, age, record, a phone link big enough to tap),
                  // then when and why, then the hold, then the actions full width. No column
                  // names on the phone: each part says what it is, so nothing is squeezed into
                  // a narrow second column, and every long word wraps inside the card.
                  <tr key={r.id} role="row" className={cx(TR, "max-md:flex max-md:flex-col max-md:gap-3 max-md:p-4")}>
                    <td role="cell" className={cx(TD, "max-md:order-2")} data-label="">
                      <span className="flex items-start gap-2 font-medium tabular-nums text-slate-900">
                        <CalendarClock aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500 md:hidden" />
                        <span className="min-w-0">
                          {dayTime(r.starts_at)}
                          <span className="block text-sm font-normal text-slate-700">{r.doctor_name}</span>
                          {r.original_starts_at !== null && (
                            <span className="block text-sm font-normal text-slate-700">First asked: {dayTime(r.original_starts_at)}</span>
                          )}
                        </span>
                      </span>
                    </td>
                    <td role="cell" className={cx(TD, "max-md:order-1")} data-label="">
                      <span className="block break-words font-semibold text-slate-900 max-md:text-base">{r.full_name}</span>
                      {(about !== "" || r.patient_code !== null) && (
                        <span className="block text-sm text-slate-700">
                          {about}
                          {about !== "" && r.patient_code !== null && " · "}
                          {r.patient_code !== null && <span className="tabular-nums">Record {r.patient_code}</span>}
                        </span>
                      )}
                      <a
                        href={`tel:${r.phone_e164}`}
                        className="mt-1 inline-flex min-h-6 items-center gap-1.5 rounded text-sm font-medium tabular-nums text-brand-800 underline underline-offset-2 hover:text-brand-900 max-md:min-h-11"
                      >
                        <Phone aria-hidden="true" className="size-4 shrink-0" />
                        {r.phone_e164}
                      </a>
                    </td>
                    <td role="cell" className={cx(TD, "max-md:order-3", r.reason === null && "max-md:hidden")} data-label="">
                      <span className="text-sm text-slate-700 md:hidden">Reason: </span>
                      <span className="break-words text-slate-900 max-md:text-sm">{r.reason ?? "—"}</span>
                    </td>
                    <td role="cell" className={cx(TD, "max-md:order-4")} data-label="">
                      {state === "open" ? (
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 md:block">
                          {r.status === "PROPOSED" ? (
                            <StatusBadge tone="active">Waiting for the patient</StatusBadge>
                          ) : r.holding ? (
                            <StatusBadge tone="waiting">Held until {formatClock(r.hold_expires_at, clinic.timezone)}</StatusBadge>
                          ) : (
                            <StatusBadge tone="neutral">{r.hold_overridden ? "Booked over" : "Hold ended"}</StatusBadge>
                          )}
                          <span className="block text-sm tabular-nums text-slate-700 md:mt-1">Reply by {formatClock(r.respond_by, clinic.timezone)}</span>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <StatusBadge tone={r.status === "ACCEPTED" ? "done" : r.status === "EXPIRED" ? "missed" : "neutral"}>{OUTCOME[r.status]}</StatusBadge>
                          {r.decline_reason !== null && r.decline_reason !== "PATIENT_DECLINED" && r.decline_reason !== "CLINIC_UNAVAILABLE" && (
                            <span className="block text-sm text-slate-700">{DECLINE_LABELS[r.decline_reason]}</span>
                          )}
                          {r.decline_reason === "PATIENT_DECLINED" && <span className="block text-sm text-slate-700">The patient said no thanks</span>}
                          {r.decline_reason === "CLINIC_UNAVAILABLE" && (
                            <span className="block text-sm text-slate-700">Withdrawn while the clinic was suspended</span>
                          )}
                          {r.decline_note !== null && <span className="block break-words text-sm text-slate-700">Note: {r.decline_note}</span>}
                          {(r.answered_by_name !== null || r.decided_at !== null) && (
                            <span className="block text-sm text-slate-700">
                              {r.answered_by_name !== null ? `By ${r.answered_by_name}` : ""}
                              {r.decided_at !== null ? ` · ${dayTime(r.decided_at)}` : ""}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    {state === "open" && (
                      <td role="cell" className={cx(TD, "max-md:order-5 max-md:border-t max-md:border-line max-md:pt-3 md:text-right")} data-label="">
                        {/* Phone: Accept full width on top (the main answer), the other two side by side. */}
                        <div className="grid grid-cols-2 gap-2 md:flex md:flex-nowrap md:justify-end">
                          {r.status === "PENDING" && (
                            <>
                              <Button
                                variant="primary"
                                className="col-span-2 max-md:min-h-11 md:min-h-8 md:px-3 md:py-1 md:text-sm"
                                onClick={() => setOpen({ kind: "accept", request: r })}
                                aria-label={`Accept ${r.full_name}'s request`}
                              >
                                Accept
                              </Button>
                              <Button
                                className="max-md:min-h-11 max-md:px-2 md:min-h-8 md:px-3 md:py-1 md:text-sm"
                                onClick={() => setOpen({ kind: "propose", request: r })}
                                aria-label={`Propose another time to ${r.full_name}`}
                              >
                                <span className="md:hidden">Propose time</span>
                                <span className="max-md:hidden">Propose another time</span>
                              </Button>
                            </>
                          )}
                          <Button
                            variant="ghost"
                            className={cx(
                              "text-danger hover:bg-danger-soft hover:text-danger max-md:min-h-11 max-md:border max-md:border-danger-line md:min-h-8 md:px-3 md:py-1 md:text-sm",
                              r.status !== "PENDING" && "col-span-2",
                            )}
                            onClick={() => setOpen({ kind: "decline", request: r })}
                            aria-label={`Decline ${r.full_name}'s request`}
                          >
                            Decline
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
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
