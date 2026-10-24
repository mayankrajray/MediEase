"""Favourites, templates and suggestions (FR-RX-05, FR-RX-10; spec R7; M4-P3 1A-5A). Pure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mediease_api.domain.prescriptions.errors import Stale
from mediease_api.domain.prescriptions.library import Favourite, Template, name_key
from mediease_api.domain.prescriptions.prescription import (
    Advice,
    PrescriptionItem,
    item_from_json,
    item_json,
)
from mediease_api.domain.prescriptions.schedule import Frequency
from mediease_api.domain.prescriptions.suggestions import (
    HistoryName,
    SuggestionSource,
    clean_query,
    rank,
)
from mediease_api.domain.prescriptions.vocabulary import (
    Preparation,
    PreparationCode,
    Timing,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import new_id

NOW = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)


def line(name: str = "Syrup X") -> PrescriptionItem:
    return PrescriptionItem.create(
        id=new_id(),
        position=1,
        medicine_name=name,
        dose="5 ml",
        frequency=Frequency.parse("1-0-1"),
        timing=Timing.AFTER_FOOD,
        preparation=[Preparation.of(PreparationCode.DILUTE_IN_WATER, "10 ml", "p")],
    )


def favourite(name: str, medicine: str, uses: int = 0) -> Favourite:
    fav = Favourite.create(
        id=new_id(), clinic_id=new_id(), doctor_id=new_id(), name=name, item=line(medicine), now=NOW
    )
    fav.use_count = uses
    return fav


def test_fr_rx_05_a_favourite_and_a_template_keep_a_draft_shaped_body() -> None:
    fav = favourite(" Fever syrup ", "Syrup X")
    assert (fav.name, fav.revision, fav.use_count, fav.last_used_at) == ("Fever syrup", 1, 0, None)
    body = item_json(fav.item)
    again = item_from_json(body, id=new_id(), position=3)
    assert item_json(again) == body and again.position == 3

    fav.replace(name="Fever", item=line("Syrup Y"), seen_revision=1, now=NOW)
    assert (fav.name, fav.item.medicine_name, fav.revision) == ("Fever", "Syrup Y", 2)
    with pytest.raises(Stale):
        fav.replace(name="x", item=line(), seen_revision=1, now=NOW)
    fav.record_use(NOW + timedelta(hours=1))
    assert (fav.use_count, fav.last_used_at) == (1, NOW + timedelta(hours=1))


def test_a_template_needs_content_and_a_sane_follow_up() -> None:
    template = Template.create(
        id=new_id(),
        clinic_id=new_id(),
        doctor_id=new_id(),
        name="Viral fever",
        items=[line()],
        advice=Advice.create(diet=["fluids"]),
        follow_up_days=5,
        now=NOW,
    )
    assert (template.follow_up_days, len(template.items)) == (5, 1)
    template.replace(
        name="Viral",
        items=[],
        advice=Advice.create(notes="rest"),
        follow_up_days=None,
        seen_revision=1,
        now=NOW,
    )
    assert (template.revision, template.items, template.follow_up_days) == (2, (), None)
    with pytest.raises(Stale):
        template.replace(
            name="x",
            items=[line()],
            advice=Advice(),
            follow_up_days=None,
            seen_revision=1,
            now=NOW,
        )
    template.record_use(NOW)
    assert template.use_count == 1
    for items, advice, days in (
        ([], Advice(), None),
        ([line()], Advice(), 0),
        ([line()], Advice(), 366),
    ):
        with pytest.raises(InvalidValue):
            Template.create(
                id=new_id(),
                clinic_id=new_id(),
                doctor_id=new_id(),
                name="x",
                items=items,
                advice=advice,
                follow_up_days=days,
                now=NOW,
            )
    with pytest.raises(InvalidValue):
        favourite("  ", "Syrup X")
    assert name_key("  Fever   SYRUP ") == "fever syrup"


def test_r7_favourites_come_first_then_history_by_visits_then_recency() -> None:
    favs = [favourite("a", "Syrup Kof", uses=1), favourite("b", "Syrup Amox", uses=4)]
    history = [
        HistoryName("syrup  kof", 9, NOW),  # also a favourite: shown once, as the favourite
        HistoryName("Syrup Para", 3, NOW - timedelta(days=9)),
        HistoryName("Syrup Zinc", 3, NOW),
        HistoryName("Syrup Iron", 7, NOW - timedelta(days=30)),
        HistoryName("Tab Para", 50, NOW),  # does not match
    ]
    ranked = rank("syr", favs, history)
    assert [(s.name, s.source) for s in ranked] == [
        ("Syrup Amox", SuggestionSource.FAVOURITE),
        ("Syrup Kof", SuggestionSource.FAVOURITE),
        ("Syrup Iron", SuggestionSource.HISTORY),
        ("Syrup Zinc", SuggestionSource.HISTORY),
        ("Syrup Para", SuggestionSource.HISTORY),
    ]
    assert ranked[0].favourite_id == favs[1].id and ranked[2].uses == 7


def test_ac5_nothing_outside_what_was_handed_in_and_the_cap() -> None:
    assert rank("Dru", [], [HistoryName("Drug P", 1, NOW)])[0].name == "Drug P"
    assert rank("Dru", [], []) == []
    many = [HistoryName(f"Syrup {i:02d}", i, NOW) for i in range(30)]
    assert len(rank("Syrup", [], many)) == 10


@pytest.mark.parametrize("raw", ["", " d ", "x" * 51])
def test_queries_are_two_to_fifty_characters(raw: str) -> None:
    with pytest.raises(InvalidValue):
        clean_query(raw)
    assert clean_query("  syr   up ") == "syr up"
