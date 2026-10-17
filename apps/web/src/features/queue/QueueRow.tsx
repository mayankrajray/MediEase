"use client";

import Link from "next/link";

import { useClinic } from "@/features/shell/ClinicGate";
import { Menu, type MenuItem } from "@/components/Menu";
import { useNow } from "@/components/useNow";
import { STATUS_LABELS, placeText, type AppointmentStatus } from "@/features/appointments/api";
import { patientPath } from "@/features/patients/RegisterPatientDrawer";
import { formatClock, formatDuration } from "@/lib/format/time";

import type { Queue } from "./useQueue";

export type QueueSession = Queue["sessions"][number];
export type QueueEntry = QueueSession["appointments"][number];

/** The one next step for each status (spec §6), with the accessible name naming the patient. */
export const NEXT_STEP: Partial<
  Record<AppointmentStatus, { readonly to: AppointmentStatus; readonly text: string; readonly name: (who: string) => string }>
> = {
  BOOKED: { to: "ARRIVED", text: "Arrived", name: (who) => `Mark ${who} arrived` },
  NO_SHOW: { to: "ARRIVED", text: "Arrived", name: (who) => `Mark ${who} arrived (late)` },
  ARRIVED: { to: "IN_CONSULTATION", text: "Start", name: (who) => `Start ${who}'s consultation` },
  IN_CONSULTATION: { to: "COMPLETED", text: "Complete", name: (who) => `Complete ${who}'s consultation` },
};

export interface RowActions {
  /** Moves the queue (QUEUE_MOVE, the session's day only). */
  readonly canMove: boolean;
  /** Books, cancels and reschedules (APPOINTMENTS_MANAGE). */
  readonly canManage: boolean;
  readonly busy: boolean;
  readonly onStep: (entry: QueueEntry, to: AppointmentStatus) => void;
  readonly onNoShow: (entry: QueueEntry) => void;
  readonly onCancel: (entry: QueueEntry) => void;
  readonly onReschedule: (entry: QueueEntry) => void;
}

/**
 * One appointment on the board (FR-QUE-01): place, patient, status, wait, the next step as a
 * single button, and the rest in a menu. State is text, not colour alone.
 */
export function QueueRow({ entry, session, actions }: { entry: QueueEntry; session: QueueSession; actions: RowActions }) {
  const clinic = useClinic();
  const now = useNow();
  const who = entry.patient.full_name;
  const status = entry.status;
  const step = NEXT_STEP[status];
  const started = new Date(entry.slot_start ?? session.starts_at).getTime() <= now;

  const menu: MenuItem[] = [];
  if (actions.canMove && (status === "BOOKED" || status === "ARRIVED") && started) {
    menu.push({ label: "No-show…", onSelect: () => actions.onNoShow(entry) });
  }
  if (actions.canManage && (status === "BOOKED" || status === "ARRIVED")) {
    menu.push({ label: "Cancel…", onSelect: () => actions.onCancel(entry) });
  }
  if (actions.canManage && status === "BOOKED") {
    menu.push({ label: "Reschedule…", onSelect: () => actions.onReschedule(entry) });
  }

  const waited =
    entry.wait_minutes !== null && status === "ARRIVED" && entry.arrived_at !== null
      ? Math.max(entry.wait_minutes, Math.floor((now - new Date(entry.arrived_at).getTime()) / 60_000))
      : entry.wait_minutes;

  return (
    <tr className="border-t border-slate-200 align-middle">
      <td className="py-3 pr-3 font-semibold">{placeText(entry, (iso) => formatClock(iso, clinic.timezone))}</td>
      <td className="py-3 pr-3">
        <Link href={patientPath(entry.patient.id)} className="font-semibold text-blue-900 underline">
          {who}
        </Link>
        <span className="block text-sm text-slate-700">
          {entry.patient.code} · {entry.patient.age_years} y{entry.source === "WALK_IN" ? " · walk-in" : ""}
        </span>
      </td>
      <td className="py-3 pr-3">{STATUS_LABELS[status]}</td>
      <td className="py-3 pr-3 text-slate-800">{waited === null ? "" : formatDuration(waited)}</td>
      <td className="py-3">
        <div className="flex items-center justify-end gap-3">
          {step !== undefined && actions.canMove && (status !== "NO_SHOW" || started) && (
            <button
              type="button"
              aria-label={step.name(who)}
              disabled={actions.busy}
              onClick={() => actions.onStep(entry, step.to)}
              className="min-w-24 rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900 disabled:bg-slate-400"
            >
              {step.text}
            </button>
          )}
          {menu.length > 0 && <Menu label={`More actions for ${who}`} items={menu} />}
        </div>
      </td>
    </tr>
  );
}
