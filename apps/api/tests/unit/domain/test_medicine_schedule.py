"""The medicine-schedule engine (M6b-P3; D1-D3, D8, D9; prescriptions R21-R25; portal R28-R39).

Pure: ``schedule.py`` (slots, patterns, duration kinds), ``plan.py`` (a day, a course), the
wording, the layout-2 schedule rows and the patient's own settings.
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import date, time, timedelta

import pytest

from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.medicines import MedicineReminderPref, SlotTimes
from mediease_api.domain.prescriptions.document import (
    duration_field,
    frequency_words,
    schedule_rows,
)
from mediease_api.domain.prescriptions.patient_view import build_patient_view
from mediease_api.domain.prescriptions.plan import (
    ENDED_SHOWN_DAYS,
    LineWarning,
    PlanSource,
    course_start,
    courses,
    is_remindable,
    line_warnings,
    plan_for_day,
)
from mediease_api.domain.prescriptions.prescription import (
    START_WINDOW_DAYS,
    Prescription,
    PrescriptionItem,
    item_from_json,
    item_json,
)
from mediease_api.domain.prescriptions.schedule import (
    SLOT_SETS,
    DurationKind,
    Frequency,
    FrequencyKind,
    Slot,
)
from mediease_api.domain.prescriptions.vocabulary import Timing
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import new_id
from tests.unit.domain.test_prescriptions import NOW, TODAY, draft, filled
from tests.unit.domain.test_rx_document import issued

TZ = "Asia/Kolkata"
M, A, E, N = Slot.MORNING, Slot.AFTERNOON, Slot.EVENING, Slot.NIGHT


def line(
    position: int = 1,
    *,
    frequency: str | None = "1-0-1",
    timing: Timing | None = None,
    days: int | None = 5,
    kind: DurationKind | None = None,
    custom: str | None = None,
    name: str = "Tab Sample",
) -> PrescriptionItem:
    return PrescriptionItem.create(
        id=new_id(),
        position=position,
        medicine_name=name,
        dose="1 tablet",
        frequency=Frequency.parse(frequency) if frequency else None,
        frequency_text=custom,
        timing=timing,
        duration_days=days,
        duration_kind=kind,
    )


def rx_with(*items: PrescriptionItem, starts_on: date | None = None) -> Prescription:
    rx = issued()
    rx.items = tuple(items)
    rx.starts_on = starts_on
    return rx


def source(rx: Prescription, clinic: str = "Alpha Sample Clinic") -> PlanSource:
    return PlanSource(rx, rx.clinic_id, clinic, TZ)


# --- Patterns (D1, R21) --------------------------------------------------------------------------


def _all_patterns() -> list[str]:
    found = []
    for length in SLOT_SETS:
        for digits in itertools.product("01", repeat=length):
            if "1" in digits:
                found.append("-".join(digits))
    return found


@pytest.mark.parametrize("pattern", _all_patterns())
def test_d1_every_binary_pattern_marks_exactly_its_ones(pattern: str) -> None:
    digits = pattern.split("-")
    freq = Frequency.parse(pattern)
    assert freq.value == pattern and freq.kind is FrequencyKind.PATTERN
    expected = tuple(s for s, d in zip(SLOT_SETS[len(digits)], digits, strict=True) if d == "1")
    assert freq.slots == expected
    # Written without dashes or with spaces, it is the same pattern.
    assert Frequency.parse("".join(digits)) == freq == Frequency.parse(" ".join(digits))


def test_d1_there_are_21_patterns_and_two_slot_sets() -> None:
    assert len(_all_patterns()) == 7 + 15
    assert SLOT_SETS[3] == (M, A, N) and SLOT_SETS[4] == (M, A, E, N)
    with pytest.raises(TypeError):
        SLOT_SETS[5] = (M,)  # type: ignore[index]


@pytest.mark.parametrize(
    "raw",
    ["000", "0-0-0", "0-0-0-0", "2-0-2", "½-0-½", "1-0", "10", "1-0-1-0-1", "", "x", "1-0-1/2"],
)
def test_d1_other_patterns_are_refused_without_echoing_the_value(raw: str) -> None:
    with pytest.raises(InvalidValue) as error:
        Frequency.parse(raw, "items.2.frequency")
    assert error.value.field == "items.2.frequency"
    # One fixed hint for every refused value: nothing of what was written comes back.
    assert (
        error.value.reason == "use 0 and 1 for 3 or 4 times of day (e.g. 1-0-1), or choose CUSTOM"
    )


def test_d1_sos_once_custom_have_no_slots_and_are_never_reminded() -> None:
    for raw, freq in (
        ("sos", Frequency.SOS),
        ("Once", Frequency.ONCE),
        ("CUSTOM", Frequency.CUSTOM),
    ):
        assert Frequency.parse(raw) == freq and freq.slots == ()
    assert not is_remindable(line(frequency="SOS"))
    assert not is_remindable(line(frequency="CUSTOM", custom="every 6 hours"))
    assert not is_remindable(line(frequency=None))
    assert is_remindable(line(frequency="0-0-1-0"))


def test_a_stored_value_must_already_be_canonical() -> None:
    assert Frequency("1-1-0").slots == (M, A)
    for bad in ("110", "0-0-0", "1-1"):
        with pytest.raises(InvalidValue):
            Frequency(bad)


# --- Wording (prescriptions R21; the 1-1-1 change) -----------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "en"),
    [
        ("1-0-0", "Once a day, in the morning"),
        ("0-0-1", "Once a day, at night"),
        ("1-0-1", "Twice a day, morning and night"),
        ("1-1-0", "Twice a day, morning and afternoon"),
        ("1-1-1", "Three times a day, morning, afternoon and night"),
        ("0-0-1-0", "Once a day, in the evening"),
        ("1-1-1-1", "Four times a day, morning, afternoon, evening and night"),
    ],
)
def test_r21_a_pattern_is_worded_from_its_slots(pattern: str, en: str) -> None:
    assert frequency_words(Frequency.parse(pattern), None, Language.EN) == en


def test_r21_hindi_wording_and_the_doctors_custom_words_as_written() -> None:
    hi = frequency_words(Frequency.parse("1-0-1"), None, Language.HI)
    assert hi == "दिन में दो बार, सुबह और रात"
    assert frequency_words(Frequency.CUSTOM, "every 6 hours", Language.HI) == "every 6 hours"
    assert frequency_words(Frequency.SOS, None, Language.EN) == "Only when needed"


# --- Bedtime (D2, R22) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        ("1-0-0", (LineWarning.BEDTIME_WITHOUT_NIGHT,)),
        ("0-1-0-0", (LineWarning.BEDTIME_WITHOUT_NIGHT,)),
        ("1-0-1", (LineWarning.BEDTIME_WITH_OTHER_SLOTS,)),
        ("0-0-1", ()),
        ("0-0-0-1", ()),
        ("SOS", (LineWarning.BEDTIME_UNTIMED,)),
        (None, ()),
    ],
)
def test_d2_bedtime_is_a_warning_for_the_doctor_only(
    frequency: str | None, expected: tuple[LineWarning, ...]
) -> None:
    item = line(frequency=frequency, timing=Timing.BEDTIME)
    assert line_warnings(item) == expected
    assert line_warnings(replace(item, timing=Timing.AFTER_FOOD)) == ()


def test_d2_the_plan_shows_a_bedtime_line_in_its_own_slots() -> None:
    rx = rx_with(line(frequency="1-0-0", timing=Timing.BEDTIME))
    day = plan_for_day([source(rx)], course_start(rx, TZ))
    assert [d.slot for d in day.doses] == [M]


# --- Duration and start (D3, R23, R24) -----------------------------------------------------------


def test_d3_days_alone_is_days_and_the_kinds_go_with_days_only_for_days() -> None:
    assert line(days=5).duration_kind is DurationKind.DAYS
    assert line(days=None, kind=DurationKind.ONGOING).duration_days is None
    assert line(days=None).duration_kind is None
    for days, kind in ((None, DurationKind.DAYS), (5, DurationKind.UNTIL_REVIEW)):
        with pytest.raises(InvalidValue, match="duration_days"):
            line(days=days, kind=kind)


def test_d3_a_body_from_before_m6b_p3_reads_its_days_as_days() -> None:
    old = item_json(line(days=7))
    old.pop("duration_kind")
    again = item_from_json(old, id=new_id(), position=1)
    assert (again.duration_kind, again.duration_days) == (DurationKind.DAYS, 7)
    kept = item_from_json(
        item_json(line(days=None, kind=DurationKind.UNTIL_REVIEW)), id=new_id(), position=1
    )
    assert kept.duration_kind is DurationKind.UNTIL_REVIEW


def test_r24_a_start_within_30_days_and_none_means_the_issue_day() -> None:
    rx = draft()
    for days in (-START_WINDOW_DAYS, 0, START_WINDOW_DAYS):
        rx.replace_body(
            items=[line()],
            advice=rx.advice,
            follow_up_date=None,
            seen_revision=rx.revision,
            today=TODAY,
            now=NOW,
            starts_on=TODAY + timedelta(days=days),
        )
    with pytest.raises(InvalidValue, match="starts_on"):
        rx.replace_body(
            items=[line()],
            advice=rx.advice,
            follow_up_date=None,
            seen_revision=rx.revision,
            today=TODAY,
            now=NOW,
            starts_on=TODAY + timedelta(days=START_WINDOW_DAYS + 1),
        )
    assert course_start(rx_with(line()), TZ) == TODAY
    assert course_start(
        rx_with(line(), starts_on=TODAY + timedelta(days=3)), TZ
    ) == TODAY + timedelta(days=3)


def test_r33_a_revision_starts_without_a_start_day() -> None:
    first = rx_with(line(), starts_on=TODAY + timedelta(days=2))
    revision = Prescription.revision_of(
        first, id=new_id(), new_item_id=new_id, created_by=new_id(), now=NOW
    )
    assert revision.starts_on is None and first.starts_on == TODAY + timedelta(days=2)


# --- A day and a course (R32, R35, R36) ----------------------------------------------------------


def test_r32_day_n_of_m_from_the_start_and_nothing_outside_the_course() -> None:
    start = TODAY + timedelta(days=1)
    rx = rx_with(line(frequency="1-1-0", days=5), starts_on=start)
    assert plan_for_day([source(rx)], TODAY).doses == ()
    first = plan_for_day([source(rx)], start)
    assert [(d.slot, d.line.day, d.line.days_total) for d in first.doses] == [(M, 1, 5), (A, 1, 5)]
    last = plan_for_day([source(rx)], start + timedelta(days=4))
    assert {d.line.day for d in last.doses} == {5}
    assert plan_for_day([source(rx)], start + timedelta(days=5)).doses == ()


@pytest.mark.parametrize("kind", [DurationKind.UNTIL_REVIEW, DurationKind.ONGOING, None])
def test_r32_open_ended_lines_show_with_no_invented_end(kind: DurationKind | None) -> None:
    rx = rx_with(line(days=None, kind=kind))
    far = TODAY + timedelta(days=400)
    [dose_m, dose_n] = plan_for_day([source(rx)], far).doses
    assert (dose_m.line.end, dose_m.line.days_total, dose_n.slot) == (None, None, N)
    assert courses([source(rx)], far)[0].end is None


def test_r36_untimed_lines_are_listed_as_written_and_nothing_is_merged() -> None:
    a = rx_with(line(1, name="Tab Same"), line(2, frequency="SOS", days=None))
    b = rx_with(line(1, name="Tab Same"))
    day = plan_for_day([source(a, "Alpha"), source(b, "Beta")], TODAY)
    morning = [d for d in day.doses if d.slot is M]
    assert [d.line.source.clinic_name for d in morning] == ["Alpha", "Beta"]  # two entries
    assert [u.item.frequency for u in day.untimed] == [Frequency.SOS]
    assert [d.slot for d in day.doses] == [M, M, N, N]


def test_r35_a_days_course_that_ended_over_seven_days_ago_is_left_out() -> None:
    rx = rx_with(line(days=5))
    end = TODAY + timedelta(days=4)
    assert courses([source(rx)], end + timedelta(days=ENDED_SHOWN_DAYS))[0].end == end
    assert courses([source(rx)], end + timedelta(days=ENDED_SHOWN_DAYS + 1)) == []
    mixed = rx_with(line(1, days=5), line(2, days=None, kind=DurationKind.ONGOING))
    assert courses([source(mixed)], TODAY + timedelta(days=90))[0].end is None


def test_r28_the_engine_never_changes_what_the_doctor_wrote() -> None:
    rx = rx_with(line(frequency="1-0-1", timing=Timing.BEDTIME, days=3))
    before = rx.items
    plan_for_day([source(rx)], TODAY)
    courses([source(rx)], TODAY)
    schedule_rows(rx, Language.EN)
    assert rx.items == before


# --- Layout 2's schedule section (R25) -----------------------------------------------------------


def test_r25_schedule_rows_mark_the_slots_and_word_the_rest() -> None:
    rx = rx_with(
        line(1, frequency="1-1-0", timing=Timing.AFTER_FOOD),
        line(2, frequency="0-0-1-0", days=None, kind=DurationKind.UNTIL_REVIEW),
        line(3, frequency="SOS", days=None),
        line(4, frequency=None, days=None),
    )
    rows = schedule_rows(rx, Language.EN)
    assert [r.marks for r in rows[:2]] == [(True, True, False, False), (False, False, True, False)]
    assert (rows[0].timing, rows[0].duration) == ("after food", "5 days")
    assert rows[1].duration == "Until your next review"
    assert (rows[2].marks, rows[2].as_written) == ((False,) * 4, "Only when needed")
    assert rows[3].as_written == "Times not stated — ask your clinic"
    assert rows[3].duration == "Duration not stated — ask your clinic"


def test_r25_a_version_issued_on_layout_1_keeps_its_words_and_has_no_schedule() -> None:
    rx = rx_with(line(frequency="1-0-1", days=None))
    old = replace(rx, layout_version=1)
    assert duration_field(old.items[0], Language.EN, old.layout_version) is None
    page = build_patient_view([old], language=Language.EN, timezone=TZ)
    assert page is not None and page.schedule == ()
    assert "For how long" not in {f.label for f in page.medicines[0].fields}
    new = build_patient_view([rx], language=Language.EN, timezone=TZ)
    assert new is not None and len(new.schedule) == 1
    assert {f.label: f.value for f in new.medicines[0].fields}["For how long"] == (
        "Duration not stated — ask your clinic"
    )


# --- The person's settings (R34, R38) ------------------------------------------------------------


def test_r34_slot_times_default_and_must_run_in_order_within_the_day() -> None:
    t = SlotTimes()
    assert [t.at(s) for s in (M, A, E, N)] == [time(8), time(14), time(18), time(21)]
    SlotTimes(time(5), time(5, 1), time(5, 2), time(23, 30))
    for bad in (
        (time(9), time(8), time(18), time(21)),
        (time(4, 59), time(14), time(18), time(21)),
        (time(8), time(14), time(18), time(23, 31)),
        (time(8, 0, 30), time(14), time(18), time(21)),
    ):
        with pytest.raises(InvalidValue):
            SlotTimes(*bad)


def test_r38_a_reminder_choice_changes_only_itself() -> None:
    pref = MedicineReminderPref.create(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        account_id=new_id(),
        prescription_id=new_id(),
        item_id=new_id(),
        slot=M,
        enabled=True,
        remind_at=time(7, 30),
        now=NOW,
    )
    assert not pref.change(enabled=True, remind_at=time(7, 30), now=NOW)
    assert pref.change(enabled=False, remind_at=None, now=NOW + timedelta(minutes=1))
    assert (pref.enabled, pref.remind_at, pref.updated_at) == (
        False,
        None,
        NOW + timedelta(minutes=1),
    )
    with pytest.raises(InvalidValue, match="remind_at"):
        pref.change(enabled=True, remind_at=time(4), now=NOW)


def test_filled_drafts_carry_no_start_until_the_doctor_chooses_one() -> None:
    assert filled(draft()).starts_on is None
