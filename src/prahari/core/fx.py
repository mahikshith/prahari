"""Currency conversion.

Necessary because the buyer sets budgets in **INR** while most providers bill in
**USD**. A budget engine that cannot cross that boundary is useless to an Indian
finance team, and one that crosses it carelessly is worse than useless.

Three rules, all learned from how finance teams actually audit a number:

1. **Rates are dated.** Converting last quarter's spend at today's rate produces a
   number that does not match anything the customer has on file. Every conversion
   takes the transaction date and uses the rate in force then.
2. **Conversions are recorded, not just performed.** `UsageRecord` stores `currency`
   and `fx_rate_date` alongside the amount so any figure can be traced back.
3. **A missing rate is an error, never a guess.** Silently falling back to a nearby
   rate is how a reconciliation drifts past the 2% gate with nobody noticing.

The built-in table is a **placeholder** (ASSUMPTIONS.md A6). Production must load RBI
reference rates. The interface is built so that swap is a data change, not a code
change.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


class FxError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FxRate:
    base: str
    quote: str
    rate: Decimal
    as_of: date
    source: str

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("fx rate must be positive")


# Placeholder monthly USD->INR marks. Order matters: kept sorted by date.
# Replace with an RBI reference-rate feed before any customer-facing number.
_DEFAULT_USD_INR: list[tuple[date, str]] = [
    (date(2026, 1, 1), "83.20"),
    (date(2026, 2, 1), "83.55"),
    (date(2026, 3, 1), "83.90"),
    (date(2026, 4, 1), "84.10"),
    (date(2026, 5, 1), "84.05"),
    (date(2026, 6, 1), "83.85"),
    (date(2026, 7, 1), "84.30"),
    (date(2026, 8, 1), "84.45"),
]


class FxTable:
    """Dated rate lookup with explicit as-of semantics."""

    def __init__(self, rates: list[FxRate] | None = None) -> None:
        self._rates: dict[tuple[str, str], list[FxRate]] = {}
        # Aggregation converts every record, so the same (pair, date) is looked up
        # thousands of times per report. Cached rather than bisected each time;
        # invalidated whenever the table changes.
        self._cache: dict[tuple[str, str, date], FxRate] = {}
        for rate in rates if rates is not None else _default_rates():
            self.add(rate)

    def add(self, rate: FxRate) -> None:
        series = self._rates.setdefault((rate.base, rate.quote), [])
        series.append(rate)
        series.sort(key=lambda r: r.as_of)
        self._cache.clear()

    def rate_on(self, base: str, quote: str, on: date) -> FxRate:
        key = (base.upper(), quote.upper(), on)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        resolved = self._resolve(*key)
        self._cache[key] = resolved
        return resolved

    def _resolve(self, base: str, quote: str, on: date) -> FxRate:
        """Rate in force on `on` - the most recent mark at or before that date.

        Deliberately never interpolates forward. A rate published after the
        transaction did not exist when the transaction happened, and using it means
        our number can change retroactively.
        """
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return FxRate(base, quote, Decimal(1), on, "identity")

        series = self._rates.get((base, quote))
        if not series:
            # Try the inverse before giving up - a table with USD->INR implies INR->USD.
            inverse = self._rates.get((quote, base))
            if inverse:
                found = self._most_recent(inverse, on)
                return FxRate(base, quote, Decimal(1) / found.rate, found.as_of, found.source)
            raise FxError(f"no {base}->{quote} rate available")

        return self._most_recent(series, on)

    @staticmethod
    def _most_recent(series: list[FxRate], on: date) -> FxRate:
        idx = bisect.bisect_right([r.as_of for r in series], on)
        if idx == 0:
            raise FxError(
                f"no {series[0].base}->{series[0].quote} rate on or before {on} "
                f"(earliest available {series[0].as_of})"
            )
        return series[idx - 1]

    def convert(self, amount: Decimal, base: str, quote: str, on: date) -> Decimal:
        """Convert, rounding to 2dp at the boundary only.

        Callers must not round before this point. Intermediate rounding across
        thousands of hourly records accumulates into a variance the customer sees.
        """
        if base.upper() == quote.upper():
            return amount
        fx = self.rate_on(base, quote, on)
        return (amount * fx.rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _default_rates() -> list[FxRate]:
    return [
        FxRate("USD", "INR", Decimal(value), as_of, "placeholder")
        for as_of, value in _DEFAULT_USD_INR
    ]


DEFAULT_TABLE = FxTable()


def to_inr(amount: Decimal, currency: str, on: date, table: FxTable | None = None) -> Decimal:
    return (table or DEFAULT_TABLE).convert(amount, currency, "INR", on)


# --- presentation -------------------------------------------------------------


def group_indian(amount: Decimal) -> str:
    """Indian digit grouping: 1234567 -> '12,34,567'.

    Last three digits, then pairs. Western grouping on an Indian invoice reads as
    carelessness to the buyer we are selling to.
    """
    digits = f"{int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))}"
    sign, digits = ("-", digits[1:]) if digits.startswith("-") else ("", digits)
    if len(digits) <= 3:
        return sign + digits

    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        head, pair = head[:-2], head[-2:]
        pairs.insert(0, pair)
    if head:
        pairs.insert(0, head)
    return sign + ",".join([*pairs, tail])


def format_inr(amount: Decimal, *, scale: bool = True) -> str:
    """Render INR the way the buyer thinks: crore and lakh, not millions."""
    if not scale:
        return f"Rs {group_indian(amount)}"

    crore = amount / Decimal("10000000")
    lakh = amount / Decimal("100000")
    if abs(crore) >= 1:
        return f"Rs {crore.quantize(Decimal('0.01'))} crore"
    if abs(lakh) >= 1:
        return f"Rs {lakh.quantize(Decimal('0.01'))} lakh"
    return f"Rs {group_indian(amount)}"
