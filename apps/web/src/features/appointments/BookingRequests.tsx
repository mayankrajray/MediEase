"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatClock, formatDayTime } from "@/lib/format/time";

import { useAppointmentApi, type StaffBookingRequest } from "./api";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly StaffBookingRequest[] }
  | { readonly status: "failed"; readonly error: unknown };

const SEX: Readonly<Record<NonNullable<StaffBookingRequest["sex"]>, string>> = {
  FEMALE: "Female",
  MALE: "Male",
  OTHER: "Other",
  UNDISCLOSED: "Prefers not to say",
};

/**
 * Online booking requests (M6b-P4, spec R22): what patients asked for through the clinic's public
 * page, oldest first, and whether each still holds its time. Reading only: accepting, declining
 * and proposing another time arrive in M6b-P5. To book a held time meanwhile, use the booking
 * drawer's "Book anyway" (R18a).
 */
export function BookingRequests() {
  const api = useAppointmentApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const dayTime = (iso: string) => formatDayTime(iso, clinic.timezone);

  useEffect(() => {
    let cancelled = false;
    api.bookingRequests().then(
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
  }, [api, attempt, endSession]);

  return (
    <section className="space-y-4">
      <PageHeader
        title="Booking requests"
        description="Times patients asked for on your clinic page. A request holds its time for a short while; it stays open until you reply."
      />
      {load.status === "loading" && (
        <>
          <p role="status" className="sr-only">
            Loading booking requests.
          </p>
          <Skeleton className="h-40" />
        </>
      )}
      {load.status === "failed" && <ErrorNotice error={load.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {load.status === "ready" && load.items.length === 0 && (
        <EmptyState title="No open requests">Requests from your clinic page appear here and in your notifications.</EmptyState>
      )}
      {load.status === "ready" && load.items.length > 0 && (
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <caption className="sr-only">Open booking requests, oldest first</caption>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>Asked for</th>
                <th role="columnheader" scope="col" className={TH}>Patient</th>
                <th role="columnheader" scope="col" className={TH}>Phone</th>
                <th role="columnheader" scope="col" className={TH}>Reason</th>
                <th role="columnheader" scope="col" className={TH}>Hold</th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {load.items.map((r) => (
                <tr key={r.id} role="row" className={TR}>
                  <td role="cell" className={TD} data-label="Asked for">
                    {dayTime(r.starts_at)}
                    <span className="block text-sm text-slate-700">{r.doctor_name}</span>
                  </td>
                  <td role="cell" className={TD} data-label="Patient">
                    {r.full_name}
                    {(r.age_years !== null || r.sex !== null) && (
                      <span className="block text-sm text-slate-700">
                        {[r.age_years === null ? null : `${r.age_years} years`, r.sex === null ? null : SEX[r.sex]].filter((p) => p !== null).join(", ")}
                      </span>
                    )}
                  </td>
                  <td role="cell" className={TD} data-label="Phone">
                    <a href={`tel:${r.phone_e164}`} className="text-brand-800 underline">
                      {r.phone_e164}
                    </a>
                  </td>
                  <td role="cell" className={TD} data-label="Reason">
                    {r.reason ?? "—"}
                  </td>
                  <td role="cell" className={TD} data-label="Hold">
                    {r.holding ? (
                      <StatusBadge tone="waiting">Held until {formatClock(r.hold_expires_at, clinic.timezone)}</StatusBadge>
                    ) : r.hold_overridden ? (
                      <StatusBadge tone="neutral">Booked over</StatusBadge>
                    ) : (
                      <StatusBadge tone="neutral">Hold ended</StatusBadge>
                    )}
                    <span className="block text-sm text-slate-700">Reply by {formatClock(r.respond_by, clinic.timezone)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
