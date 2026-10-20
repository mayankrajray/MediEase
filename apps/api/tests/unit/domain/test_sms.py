"""The SMS fallback's rules, wording and console provider (M5-P5; FR-REM-06; decision 4A)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.adapters.messaging.console_sms import ConsoleSmsAdapter
from mediease_api.domain.messaging.errors import (
    MSG_NO_CONSENT,
    MSG_OUTCOME_UNKNOWN,
    MSG_PROVIDER_UNAVAILABLE,
    MSG_RECIPIENT_INVALID,
    MSG_TEMPLATE_NOT_FOUND,
    ProviderRefused,
)
from mediease_api.domain.messaging.message import (
    Channel,
    Message,
    MessageStatus,
    SourceType,
)
from mediease_api.domain.messaging.sms import falls_back_to_sms, sms_segments
from mediease_api.domain.messaging.template import (
    LocalisedBody,
    MessageTemplate,
    TemplateCategory,
    Variable,
    VariableKind,
)
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.messaging import OutboundTemplateMessage
from tests.builders import NOW, new_id

VALUES = {
    "clinic_name": "Sample Clinic",
    "doctor_name": "Dr Sample",
    "follow_up_date": "Tue 20 Oct 2026",
    "clinic_phone": "+919000000009",
}


def _failed(code: str, **changes: Any) -> Message:
    message = Message.prepare(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        source_type=SourceType.REMINDER,
        source_id=new_id(),
        channel=Channel.WHATSAPP,
        provider="whatsapp_cloud",
        template_key="follow_up_due",
        template_version=1,
        language=Language.EN,
        variables={},
        to_phone_encrypted="x",
        idempotency_key=f"k-{new_id()}",
        request_id=None,
        job_id=None,
        now=NOW,
    )
    message.fail(code, NOW)
    return replace(message, **changes)


@pytest.mark.parametrize("code", [MSG_RECIPIENT_INVALID, MSG_PROVIDER_UNAVAILABLE])
def test_fr_rem_06_a_definite_non_delivery_of_a_reminder_falls_back(code: str) -> None:
    assert falls_back_to_sms(_failed(code))


@pytest.mark.parametrize(
    ("code", "changes"),
    [
        (MSG_OUTCOME_UNKNOWN, {}),
        (MSG_NO_CONSENT, {}),
        (MSG_RECIPIENT_INVALID, {"channel": Channel.SMS}),
        (MSG_RECIPIENT_INVALID, {"source_type": SourceType.APPOINTMENT}),
        (MSG_RECIPIENT_INVALID, {"status": MessageStatus.SENT}),
    ],
    ids=["unknown-outcome", "skipped", "already-sms", "not-a-reminder", "not-failed"],
)
def test_fr_rem_06_nothing_else_falls_back(code: str, changes: dict[str, Any]) -> None:
    assert not falls_back_to_sms(_failed(code, **changes))


def test_sms_segments_follow_the_gsm_and_unicode_limits() -> None:
    assert sms_segments("a" * 160) == 1
    assert sms_segments("a" * 161) == 2
    assert sms_segments("a" * 306) == 2 and sms_segments("a" * 307) == 3
    assert sms_segments("ब" * 70) == 1
    assert sms_segments("ब" * 71) == 2
    assert sms_segments("") == 1


def test_follow_up_due_has_sms_wording_in_both_languages() -> None:
    template = YamlTemplateCatalog.from_package().get("follow_up_due")
    assert template.has_sms
    english = template.render_sms(Language.EN, VALUES)
    assert "Sample Clinic" in english and "+919000000009" in english
    assert sms_segments(english) == 1
    assert not YamlTemplateCatalog.from_package().get("rx_ready").has_sms


def _template(**sms: str) -> MessageTemplate:
    body = LocalisedBody(provider_name="t_v1", body="{{clinic_name}} {{link}}")
    return MessageTemplate.create(
        key="with_link",
        version=1,
        category=TemplateCategory.UTILITY,
        variables=(
            Variable("clinic_name", VariableKind.CLINIC_NAME),
            Variable("link", VariableKind.LINK),
        ),
        languages={Language.EN: body, Language.HI: body},
        sms={Language(k): v for k, v in sms.items()},
    )


def test_sms_wording_never_carries_a_link_and_needs_both_languages() -> None:
    with pytest.raises(InvalidValue, match="link"):
        _template(en="{{clinic_name}} {{link}}", hi="{{clinic_name}} {{link}}")
    with pytest.raises(InvalidValue, match="en and hi"):
        _template(en="{{clinic_name}} {{link}}")
    assert not _template().has_sms


def test_the_console_sms_provider_sends_sms_wording_and_refuses_a_template_without() -> None:
    catalog = YamlTemplateCatalog.from_package()
    sms = ConsoleSmsAdapter()
    assert (sms.channel, sms.provider) == (Channel.SMS, "console")

    def message(key: str, values: dict[str, str]) -> OutboundTemplateMessage:
        return OutboundTemplateMessage(
            idempotency_key=f"sms:{key}",
            to=PhoneNumber("+919000000001"),
            template=catalog.get(key),
            language=Language.HI,
            variables=values,
        )

    first = sms.send_template(message("follow_up_due", VALUES))
    assert sms.send_template(message("follow_up_due", VALUES)) == first  # same key, same ID
    with pytest.raises(ProviderRefused) as refused:
        sms.send_template(
            message("rx_ready", {"clinic_name": "Sample Clinic", "link": "https://x.test/l"})
        )
    assert refused.value.code == MSG_TEMPLATE_NOT_FOUND and not refused.value.retryable
