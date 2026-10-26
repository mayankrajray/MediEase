"""The day's collection (M6d-P5; FR-BIL-06; spec billing R55-R62).

One clinic-local day: every payment and refund recorded that day, by mode and by doctor, with the
net. A voided entry is listed but never counted (R57). Payments are never edited or deleted, and
a void is possible only on its own day (R35), so a day's figures stop changing once the day ends.
This module only adds up; it holds no I/O and no clinical content.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from mediease_api.domain.billing.payment import Payment, PaymentKind, PaymentMode


@dataclass(frozen=True, slots=True)
class Tally:
    payments_paise: int = 0
    refunds_paise: int = 0
    count: int = 0

    @property
    def net_paise(self) -> int:
        return self.payments_paise - self.refunds_paise

    def add(self, payment: Payment) -> Tally:
        if payment.kind is PaymentKind.PAYMENT:
            return Tally(
                self.payments_paise + payment.amount_paise, self.refunds_paise, self.count + 1
            )
        return Tally(self.payments_paise, self.refunds_paise + payment.amount_paise, self.count + 1)


@dataclass(frozen=True, slots=True)
class Collection:
    total: Tally
    by_mode: tuple[tuple[PaymentMode, Tally], ...]
    # Doctor ID (None: a bill without a doctor) -> tally, the largest net first.
    by_doctor: tuple[tuple[UUID | None, Tally], ...]
    voided: Tally


def summarise(payments: Iterable[Payment]) -> Collection:
    """R56-R58: the day's totals; voided entries only in ``voided``."""
    total, voided = Tally(), Tally()
    modes: dict[PaymentMode, Tally] = {mode: Tally() for mode in PaymentMode}
    doctors: dict[UUID | None, Tally] = {}
    for p in payments:
        if p.is_voided:
            voided = voided.add(p)
            continue
        total = total.add(p)
        modes[p.mode] = modes[p.mode].add(p)
        doctors[p.doctor_id] = doctors.get(p.doctor_id, Tally()).add(p)
    ordered: Sequence[tuple[UUID | None, Tally]] = sorted(
        doctors.items(), key=lambda kv: (-kv[1].net_paise, str(kv[0]))
    )
    return Collection(total, tuple(modes.items()), tuple(ordered), voided)
