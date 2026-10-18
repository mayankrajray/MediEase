"""Message templates, messages and patient-facing formatting (M5-P2; spec R6-R8, FR-MSG-04)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mediease_api.domain.messaging.errors import (
    MSG_OUTCOME_UNKNOWN,
    MSG_PROVIDER_RATE_LIMIT,
    MSG_PROVIDER_UNAVAILABLE,
    MSG_RECIPIENT_INVALID,
    ProviderOutcomeUnknown,
    ProviderRefused,
    TemplateParamsInvalid,
)
from mediease_api.domain.messaging.formatting import appointment_when
from mediease_api.domain.messaging.jobs import booking_confirmation_key, rx_link_key
from mediease_api.domain.messaging.message import Channel, Message, MessageStatus, SourceType
from mediease_api.domain.messaging.template import (
    LINK_PLACEHOLDER,
    LocalisedBody,
    MessageTemplate,
    TemplateCategory,
    Variable,
    VariableKind,
)
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from tests.builders import NOW, new_id

VARIABLES = (
    Variable("clinic_name", VariableKind.CLINIC_NAME),
    Variable("link", VariableKind.LINK),
)


def _template(**overrides: object) -> MessageTemplate:
    fields: dict[str, object] = {
        "key": "rx_ready",
        "version": 2,
        "category": TemplateCategory.UTILITY,
        "variables": VARIABLES,
        "languages": {
            Language.EN: LocalisedBody("rx_ready_v2", "From {{clinic_name}}: {{link}}"),
            Language.HI: LocalisedBody("rx_ready_v2", "{{clinic_name}} से: {{link}}"),
        },
    }
    fields.update(overrides)
    return MessageTemplate.create(**fields)  # type: ignore[arg-type]


GOOD = {"clinic_name": "Sample Clinic", "link": "https://app.example.test/p/abc"}


# --- Templates (R8) -----------------------------------------------------------------------------


def test_r8_a_template_checks_values_and_keeps_the_link_out_of_storage() -> None:
    template = _template()
    assert template.check(GOOD) == GOOD
    assert template.stored(GOOD) == {"clinic_name": "Sample Clinic", "link": LINK_PLACEHOLDER}
    assert template.render(Language.HI, GOOD) == "Sample Clinic से: https://app.example.test/p/abc"
    assert template.body(Language.EN).provider_name == "rx_ready_v2"


@pytest.mark.parametrize(
    "values",
    [
        {"clinic_name": "Sample Clinic"},  # missing
        {**GOOD, "diagnosis": "x"},  # an extra variable is never passed on
        {**GOOD, "clinic_name": "  "},
        {**GOOD, "clinic_name": "A" * 201},
        {**GOOD, "clinic_name": "line one\nline two"},
        {**GOOD, "clinic_name": "too     many spaces"},
        {**GOOD, "link": "javascript:alert(1)"},
        {**GOOD, "link": 7},
    ],
)
def test_r8_values_outside_the_schema_are_refused_without_echoing_them(
    values: dict[str, object],
) -> None:
    with pytest.raises(TemplateParamsInvalid) as error:
        _template().check(values)  # type: ignore[arg-type]
    assert error.value.code == "MSG_TEMPLATE_PARAMS"
    assert "alert" not in str(error.value) and "line one" not in str(error.value)


def test_r8_a_phone_variable_must_be_e164() -> None:
    template = _template(
        key="follow_up_due",
        variables=(Variable("clinic_phone", VariableKind.PHONE),),
        languages={
            Language.EN: LocalisedBody("f", "Call {{clinic_phone}}"),
            Language.HI: LocalisedBody("f", "{{clinic_phone}} पर कॉल करें"),
        },
    )
    assert template.check({"clinic_phone": "+919000000001"})
    with pytest.raises(TemplateParamsInvalid):
        template.check({"clinic_phone": "9000000001"})


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"key": "Bad Key"}, "key"),
        ({"version": 0}, "rx_ready.version"),
        ({"variables": (*VARIABLES, VARIABLES[0])}, "rx_ready.variables"),
        ({"languages": {Language.EN: LocalisedBody("x", "{{clinic_name}} {{link}}")}}, "languages"),
        (
            {
                "languages": {
                    Language.EN: LocalisedBody("x", "{{link}} {{clinic_name}}"),
                    Language.HI: LocalisedBody("x", "{{clinic_name}} {{link}}"),
                }
            },
            "rx_ready.en.body",
        ),
        (
            {
                "languages": {
                    Language.EN: LocalisedBody(" ", "{{clinic_name}} {{link}}"),
                    Language.HI: LocalisedBody("x", "{{clinic_name}} {{link}}"),
                }
            },
            "rx_ready.en.provider_name",
        ),
        (
            {
                "languages": {
                    Language.EN: LocalisedBody("x", "{{clinic_name}} {{link}} {{patient}}"),
                    Language.HI: LocalisedBody("x", "{{clinic_name}} {{link}}"),
                }
            },
            "rx_ready.en.body",
        ),
    ],
)
def test_a_malformed_template_is_refused(overrides: dict[str, object], field: str) -> None:
    with pytest.raises(InvalidValue) as error:
        _template(**overrides)
    assert field in error.value.details["field"]


# --- Messages (R6, R7, decision 4A) -------------------------------------------------------------


def _message() -> Message:
    return Message.prepare(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        source_type=SourceType.APPOINTMENT,
        source_id=new_id(),
        channel=Channel.CONSOLE,
        provider="console",
        template_key="booking_confirmed",
        template_version=1,
        language=Language.EN,
        variables={"clinic_name": "Sample Clinic"},
        to_phone_encrypted="ciphertext",
        idempotency_key="booking_confirmed:x",
        request_id="req-1",
        job_id=new_id(),
        now=NOW,
    )


def test_r6_a_message_is_written_as_started_before_the_provider_call() -> None:
    message = _message()
    assert (message.status, message.sending_started_at) == (MessageStatus.QUEUED, NOW)
    assert message.outcome_unknown  # if found like this later, the call may have happened
    assert "ciphertext" not in repr(message) and "Sample" not in repr(message)


def test_r7_a_refused_message_can_be_restarted_and_then_accepted() -> None:
    message = _message()
    later = NOW + timedelta(minutes=1)
    message.refused(MSG_PROVIDER_RATE_LIMIT, later)
    assert (message.status, message.error_code, message.sending_started_at) == (
        MessageStatus.QUEUED,
        MSG_PROVIDER_RATE_LIMIT,
        None,
    )
    assert not message.outcome_unknown
    message.restart(variables={"a": "b"}, to_phone_encrypted="new", job_id=None, now=later)
    with pytest.raises(InvalidTransition):  # never two calls at once
        message.restart(variables={}, to_phone_encrypted="x", job_id=None, now=later)
    message.accepted(provider_message_id="p-1", now=later)
    assert (message.status, message.sent_at, message.error_code) == (
        MessageStatus.SENT,
        later,
        None,
    )
    assert message.is_accepted and message.sending_started_at is None
    for change in (
        lambda: message.fail(MSG_OUTCOME_UNKNOWN, later),
        lambda: message.refused(MSG_PROVIDER_RATE_LIMIT, later),
        lambda: message.accepted(provider_message_id="p-2", now=later),
    ):
        with pytest.raises(InvalidTransition):
            change()


def test_a_failed_message_records_the_code_and_the_time() -> None:
    message = _message()
    message.fail(MSG_OUTCOME_UNKNOWN, NOW)
    assert (message.status, message.error_code, message.failed_at) == (
        MessageStatus.FAILED,
        MSG_OUTCOME_UNKNOWN,
        NOW,
    )
    assert not message.is_accepted and not message.outcome_unknown


def test_r7_only_rate_limits_and_outages_are_retryable() -> None:
    assert ProviderRefused(MSG_PROVIDER_RATE_LIMIT).retryable
    assert ProviderRefused(MSG_PROVIDER_UNAVAILABLE).retryable
    assert not ProviderRefused(MSG_RECIPIENT_INVALID).retryable
    assert str(ProviderRefused(MSG_RECIPIENT_INVALID)) == MSG_RECIPIENT_INVALID
    assert str(ProviderOutcomeUnknown()) == MSG_OUTCOME_UNKNOWN


def test_keys_name_the_thing_they_confirm() -> None:
    some = new_id()
    assert booking_confirmation_key(some) == f"booking_confirmed:{some}"
    assert rx_link_key(some) == f"rx_link:{some}"


# --- Formatting in the clinic's time zone -------------------------------------------------------


def test_appointment_times_read_in_the_clinic_zone_in_both_languages() -> None:
    at = datetime(2026, 10, 20, 5, 0, tzinfo=UTC)  # 10:30 in Kolkata
    assert (
        appointment_when(
            starts_at=at, token_number=None, timezone="Asia/Kolkata", language=Language.EN
        )
        == "Tue 20 Oct 2026, 10:30 AM"
    )
    assert (
        appointment_when(
            starts_at=at, token_number=12, timezone="Asia/Kolkata", language=Language.HI
        )
        == "20/10/2026, 10:30, टोकन 12"
    )
    late = datetime(2026, 10, 20, 19, 0, tzinfo=UTC)  # 00:30 the next day
    assert appointment_when(
        starts_at=late, token_number=3, timezone="Asia/Kolkata", language=Language.EN
    ) == ("Wed 21 Oct 2026, 12:30 AM, token 3")
    noon = datetime(2026, 10, 20, 6, 30, tzinfo=UTC)
    assert appointment_when(
        starts_at=noon, token_number=None, timezone="Asia/Kolkata", language=Language.EN
    ).endswith("12:00 PM")
