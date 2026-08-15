"""Consumption analysis - who is spending, on what, and what changed.

Answers the questions a FinOps lead is actually asked in a review:

  - per-user token consumption, and cost per user
  - which project or group is burning the most, and the least
  - what moved since last month, and by how much
  - how much we still cannot attribute to anyone

That last one is the point of `unallocated_share`. Every competing tool quietly
buries it; surfacing it is a credibility play, because a finance buyer who finds
hidden unattributed spend on their own stops believing the rest of the numbers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from prahari.core.budget import scope_value
from prahari.core.fx import FxTable
from prahari.core.models import AllocationMethod, UsageRecord

UNATTRIBUTED = "(unattributed)"


@dataclass(frozen=True, slots=True)
class ConsumptionRow:
    key: str
    cost: Decimal
    share: Decimal
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    requests: int
    record_count: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cached_tokens

    @property
    def cost_per_million_tokens(self) -> Decimal | None:
        """Blended rate. The single most useful efficiency number: two teams on the
        same workload with a 3x gap here are making different model choices, and that
        is an actionable conversation rather than a scolding about volume."""
        if self.total_tokens == 0:
            return None
        return (self.cost / (Decimal(self.total_tokens) / Decimal(1_000_000))).quantize(
            Decimal("0.01")
        )


@dataclass(frozen=True, slots=True)
class Mover:
    key: str
    current: Decimal
    prior: Decimal

    @property
    def delta(self) -> Decimal:
        return self.current - self.prior

    @property
    def pct_change(self) -> Decimal | None:
        """None when there is no prior spend - a new line item has no percentage,
        and reporting one as infinite or 100% is a lie either way."""
        if self.prior == 0:
            return None
        return (self.delta / self.prior).quantize(Decimal("0.0001"))

    @property
    def is_new(self) -> bool:
        return self.prior == 0 and self.current > 0


def aggregate_by(
    records: Iterable[UsageRecord],
    dimension: str,
    *,
    currency: str = "INR",
    fx: FxTable | None = None,
    missing_key: str = UNATTRIBUTED,
) -> list[ConsumptionRow]:
    """Group spend and tokens by any scope dimension, largest first.

    Records whose dimension is absent are bucketed under `missing_key` rather than
    dropped. Dropping them would make the shares add to 100% of a number that is not
    the real total, which is exactly the kind of quiet wrongness that loses a
    reconciliation.
    """
    table = fx or FxTable()
    buckets: dict[str, list[UsageRecord]] = {}

    for record in records:
        key = scope_value(record, dimension) or missing_key
        buckets.setdefault(key, []).append(record)

    totals = {
        key: sum(
            (_convert(r, currency, table) for r in group),
            Decimal(0),
        )
        for key, group in buckets.items()
    }
    grand_total = sum(totals.values(), Decimal(0))

    rows = [
        ConsumptionRow(
            key=key,
            cost=totals[key].quantize(Decimal("0.01")),
            share=(totals[key] / grand_total) if grand_total else Decimal(0),
            input_tokens=sum(r.tokens.input_tokens for r in group),
            output_tokens=sum(r.tokens.output_tokens for r in group),
            cached_tokens=sum(r.tokens.cache_read_tokens for r in group),
            requests=sum(r.tokens.requests for r in group),
            record_count=len(group),
        )
        for key, group in buckets.items()
    ]
    rows.sort(key=lambda r: -r.cost)
    return rows


def top_consumers(
    records: Iterable[UsageRecord], dimension: str, n: int = 10, **kwargs
) -> list[ConsumptionRow]:
    return aggregate_by(records, dimension, **kwargs)[:n]


def bottom_consumers(
    records: Iterable[UsageRecord], dimension: str, n: int = 10, **kwargs
) -> list[ConsumptionRow]:
    """Smallest spenders, excluding zeros.

    Worth reporting: a project with a provisioned budget and near-zero spend is
    either a rollout that stalled or a licence nobody uses. Both are money.
    """
    rows = [r for r in aggregate_by(records, dimension, **kwargs) if r.cost > 0]
    return sorted(rows, key=lambda r: r.cost)[:n]


def per_user_consumption(
    records: Iterable[UsageRecord], **kwargs
) -> list[ConsumptionRow]:
    """Token consumption and cost per user.

    Falls back to the credential when a provider reports no user - most API traffic
    is service-account traffic, and pretending otherwise would leave the majority of
    spend under `(unattributed)`.
    """
    table = kwargs.pop("fx", None) or FxTable()
    currency = kwargs.pop("currency", "INR")
    buckets: dict[str, list[UsageRecord]] = {}

    for record in records:
        key = record.user_id or record.api_key_id or UNATTRIBUTED
        buckets.setdefault(key, []).append(record)

    totals = {
        key: sum((_convert(r, currency, table) for r in group), Decimal(0))
        for key, group in buckets.items()
    }
    grand = sum(totals.values(), Decimal(0))

    rows = [
        ConsumptionRow(
            key=key,
            cost=totals[key].quantize(Decimal("0.01")),
            share=(totals[key] / grand) if grand else Decimal(0),
            input_tokens=sum(r.tokens.input_tokens for r in group),
            output_tokens=sum(r.tokens.output_tokens for r in group),
            cached_tokens=sum(r.tokens.cache_read_tokens for r in group),
            requests=sum(r.tokens.requests for r in group),
            record_count=len(group),
        )
        for key, group in buckets.items()
    ]
    rows.sort(key=lambda r: -r.cost)
    return rows


def movers(
    current: Sequence[UsageRecord],
    prior: Sequence[UsageRecord],
    dimension: str,
    *,
    n: int = 10,
    **kwargs,
) -> list[Mover]:
    """Biggest absolute changes between two periods, increases first.

    Absolute rather than percentage on purpose: a project going from Rs 100 to
    Rs 400 is a 300% rise and irrelevant, while one going from Rs 40 lakh to
    Rs 55 lakh is 37% and the only thing worth discussing.
    """
    now = {r.key: r.cost for r in aggregate_by(current, dimension, **kwargs)}
    before = {r.key: r.cost for r in aggregate_by(prior, dimension, **kwargs)}

    all_keys = set(now) | set(before)
    result = [
        Mover(key=k, current=now.get(k, Decimal(0)), prior=before.get(k, Decimal(0)))
        for k in all_keys
    ]
    result.sort(key=lambda m: -abs(m.delta))
    return result[:n]


@dataclass(frozen=True, slots=True)
class AllocationCoverage:
    total: Decimal
    allocated: Decimal
    unallocated: Decimal
    coverage: Decimal
    by_method: dict[str, Decimal]

    @property
    def meets_target(self) -> bool:
        """docs/REQUIREMENTS.md F3.2 targets under 15% unallocated."""
        return self.coverage >= Decimal("0.85")


def allocation_coverage(
    records: Iterable[UsageRecord], *, currency: str = "INR", fx: FxTable | None = None
) -> AllocationCoverage:
    """How much spend we can actually attribute, and by what means.

    Surfaced prominently rather than buried. A buyer who discovers unattributed spend
    themselves stops trusting every other number we show them.
    """
    table = fx or FxTable()
    total = Decimal(0)
    allocated = Decimal(0)
    by_method: dict[str, Decimal] = {}

    for record in records:
        amount = _convert(record, currency, table)
        total += amount
        method = record.allocation_method
        by_method[str(method)] = by_method.get(str(method), Decimal(0)) + amount
        if method is not AllocationMethod.UNALLOCATED:
            allocated += amount

    return AllocationCoverage(
        total=total.quantize(Decimal("0.01")),
        allocated=allocated.quantize(Decimal("0.01")),
        unallocated=(total - allocated).quantize(Decimal("0.01")),
        coverage=(allocated / total) if total else Decimal(0),
        by_method={k: v.quantize(Decimal("0.01")) for k, v in by_method.items()},
    )


def ai_vs_cloud_split(
    records: Iterable[UsageRecord], *, currency: str = "INR", fx: FxTable | None = None
) -> dict[str, Decimal]:
    """Spend split by service category.

    The wedge is AI; the North Star is total cloud. This is the one number that shows
    both at once, and it is how an AI-first conversation expands into a cloud one
    without a second sales cycle.
    """
    table = fx or FxTable()
    split: dict[str, Decimal] = {}
    for record in records:
        category = str(record.extensions.get("service_category") or "ai")
        split[category] = split.get(category, Decimal(0)) + _convert(record, currency, table)
    return {k: v.quantize(Decimal("0.01")) for k, v in sorted(split.items(), key=lambda kv: -kv[1])}


def _convert(record: UsageRecord, currency: str, table: FxTable) -> Decimal:
    if record.currency.upper() == currency.upper():
        return record.billed_cost
    on: date = record.fx_rate_date or record.period_start.date()
    return table.convert(record.billed_cost, record.currency, currency, on)
