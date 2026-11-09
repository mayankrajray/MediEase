"""Guard rails (M7a-P3; FR-AI-02; spec assistant R4, R5, R10; AC2). A CI gate."""

from __future__ import annotations

import pytest

from mediease_api.domain.assistant.guard_rails import (
    REFERRAL,
    ReferralReason,
    numbers_in,
    referral_reason,
    reply_is_grounded,
    reply_is_safe,
)
from mediease_api.domain.patients.patient import Language

ADVICE = [
    # Dose and drug changes
    ("Can I take two tablets instead of one?", ReferralReason.DOSE_CHANGE),
    ("Should I increase the dose?", ReferralReason.DOSE_CHANGE),
    ("Can I stop taking the syrup now?", ReferralReason.DOSE_CHANGE),
    ("I missed a dose, what now?", ReferralReason.DOSE_CHANGE),
    ("Can I double the tablet tonight?", ReferralReason.DOSE_CHANGE),
    ("Is it ok with alcohol?", ReferralReason.DOSE_CHANGE),
    ("Can I take extra medicine for the pain?", ReferralReason.DOSE_CHANGE),
    ("दवा बंद कर दूँ?", ReferralReason.DOSE_CHANGE),
    ("dawa band kar du kya", ReferralReason.DOSE_CHANGE),
    # Results
    ("Is my sugar 180 high?", ReferralReason.RESULTS),
    ("My BP reading is 150, is that normal?", ReferralReason.RESULTS),
    ("What does my report mean?", ReferralReason.RESULTS),
    ("मेरी रिपोर्ट ठीक है?", ReferralReason.RESULTS),
    # Drug suggestions and information
    ("Which medicine is good for a cough?", ReferralReason.DRUG_ADVICE),
    ("Can you suggest something for my headache?", ReferralReason.DRUG_ADVICE),
    ("What are the side effects?", ReferralReason.DRUG_ADVICE),
    ("What is this medicine for?", ReferralReason.DRUG_ADVICE),
    ("Is it safe during pregnancy?", ReferralReason.DRUG_ADVICE),
    ("Is there a generic substitute?", ReferralReason.DRUG_ADVICE),
    ("कौन सी दवा लूँ?", ReferralReason.DRUG_ADVICE),
    # Diagnosis
    ("Do I have an infection?", ReferralReason.DIAGNOSIS),
    ("What is wrong with me?", ReferralReason.DIAGNOSIS),
    ("Could it be dengue?", ReferralReason.DIAGNOSIS),
    ("Please diagnose my rash", ReferralReason.DIAGNOSIS),
    ("क्या मुझे बुखार की बीमारी है?", ReferralReason.DIAGNOSIS),
    # Treatment
    ("What should I do for a fever?", ReferralReason.TREATMENT),
    ("Any home remedy for cold?", ReferralReason.TREATMENT),
    ("Should I eat rice?", ReferralReason.TREATMENT),
    # Emergencies
    ("I have chest pain", ReferralReason.EMERGENCY),
    ("my child is unconscious", ReferralReason.EMERGENCY),
    ("सीने में दर्द है", ReferralReason.EMERGENCY),
    # M7c-P1: advice words about the doctor still refer when they ask for a change or a new drug
    ("Did the doctor say I can stop the medicine?", ReferralReason.DOSE_CHANGE),
    ("Can you suggest a diet for diabetes?", ReferralReason.DRUG_ADVICE),
    ("What can I eat for a fever?", ReferralReason.TREATMENT),
    # M7c-P2: Hinglish
    ("kya main do goli le lu", ReferralReason.DOSE_CHANGE),
    ("goli chhod du kya", ReferralReason.DOSE_CHANGE),
    ("dawai bhool gaya ab kya karu", ReferralReason.DOSE_CHANGE),
    ("khansi ke liye konsi dawai lu", ReferralReason.DRUG_ADVICE),
    ("ye goli kis liye hai", ReferralReason.DRUG_ADVICE),
    ("kya mujhe dengue hai", ReferralReason.DIAGNOSIS),
    ("bukhar me kya khau", ReferralReason.TREATMENT),
    ("sardi ka gharelu nuskha batao", ReferralReason.TREATMENT),
    ("mera sugar 180 zyada hai kya", ReferralReason.RESULTS),
    ("seene mein dard ho raha hai", ReferralReason.EMERGENCY),
]

RESTATING = [
    "When do I take my medicine?",
    "How long do I take the syrup?",
    "What did the doctor write?",
    "Explain my prescription",
    "Explain medicine 2",
    "How do I give the drops?",
    "How much syrup do I give?",
    "When is my next visit?",
    "I want to book an appointment at Alpha Sample Clinic",
    "Do I have an appointment tomorrow?",
    "Show my appointments",
    "the first one, 9000000777",
    "book on 28/10 please",
    "दवा कब लेनी है?",
    "मेरी अपॉइंटमेंट दिखाओ",
    "show today's queue",
    "find patient Asha",
    # M7c-P1: the developer's own questions about what the doctor wrote (4 Nov 2026)
    "is there any other advice that doctor mentioned in the prescription?",
    "name the medicine that is listed in the prescription",
    "What did the doctor suggest?",
    "What did the doctor recommend for food?",
    "What has the doctor advised about rest?",
    "What can I eat as per the prescription?",
    "Should I avoid anything according to my prescription?",
    "What diet did the doctor tell me to follow?",
    "डॉक्टर ने क्या सलाह दी है?",
    # M7c-P2: Hinglish
    "doctor ne kya likha hai",
    "doctor ne khane ke liye kya bola",
    "parche mein aur kya likha hai",
    "dawai kab leni hai",
    "kal ka appointment chahiye",
    "mera appointment dikhao",
    "Asha ka appointment kal ke liye book karo",
]


@pytest.mark.parametrize(("question", "reason"), ADVICE)
def test_fr_ai_02_advice_requests_are_referred(question: str, reason: ReferralReason) -> None:
    assert referral_reason(question) is reason


@pytest.mark.parametrize("question", RESTATING)
def test_fr_ai_02_restating_and_booking_questions_pass(question: str) -> None:
    assert referral_reason(question) is None


def test_the_referral_exists_in_both_languages_and_names_the_emergency_number() -> None:
    for language in Language:
        assert "112" in REFERRAL[language]


@pytest.mark.parametrize(
    "reply",
    [
        "You should take two tablets.",
        "I recommend paracetamol.",
        "It sounds like you have a cold.",
        "Your sugar is high.",
        "Common side effects are nausea.",
        "You may have an infection.",
        "180 is within the normal range.",
    ],
)
def test_r5_advice_phrasing_in_a_reply_is_unsafe(reply: str) -> None:
    assert not reply_is_safe(reply)


def test_r5_the_doctors_own_words_are_not_mistaken_for_advice() -> None:
    warning = "You should avoid alcohol while taking this"
    assert not reply_is_safe(f"The doctor wrote: {warning}.")
    assert reply_is_safe(f"The doctor wrote: {warning}.", own_words={warning})


def test_r10_grounding_allows_only_the_records_numbers() -> None:
    allowed = numbers_in("1. Syrup X 5 ml, twice a day, 5 days, next visit 24 Oct 2026")
    assert reply_is_grounded("Take 5 ml for 5 days (medicine 1).", allowed)
    assert not reply_is_grounded("Take 10 ml for 5 days.", allowed)
    assert numbers_in("2,5 and 3.5") == {"2.5", "3.5"}
