"""The English and Hindi phrasebook (spec prescriptions R20, D5; M4-P4 decision 4A)."""

from __future__ import annotations

import pytest

from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions import phrasebook
from mediease_api.domain.prescriptions.phrasebook import (
    ENGLISH,
    HINDI,
    phrase,
    placeholders,
    required_keys,
)


@pytest.mark.parametrize("language", list(Language))
def test_r20_every_label_and_vocabulary_code_has_a_phrase(language: Language) -> None:
    book = phrasebook.BOOKS[language]
    missing = sorted(k for k in required_keys() if not book.get(k, "").strip())
    assert missing == []


def test_r20_the_books_have_the_same_keys_and_placeholders() -> None:
    assert set(HINDI) == set(ENGLISH)
    for key, english in ENGLISH.items():
        assert placeholders(HINDI[key]) == placeholders(english), key


def test_r20_hindi_phrases_are_written_in_devanagari() -> None:
    # A label left in English would pass the completeness test; this catches it. The footer
    # names the product, so it keeps "MediEase" alongside Devanagari.
    def devanagari(text: str) -> bool:
        return any("\u0900" <= ch <= "\u097f" for ch in text)

    assert [k for k, v in HINDI.items() if not devanagari(v)] == []


def test_d5_a_missing_hindi_phrase_falls_back_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(phrasebook.BOOKS, Language.HI, {})
    assert phrase("title", Language.HI) == "Prescription"


def test_phrases_take_their_values() -> None:
    assert phrase("preparation.DILUTE_IN_WATER", Language.EN, amount="10 ml") == (
        "Mix in 10 ml of water"
    )
    assert phrase("storage.DISCARD_AFTER_DAYS", Language.HI, days=7) == ("खोलने के 7 दिन बाद फेंक दें")


def test_decision_4a_the_hindi_wording_is_marked_unreviewed_until_l07() -> None:
    assert phrasebook.HINDI_REVIEWED is False
