"""Read-only bonus facts; all values remain in hundredths of a bonus."""

import dataclasses
import datetime

from gameclub_backend.modules.clients.bonus import BonusOperationKind


@dataclasses.dataclass(frozen=True)
class BonusPeriodTotals:
    credited_cents: int = 0
    spent_cents: int = 0
    adjustments_cents: int = 0
    opening_cents: int = 0
    reserved_in_cents: int = 0
    released_cents: int = 0

    def record(
        self, kind: BonusOperationKind, key: str, total_delta: int, reserve_delta: int
    ) -> "BonusPeriodTotals":
        if kind is BonusOperationKind.ADJUST:
            # These namespaces belong exclusively to the automatic earning/opening producers.
            field = (
                "credited_cents"
                if key.startswith("bonus-earning:")
                else "opening_cents"
                if key.startswith("bonus-opening:")
                else "adjustments_cents"
            )
            delta = total_delta
        elif kind in (BonusOperationKind.DEBIT, BonusOperationKind.CONSUME):
            field, delta = "spent_cents", -total_delta
        elif kind is BonusOperationKind.RESERVE:
            field, delta = "reserved_in_cents", reserve_delta
        else:
            field, delta = "released_cents", -reserve_delta
        return dataclasses.replace(self, **{field: getattr(self, field) + delta})


@dataclasses.dataclass(frozen=True)
class BonusReport:
    start_at: datetime.datetime
    end_at: datetime.datetime
    observed_at: datetime.datetime
    period: BonusPeriodTotals
    total_cents: int
    available_cents: int
    reserved_cents: int
    pending_cents: int
