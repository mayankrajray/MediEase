"""The assistant over HTTP (M7a-P3..P5; FR-AI-01..04; spec assistant R3-R12, AC2-AC5).

The model is either the real console adapter (the app's default) or ``ScriptedLlm``, which plays
a model's tool calls and records everything it was sent. Synthetic people and data only.
"""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from mediease_api.domain.assistant.llm import LlmBusy, LlmUnavailable
from tests.assistant_helpers import (
    ScriptedLlm,
    bot,
    call,
    patient_confirm,
    patient_turn,
    say,
    staff_confirm,
    staff_turn,
    user,
    with_llm,
)
from tests.booking_helpers import ensure_schedule, offers, verified_client
from tests.conftest import World
from tests.integration.test_appointments_http import _patient
from tests.integration.test_prescriptions_http import _issued
from tests.portal_helpers import PORTAL, link_by_invite, portal_client
from tests.sessions_now import running_session

EMAIL = "assistant.patient@example.test"
OTHER = "assistant.other@example.test"


def _linked(world: World, email: str = EMAIL) -> tuple[FlaskClient, dict[str, Any]]:
    """An issued Syrup X prescription and an account linked to its patient."""
    _, visit, rx = _issued(world)
    patient = portal_client(world, email)
    link_by_invite(world.client_for(world.a.owner), patient, visit["patient_id"])
    return patient, rx


def _code(resp: Any) -> str:
    return str(resp.get_json()["error"]["code"])


# --- Explanations from the record (R9, R10, AC5; FR-AI-04) ---------------------------------------


def test_fr_ai_04_the_chosen_prescription_is_explained_from_its_record(world: World) -> None:
    patient, rx = _linked(world)
    resp = patient_turn(
        patient, user("When do I take my medicine?"), context={"prescription_id": rx["id"]}
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["kind"] == "ANSWER" and body["proposal"] is None
    reply = body["reply"]
    for line in ("Syrup X", "5 ml", "Twice a day, morning and night, after food", "5 days"):
        assert line in reply, line
    assert resp.headers["Cache-Control"] == "no-store"


def test_fr_ai_04_one_medicine_by_number_and_hindi(world: World) -> None:
    patient, rx = _linked(world)
    one = patient_turn(
        patient, user("explain medicine 1"), context={"prescription_id": rx["id"]}
    ).get_json()["reply"]
    assert "1. Syrup X" in one
    hindi = patient_turn(
        patient, user("दवा कब लेनी है"), language="hi", context={"prescription_id": rx["id"]}
    ).get_json()["reply"]
    assert "Syrup X" in hindi and "दवाइयाँ" in hindi


def test_fr_ai_04_without_a_choice_the_assistant_asks_for_one(world: World) -> None:
    patient, _ = _linked(world)
    reply = patient_turn(patient, user("Explain my prescription")).get_json()["reply"]
    assert "choose a prescription" in reply
    assert "Syrup X" not in reply


def test_r9_another_accounts_prescription_is_not_found(world: World) -> None:
    _, rx = _linked(world)
    stranger = portal_client(world, OTHER)
    resp = patient_turn(stranger, user("explain it"), context={"prescription_id": rx["id"]})
    assert resp.status_code == 404 and _code(resp) == "REQ_NOT_FOUND"


def test_r9_context_names_exactly_one_thing(world: World) -> None:
    patient, rx = _linked(world)
    both = patient_turn(
        patient,
        user("explain"),
        context={"prescription_id": rx["id"], "upload_id": rx["id"]},
    )
    assert both.status_code == 422


def test_r10_a_made_up_number_is_replaced_by_the_records_own_text(world: World) -> None:
    llm = ScriptedLlm([call("explain_prescription"), say("Take 333 ml three times a day.")])
    w = with_llm(world, llm)
    patient, rx = _linked(w)
    body = patient_turn(
        patient, user("how much syrup?"), context={"prescription_id": rx["id"]}
    ).get_json()
    assert body["kind"] == "ANSWER"
    assert "333" not in body["reply"] and "5 ml" in body["reply"]


def test_r10_a_reply_that_restates_the_record_passes(world: World) -> None:
    llm = ScriptedLlm([call("explain_prescription"), say("Take 5 ml of Syrup X, 5 days.")])
    w = with_llm(world, llm)
    patient, rx = _linked(w)
    body = patient_turn(
        patient, user("how much?"), context={"prescription_id": rx["id"]}
    ).get_json()
    assert body["reply"] == "Take 5 ml of Syrup X, 5 days."
    # The model was given the record's lines as the tool's result, and nothing else clinical.
    (result,) = llm.tool_results()
    assert "Syrup X" in result["summary"]


# --- Guard rails (R4, R5, AC2; FR-AI-02) ---------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Can I take two tablets instead of one?",
        "Should I stop the medicine if I feel better?",
        "Is my sugar 180 high?",
        "What medicine should I take for fever?",
        "Do I have an infection?",
        "दवा बंद कर दूँ?",
        "I have chest pain",
    ],
)
def test_fr_ai_02_advice_requests_get_the_referral_and_never_reach_the_model(
    world: World, question: str
) -> None:
    llm = ScriptedLlm([say("should never be used")])
    w = with_llm(world, llm)
    patient, rx = _linked(w)
    body = patient_turn(patient, user(question), context={"prescription_id": rx["id"]}).get_json()
    assert body["kind"] == "REFERRAL"
    assert "medical advice" in body["reply"] or "चिकित्सा सलाह" in body["reply"]
    assert llm.calls == []


