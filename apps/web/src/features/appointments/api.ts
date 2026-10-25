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
  readonly reschedule: (id: string, sessionId: string, slotStart?: string, overrideHold?: boolean) => Promise<Appointment>;
  readonly transition: (id: string, from: AppointmentStatus, to: AppointmentStatus) => Promise<Appointment>;
  readonly walkIn: (doctorId: string, patientId: string) => Promise<Appointment>;
  readonly patientAppointments: (patientId: string) => Promise<readonly Appointment[]>;
  readonly schedule: (doctorId: string) => Promise<Schedule>;
  readonly replaceSchedule: (doctorId: string, blocks: readonly ScheduleBlockInput[]) => Promise<ScheduleChange>;
  readonly addException: (doctorId: string, body: NewScheduleException) => Promise<ScheduleExceptionChange>;
  readonly removeException: (doctorId: string, exceptionId: string) => Promise<ScheduleExceptionChange>;
  readonly setBookingMode: (mode: BookingMode) => Promise<unknown>;
  /** M6a-P8 (FR-APT-09): live bookings in sessions a schedule change closed. */
  readonly toMove: (doctorId?: string) => Promise<readonly BookingToMove[]>;
  /** M6a-P8 (FR-APT-08): the clinic's appointment reminders (owners). */
  readonly setReminders: (change: ReminderSettings) => Promise<unknown>;
  /** M6b-P4, P5 (R44, R45): the inbox, open (oldest first) or answered (last 7 days), with counts. */
  readonly bookingRequests: (state?: "open" | "answered") => Promise<BookingInbox>;
  /** M6b-P5 (R36): the records that may be the request's patient. */
  readonly requestCandidates: (id: string) => Promise<RequestCandidates>;
  readonly acceptRequest: (id: string, record: RecordChoice) => Promise<RequestAnswer>;
  readonly declineRequest: (id: string, reason: StaffDeclineReason, note?: string) => Promise<RequestAnswer>;
  readonly proposeTime: (id: string, sessionId: string, slotStart: string | undefined, record: RecordChoice) => Promise<RequestAnswer>;
  /** M6b-P4 (R20): how long a request holds its slot, and whether the form asks age and sex (owners). */
  readonly setRequestSettings: (change: RequestSettings) => Promise<unknown>;
  /** M6b-P6 (R69): the appointment's live token link, to send to the patient (APPOINTMENTS_MANAGE). */
  readonly liveLink: (id: string) => Promise<LiveLink>;
}

export type LiveLink = S["LiveLink"];

export type StaffBookingRequest = S["StaffBookingRequest"];
export type BookingInbox = S["StaffBookingRequestList"];
export type RequestCandidates = S["RequestCandidateList"];
export type RequestAnswer = S["RequestAnswer"];
export type RecordChoice = S["RequestRecordChoice"];
export type StaffDeclineReason = S["RequestDecline"]["reason"];
export interface RequestSettings {
  readonly request_hold_minutes?: number;
  readonly request_requires_age_sex?: boolean;
}

export type BookingToMove = S["BookingToMove"];
export interface ReminderSettings {
  readonly reminder_evening_before?: boolean;
  readonly reminder_hours_before?: number;
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
      reschedule: async (id, sessionId, slotStart, overrideHold) =>
        (
          await sessionPost(
            "/api/v1/appointments/{appointment_id}/reschedule",
            {
              session_id: sessionId,
              ...(slotStart === undefined ? {} : { slot_start: slotStart }),
              ...(overrideHold === true ? { override_hold: true } : {}),
            },
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
      toMove: async (doctorId) =>
        (
          await sessionGet("/api/v1/appointments/to-move", {
            ...base,
            ...(doctorId === undefined ? {} : { query: { doctor_id: doctorId } }),
          })
        ).data.items,
      setReminders: async (change) => (await sessionPatch("/api/v1/clinic", change, base)).data,
      bookingRequests: async (state = "open") =>
        (await sessionGet("/api/v1/booking-requests", { ...base, query: { state } })).data,
      requestCandidates: async (id) =>
        (await sessionGet("/api/v1/booking-requests/{request_id}/candidates", { ...base, pathParams: { request_id: id } })).data,
      acceptRequest: async (id, record) =>
        (await sessionPost("/api/v1/booking-requests/{request_id}/accept", record, { ...base, pathParams: { request_id: id } })).data,
      declineRequest: async (id, reason, note) =>
        (
          await sessionPost(
            "/api/v1/booking-requests/{request_id}/decline",
            { reason, ...(note === undefined || note.trim() === "" ? {} : { note: note.trim() }) },
            { ...base, pathParams: { request_id: id } },
          )
        ).data,
      proposeTime: async (id, sessionId, slotStart, record) =>
        (
          await sessionPost(
            "/api/v1/booking-requests/{request_id}/propose",
            { session_id: sessionId, ...(slotStart === undefined ? {} : { slot_start: slotStart }), ...record },
            { ...base, pathParams: { request_id: id } },
          )
        ).data,
      setRequestSettings: async (change) => (await sessionPatch("/api/v1/clinic", change, base)).data,
      liveLink: async (id) => (await sessionGet("/api/v1/appointments/{appointment_id}/live-link", appt(id))).data,
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
