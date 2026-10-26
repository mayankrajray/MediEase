"""The staff assistant (M7a-P5; FR-AI-01, 02; spec assistant R3-R12).

Tools wrap the clinic's own use cases with the request's ``RequestContext``, and the model is
offered only those the member's role allows (R6): every tool names the permission its route
needs, the same one the HTTP endpoint declares.

- reads: ``today_queue``, ``list_sessions``, ``find_patient``, ``patient_appointments``;
- writes, after a confirmation: ``book_appointment``, ``cancel_appointment``,
  ``reschedule_appointment``.

No tool reads clinical content. Patient phone numbers are masked to their last digits (R6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Protocol
from uuid import UUID

from mediease_api.application.appointments.book import BookAppointment, BookCommand
from mediease_api.application.appointments.cancel import CancelAppointment, CancelCommand
from mediease_api.application.appointments.queries import GetAppointment, ListPatientAppointments
from mediease_api.application.appointments.queue import GetQueue
from mediease_api.application.appointments.reschedule import (
    RescheduleAppointment,
    RescheduleCommand,
)
from mediease_api.application.assistant.engine import (
    AssistantEngine,
    Caller,
    TurnMessage,
    TurnReply,
)
from mediease_api.application.assistant.errors import RateLimited
from mediease_api.application.assistant.tools import (
    Args,
    Prepared,
    Tool,
    ToolArgumentError,
    ToolKind,
    ToolResult,
    spec,
    string,
)
from mediease_api.application.clinics.queries import GetClinic, ListDoctors
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.patients.queries import GetPatient, LookupPatients
from mediease_api.application.scheduling.sessions import ListSessions
from mediease_api.domain.appointments.status import CancelReason
from mediease_api.domain.assistant.llm import JsonValue
from mediease_api.domain.assistant.proposal import CallerKind
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.messaging.formatting import appointment_when
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort

TURNS_PER_MINUTE = 12
MAX_ENTRIES = 40
CANCEL_REASONS = tuple(r.value for r in CancelReason if r is not CancelReason.RESCHEDULED)


class StaffToolUseCases(Protocol):
    def get_clinic(self) -> GetClinic: ...
    def list_doctors(self) -> ListDoctors: ...
    def get_queue(self) -> GetQueue: ...
    def list_sessions(self) -> ListSessions: ...
    def lookup_patients(self) -> LookupPatients: ...
    def get_patient(self) -> GetPatient: ...
    def list_patient_appointments(self) -> ListPatientAppointments: ...
    def get_appointment(self) -> GetAppointment: ...
    def book_appointment(self) -> BookAppointment: ...
    def cancel_appointment(self) -> CancelAppointment: ...
    def reschedule_appointment(self) -> RescheduleAppointment: ...


def system_prompt(today: str, clinic_name: str) -> str:
    return (
        f"You are the MediEase assistant for the staff of {clinic_name}, a small clinic in India. "
        f"Today is {today} (clinic time). Reply briefly in English.\n"
        "Rules you must always follow:\n"
        "1. Never give medical advice and never discuss diagnoses or medicines; you have no "
        "clinical tools.\n"
        "2. Use tools for every fact; never invent patients, sessions, times or IDs. Pass IDs and "
        "times exactly as tools returned them.\n"
        "3. To book: find the patient (find_patient), find the session (list_sessions for the "
        "day), then call book_appointment. To cancel or move: find the appointment with "
        "patient_appointments first. The user confirms every change on screen.\n"
        "4. If something is missing or there are several matches, ask one short question."
    )


class StaffToolbox:
    def __init__(self, *, use_cases: StaffToolUseCases, ctx: RequestContext, timezone: str) -> None:
        self._uc = use_cases
        self._ctx = ctx
        self._tz = timezone
        self._doctor_names: dict[UUID, str] | None = None

    def tools(self) -> list[Tool]:
        offered: list[tuple[Permission, Tool]] = [
            (
                Permission.APPOINTMENTS_MANAGE,
                Tool(
                    spec(
                        "today_queue",
                        "The day's queue by session: tokens or times, patients and status.",
                        {"date": string("YYYY-MM-DD, optional; default today")},
                    ),
                    ToolKind.READ,
                    run=self._queue,
                ),
            ),
            (
                Permission.APPOINTMENTS_MANAGE,
                Tool(
                    spec(
                        "list_sessions",
                        "The doctors' sessions on a day, with free places and session ids.",
                        {"date": string("YYYY-MM-DD")},
                        ("date",),
                    ),
                    ToolKind.READ,
                    run=self._sessions,
                ),
            ),
            (
                Permission.PATIENTS_MANAGE,
                Tool(
                    spec(
                        "find_patient",
                        "Find patients by phone number, patient code or name.",
                        {"text": string("Phone, code (e.g. ME-0142) or the start of a name")},
                        ("text",),
                    ),
                    ToolKind.READ,
                    run=self._find_patient,
                ),
            ),
            (
                Permission.APPOINTMENTS_MANAGE,
                Tool(
                    spec(
                        "patient_appointments",
                        "One patient's appointments, with appointment ids.",
                        {"patient_id": string("The patient's id from find_patient")},
                        ("patient_id",),
                    ),
                    ToolKind.READ,
                    run=self._patient_appointments,
                ),
            ),
            (
                Permission.APPOINTMENTS_MANAGE,
                Tool(
                    spec(
                        "book_appointment",
                        "Book a patient into a session (and a slot in slot mode). The user "
                        "confirms.",
                        {
                            "patient_id": string("From find_patient"),
                            "session_id": string("From list_sessions"),
                            "date": string("The session's date, YYYY-MM-DD"),
                            "slot_start": string(
                                "A free slot time from list_sessions, slot mode only"
                            ),
                        },
                        ("patient_id", "session_id", "date"),
                    ),
                    ToolKind.WRITE,
                    prepare=self._prepare_book,
                    perform=self._book,
                ),
            ),
            (
                Permission.APPOINTMENTS_MANAGE,
                Tool(
                    spec(
                        "cancel_appointment",
                        "Cancel an appointment. Confirmed by the user.",
                        {
                            "appointment_id": string("From patient_appointments or today_queue"),
                            "reason": {"type": "string", "enum": list(CANCEL_REASONS)},
                            "note": string("Required when the reason is OTHER"),
                        },
                        ("appointment_id", "reason"),
                    ),
                    ToolKind.WRITE,
                    prepare=self._prepare_cancel,
                    perform=self._cancel,
                ),
            ),
            (
                Permission.APPOINTMENTS_MANAGE,
                Tool(
                    spec(
                        "reschedule_appointment",
                        "Move a booked appointment to another session. Confirmed by the user.",
                        {
                            "appointment_id": string("From patient_appointments or today_queue"),
                            "session_id": string("The new session, from list_sessions"),
                            "date": string("The new session's date, YYYY-MM-DD"),
                            "slot_start": string("A free slot time, slot mode only"),
                        },
                        ("appointment_id", "session_id", "date"),
                    ),
                    ToolKind.WRITE,
                    prepare=self._prepare_reschedule,
                    perform=self._reschedule,
                ),
            ),
        ]
        return [tool for permission, tool in offered if self._ctx.allows(permission)]

    # --- Helpers --------------------------------------------------------------------------------

    def _when(self, starts_at: datetime, token: int | None = None) -> str:
        return appointment_when(
            starts_at=starts_at, token_number=token, timezone=self._tz, language=Language.EN
        )

    def _doctor(self, doctor_id: UUID) -> str:
        if self._doctor_names is None:
            self._doctor_names = {
                d.id: d.display_name for d in self._uc.list_doctors().execute(self._ctx)
            }
        return self._doctor_names.get(doctor_id, "a doctor")

    def _session_on(self, session_id: UUID, day: date) -> tuple[datetime, str, bool]:
        for view in self._uc.list_sessions().execute(self._ctx, day):
            s = view.session
            if s.id == session_id:
                return s.starts_at, self._doctor(s.doctor_id), s.mode.value == "SLOTS"
        raise ToolArgumentError("no such session on that date; use list_sessions")

    # --- Reads ----------------------------------------------------------------------------------

    def _queue(self, args: Args) -> ToolResult:
        queue = self._uc.get_queue().execute(self._ctx, on_date=args.day("date", required=False))
        lines = [f"Queue for {queue.on_date.isoformat()}:"]
        sessions: list[JsonValue] = []
        shown = 0
        for qs in queue.sessions:
            s = qs.session
            lines.append(
                f"{self._doctor(s.doctor_id)}, {self._when(s.starts_at)}: {len(qs.entries)} booked"
            )
            entries: list[JsonValue] = []
            for e in qs.entries:
                if shown >= MAX_ENTRIES:
                    break
                shown += 1
                a = e.view.appointment
                mark = (
                    f"#{a.token_number}"
                    if a.token_number
                    else self._when(a.slot_start or s.starts_at)
                )
                lines.append(f"  {mark} {e.patient.full_name} ({e.patient.code}) {a.status.value}")
                entries.append(
                    {
                        "appointment_id": str(a.id),
                        "patient_id": str(e.patient.id),
                        "patient": e.patient.full_name,
                        "code": e.patient.code,
                        "token": a.token_number,
                        "status": a.status.value,
                    }
                )
            sessions.append(
                {"session_id": str(s.id), "doctor": self._doctor(s.doctor_id), "entries": entries}
            )
        if not queue.sessions:
            lines.append("No sessions.")
        return ToolResult("\n".join(lines), {"sessions": sessions})

    def _sessions(self, args: Args) -> ToolResult:
        day = args.day("date")
        assert day is not None
        views = self._uc.list_sessions().execute(self._ctx, day)
        lines = [f"Sessions on {day.isoformat()}:"]
        data: list[JsonValue] = []
        for view in views:
            s = view.session
            free: list[str] = []
            if s.mode.value == "SLOTS" and s.slot_minutes:
                held = {h.slot_start for h in view.held if h.slot_start}
                t = s.starts_at
                while t < s.ends_at and len(free) < 12:
                    if t not in view.taken_slots and t not in held:
                        free.append(t.isoformat())
                    t += timedelta(minutes=s.slot_minutes)
            lines.append(
                f"- {self._doctor(s.doctor_id)}, {self._when(s.starts_at)}"
                f" ({s.status.value}, {max(s.available, 0)} places left)"
            )
            data.append(
                {
                    "session_id": str(s.id),
                    "doctor": self._doctor(s.doctor_id),
                    "starts_at": s.starts_at.isoformat(),
                    "mode": s.mode.value,
                    "status": s.status.value,
                    "places_left": max(s.available, 0),
                    "free_slots": list(free),
                }
            )
        if not views:
            lines.append("No sessions that day.")
        return ToolResult("\n".join(lines), {"date": day.isoformat(), "sessions": data})

    def _find_patient(self, args: Args) -> ToolResult:
        found = self._uc.lookup_patients().execute(
            self._ctx, args.required_text("text", max_length=100)
        )[:10]
        if not found:
            return ToolResult("No patient found.")
        lines = ["Patients:"]
        data: list[JsonValue] = []
        for p in found:
            phone = PhoneNumber(p.phone_e164).masked()
            lines.append(f"- {p.full_name} ({p.code}), {p.age_years} y, {phone}")
            data.append(
                {
                    "patient_id": str(p.id),
                    "name": p.full_name,
                    "code": p.code,
                    "age": p.age_years,
                    "phone": phone,
                }
            )
        return ToolResult("\n".join(lines), {"patients": data})

    def _patient_appointments(self, args: Args) -> ToolResult:
        patient_id = args.uuid("patient_id")
        views = self._uc.list_patient_appointments().execute(self._ctx, patient_id)[:10]
        if not views:
            return ToolResult("No appointments for this patient.")
        lines = ["Appointments:"]
        data: list[JsonValue] = []
        for v in views:
            a, s = v.appointment, v.session
            when = self._when(a.slot_start or s.starts_at, a.token_number)
            lines.append(f"- {when} with {self._doctor(s.doctor_id)} ({a.status.value})")
            data.append({"appointment_id": str(a.id), "when": when, "status": a.status.value})
        return ToolResult("\n".join(lines), {"appointments": data})

    # --- Writes ---------------------------------------------------------------------------------

    def _patient_name(self, patient_id: UUID) -> str:
        p = self._uc.get_patient().execute(self._ctx, patient_id)
        return f"{p.full_name} ({p.code})"

    def _prepare_book(self, args: Args) -> Prepared:
        patient_id, session_id = args.uuid("patient_id"), args.uuid("session_id")
        day = args.day("date")
        assert day is not None
        slot = args.instant("slot_start", required=False)
        starts_at, doctor, slots = self._session_on(session_id, day)
        if slots and slot is None:
            raise ToolArgumentError("this session books by time: pass slot_start")
        who = self._patient_name(patient_id)
        when = self._when(slot or starts_at)
        values = {
            "patient_id": str(patient_id),
            "session_id": str(session_id),
            "summary": f"{who}, {when}",
        }
        if slot is not None:
            values["slot_start"] = slot.isoformat()
        return Prepared(f"Book {who} with {doctor} on {when}?", values)

    def _book(self, values: Mapping[str, str]) -> str:
        slot = values.get("slot_start")
        self._uc.book_appointment().execute(
            clinic_id=self._ctx.clinic_id,
            actor=Actor.staff(self._ctx),
            cmd=BookCommand(
                session_id=UUID(values["session_id"]),
                patient_id=UUID(values["patient_id"]),
                slot_start=datetime.fromisoformat(slot) if slot else None,
            ),
        )
        return f"Booked: {values['summary']}."

    def _appointment(self, appointment_id: UUID) -> tuple[str, str]:
        detail = self._uc.get_appointment().execute(self._ctx, appointment_id)
        a, s = detail.view.appointment, detail.view.session
        return self._patient_name(a.patient_id), self._when(
            a.slot_start or s.starts_at, a.token_number
        )

    def _prepare_cancel(self, args: Args) -> Prepared:
        appointment_id = args.uuid("appointment_id")
        reason = args.required_text("reason", max_length=40)
        if reason not in CANCEL_REASONS:
            raise ToolArgumentError(f"reason must be one of {', '.join(CANCEL_REASONS)}")
        note = args.text("note", required=False, max_length=200)
        if reason == CancelReason.OTHER.value and not note:
            raise ToolArgumentError("a note is required when the reason is OTHER")
        who, when = self._appointment(appointment_id)
        values = {
            "appointment_id": str(appointment_id),
            "reason": reason,
            "summary": f"{who}, {when}",
        }
        if note:
            values["note"] = note
        return Prepared(f"Cancel the appointment of {who} on {when} ({reason})?", values)

    def _cancel(self, values: Mapping[str, str]) -> str:
        self._uc.cancel_appointment().execute(
            clinic_id=self._ctx.clinic_id,
            actor=Actor.staff(self._ctx),
            appointment_id=UUID(values["appointment_id"]),
            cmd=CancelCommand(reason=CancelReason(values["reason"]), note=values.get("note")),
        )
        return f"Cancelled: {values['summary']}."

    def _prepare_reschedule(self, args: Args) -> Prepared:
        appointment_id, session_id = args.uuid("appointment_id"), args.uuid("session_id")
        day = args.day("date")
        assert day is not None
        slot = args.instant("slot_start", required=False)
        starts_at, doctor, slots = self._session_on(session_id, day)
        if slots and slot is None:
            raise ToolArgumentError("this session books by time: pass slot_start")
        who, old = self._appointment(appointment_id)
        new = self._when(slot or starts_at)
        values = {
            "appointment_id": str(appointment_id),
            "session_id": str(session_id),
            "summary": f"{who}, {new}",
        }
        if slot is not None:
            values["slot_start"] = slot.isoformat()
        return Prepared(f"Move {who} from {old} to {new} with {doctor}?", values)

    def _reschedule(self, values: Mapping[str, str]) -> str:
        slot = values.get("slot_start")
        self._uc.reschedule_appointment().execute(
            clinic_id=self._ctx.clinic_id,
            actor=Actor.staff(self._ctx),
            appointment_id=UUID(values["appointment_id"]),
            cmd=RescheduleCommand(
                session_id=UUID(values["session_id"]),
                slot_start=datetime.fromisoformat(slot) if slot else None,
            ),
        )
        return f"Moved: {values['summary']}."


class StaffAssistant:
    """``POST /assistant/turns`` and ``…/confirm`` for clinic staff (R3-R11)."""

    def __init__(
        self, *, engine: AssistantEngine, use_cases: StaffToolUseCases, clock: ClockPort
    ) -> None:
        self._engine = engine
        self._uc = use_cases
        self._clock = clock

    def _caller(self, ctx: RequestContext) -> Caller:
        return Caller(CallerKind.STAFF, ctx.user_id, ctx.clinic_id)

    def turn(self, ctx: RequestContext, messages: Sequence[TurnMessage]) -> TurnReply:
        caller = self._caller(ctx)
        wait = self._engine.limit(caller, TURNS_PER_MINUTE)
        if wait is not None:
            raise RateLimited(wait)
        clinic = self._uc.get_clinic().execute(ctx)
        today = local_date(self._clock.now(), clinic.timezone)
        return self._engine.turn(
            caller=caller,
            messages=messages,
            language=Language.EN,
            system_prompt=system_prompt(f"{today.isoformat()} ({today:%A})", clinic.name),
            tools=StaffToolbox(use_cases=self._uc, ctx=ctx, timezone=clinic.timezone).tools(),
        )

    def confirm(self, ctx: RequestContext, token: str) -> TurnReply:
        clinic = self._uc.get_clinic().execute(ctx)
        tools = StaffToolbox(use_cases=self._uc, ctx=ctx, timezone=clinic.timezone).tools()
        return self._engine.confirm(caller=self._caller(ctx), token=token, tools=tools)