def test_r5_an_advice_like_reply_becomes_the_referral(world: World) -> None:
    llm = ScriptedLlm([say("I recommend paracetamol; you should take two.")])
    patient = portal_client(with_llm(world, llm), EMAIL)
    body = patient_turn(patient, user("hello")).get_json()
    assert body["kind"] == "REFERRAL"


# --- Booking by chat, confirmation (R6-R8, AC3, AC4; FR-AI-01) -----------------------------------


def _booking_turns(world: World) -> tuple[World, FlaskClient, ScriptedLlm, dict[str, Any]]:
    ensure_schedule(world, world.a)
    first = offers(world, world.a)[0]
    llm = ScriptedLlm()
    w = with_llm(world, llm)
    patient = verified_client(w, EMAIL)
    return w, patient, llm, first


def test_fr_ai_01_booking_by_chat_asks_then_proposes_then_books_once(world: World) -> None:
    w, patient, llm, first = _booking_turns(world)
    slug, doctor = w.a.clinic.slug, str(w.a.doctor.id)

    llm.steps = [say("Which clinic would you like to book with?")]
    asked = patient_turn(patient, user("I want to book an appointment")).get_json()
    assert asked["kind"] == "ANSWER" and asked["proposal"] is None

    llm.steps = [call("list_slots", clinic_slug=slug, doctor_id=doctor), say("Here are the times.")]
    times = patient_turn(
        patient, user("book"), bot(asked["reply"]), user("Alpha Sample Clinic")
    ).get_json()
    assert times["kind"] == "ANSWER"
    listed = llm.tool_results()[-1]["data"]["times"]
    assert listed and listed[0]["session_start"] == first["starts_at"]

    booking: dict[str, Any] = {
        "clinic_slug": slug,
        "doctor_id": doctor,
        "session_start": first["starts_at"],
        "contact_phone": "9000000777",
    }
    if first["slots"]:
        booking["slot_start"] = first["slots"][0]["starts_at"]
    llm.steps = [call("request_booking", **booking)]
    proposed = patient_turn(patient, user("the first one, 9000000777")).get_json()
    assert proposed["kind"] == "CONFIRM"
    assert "Alpha Sample Clinic" in proposed["reply"]
    assert "not for emergencies" in proposed["reply"]
    token = proposed["proposal"]["token"]
    # Nothing is written before the confirmation.
    assert patient.get(f"{PORTAL}/booking-requests").get_json()["items"] == []

    done = patient_confirm(patient, token)
    assert done.status_code == 200, done.get_json()
    assert done.get_json()["kind"] == "DONE"
    assert len(patient.get(f"{PORTAL}/booking-requests").get_json()["items"]) == 1

    again = patient_confirm(patient, token)
    assert again.status_code == 409 and _code(again) == "AI_PROPOSAL_USED"


def test_r8_a_proposal_is_bound_to_its_account_and_cannot_be_altered(world: World) -> None:
    w, patient, llm, first = _booking_turns(world)
    llm.steps = [
        call(
            "request_booking",
            clinic_slug=w.a.clinic.slug,
            doctor_id=str(w.a.doctor.id),
            session_start=first["starts_at"],
            contact_phone="9000000777",
        )
    ]
    token = patient_turn(patient, user("book it")).get_json()["proposal"]["token"]
    stranger = verified_client(w, OTHER)
    assert _code(patient_confirm(stranger, token)) == "AI_PROPOSAL_INVALID"
    body, mac = token.split(".")
    tampered = f"{body[:-2]}AA.{mac}"
    assert _code(patient_confirm(patient, tampered)) == "AI_PROPOSAL_INVALID"


def test_r7_bad_arguments_go_back_to_the_model_not_the_user(world: World) -> None:
    w, patient, llm, _ = _booking_turns(world)
    llm.steps = [
        call("request_booking", clinic_slug=w.a.clinic.slug, doctor_id="not-an-id"),
        say("What is your phone number?"),
    ]
    body = patient_turn(patient, user("book")).get_json()
    assert body["kind"] == "ANSWER" and body["reply"] == "What is your phone number?"
    assert llm.tool_results()[0]["error"] == "BAD_ARGUMENTS"


def test_fr_ai_01_the_model_only_sees_this_accounts_appointments(world: World) -> None:
    llm = ScriptedLlm([call("my_appointments"), say("ok")])
    w = with_llm(world, llm)
    patient = portal_client(w, EMAIL)
    patient_turn(patient, user("my appointments"))
    assert "no appointments" in llm.tool_results()[0]["summary"]


# --- Provider failures and limits (R2, R11) -------------------------------------------------------


