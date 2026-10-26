"""The patient assistant (M7a-P3, P4; FR-AI-01, 02, 04; spec assistant R3-R12).

Tools wrap the portal and booking use cases with the signed-in account (``PatientPrincipal``), so
each one sees exactly what the portal shows that account:

- reads: ``search_clinics``, ``list_slots``, ``my_appointments``, ``my_booking_requests``,
  ``my_prescriptions``, ``explain_prescription`` (only the prescription the request chose);
- writes, after a confirmation: ``request_booking``, ``answer_proposal``.

Cancelling or moving an appointment has no patient use case yet (FR-PRT-08), so the assistant
points to the clinic. The chosen prescription comes from the portal picker (an ``ISSUED``
version in the account's ``PortalScope``) or, from M7b, a verified upload; it is re-authorised on
every turn.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

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
    boolean,
    integer,
    say,
    spec,
    string,
)
from mediease_api.application.booking.answers import AcceptProposal, DeclineProposal
from mediease_api.application.booking.public import GetAvailability, GetPublicClinic
from mediease_api.application.booking.requests import (
    BookingRequestCommand,
    CreateBookingRequest,
    ListMyBookingRequests,
)
from mediease_api.application.context import RequestInfo
from mediease_api.application.discovery.search import SearchClinics, SearchQuery
from mediease_api.application.portal.records import (
    GetPortalPrescription,
    ListPortalAppointments,
    ListPortalPrescriptions,
)
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.assistant.explain import explain
from mediease_api.domain.assistant.llm import JsonValue
from mediease_api.domain.assistant.proposal import CallerKind
from mediease_api.domain.booking.request import RequestStatus
from mediease_api.domain.messaging.formatting import appointment_when
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.patient_view import PatientPage
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.clock import ClockPort

TURNS_PER_MINUTE = 12
INDIA = "Asia/Kolkata"
MAX_DAYS = 3
MAX_SLOTS_PER_SESSION = 8


@dataclass(frozen=True, slots=True)
class ChosenPrescription:
    """R9: the prescription a turn may explain, already authorised for this account."""

    page: PatientPage
    historical: bool = False
    # For logs: which IDs it came from (never content).
    ids: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PatientContext:
    prescription_id: UUID | None = None
    upload_id: UUID | None = None


class PatientToolUseCases(Protocol):
    """Fresh use cases per call, from the composition root."""

    def search_clinics(self) -> SearchClinics: ...
    def get_public_clinic(self) -> GetPublicClinic: ...
    def get_availability(self) -> GetAvailability: ...
    def create_booking_request(self) -> CreateBookingRequest: ...
    def list_my_booking_requests(self) -> ListMyBookingRequests: ...
    def accept_proposal(self) -> AcceptProposal: ...
    def decline_proposal(self) -> DeclineProposal: ...
    def list_portal_appointments(self) -> ListPortalAppointments: ...
    def list_portal_prescriptions(self) -> ListPortalPrescriptions: ...
    def get_portal_prescription(self) -> GetPortalPrescription: ...


# M7b-P10 (prescription-uploads R16): the verified upload's chosen version, or NotFound.
UploadReader = Callable[[PatientPrincipal, UUID, Language], ChosenPrescription]


def system_prompt(language: Language, today: str, has_prescription: bool) -> str:
    reply_in = "Hindi (Devanagari)" if language is Language.HI else "English"
    chosen = (
        "The user has chosen one prescription; call explain_prescription to read it."
        if has_prescription
        else "No prescription is chosen; if asked about one, tell the user to choose it from "
        "'My prescriptions' or upload it first."
    )
    return (
        "You are the MediEase assistant for patients of small clinics in India. "
        f"Today is {today} (India time). Reply briefly in {reply_in}.\n"
        "Rules you must always follow:\n"
        "1. Never give medical advice: no diagnosis, no explaining test results, no changing, "
        "stopping, starting or suggesting any medicine or dose, no treatment or diet advice. For "
        "any such question say you cannot help and ask them to contact their clinic.\n"
        "2. Use tools for every fact. Never invent clinics, doctors, times, prescriptions or "
        "instructions.\n"
        "3. For a prescription, call explain_prescription and repeat only what it returns, in "
        f"plain words, adding nothing. {chosen}\n"
        "4. To book: find the clinic with search_clinics, get free times with list_slots, let "
        "the user choose, ask for their phone number, then call request_booking. The user "
        "confirms on screen; never say a booking is done before that.\n"
        "5. If something is missing, ask one short question.\n"
        "6. You cannot cancel or move an appointment; tell the user to call the clinic."
    )


class PatientToolbox:
    """The tools for one account and one turn (or one confirmation)."""

    def __init__(
        self,
        *,
        use_cases: PatientToolUseCases,
        principal: PatientPrincipal,
        info: RequestInfo,
        language: Language,
        chosen: ChosenPrescription | None,
    ) -> None:
        self._uc = use_cases
        self._principal = principal
        self._info = info
        self._lang = language
        self._chosen = chosen

    def tools(self) -> list[Tool]:
        return [
            Tool(
                spec(
                    "search_clinics",
                    "Find clinics by clinic name, doctor name or speciality, optionally in a city.",
                    {"query": string("Words to search for"), "city": string("City, optional")},
                    ("query",),
                ),
                ToolKind.READ,
                run=self._search_clinics,
            ),
            Tool(
                spec(
                    "list_slots",
                    "Free appointment times for one doctor of one clinic (from a search result).",
                    {
                        "clinic_slug": string("The clinic's slug from search_clinics"),
                        "doctor_id": string("The doctor's id from search_clinics"),
                        "from_date": string("First day to look at, YYYY-MM-DD, optional"),
                    },
                    ("clinic_slug", "doctor_id"),
                ),
                ToolKind.READ,
                run=self._list_slots,
            ),
            Tool(
                spec(
                    "request_booking",
                    "Ask the clinic for one of the free times from list_slots. The user confirms.",
                    {
                        "clinic_slug": string("The clinic's slug"),
                        "doctor_id": string("The doctor's id"),
                        "session_start": string("session_start from list_slots, as given"),
                        "slot_start": string("slot_start from list_slots, if the time has one"),
                        "contact_phone": string("The user's phone number"),
                        "reason": string("A few words on why, optional (not for emergencies)"),
                    },
                    ("clinic_slug", "doctor_id", "session_start", "contact_phone"),
                ),
                ToolKind.WRITE,
                prepare=self._prepare_booking,
                perform=self._request_booking,
            ),
            Tool(
                spec("my_appointments", "The user's appointments in their clinics."),
                ToolKind.READ,
                run=self._my_appointments,
            ),
            Tool(
                spec(
                    "my_booking_requests",
                    "The user's booking requests and any other time a clinic proposed.",
                ),
                ToolKind.READ,
                run=self._my_requests,
            ),
            Tool(
                spec(
                    "answer_proposal",
                    "Accept or decline another time a clinic proposed. The user confirms.",
                    {
                        "request_id": string("The request's id from my_booking_requests"),
                        "accept": boolean("true to accept, false to decline"),
                    },
                    ("request_id", "accept"),
                ),
                ToolKind.WRITE,
                prepare=self._prepare_answer,
                perform=self._answer,
            ),
            Tool(
                spec("my_prescriptions", "The user's current prescriptions (no content)."),
                ToolKind.READ,
                run=self._my_prescriptions,
            ),
            Tool(
                spec(
                    "explain_prescription",
                    "What the doctor wrote on the chosen prescription, in plain words.",
                    {"medicine_number": integer("Only this medicine's number, optional")},
                ),
                ToolKind.READ,
                run=self._explain,
            ),
        ]

    # --- Reads ----------------------------------------------------------------------------------

    def _search_clinics(self, args: Args) -> ToolResult:
        query = SearchQuery(
            q=args.required_text("query", max_length=100),
            city=args.text("city", required=False, max_length=100),
        )
        hits = self._uc.search_clinics().execute(query, self._info)[:5]
        if not hits:
            return ToolResult(
                say(self._lang, "I found no clinic for that.", "मुझे इसके लिए कोई क्लिनिक नहीं मिला।")
            )
        lines = [say(self._lang, "Clinics I found:", "मुझे ये क्लिनिक मिले:")]
        clinics: list[JsonValue] = []
        for n, hit in enumerate(hits, 1):
            doctors = ", ".join(d.display_name for d in hit.doctors) or "-"
            lines.append(f"{n}. {hit.clinic.name} ({hit.clinic.city or '-'}): {doctors}")
            clinics.append(
                {
                    "clinic_slug": hit.clinic.slug,
                    "name": hit.clinic.name,
                    "city": hit.clinic.city,
                    "doctors": [
                        {"doctor_id": str(d.id), "name": d.display_name, "specialty": d.specialty}
                        for d in hit.doctors
                    ],
                }
            )
        return ToolResult("\n".join(lines), {"clinics": clinics})

    def _list_slots(self, args: Args) -> ToolResult:
        slug = args.required_text("clinic_slug", max_length=63)
        doctor_id = args.uuid("doctor_id")
        clinic = self._uc.get_public_clinic().execute(slug, self._info)
        doctor = next((d for d in clinic.doctors if d.id == doctor_id), None)
        if doctor is None:
            raise NotFound("doctor")
        days = self._uc.get_availability().execute(
            slug, doctor_id, args.day("from_date", required=False), self._info
        )[:MAX_DAYS]
        tz = clinic.clinic.timezone
        header = say(
            self._lang,
            f"Free times with {doctor.display_name} at {clinic.clinic.name}:",
            f"{clinic.clinic.name} में {doctor.display_name} के खाली समय:",
        )
        lines = [header]
        offers: list[JsonValue] = []
        n = 0
        for day in days:
            for session in day.sessions:
                starts = [s.starts_at for s in session.slots[:MAX_SLOTS_PER_SESSION]]
                if session.mode is BookingMode.TOKENS:
                    starts = [session.starts_at]
                for start in starts:
                    n += 1
                    when = appointment_when(
                        starts_at=start, token_number=None, timezone=tz, language=self._lang
                    )
                    lines.append(f"{n}. {when}")
                    offers.append(
                        {
                            "number": n,
                            "session_start": session.starts_at.isoformat(),
                            "slot_start": start.isoformat()
                            if session.mode is BookingMode.SLOTS
                            else None,
                            "when": when,
                        }
                    )
        if not offers:
            return ToolResult(
                say(
                    self._lang,
                    f"{doctor.display_name} has no free time in the next days.",
                    f"{doctor.display_name} के पास अगले दिनों में कोई खाली समय नहीं है।",
                ),
                {"clinic_slug": slug, "doctor_id": str(doctor_id), "times": []},
            )
        lines.append(
            say(
                self._lang,
                "Tell me the number of the time you want and your phone number.",
                "जो समय चाहिए उसका नंबर और अपना फ़ोन नंबर बताइए।",
            )
        )
        return ToolResult(
            "\n".join(lines), {"clinic_slug": slug, "doctor_id": str(doctor_id), "times": offers}
        )

    def _my_appointments(self, args: Args) -> ToolResult:
        groups = self._uc.list_portal_appointments().execute(self._principal)
        lines: list[str] = []
        items: list[JsonValue] = []
        for group in groups:
            for a in group.appointments[:10]:
                when = appointment_when(
                    starts_at=a.starts_at,
                    token_number=a.appointment.token_number,
                    timezone=group.clinic_timezone,
                    language=self._lang,
                )
                status = a.appointment.status.value
                lines.append(f"- {when}: {a.doctor_name}, {group.clinic_name} ({status})")
                items.append(
                    {
                        "clinic": group.clinic_name,
                        "doctor": a.doctor_name,
                        "when": when,
                        "status": status,
                    }
                )
        if not items:
            return ToolResult(
                say(self._lang, "You have no appointments yet.", "आपकी अभी कोई अपॉइंटमेंट नहीं है।")
            )
        title = say(self._lang, "Your appointments:", "आपकी अपॉइंटमेंट:")
        return ToolResult("\n".join([title, *lines]), {"appointments": items})

    def _my_requests(self, args: Args) -> ToolResult:
        requests = self._uc.list_my_booking_requests().execute(self._principal)
        if not requests:
            return ToolResult(
                say(
                    self._lang,
                    "You have no open booking requests.",
                    "आपका कोई खुला बुकिंग अनुरोध नहीं है।",
                )
            )
        lines = [say(self._lang, "Your booking requests:", "आपके बुकिंग अनुरोध:")]
        items: list[JsonValue] = []
        for r in requests:
            when = appointment_when(
                starts_at=r.starts_at, token_number=None, timezone=r.timezone, language=self._lang
            )
            proposed = r.status is RequestStatus.PROPOSED
            note = (
                say(self._lang, " - the clinic proposed this time", " - क्लिनिक ने यह समय सुझाया")
                if proposed
                else ""
            )
            lines.append(f"- {r.clinic_name}, {r.doctor_name}: {when} ({r.status.value}){note}")
            items.append(
                {
                    "request_id": str(r.id),
                    "clinic": r.clinic_name,
                    "doctor": r.doctor_name,
                    "when": when,
                    "status": r.status.value,
                }
            )
        return ToolResult("\n".join(lines), {"requests": items})

    def _my_prescriptions(self, args: Args) -> ToolResult:
        items = self._uc.list_portal_prescriptions().execute(self._principal)[:10]
        if not items:
            return ToolResult(
                say(
                    self._lang,
                    "You have no prescriptions in your account yet.",
                    "आपके खाते में अभी कोई पर्चा नहीं है।",
                )
            )
        lines = [
            say(
                self._lang,
                "Your prescriptions (choose one under 'My prescriptions' to ask about it):",
                "आपके पर्चे (किसी के बारे में पूछने के लिए उसे 'मेरे पर्चे' में चुनें):",
            )
        ]
        data: list[JsonValue] = []
        for p in items:
            day = p.issued_at.astimezone(ZoneInfo(INDIA)).date().isoformat()
            lines.append(f"- {p.doctor_name}, {p.clinic_name}, {day}")
            data.append({"clinic": p.clinic_name, "doctor": p.doctor_name, "issued_on": day})
        return ToolResult("\n".join(lines), {"prescriptions": data})

    def _explain(self, args: Args) -> ToolResult:
        if self._chosen is None:
            return ToolResult(
                say(
                    self._lang,
                    "Please choose a prescription under 'My prescriptions' (or upload one) first.",
                    "कृपया पहले 'मेरे पर्चे' में से एक पर्चा चुनें (या अपलोड करें)।",
                )
            )
        result = explain(
            self._chosen.page,
            historical=self._chosen.historical,
            medicine_number=args.number("medicine_number", maximum=50),
        )
        return ToolResult(result.text, {"text": result.text}, explanation=result)

    # --- Writes ---------------------------------------------------------------------------------

    def _prepare_booking(self, args: Args) -> Prepared:
        slug = args.required_text("clinic_slug", max_length=63)
        doctor_id = args.uuid("doctor_id")
        session_start = args.instant("session_start")
        slot_start = args.instant("slot_start", required=False)
        assert session_start is not None
        phone = PhoneNumber.parse(
            args.required_text("contact_phone", max_length=20), field="contact_phone"
        )
        reason = args.text("reason", required=False, max_length=200)
        clinic = self._uc.get_public_clinic().execute(slug, self._info)
        doctor = next((d for d in clinic.doctors if d.id == doctor_id), None)
        if doctor is None:
            raise NotFound("doctor")
        when = appointment_when(
            starts_at=slot_start or session_start,
            token_number=None,
            timezone=clinic.clinic.timezone,
            language=self._lang,
        )
        summary = say(
            self._lang,
            f"Send a booking request to {clinic.clinic.name} for {doctor.display_name} on {when}, "
            f"phone {phone.masked()}? The clinic will confirm or suggest another time. This is not "
            "for emergencies.",
            f"{clinic.clinic.name} को {doctor.display_name} के लिए {when} का बुकिंग अनुरोध भेजें, "
            f"फ़ोन {phone.masked()}? क्लिनिक पुष्टि करेगा या दूसरा समय सुझाएगा। "
            "यह आपात स्थिति के लिए नहीं है।",
        )
        values = {
            "clinic_slug": slug,
            "doctor_id": str(doctor_id),
            "session_start": session_start.isoformat(),
            "contact_phone": phone.e164,
            "when": when,
            "clinic_name": clinic.clinic.name,
        }
        if slot_start is not None:
            values["slot_start"] = slot_start.isoformat()
        if reason:
            values["reason"] = reason
        return Prepared(summary, values)

    def _request_booking(self, values: Mapping[str, str]) -> str:
        slot = values.get("slot_start")
        self._uc.create_booking_request().execute(
            self._principal,
            BookingRequestCommand(
                clinic_slug=values["clinic_slug"],
                doctor_id=UUID(values["doctor_id"]),
                session_start=datetime.fromisoformat(values["session_start"]),
                slot_start=datetime.fromisoformat(slot) if slot else None,
                contact_phone=values["contact_phone"],
                age_years=None,
                sex=None,
                reason=values.get("reason"),
                not_emergency_ack=True,  # the confirmation said it is not for emergencies
            ),
            self._info,
        )
        return say(
            self._lang,
            f"Your request for {values['when']} was sent to {values['clinic_name']}. You will see "
            "their answer under My appointments.",
            f"{values['when']} का आपका अनुरोध {values['clinic_name']} को भेज दिया गया। उनका उत्तर "
            "'मेरी अपॉइंटमेंट' में दिखेगा।",
        )

    def _prepare_answer(self, args: Args) -> Prepared:
        request_id = args.uuid("request_id")
        accept = args.flag("accept")
        mine = self._uc.list_my_booking_requests().execute(self._principal)
        request = next((r for r in mine if r.id == request_id), None)
        if request is None or request.status is not RequestStatus.PROPOSED:
            raise ToolArgumentError("that request has no time waiting for an answer")
        when = appointment_when(
            starts_at=request.starts_at,
            token_number=None,
            timezone=request.timezone,
            language=self._lang,
        )
        summary = (
            say(
                self._lang,
                f"Accept {when} with {request.doctor_name} at {request.clinic_name}?",
                f"{request.clinic_name} में {request.doctor_name} के साथ {when} स्वीकार करें?",
            )
            if accept
            else say(
                self._lang,
                f"Decline the time {request.clinic_name} proposed ({when})?",
                f"{request.clinic_name} का सुझाया समय ({when}) अस्वीकार करें?",
            )
        )
        return Prepared(
            summary,
            {"request_id": str(request_id), "accept": "true" if accept else "false", "when": when},
        )

    def _answer(self, values: Mapping[str, str]) -> str:
        request_id = UUID(values["request_id"])
        if values["accept"] == "true":
            self._uc.accept_proposal().execute(self._principal, request_id, self._info)
            return say(
                self._lang,
                f"Done: your appointment is {values['when']}.",
                f"हो गया: आपकी अपॉइंटमेंट {values['when']} है।",
            )
        self._uc.decline_proposal().execute(self._principal, request_id, self._info)
        return say(
            self._lang, "Done: you declined that time.", "हो गया: आपने वह समय अस्वीकार कर दिया।"
        )


class PatientAssistant:
    """``POST /portal/assistant/turns`` and ``…/confirm`` (R3-R11)."""

    def __init__(
        self,
        *,
        engine: AssistantEngine,
        use_cases: PatientToolUseCases,
        clock: ClockPort,
        uploads: UploadReader | None = None,
    ) -> None:
        self._engine = engine
        self._uc = use_cases
        self._clock = clock
        self._uploads = uploads

    def _language(self, principal: PatientPrincipal, language: Language | None) -> Language:
        return language or principal.account.language

    def _chosen(
        self, principal: PatientPrincipal, context: PatientContext | None, language: Language
    ) -> ChosenPrescription | None:
        """R9: re-authorised on every turn; anything not the account's is REQ_NOT_FOUND."""
        if context is None:
            return None
        if context.prescription_id is not None:
            page = self._uc.get_portal_prescription().execute(
                principal, context.prescription_id, language
            )
            return ChosenPrescription(page, ids={"prescription_id": str(context.prescription_id)})
        if context.upload_id is not None:
            if self._uploads is None:
                raise NotFound("upload")
            return self._uploads(principal, context.upload_id, language)
        return None

    def turn(
        self,
        principal: PatientPrincipal,
        messages: Sequence[TurnMessage],
        *,
        language: Language | None,
        context: PatientContext | None,
        info: RequestInfo,
    ) -> TurnReply:
        caller = Caller(CallerKind.PATIENT, principal.account_id)
        wait = self._engine.limit(caller, TURNS_PER_MINUTE)
        if wait is not None:
            raise RateLimited(wait)
        lang = self._language(principal, language)
        chosen = self._chosen(principal, context, lang)
        today = (self._clock.now().astimezone(ZoneInfo(INDIA))).date()
        toolbox = PatientToolbox(
            use_cases=self._uc, principal=principal, info=info, language=lang, chosen=chosen
        )
        return self._engine.turn(
            caller=caller,
            messages=messages,
            language=lang,
            system_prompt=system_prompt(
                lang, f"{today.isoformat()} ({today:%A})", chosen is not None
            ),
            tools=toolbox.tools(),
            context_ids=chosen.ids if chosen else None,
        )

    def confirm(
        self,
        principal: PatientPrincipal,
        token: str,
        *,
        language: Language | None,
        info: RequestInfo,
    ) -> TurnReply:
        lang = self._language(principal, language)
        toolbox = PatientToolbox(
            use_cases=self._uc, principal=principal, info=info, language=lang, chosen=None
        )
        return self._engine.confirm(
            caller=Caller(CallerKind.PATIENT, principal.account_id),
            token=token,
            tools=toolbox.tools(),
        )
