"use client";

/**
 * The booking, queue and schedule calls (M3-P5), in one place. Like the patient calls, each names
 * the active clinic when the person has several and refreshes an expired session once.
 */

import { useMemo } from "react";

import type { Tone } from "@/components/ui/StatusBadge";
import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionDelete, sessionGet, sessionPatch, sessionPost, sessionPut } from "@/lib/auth/refresh";

type S = components["schemas"];
export type Doctor = S["Doctor"];
export type DoctorSession = S["DoctorSession"];
export type Appointment = S["Appointment"];
export type AppointmentStatus = S["AppointmentStatus"];
export type CancelReason = S["AppointmentCancel"]["reason"];
export type Schedule = S["Schedule"];
export type ScheduleBlockInput = S["ScheduleBlockInput"];
export type ScheduleChange = S["ScheduleChange"];
export type NewScheduleException = S["NewScheduleException"];
export type ScheduleExceptionChange = S["ScheduleExceptionChange"];
export type BookingMode = S["BookingMode"];

export interface AppointmentApi {
  readonly clinicId: string | undefined;
  readonly doctors: () => Promise<readonly Doctor[]>;
  readonly sessions: (date: string, doctorId?: string) => Promise<readonly DoctorSession[]>;
  readonly book: (body: S["NewAppointment"]) => Promise<Appointment>;
  readonly cancel: (id: string, reason: CancelReason, note?: string) => Promise<Appointment>;
  readonly reschedule: (id: string, sessionId: string, slotStart?: string) => Promise<Appointment>;
  readonly transition: (id: string, from: AppointmentStatus, to: AppointmentStatus) => Promise<Appointment>;
  readonly walkIn: (doctorId: string, patientId: string) => Promise<Appointment>;
  readonly patientAppointments: (patientId: string) => Promise<readonly Appointment[]>;
  readonly schedule: (doctorId: string) => Promise<Schedule>;
  readonly replaceSchedule: (doctorId: string, blocks: readonly ScheduleBlockInput[]) => Promise<ScheduleChange>;
  readonly addException: (doctorId: string, body: NewScheduleException) => Promise<ScheduleExceptionChange>;
  readonly removeException: (doctorId: string, exceptionId: string) => Promise<ScheduleExceptionChange>;
  readonly setBookingMode: (mode: BookingMode) => Promise<unknown>;
}

export function useAppointmentApi(): AppointmentApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    const appt = (id: string): RequestOptions => ({ ...base, pathParams: { appointment_id: id } });
    const doctor = (id: string): RequestOptions => ({ ...base, pathParams: { doctor_id: id } });
    return {
      clinicId,
      doctors: async () => (await sessionGet("/api/v1/clinic/doctors", base)).data.items,
      sessions: async (date, doctorId) =>
        (await sessionGet("/api/v1/sessions", { ...base, query: { date, doctor_id: doctorId } })).data.items,
      book: async (body) => (await sessionPost("/api/v1/appointments", body, base)).data,
      cancel: async (id, reason, note) =>
        (
          await sessionPost(
            "/api/v1/appointments/{appointment_id}/cancel",
            { reason, ...(note === undefined || note.trim() === "" ? {} : { note }) },
            appt(id),
          )
        ).data,
      reschedule: async (id, sessionId, slotStart) =>
        (
          await sessionPost(
            "/api/v1/appointments/{appointment_id}/reschedule",
            { session_id: sessionId, ...(slotStart === undefined ? {} : { slot_start: slotStart }) },
            appt(id),
          )
        ).data,
      transition: async (id, from, to) =>
        (await sessionPost("/api/v1/appointments/{appointment_id}/transitions", { from, to }, appt(id))).data,
      walkIn: async (doctorId, patientId) =>
        (await sessionPost("/api/v1/queue/walk-ins", { doctor_id: doctorId, patient_id: patientId }, base)).data,
      patientAppointments: async (patientId) =>
        (
          await sessionGet("/api/v1/patients/{patient_id}/appointments", {
            ...base,
            pathParams: { patient_id: patientId },
          })
        ).data.items,
      schedule: async (doctorId) =>
        (await sessionGet("/api/v1/clinic/doctors/{doctor_id}/schedule", doctor(doctorId))).data,
      replaceSchedule: async (doctorId, blocks) =>
        (await sessionPut("/api/v1/clinic/doctors/{doctor_id}/schedule", { blocks: [...blocks] }, doctor(doctorId)))
          .data,
      addException: async (doctorId, body) =>
        (await sessionPost("/api/v1/clinic/doctors/{doctor_id}/schedule-exceptions", body, doctor(doctorId))).data,
      removeException: async (doctorId, exceptionId) =>
        (
          await sessionDelete("/api/v1/clinic/doctors/{doctor_id}/schedule-exceptions/{exception_id}", {
            ...base,
            pathParams: { doctor_id: doctorId, exception_id: exceptionId },
          })
        ).data,
      setBookingMode: async (mode) => (await sessionPatch("/api/v1/clinic", { booking_mode: mode }, base)).data,
    };
  }, [clinicId]);
}

/** One accent per status (M6-P1 decision 1A); the badge always says the status in words. */
export const STATUS_TONES: Readonly<Record<AppointmentStatus, Tone>> = {
  BOOKED: "neutral",
  ARRIVED: "waiting",
  IN_CONSULTATION: "active",
  COMPLETED: "done",
  NO_SHOW: "missed",
  CANCELLED: "neutral",
};

export const STATUS_LABELS: Readonly<Record<AppointmentStatus, string>> = {
  BOOKED: "Booked",
  ARRIVED: "Arrived",
  IN_CONSULTATION: "With doctor",
  COMPLETED: "Completed",
  NO_SHOW: "No-show",
  CANCELLED: "Cancelled",
};

export const CANCEL_REASON_LABELS: Readonly<Record<CancelReason, string>> = {
  PATIENT_REQUEST: "Patient asked",
  CLINIC_REQUEST: "Clinic asked",
  DOCTOR_UNAVAILABLE: "Doctor unavailable",
  DUPLICATE: "Booked twice",
  OTHER: "Other (say why)",
};

/** "Token 4" or "10:15" — where an appointment sits in its session. */
export function placeText(a: Pick<Appointment, "token_number" | "slot_start">, clock: (iso: string) => string): string {
  if (a.token_number !== null) return `Token ${a.token_number}`;
  return a.slot_start === null ? "–" : clock(a.slot_start);
}
