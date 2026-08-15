"""Safe money parsing.

`Decimal` accepts `NaN` and `Infinity`, and both are dangerous here in different ways:

  Decimal("Infinity") > Decimal(1000)  ->  True
  Decimal("NaN")      > Decimal(1000)  ->  raises InvalidOperation
  sum([Decimal(1), Decimal("NaN")])    ->  NaN, silently

An `Infinity` cost from a malformed or hostile upstream response would compare as
greater than every budget limit. With `EnforcementAction.HARD_STOP` configured, that
marks all budgets exceeded and drives credential revocation against production - an
availability incident caused by our own control plane, triggered by data we did not
validate.

`NaN` is quieter and worse to debug: it propagates through every `sum()` in the
aggregation path without complaint, then raises `InvalidOperation` at some unrelated
comparison far from the record that caused it.

So money is parsed exactly once, at the boundary, and never trusted raw.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

MAX_REASONABLE = Decimal("1e15")
"""Roughly Rs 1000 lakh crore in a single record. Any line item above this is a
provider bug or an attack on our arithmetic, not a real charge."""


class MoneyError(ValueError):
    """Raised when a value cannot be trusted as a monetary amount."""


def parse_money(value: object, *, field: str = "amount", default: Decimal | None = None) -> Decimal:
    """Parse a provider-supplied amount into a finite `Decimal`.

    `default` is returned only for `None` / missing input. A value that is present
    but unparseable always raises - silently defaulting a malformed cost to zero
    understates the bill, which is the failure mode a customer notices last and
    trusts us least for.
    """
    if value is None or value == "":
        if default is not None:
            return default
        raise MoneyError(f"{field}: missing")

    if isinstance(value, Decimal):
        candidate = value
    else:
        try:
            # str() first: float -> Decimal directly inherits binary float error, and
            # these amounts are multiplied by millions of tokens downstream.
            candidate = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise MoneyError(f"{field}: not a number ({value!r})") from exc

    if not candidate.is_finite():
        raise MoneyError(f"{field}: non-finite value ({value!r})")
    if abs(candidate) > MAX_REASONABLE:
        raise MoneyError(f"{field}: implausible magnitude ({candidate})")

    return candidate


def is_safe_money(value: Decimal) -> bool:
    return value.is_finite() and abs(value) <= MAX_REASONABLE
