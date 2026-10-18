"""The template catalogue, the console provider and the phone cipher (M5-P2; decisions 1A, 2A)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from mediease_api.adapters.messaging.catalog import (
    TemplateFileInvalid,
    YamlTemplateCatalog,
    parse_templates,
)
from mediease_api.adapters.messaging.console import ConsoleMessagingAdapter
from mediease_api.adapters.security.phone_cipher import FernetPhoneCipher, PhoneDecryptionFailed
from mediease_api.domain.messaging.jobs import REQUIRED_TEMPLATES
from mediease_api.domain.messaging.message import Channel
from mediease_api.domain.messaging.template import TemplateCategory, VariableKind
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.messaging import OutboundTemplateMessage
from tests.conftest import LogReader

PHONE = PhoneNumber.parse("9000000001")

# --- The catalogue (R8, decision 2A) ------------------------------------------------------------


def test_the_shipped_templates_load_with_every_template_the_code_sends() -> None:
    catalog = YamlTemplateCatalog.from_package()
    assert catalog.template_keys() >= REQUIRED_TEMPLATES
    booking = catalog.get("booking_confirmed")
    assert [v.name for v in booking.variables] == [
        "clinic_name",
        "doctor_name",
        "date_time_or_token",
    ]
    assert set(booking.languages) == {Language.EN, Language.HI}
    assert catalog.get("opt_out_confirmed").category is TemplateCategory.SERVICE
    # R8: no template carries anything but the allowed kinds.
    for key in catalog.template_keys():
        for variable in catalog.get(key).variables:
            assert variable.kind in set(VariableKind)


def _file(body: str) -> str:
    """A complete file whose ``booking_confirmed`` entry is replaced by ``body``."""
    simple = """
    version: 1
    category: utility
    variables: [{ name: clinic_name, kind: clinic_name }]
    languages:
      en: { provider_name: x, body: "{{clinic_name}}" }
      hi: { provider_name: x, body: "{{clinic_name}}" }
"""
    others = "".join(
        f"  {key}:{simple}" for key in sorted(REQUIRED_TEMPLATES - {"booking_confirmed"})
    )
    return f"templates:\n  booking_confirmed:{body}\n{others}"


GOOD = """
    version: 1
    category: utility
    variables: [{ name: clinic_name, kind: clinic_name }]
    languages:
      en: { provider_name: x, body: "{{clinic_name}}" }
      hi: { provider_name: x, body: "{{clinic_name}}" }
"""


def test_a_well_formed_file_parses() -> None:
    assert parse_templates(_file(GOOD))["booking_confirmed"].version == 1


@pytest.mark.parametrize(
    ("text", "where"),
    [
        ("templates: [", "not valid YAML"),
        ("nothing: here", "'templates' is missing"),
        ("templates: [1, 2]", "must be a mapping"),
        ("templates:\n  booking_confirmed:" + GOOD, "missing templates"),
        (_file(GOOD.replace("kind: clinic_name", "kind: diagnosis")), "booking_confirmed"),
        (_file(GOOD.replace("category: utility", "category: marketing")), "booking_confirmed"),
        (
            _file(GOOD.replace('body: "{{clinic_name}}" }\n      hi', 'body: "hi" }\n      hi')),
            "body",
        ),
        (_file(GOOD.replace("    version: 1\n", "")), "'version' is missing"),
        (_file(GOOD.replace("      hi:", "      fr:")), "booking_confirmed"),
        ("templates:\n  booking_confirmed: !!python/object:os.system {}", "not valid YAML"),
    ],
)
def test_a_malformed_file_stops_start_up_naming_where(text: str, where: str) -> None:
    with pytest.raises(TemplateFileInvalid) as error:
        parse_templates(text)
    assert where in str(error.value)


# --- The console provider ----------------------------------------------------------------------


def test_the_console_provider_logs_names_not_values_and_repeats_its_answer(
    json_logs: LogReader,
) -> None:
    template = YamlTemplateCatalog.from_package().get("rx_ready")
    console = ConsoleMessagingAdapter()
    msg = OutboundTemplateMessage(
        idempotency_key="rx_link:1",
        to=PHONE,
        template=template,
        language=Language.EN,
        variables={"clinic_name": "Sample Clinic", "link": "https://app.example.test/p/secret-tok"},
    )
    first = console.send_template(msg)
    again = console.send_template(msg)
    assert first == again and console.calls == 2
    # IDs never repeat across adapters (a restarted worker): the column is unique.
    assert ConsoleMessagingAdapter().send_template(msg) != first
    assert (console.channel, console.provider) == (Channel.CONSOLE, "console")
    [one, two, _] = [e for e in json_logs() if e["event"] == "messaging.console_accepted"]
    assert (one["repeat"], two["repeat"]) == (False, True)
    assert one["variables"] == ["clinic_name", "link"]
    assert one["to"] == PHONE.masked()
    text = str(one)
    assert "secret-tok" not in text and "Sample Clinic" not in text and PHONE.e164 not in text
    assert "secret-tok" not in repr(msg) and PHONE.e164 not in repr(msg)


# --- The phone cipher (decision 1A) -------------------------------------------------------------


def test_phone_numbers_are_encrypted_differently_each_time_and_decrypt_back() -> None:
    cipher = FernetPhoneCipher([Fernet.generate_key()])
    one, two = cipher.encrypt(PHONE), cipher.encrypt(PHONE)
    assert one != two
    assert PHONE.e164[1:] not in one
    assert cipher.decrypt(one) == cipher.decrypt(two) == PHONE


def test_keys_rotate_new_first_and_an_unknown_key_fails_closed() -> None:
    old, new = Fernet.generate_key(), Fernet.generate_key()
    stored = FernetPhoneCipher([old]).encrypt(PHONE)
    rotated = FernetPhoneCipher([new, old])
    assert rotated.decrypt(stored) == PHONE
    assert FernetPhoneCipher([new]).decrypt(rotated.encrypt(PHONE)) == PHONE
    with pytest.raises(PhoneDecryptionFailed):
        FernetPhoneCipher([new]).decrypt(stored)
    with pytest.raises(PhoneDecryptionFailed):
        rotated.decrypt("not-a-token")
    with pytest.raises(ValueError):
        FernetPhoneCipher([])
