"""The fee schedule's rules (M6d-P1; FR-BIL-01; spec billing R1-R5, R10)."""

from __future__ import annotations

import pytest

from mediease_api.domain.billing.fees import (
    ClinicService,
    ServiceKind,
    ServiceNameTaken,
    check_unique_name,
    consultation_service,
    default_services,
    price_for,
)
from mediease_api.domain.billing.money import MAX_LINE_PAISE, check_price, percent_of
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id


def _service(
    name: str = "Dressing", kind: ServiceKind = ServiceKind.PROCEDURE, **kw: object
) -> ClinicService:
    fields: dict[str, object] = {
        "id": new_id(),
        "clinic_id": new_id(),
        "name": name,
        "kind": kind,
        "default_price_paise": 20000,
        "position": 3,
        "now": NOW,
    }
    fields.update(kw)
    return ClinicService.create(**fields)  # type: ignore[arg-type]


def test_b1_prices_are_whole_paise_up_to_one_lakh() -> None:
    assert check_price(0, "p") == 0 and check_price(MAX_LINE_PAISE, "p") == MAX_LINE_PAISE
    for bad in (-1, MAX_LINE_PAISE + 1):
        with pytest.raises(InvalidValue):
            check_price(bad, "p")
    with pytest.raises(InvalidValue):
        check_price(True, "p")  # type: ignore[arg-type]
    assert percent_of(12345, 1000) == 1235  # 10% of ₹123.45, half up
    assert percent_of(5, 1000) == 1  # 0.5 paisa rounds up


def test_r2_every_clinic_starts_with_consultation_and_follow_up_unpriced() -> None:
    clinic = new_id()
    services = default_services(clinic, (new_id() for _ in range(2)), NOW)
    assert [(s.name, s.kind, s.default_price_paise, s.position) for s in services] == [
        ("Consultation", ServiceKind.CONSULTATION, None, 1),
        ("Follow-up", ServiceKind.FOLLOW_UP, None, 2),
    ]
    assert all(s.active and s.clinic_id == clinic for s in services)


def test_r3_names_are_checked_and_unique_among_active_services() -> None:
    with pytest.raises(InvalidValue):
        _service(name=" ")
    with pytest.raises(InvalidValue):
        _service(name="x" * 81)
    first = _service(name="Dressing")
    with pytest.raises(ServiceNameTaken):
        check_unique_name([first], " dressing ")
    check_unique_name([first], "Dressing", except_id=first.id)  # renaming itself is fine
    first.change(now=NOW, active=False)
    check_unique_name([first], "Dressing")  # a retired name may be used again


def test_r4_a_doctors_own_price_wins_over_the_default() -> None:
    service = _service()
    doctor, other = new_id(), new_id()
    prices = {(service.id, doctor): 15000}
    assert price_for(service, doctor, prices) == 15000
    assert price_for(service, other, prices) == 20000
    assert price_for(service, None, prices) == 20000
    service.change(now=NOW, clear_default_price=True)
    assert price_for(service, other, prices) is None


def test_r5_only_the_values_given_change() -> None:
    service = _service()
    service.change(now=NOW, default_price_paise=25000)
    assert (service.name, service.kind, service.default_price_paise) == (
        "Dressing",
        ServiceKind.PROCEDURE,
        25000,
    )
    with pytest.raises(InvalidValue):
        service.change(now=NOW, default_price_paise=MAX_LINE_PAISE + 1)
    with pytest.raises(InvalidValue):
        service.change(now=NOW, position=0)
    assert service.default_price_paise == 25000


def test_r10_the_public_fee_is_the_first_active_consultation() -> None:
    later = _service(name="Evening consultation", kind=ServiceKind.CONSULTATION, position=5)
    first = _service(name="Consultation", kind=ServiceKind.CONSULTATION, position=1)
    assert consultation_service([later, first]) is first
    first.change(now=NOW, active=False)
    assert consultation_service([later, first]) is later
    assert consultation_service([_service()]) is None
