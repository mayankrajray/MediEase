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
import { clinicToday } from "@/features/patients/fields";
import { formatClock, formatDay } from "@/lib/format/time";

import { useAppointmentApi, type BookingToMove, type Doctor } from "./api";
import { BookDrawer } from "./BookDrawer";
import { CancelDialog } from "./CancelDialog";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly BookingToMove[]; readonly doctors: readonly Doctor[] }
  | { readonly status: "failed"; readonly error: unknown };

type Open =
  | { readonly kind: "reschedule"; readonly item: BookingToMove }
  | { readonly kind: "cancel"; readonly item: BookingToMove };

const REASONS: Record<BookingToMove["reason"], string> = {
  LEAVE: "Doctor on leave",
  SCHEDULE_CHANGED: "Schedule changed",
};

const who = (item: BookingToMove) => `${item.patient.first_name} · ${item.patient.code}`;

/**
 * Bookings to move (M6a-P8, FR-APT-09, decision 6A): the patients still booked in sessions that
 * leave or a schedule change closed, from today on. Each can be rescheduled (the booking drawer,
 * the patient and doctor chosen) or cancelled ("Doctor unavailable" preselected, which tells the
 * patient on WhatsApp when they agreed to messages). Shows who and where only.
 */
export function BookingsToMove() {
  const api = useAppointmentApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState<Open | undefined>(undefined);
  const [message, setMessage] = useState("");
  const clock = (iso: string) => formatClock(iso, clinic.timezone);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.toMove(), api.doctors()]).then(
      ([items, doctors]) => {
        if (!cancelled) setLoad({ status: "ready", items, doctors });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, attempt, endSession]);

  function done(text: string) {
    setOpen(undefined);
    setMessage(text);
    setAttempt((n) => n + 1);
  }

  const doctors = load.status === "ready" ? load.doctors : [];
  const doctorName = (id: string) => doctors.find((d) => d.id === id)?.display_name ?? "";
  const place = (item: BookingToMove) =>
    item.token_number !== null ? `token ${item.token_number}` : clock(item.slot_start ?? item.starts_at);

  return (
    <section className="space-y-4">
      <PageHeader
        title="Bookings to move"
        description="Patients booked in sessions closed by leave or a schedule change. Move or cancel each one."
      />
      <p role="status" aria-live="polite" className={message === "" ? "sr-only" : "font-medium text-emerald-900"}>
        {load.status === "loading" ? "Loading bookings to move…" : message}
      </p>
      {load.status === "loading" && <Skeleton className="h-40" />}
      {load.status === "failed" && <ErrorNotice error={load.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {load.status === "ready" && load.items.length === 0 && (
        <EmptyState title="Nothing to move">Everyone booked is in a session that is still open.</EmptyState>
      )}
      {load.status === "ready" && load.items.length > 0 && (
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <caption className="sr-only">Bookings to move, earliest first</caption>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>When</th>
                <th role="columnheader" scope="col" className={TH}>Patient</th>
                <th role="columnheader" scope="col" className={TH}>Doctor</th>
                <th role="columnheader" scope="col" className={TH}>Why</th>
                <th role="columnheader" scope="col" className={`${TH} text-right`}>Actions</th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {load.items.map((item) => (
                <tr key={item.id} role="row" className={TR}>
                  <td role="cell" className={TD} data-label="When">
                    {formatDay(item.on_date)}, {place(item)}
                  </td>
                  <td role="cell" className={TD} data-label="Patient">
                    <span className="font-medium">{who(item)}</span>
                    <span className="block text-sm text-slate-700">{item.patient.phone_masked}</span>
                  </td>
                  <td role="cell" className={TD} data-label="Doctor">
                    {doctorName(item.doctor_id)}
                  </td>
                  <td role="cell" className={TD} data-label="Why">
                    <StatusBadge tone="missed">{REASONS[item.reason]}</StatusBadge>
                  </td>
                  <td role="cell" className={`${TD} text-right`} data-label="Actions">
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button size="sm" variant="primary" aria-label={`Reschedule ${who(item)}`} onClick={() => setOpen({ kind: "reschedule", item })}>
                        Reschedule
                      </Button>
                      <Button size="sm" variant="danger" aria-label={`Cancel ${who(item)}`} onClick={() => setOpen({ kind: "cancel", item })}>
                        Cancel
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {open?.kind === "reschedule" && (
        <BookDrawer
          target={{ kind: "reschedule", appointment: { id: open.item.id }, patientName: who(open.item) }}
          doctors={doctors.filter((d) => d.is_active)}
          doctorId={open.item.doctor_id}
          date={open.item.on_date < clinicToday(clinic.timezone) ? clinicToday(clinic.timezone) : open.item.on_date}
          onDone={(_a, text) => done(text)}
          onClose={() => setOpen(undefined)}
        />
      )}
      {open?.kind === "cancel" && (
        <CancelDialog
          appointmentId={open.item.id}
          patientName={who(open.item)}
          initialReason="DOCTOR_UNAVAILABLE"
          onDone={(_a, text) => done(text)}
          onClose={() => setOpen(undefined)}
        />
      )}
    </section>
  );
}