def test_r2_provider_failures_are_503_with_their_codes(world: World) -> None:
    llm = ScriptedLlm([LlmUnavailable("network"), LlmBusy(17)])
    patient = portal_client(with_llm(world, llm), EMAIL)
    down = patient_turn(patient, user("hello"))
    assert down.status_code == 503 and _code(down) == "AI_UNAVAILABLE"
    busy = patient_turn(patient, user("hello"))
    assert busy.status_code == 503 and _code(busy) == "AI_PROVIDER_BUSY"
    assert busy.headers["Retry-After"] == "17"


def test_r11_more_than_12_turns_a_minute_are_refused(world: World) -> None:
    patient = portal_client(world, EMAIL)
    codes = [patient_turn(patient, user("hello")).status_code for _ in range(13)]
    assert codes[:12] == [200] * 12
    assert codes[12] == 429


def test_r3_the_conversation_is_validated(world: World) -> None:
    patient = portal_client(world, EMAIL)
    assert patient_turn(patient, bot("hi")).status_code == 422  # the last must be the user's
    assert patient_turn(patient, user("x" * 2001)).status_code == 422
    too_many = [user("a")] * 21
    assert patient_turn(patient, *too_many).status_code == 422


# --- The staff assistant (P5) ---------------------------------------------------------------------


def test_fr_ai_01_staff_console_shows_the_queue(world: World) -> None:
    desk = world.client_for(world.a.desk)
    body = staff_turn(desk, str(world.a.clinic.id), user("show today's queue")).get_json()
    assert body["kind"] == "ANSWER" and body["reply"].startswith("Queue for")


def test_fr_ai_01_staff_book_and_cancel_by_chat_with_confirmation(world: World) -> None:
    llm = ScriptedLlm()
    w = with_llm(world, llm)
    owner, desk = w.client_for(w.a.owner), w.client_for(w.a.desk)
    session = running_session(owner, w.a.doctor.id)
    patient_id = _patient(desk, "Chat Patient")
    clinic = str(w.a.clinic.id)

    llm.steps = [
        call(
            "book_appointment",
            patient_id=patient_id,
            session_id=session["id"],
            date=session["on_date"],
        )
    ]
    proposed = staff_turn(desk, clinic, user("book Chat Patient now")).get_json()
    assert proposed["kind"] == "CONFIRM" and "Chat Patient" in proposed["reply"]
    assert desk.get(f"/api/v1/patients/{patient_id}/appointments").get_json()["items"] == []
    done = staff_confirm(desk, clinic, proposed["proposal"]["token"])
    assert done.status_code == 200, done.get_json()
    [appointment] = desk.get(f"/api/v1/patients/{patient_id}/appointments").get_json()["items"]

    llm.steps = [
        call("cancel_appointment", appointment_id=appointment["id"], reason="PATIENT_REQUEST")
    ]
    cancel = staff_turn(desk, clinic, user("cancel it")).get_json()
    assert cancel["kind"] == "CONFIRM"
    assert staff_confirm(desk, clinic, cancel["proposal"]["token"]).status_code == 200
    [after] = desk.get(f"/api/v1/patients/{patient_id}/appointments").get_json()["items"]
    assert after["status"] == "CANCELLED"


def test_r8_staff_tokens_are_bound_to_the_user_and_the_clinic(world: World) -> None:
    llm = ScriptedLlm()
    w = with_llm(world, llm)
    owner, desk = w.client_for(w.a.owner), w.client_for(w.a.desk)
    session = running_session(owner, w.a.doctor.id)
    patient_id = _patient(desk, "Token Patient")
    llm.steps = [
        call(
            "book_appointment",
            patient_id=patient_id,
            session_id=session["id"],
            date=session["on_date"],
        )
    ]
    token = staff_turn(desk, str(w.a.clinic.id), user("book")).get_json()["proposal"]["token"]
    other_user = w.client_for(w.multi)  # front desk in A as well, but another user
    assert _code(staff_confirm(other_user, str(w.a.clinic.id), token)) == "AI_PROPOSAL_INVALID"
    other_clinic = w.client_for(w.b.owner)
    assert _code(staff_confirm(other_clinic, str(w.b.clinic.id), token)) == "AI_PROPOSAL_INVALID"


def test_staff_tools_never_include_clinical_ones_and_phones_are_masked(world: World) -> None:
    llm = ScriptedLlm()
    w = with_llm(world, llm)
    desk = w.client_for(w.a.desk)
    _patient(desk, "Masked Patient")
    llm.steps = [call("find_patient", text="Masked"), say("found")]
    staff_turn(desk, str(w.a.clinic.id), user("find Masked"))
    _, tools = llm.calls[0]
    names = {t.name for t in tools}
    assert names == {
        "today_queue",
        "list_sessions",
        "find_patient",
        "patient_appointments",
        "book_appointment",
        "cancel_appointment",
        "reschedule_appointment",
    }
    found = llm.tool_results()[0]["data"]["patients"][0]
    assert "*" in found["phone"] and not found["phone"].endswith("******")
