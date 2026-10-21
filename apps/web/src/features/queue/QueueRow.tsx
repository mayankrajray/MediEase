"use client";

import Link from "next/link";

import { useClinic } from "@/features/shell/ClinicGate";
import { Menu, type MenuItem } from "@/components/Menu";
import { buttonClasses } from "@/components/ui/Button";
import { LIST_ITEM } from "@/components/ui/LayoutMotion";
import { m } from "@/components/ui/Motion";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TD, TR } from "@/components/ui/table";
import { useNow } from "@/components/useNow";
import { STATUS_LABELS, STATUS_TONES, placeText, type AppointmentStatus } from "@/features/appointments/api";
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
  /** M4-P6: the signed-in doctor's own row, which opens the consultation screen. */
  readonly isMine?: (entry: QueueEntry) => boolean;
  readonly onOpen?: (entry: QueueEntry) => void;
  /** M4-P6, spec D6: print the row's issued prescription (RX_PRINT). */
  readonly canPrint?: boolean;
  readonly onPrint?: (rxId: string) => void;
}

/**
 * One appointment on the board (FR-QUE-01): place, patient, status, wait, the next step as a
 * single button, and the rest in a menu. State is text, not colour alone. M6-P2: a card on a phone
 * (decision 2A), and it glides to its new place when the queue reorders (decision 4A).
 */
export function QueueRow({ entry, session, actions }: { entry: QueueEntry; session: QueueSession; actions: RowActions }) {
  const clinic = useClinic();
  const now = useNow();
  const who = entry.patient.full_name;
  const status = entry.status;
  const mine = actions.isMine?.(entry) === true && actions.onOpen !== undefined;
  // The doctor's own patient in consultation opens the screen; completing is in the menu.
  const step = mine && status === "IN_CONSULTATION" ? undefined : NEXT_STEP[status];
  const started = new Date(entry.slot_start ?? session.starts_at).getTime() <= now;

  const menu: MenuItem[] = [];
  if (mine && status === "IN_CONSULTATION" && actions.canMove) {
    menu.push({ label: "Mark completed", onSelect: () => actions.onStep(entry, "COMPLETED") });
  }
  if (mine && status === "COMPLETED" && entry.visit_id !== null) {
    menu.push({ label: "Open consultation", onSelect: () => actions.onOpen?.(entry) });
  }
  if (actions.canPrint === true && entry.prescription !== null && actions.onPrint !== undefined) {
    const rxId = entry.prescription.id;
    menu.push({ label: "Print prescription", onSelect: () => actions.onPrint?.(rxId) });
  }
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
    <m.tr {...LIST_ITEM} role="row" className={`${TR} align-middle`}>
      <td role="cell" data-label="Place" className={`${TD} font-semibold tabular-nums`}>
        {placeText(entry, (iso) => formatClock(iso, clinic.timezone))}
      </td>
      <td role="cell" data-label="Patient" className={TD}>
        <div>
        <Link href={patientPath(entry.patient.id)} className="font-semibold text-brand-800 underline-offset-2 hover:underline">
          {who}
        </Link>
        <span className="block text-sm text-slate-700">
          {entry.patient.code} · {entry.patient.age_years} y{entry.source === "WALK_IN" ? " · walk-in" : ""}
        </span>
        </div>
      </td>
      <td role="cell" data-label="Status" className={TD}>
        <div>
        <StatusBadge tone={STATUS_TONES[status]}>{STATUS_LABELS[status]}</StatusBadge>
        {entry.prescription !== null && <span className="mt-1 block text-sm font-medium text-slate-800">Prescription issued</span>}
        </div>
      </td>
      <td role="cell" data-label={waited === null ? "" : "Waiting"} className={`${TD} text-slate-800`}>
        {waited === null ? "" : formatDuration(waited)}
      </td>
      <td role="cell" data-label="" className={TD}>
        <div className="flex flex-wrap items-center gap-2 pt-1 md:justify-end md:pt-0">
          {mine && status === "IN_CONSULTATION" && (
            <button
              type="button"
              aria-label={`Open ${who}'s consultation`}
              disabled={actions.busy}
              onClick={() => actions.onOpen?.(entry)}
              className={`${buttonClasses("primary")} min-w-24`}
            >
              Open
            </button>
          )}
          {step !== undefined && actions.canMove && (status !== "NO_SHOW" || started) && (
            <button
              type="button"
              aria-label={step.name(who)}
              disabled={actions.busy}
              onClick={() => actions.onStep(entry, step.to)}
              className={`${buttonClasses("primary")} min-w-24`}
            >
              {step.text}
            </button>
          )}
          {menu.length > 0 && <Menu label={`More actions for ${who}`} items={menu} />}
        </div>
      </td>
    </m.tr>
  );
}
