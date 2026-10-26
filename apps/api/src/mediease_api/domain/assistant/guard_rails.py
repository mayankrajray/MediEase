"""Guard rails before and after the model (M7a-P3; FR-AI-02; spec assistant R4, R5; ADR-0024).

**Before:** ``referral_reason`` reads the user's last message. A request for a diagnosis, for the
meaning of a result, to change, stop, start or choose a medicine or dose, for treatment advice, or
an emergency, gets the fixed referral and is never sent to the model. Questions that only ask what
the doctor wrote ("when do I take it", "how long", "what did the doctor say") pass: the assistant
answers those from the record.

**After:** ``reply_is_safe`` refuses a model reply with advice phrasing, once the doctor's own
words (which may say "avoid alcohol") are taken out, and ``reply_is_grounded`` refuses a reply
about a prescription that uses a number the record does not contain.

The patterns are deliberately broad: a wrongly referred question costs the user a phone call; a
wrongly answered one could hurt them. English and Hindi (Devanagari and common romanised words).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum

from mediease_api.domain.patients.patient import Language


class ReferralReason(StrEnum):
    DIAGNOSIS = "DIAGNOSIS"
    RESULTS = "RESULTS"
    DOSE_CHANGE = "DOSE_CHANGE"
    DRUG_ADVICE = "DRUG_ADVICE"
    TREATMENT = "TREATMENT"
    EMERGENCY = "EMERGENCY"


REFERRAL: dict[Language, str] = {
    Language.EN: (
        "I can't give medical advice, so I can't answer that. Please ask your doctor or call "
        "your clinic. If this is an emergency, call 112 or go to the nearest hospital now."
    ),
    Language.HI: (
        "मैं चिकित्सा सलाह नहीं दे सकता, इसलिए इसका उत्तर नहीं दे सकता। कृपया अपने डॉक्टर से पूछें "
        "या अपने क्लिनिक को फ़ोन करें। आपात स्थिति हो तो अभी 112 पर कॉल करें या नज़दीकी अस्पताल जाएँ।"
    ),
}

_MED = (
    r"(?:dose|doses|dosage|tablet|tablets|tab|tabs|pill|pills|capsule|capsules|medicine|medicines"
    r"|medication|drug|drugs|syrup|drops?|injection|insulin|antibiotics?|mg|ml|dawa|dawai|goli)"
)

_PATTERNS: tuple[tuple[ReferralReason, tuple[str, ...]], ...] = (
    (
        ReferralReason.EMERGENCY,
        (
            r"\bchest pain\b",
            r"\bcan'?t breathe\b",
            r"\bcannot breathe\b",
            r"\bnot breathing\b",
            r"\bunconscious\b",
            r"\bfaint(?:ed|ing)\b",
            r"\bseizures?\b|\bconvulsion",
            r"\boverdose\b",
            r"\bpoison",
            r"\bsuicid",
            r"\bkill myself\b",
            r"\bheavy bleeding\b|\bbleeding (?:a lot|heavily)\b",
            r"सीने में दर्द",
            r"साँस नहीं|सांस नहीं",
            r"बेहोश",
        ),
    ),
    (
        ReferralReason.RESULTS,
        (
            r"\b(?:report|reports|result|results|test|tests|scan|x-?ray|ecg|mri|ultrasound"
            r"|blood|sugar|glucose|bp|pressure|cholesterol|hba1c|thyroid|tsh|level|levels|reading"
            r"|count|hemoglobin|haemoglobin)\b.*\b(?:high|low|normal|mean|means|okay|ok|bad|good"
            r"|fine|worry|serious|dangerous|range)\b",
            r"\b(?:high|low|normal)\b.*\b(?:report|result|sugar|glucose|bp|pressure|level|levels"
            r"|reading|count)\b",
            r"\binterpret",
            r"\bwhat does (?:my|the|this) (?:report|result|test|scan)\b",
            r"रिपोर्ट",
            r"शुगर",
        ),
    ),
    (
        ReferralReason.DOSE_CHANGE,
        (
            rf"\b(?:increase|decrease|reduce|lower|raise|double|halve|half|skip|stop|quit|change"
            rf"|cut)\b.*\b{_MED}\b",
            rf"\b{_MED}\b.*\b(?:increase|decrease|reduce|double|halve|skip|stop|quit|change)\b",
            rf"\b(?:more|extra|another|less|fewer)\s+(?:of (?:the |my )?)?{_MED}\b",
            r"\binstead of\b",
            r"\bmiss(?:ed)? (?:a |my |the )?(?:dose|tablet|pill|medicine)\b",
            r"\bforgot (?:to take|my|the)\b",
            r"\bwith (?:alcohol|beer|wine|whisky|another medicine|other medicine)\b",
            r"\btogether with\b",
            r"\bstop taking\b",
            r"दवा (?:बंद|छोड़|बढ़ा|घटा|कम|ज़्यादा)",
            r"(?:बंद|छोड़|बढ़ा|घटा) (?:कर|दूँ|दू|दें)",
            r"\b(?:band|chhod|badha|ghata)\b.*\b(?:dawa|dawai|goli)\b",
            r"\b(?:dawa|dawai|goli)\b.*\b(?:band|chhod|badha|ghata|kam|zyada)\b",
        ),
    ),
    (
        ReferralReason.DRUG_ADVICE,
        (
            rf"\b(?:which|what|any|some|a)\s+(?:good\s+)?{_MED}\b.*\b(?:for|should|can|to take|take"
            rf"|help|works?|best)\b",
            r"\b(?:suggest|recommend|prescribe)\b",
            r"\bside[- ]effects?\b",
            r"\binteract",
            r"\b(?:substitute|alternative|generic|equivalent|brand)\b",
            rf"\bwhat is (?:it|this|that|this {_MED}|the {_MED}|{_MED} \d+) (?:used )?for\b",
            rf"\bwhat (?:does|is) (?:it|this|that|this {_MED}|the {_MED}) (?:do|treat|cure)\b",
            r"\bsafe (?:to take|during|in|for|while)\b|\bis (?:it|this) safe\b",
            r"\bpregnan",
            r"\ballerg",
            r"कौन सी दवा|कौनसी दवा|कोई दवा",
            r"\b(?:kaun si|koi) (?:dawa|dawai|goli)\b",
        ),
    ),
    (
        ReferralReason.DIAGNOSIS,
        (
            r"\bdiagnos",
            r"\bwhat(?:'s| is) wrong with me\b",
            r"\bdo i have (?:a |an )?(?:disease|infection|cancer|diabetes|covid|dengue|malaria"
            r"|typhoid|fever|problem|condition|illness|allergy)\b",
            r"\bcould (?:it|this) be\b",
            r"\bis (?:it|this) (?:serious|cancer|infection|covid|dengue|malaria|typhoid"
            r"|contagious)\b",
            r"\bwhat (?:disease|illness|condition|infection)\b",
            r"\bwhy (?:do|does|am) (?:i|my)\b.*\b(?:hurt|pain|ache|feel|sick|dizzy|swollen)\b",
            r"\b(?:symptom|symptoms)\b",
            r"क्या मुझे .*(?:बीमारी|रोग|इन्फेक्शन|संक्रमण|बुखार|कैंसर|डायबिटीज़|डायबिटीज) है",
            r"(?:कौन सी|क्या) बीमारी",
            r"\bbimari\b",
        ),
    ),
    (
        ReferralReason.TREATMENT,
        (
            r"\bhow (?:do|can|should) i (?:treat|cure|fix|get rid of|heal)\b",
            r"\b(?:home remed|remedy|remedies|cure for|treatment for)\b",
            r"\bwhat (?:should|can|do) i (?:do|take|eat|drink|use|apply)\b.*\b(?:pain|fever|cough"
            r"|cold|vomit|vomiting|rash|itch|itching|ache|headache|diarrh|loose motion|burn|cut"
            r"|swelling|infection)",
            r"\bshould i (?:go to|see|visit) (?:a|the) (?:hospital|doctor|specialist)\b",
            r"\bshould i (?:eat|drink|avoid|exercise|rest|apply|use)\b",
            r"\bwhat can i (?:eat|drink)\b",
            r"क्या (?:खाऊँ|खाना चाहिए|पीना चाहिए|करूँ)",
            r"इलाज",
            r"\bilaj\b",
        ),
    ),
)

_COMPILED = tuple(
    (reason, tuple(re.compile(p, re.IGNORECASE) for p in ps)) for reason, ps in _PATTERNS
)


def referral_reason(text: str) -> ReferralReason | None:
    """The reason this message must be referred to the clinic, or ``None`` if it may go on."""
    normalised = " ".join(text.replace("\u2019", "'").split())
    for reason, patterns in _COMPILED:
        if any(p.search(normalised) for p in patterns):
            return reason
    return None


_UNSAFE_REPLY = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\byou (?:should|must|need to|can|could|may|might want to|ought to) (?:take|stop|increase"
        r"|decrease|reduce|double|skip|try|use|start|avoid|switch|change|apply|drink|eat)\b",
        r"\bi (?:would )?(?:recommend|suggest|advise)\b",
        r"\b(?:sounds|looks|seems) like (?:you|it|this)\b",
        r"\byou (?:may|might|probably|likely) have\b",
        r"\bdiagnos",
        r"\bnormal range\b",
        r"\b(?:is|are|looks|seems) (?:high|low|normal|elevated|within range)\b",
        r"\bside[- ]effects?\b",
        r"\binteract",
        r"\b(?:it is|it's) safe to\b",
        r"\binstead of (?:the|your)\b",
        r"आपको .* (?:लेनी|लेना|बंद) (?:चाहिए|करनी)",
        r"मेरी सलाह",
    )
)


def _without(text: str, own_words: Iterable[str]) -> str:
    for words in sorted({w for w in own_words if w}, key=len, reverse=True):
        text = text.replace(words, " ")
    return text


def reply_is_safe(reply: str, *, own_words: Iterable[str] = ()) -> bool:
    """False if the reply reads like advice, once the doctor's own words are taken out."""
    rest = _without(reply, own_words)
    return not any(p.search(rest) for p in _UNSAFE_REPLY)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> frozenset[str]:
    return frozenset(m.group(0).replace(",", ".") for m in _NUMBER.finditer(text))


def reply_is_grounded(reply: str, allowed: frozenset[str]) -> bool:
    """FR-AI-04: every number in a reply about a prescription is in its record (doses, times,
    days, dates, the medicine numbers). A number the model made up fails."""
    return numbers_in(reply) <= allowed
