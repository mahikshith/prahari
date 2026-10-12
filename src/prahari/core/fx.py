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

Rates must be supplied explicitly, with the customer's settlement or accounting
source. Missing conversions raise instead of silently using invented reference marks.
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
        if not self.rate.is_finite() or self.rate <= 0:
            raise ValueError("fx rate must be finite and positive")
        for name in ("base", "quote"):
            value = getattr(self, name).upper()
            if len(value) != 3 or not value.isascii() or not value.isalpha():
                raise ValueError("fx currencies must be three-letter codes")
            object.__setattr__(self, name, value)


class FxTable:
    """Dated rate lookup with explicit as-of semantics."""

    def __init__(self, rates: list[FxRate] | None = None) -> None:
        self._rates: dict[tuple[str, str], list[FxRate]] = {}
        # Aggregation converts every record, so the same (pair, date) is looked up
        # thousands of times per report. Cached rather than bisected each time;
        # invalidated whenever the table changes.
        self._cache: dict[tuple[str, str, date], FxRate] = {}
        for rate in rates or []:
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
        """Convert at full precision; callers round only after aggregation/display."""
        if base.upper() == quote.upper():
            return amount
        fx = self.rate_on(base, quote, on)
        return amount * fx.rate


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


def format_money(amount: Decimal, currency: str, *, scale: bool = True) -> str:
    if currency.upper() == "INR":
        return format_inr(amount, scale=scale)
    return f"{currency.upper()} {amount:,.2f}"
