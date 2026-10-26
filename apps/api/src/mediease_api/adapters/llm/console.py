"""The console "model": deterministic rules instead of a provider (M7a-P2; spec assistant R1).

For local runs, CI, Playwright and demos without a key or a network. It reads the last user
message, picks a tool by keywords (English and a few Hindi words), and answers with the tools'
own ``summary`` text, so everything it says was written by our code from the database. It also
walks the booking dialogue: it asks which clinic, searches, lists free times, and turns "2, my
number is …" into ``request_booking`` (which the user still confirms). It is refused in
production (``bootstrap.build_llm``) and never pretends to be clever: anything it does not
recognise gets a short list of what it can do.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from mediease_api.domain.assistant.llm import (
    ChatMessage,
    ChatRole,
    JsonValue,
    LlmReply,
    ToolCall,
    ToolSpec,
)

ASK_CLINIC = "Which clinic or doctor would you like to book with?"
ASK_PHONE = "Please tell me the number of the time you want and your phone number."
_FREE_TIMES = re.compile(r"^Free times with (?P<doctor>.+?) at (?P<clinic>.+?):", re.MULTILINE)
_PHONE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}")
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_TODAY = re.compile(r"Today is (\d{4}-\d{2}-\d{2})")
_MEDICINE_NUMBER = re.compile(r"(?:medicine|number|no\.?|#|दवा)\s*(\d{1,2})\b", re.IGNORECASE)

_HELP = (
    "I can explain the prescription you chose, show your appointments and booking requests, "
    "find a clinic and its free times, and send a booking request for you to confirm."
)
_STAFF_HELP = (
    "I can show today's queue, list a day's sessions, find a patient, show a patient's "
    "appointments, and book, cancel or move an appointment for you to confirm."
)

_EXPLAIN_WORDS = (
    "prescription",
    "medicine",
    "tablet",
    "syrup",
    "capsule",
    "drops",
    "dose",
    "explain",
    "how long",
    "when do i take",
    "when should i take",
    "how do i take",
    "doctor wrote",
    "instructions",
    "दवा",
    "दवाई",
    "पर्चा",
    "पर्चे",
    "कब",
    "dawa",
    "dawai",
    "goli",
)


def _has(text: str, words: Sequence[str]) -> bool:
    return any(w in text for w in words)


def _result(message: ChatMessage) -> dict[str, JsonValue]:
    try:
        value = json.loads(message.content)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _say(text: str) -> LlmReply:
    return LlmReply(content=text)


def _call(name: str, n: int, **arguments: JsonValue) -> LlmReply:
    return LlmReply(content="", tool_calls=(ToolCall(f"call_{n}", name, arguments),))


class ConsoleLlm:
    """``LlmPort`` without a provider: keyword rules over the tools offered."""

    @property
    def provider(self) -> str:
        return "console"

    @property
    def model(self) -> str:
        return "console-rules-v1"

    def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]) -> LlmReply:
        names = {t.name for t in tools}
        users = [i for i, m in enumerate(messages) if m.role is ChatRole.USER]
        if not users:
            return _say(_HELP)
        at = users[-1]
        user = messages[at].content
        previous = next(
            (m.content for m in reversed(messages[:at]) if m.role is ChatRole.ASSISTANT), ""
        )
        system = messages[0].content if messages and messages[0].role is ChatRole.SYSTEM else ""
        results = [
            (m.name or "", _result(m)) for m in messages[at + 1 :] if m.role is ChatRole.TOOL
        ]
        round_number = len(results) + 1
        if results:
            return self._after_tools(user, previous, results, names, round_number)
        return self._first(user, previous, system, names)

    # --- The first step of a turn ---------------------------------------------------------------

    def _first(self, user: str, previous: str, system: str, names: set[str]) -> LlmReply:
        text = user.lower()
        if "today_queue" in names:
            return self._staff(user, text, system, names)
        free = _FREE_TIMES.search(previous)
        if free and "request_booking" in names and re.search(r"\b\d{1,2}\b", text):
            if not _PHONE.search(user):
                return _say(ASK_PHONE)
            return _call("search_clinics", 1, query=free.group("clinic"))
        if previous.startswith(ASK_CLINIC) and "search_clinics" in names:
            return _call("search_clinics", 1, query=user.strip()[:100])
        if _has(text, ("my prescriptions", "list my prescriptions", "which prescriptions")):
            return _call("my_prescriptions", 1)
        if "explain_prescription" in names and _has(text, _EXPLAIN_WORDS):
            number = _MEDICINE_NUMBER.search(user)
            if number:
                return _call("explain_prescription", 1, medicine_number=int(number.group(1)))
            return _call("explain_prescription", 1)
        if _has(text, ("request", "proposal", "proposed")):
            return _call("my_booking_requests", 1)
        if _has(text, ("book", "appointment with", "बुक")):
            match = re.search(r"\b(?:at|with)\s+(.+)$", user, re.IGNORECASE)
            if match and "search_clinics" in names:
                return _call("search_clinics", 1, query=match.group(1).strip(" ?.")[:100])
            return _say(ASK_CLINIC)
        if _has(text, ("appointment", "visit", "अपॉइंटमेंट")):
            return _call("my_appointments", 1)
        if _has(text, ("clinic", "doctor", "find")) and "search_clinics" in names:
            query = re.sub(r"\b(find|a|the|clinic|doctor|search|for|me)\b", " ", text).strip()
            return _call("search_clinics", 1, query=(query or user)[:100])
        return _say(_HELP)

    def _staff(self, user: str, text: str, system: str, names: set[str]) -> LlmReply:
        today = _TODAY.search(system)
        day = _DATE.search(user)
        if _has(text, ("queue", "today")):
            return _call("today_queue", 1, **({"date": day.group(1)} if day else {}))
        if "session" in text:
            chosen = day.group(1) if day else (today.group(1) if today else None)
            if chosen is None:
                return _say("Which day? Please give a date like 2026-10-28.")
            return _call("list_sessions", 1, date=chosen)
        match = re.search(
            r"\b(?:find|search|patient|look up)\s+(?:patient\s+)?(.+)$", user, re.IGNORECASE
        )
        if match and "find_patient" in names:
            return _call("find_patient", 1, text=match.group(1).strip(" ?.")[:100])
        return _say(_STAFF_HELP)

    # --- After tool results ---------------------------------------------------------------------

    def _after_tools(
        self,
        user: str,
        previous: str,
        results: list[tuple[str, dict[str, JsonValue]]],
        names: set[str],
        n: int,
    ) -> LlmReply:
        name, last = results[-1]
        if "error" in last:
            return _say(f"Sorry, that did not work: {last.get('message', '')}")
        data = last.get("data")
        data = data if isinstance(data, dict) else {}
        free = _FREE_TIMES.search(previous)
        choosing = free is not None and _PHONE.search(user) is not None
        if name == "search_clinics" and "list_slots" in names:
            clinics = data.get("clinics")
            pick = self._pick_doctor(
                clinics,
                free.group("clinic") if free else None,
                free.group("doctor") if free else None,
            )
            if pick is not None and (choosing or self._single(clinics)):
                slug, doctor_id = pick
                return _call("list_slots", n, clinic_slug=slug, doctor_id=doctor_id)
        if name == "list_slots" and choosing and "request_booking" in names:
            times = data.get("times")
            number = re.search(r"\b(\d{1,2})\b", _PHONE.sub(" ", user))
            phone = _PHONE.search(user)
            if isinstance(times, list) and number and phone:
                index = int(number.group(1)) - 1
                time = times[index] if 0 <= index < len(times) else None
                if isinstance(time, dict):
                    arguments: dict[str, JsonValue] = {
                        "clinic_slug": data.get("clinic_slug"),
                        "doctor_id": data.get("doctor_id"),
                        "session_start": time.get("session_start"),
                        "contact_phone": phone.group(0),
                    }
                    if time.get("slot_start"):
                        arguments["slot_start"] = time.get("slot_start")
                    return _call("request_booking", n, **arguments)
                return _say(f"Please choose a number between 1 and {len(times)}.")
        summary = last.get("summary")
        return _say(str(summary) if summary else _HELP)

    @staticmethod
    def _single(clinics: JsonValue) -> bool:
        if not isinstance(clinics, list) or len(clinics) != 1 or not isinstance(clinics[0], dict):
            return False
        doctors = clinics[0].get("doctors")
        return isinstance(doctors, list) and len(doctors) == 1

    @staticmethod
    def _pick_doctor(
        clinics: JsonValue, clinic: str | None, doctor: str | None
    ) -> tuple[str, str] | None:
        if not isinstance(clinics, list):
            return None
        for item in clinics:
            if not isinstance(item, dict) or (clinic and item.get("name") != clinic):
                continue
            doctors = item.get("doctors")
            if not isinstance(doctors, list):
                continue
            for d in doctors:
                if isinstance(d, dict) and (doctor is None or d.get("name") == doctor):
                    return str(item.get("clinic_slug")), str(d.get("doctor_id"))
        return None
