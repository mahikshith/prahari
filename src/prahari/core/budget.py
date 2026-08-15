"""Budget engine - scoped budgets, burn rate, forecast, enforcement policy.

This is the half of the product that turns a dashboard into a control plane, and it
is what Gate 5 in docs/DECISION_GATES.md is actually testing: whether customers pay
materially more for something that can *stop* spend than for something that reports
it.

Budgets are scoped by an arbitrary set of dimensions rather than a single enum, so
the shapes customers actually ask for all fall out of one model:

    {}                                              org-wide
    {"project_id": "robotics-prod"}                 one project
    {"service": "Cloud Run"}                        one service everywhere
    {"project_id": "robotics-prod",
     "service": "Cloud Run"}                        Rs 2 lakh on Cloud Run in one project
    {"service_category": "ai"}                      all AI spend
    {"cost_centre": "cc-robotics"}                  one team
    {"user_id": "..."} / {"api_key_id": "..."}      one person or credential

Two design choices worth defending:

**Periods are IST calendar months by default.** Indian finance closes on IST month
boundaries. Computing them in UTC puts 5.5 hours of spend in the wrong month, which
is invisible until someone reconciles against a GST filing.

**Forecasting is linear and explainable.** Same principle as detection: a CFO must be
able to reproduce the number. We report the period-average burn rate *and* a trailing
7-day rate, because the gap between them is what tells you a budget is about to blow
before it does.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from prahari.core.fx import FxTable, format_inr
from prahari.core.models import UsageRecord

IST = timedelta(hours=5, minutes=30)


class BudgetPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class EnforcementAction(StrEnum):
    """What happens when a budget is breached.

    ALERT_ONLY is the default and the only safe starting point. Nobody grants write
    access to a tool that can revoke their production credentials before they have
    watched it be right in dry-run for a while.
    """

    ALERT_ONLY = "alert_only"
    THROTTLE = "throttle"
    HARD_STOP = "hard_stop"


class BudgetStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"


# Dimensions a budget can be scoped by. Maps a scope key to how it is read off a
# record - direct attribute or a key in `extensions`.
_DIRECT_FIELDS = frozenset(
    {
        "provider",
        "account_id",
        "project_id",
        "workspace_id",
        "api_key_id",
        "user_id",
        "model",
        "region",
        "cost_centre",
        "parent_entity",
    }
)
_EXTENSION_FIELDS = frozenset({"service", "service_category", "sku", "project_name"})

SCOPE_DIMENSIONS = _DIRECT_FIELDS | _EXTENSION_FIELDS


def scope_value(record: UsageRecord, dimension: str) -> str | None:
    """Read one scope dimension off a record."""
    if dimension in _DIRECT_FIELDS:
        value = getattr(record, dimension, None)
        return str(value) if value is not None else None
    if dimension in _EXTENSION_FIELDS:
        value = record.extensions.get(dimension)
        return str(value) if value is not None else None
    raise ValueError(
        f"unknown budget scope dimension {dimension!r}; "
        f"valid: {', '.join(sorted(SCOPE_DIMENSIONS))}"
    )


@dataclass(frozen=True, slots=True)
class Budget:
    id: str
    name: str
    amount: Decimal
    scope: Mapping[str, str] = field(default_factory=dict)
    currency: str = "INR"
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    thresholds: tuple[Decimal, ...] = (Decimal("0.5"), Decimal("0.8"), Decimal("1.0"))
    enforcement: EnforcementAction = EnforcementAction.ALERT_ONLY
    owner: str | None = None

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("budget amount must be positive")
        for dimension in self.scope:
            if dimension not in SCOPE_DIMENSIONS:
                raise ValueError(
                    f"unknown budget scope dimension {dimension!r}; "
                    f"valid: {', '.join(sorted(SCOPE_DIMENSIONS))}"
                )

    def matches(self, record: UsageRecord) -> bool:
        """All scope dimensions must match. An empty scope matches everything."""
        return all(scope_value(record, dim) == want for dim, want in self.scope.items())

    @property
    def describe_scope(self) -> str:
        if not self.scope:
            return "organisation-wide"
        return " AND ".join(f"{k}={v}" for k, v in sorted(self.scope.items()))


# --- period boundaries --------------------------------------------------------


def period_bounds(
    period: BudgetPeriod, at: datetime, *, tz_offset: timedelta = IST
) -> tuple[datetime, datetime]:
    """Period containing `at`, computed in local time, returned as UTC.

    Local-time boundaries matter: an IST month closes 5.5 hours before the UTC month,
    and putting that spend in the wrong month is invisible until it is reconciled
    against a GST filing.
    """
    local = at.astimezone(UTC) + tz_offset

    if period is BudgetPeriod.DAILY:
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    elif period is BudgetPeriod.WEEKLY:
        start_local = (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_local = start_local + timedelta(days=7)
    elif period is BudgetPeriod.MONTHLY:
        start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = (start_local + timedelta(days=32)).replace(day=1)
    else:  # QUARTERLY
        quarter_first_month = 3 * ((local.month - 1) // 3) + 1
        start_local = local.replace(
            month=quarter_first_month, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_local = start_local
        for _ in range(3):
            end_local = (end_local + timedelta(days=32)).replace(day=1)

    return (start_local - tz_offset, end_local - tz_offset)


# --- evaluation ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BudgetState:
    """Everything needed to explain a budget's position without re-querying."""

    budget: Budget
    period_start: datetime
    period_end: datetime
    as_of: datetime

    spent: Decimal
    remaining: Decimal
    pct_used: Decimal

    days_elapsed: Decimal
    days_total: Decimal
    burn_rate_per_day: Decimal
    recent_burn_rate_per_day: Decimal
    """Trailing 7 days (or the period so far, if shorter). The gap between this and
    the period average is the early warning."""

    forecast_period_end: Decimal
    projected_overage: Decimal
    exhausted_on: date | None

    status: BudgetStatus
    crossed_thresholds: tuple[Decimal, ...]
    contributors: tuple[tuple[str, Decimal], ...]
    record_count: int

    @property
    def is_accelerating(self) -> bool:
        """Recent burn materially above the period average - the budget is about to
        go wrong even if it currently looks fine."""
        if self.burn_rate_per_day <= 0:
            return self.recent_burn_rate_per_day > 0
        return self.recent_burn_rate_per_day > self.burn_rate_per_day * Decimal("1.5")

    def explain(self) -> str:
        parts = [
            f"[{self.status.upper()}] {self.budget.name} ({self.budget.describe_scope})",
            f"{format_inr(self.spent)} of {format_inr(self.budget.amount)}"
            f" ({self.pct_used:.0%})",
            f"burn {format_inr(self.burn_rate_per_day, scale=False)}/day",
            f"forecast {format_inr(self.forecast_period_end)} at period end",
        ]
        if self.projected_overage > 0:
            parts.append(f"projected overage {format_inr(self.projected_overage)}")
        if self.exhausted_on:
            parts.append(f"exhausted {self.exhausted_on.isoformat()}")
        if self.is_accelerating:
            parts.append("ACCELERATING")
        return " | ".join(parts)


@dataclass(frozen=True, slots=True)
class PreparedWindow:
    """Records windowed to a period, pre-converted, and inverted-indexed by scope.

    Exists purely for speed, and the index is the part that matters. `evaluate_all`
    originally rescanned and re-converted the whole record set per budget, so cost
    grew as budgets x records: 46 ms for 5 budgets and 386 ms for 40 over the same
    7,440 records.

    Windowing and converting once removed the duplicated FX work but left every
    budget still touching every row. The inverted index removes that too - a budget
    scoped to one project intersects a few posting lists and visits only its own
    rows, so cost becomes proportional to *matching* rows rather than total rows.
    Narrow budgets are the common case, which is exactly where this pays.
    """

    period: BudgetPeriod
    currency: str
    start: datetime
    end: datetime
    now: datetime
    recent_cutoff: datetime
    rows: tuple[tuple[UsageRecord, Decimal], ...]
    dim_values: dict[str, tuple[str | None, ...]]
    """dimension -> value per row, positionally aligned with `rows`."""
    index: dict[str, dict[str, frozenset[int]]]
    """dimension -> value -> row indices."""

    def candidates(self, scope: Mapping[str, str]) -> Iterable[int]:
        """Row indices matching every scope dimension.

        Intersects smallest posting list first, so a narrow dimension prunes before
        a broad one does any work.
        """
        if not scope:
            return range(len(self.rows))

        posting: list[frozenset[int]] = []
        for dim, want in scope.items():
            by_value = self.index.get(dim)
            if by_value is None:
                # Dimension absent from the index: nothing was prepared for it, so
                # no row can match. Better to return empty than to silently ignore
                # the constraint and over-report spend.
                return ()
            hits = by_value.get(want)
            if not hits:
                return ()
            posting.append(hits)

        posting.sort(key=len)
        result = posting[0]
        for other in posting[1:]:
            result = result & other
            if not result:
                break
        return result


def prepare_window(
    records: Iterable[UsageRecord],
    period: BudgetPeriod,
    currency: str,
    *,
    as_of: datetime | None = None,
    fx: FxTable | None = None,
    dimensions: Iterable[str] = (),
) -> PreparedWindow:
    """Window, convert and index once.

    `dimensions` is every scope dimension the caller will query, plus whatever it
    wants contributor breakdowns by. Only these are indexed - indexing all of them
    would cost more than it saves.
    """
    now = as_of or datetime.now(UTC)
    start, end = period_bounds(period, now)
    table = fx or FxTable()

    rows = tuple(
        (record, _to_budget_currency(record, currency, table))
        for record in records
        if start <= record.period_start < end
    )

    wanted = sorted(set(dimensions))
    dim_values: dict[str, tuple[str | None, ...]] = {}
    index: dict[str, dict[str, frozenset[int]]] = {}

    for dim in wanted:
        values = tuple(scope_value(record, dim) for record, _ in rows)
        dim_values[dim] = values

        buckets: dict[str, set[int]] = {}
        for position, value in enumerate(values):
            if value is not None:
                buckets.setdefault(value, set()).add(position)
        index[dim] = {value: frozenset(hits) for value, hits in buckets.items()}

    return PreparedWindow(
        period=period,
        currency=currency,
        start=start,
        end=end,
        now=now,
        recent_cutoff=max(start, now - timedelta(days=7)),
        rows=rows,
        dim_values=dim_values,
        index=index,
    )


def evaluate(
    budget: Budget,
    records: Iterable[UsageRecord] | None = None,
    *,
    as_of: datetime | None = None,
    fx: FxTable | None = None,
    contributor_dimension: str = "project_id",
    already_crossed: Sequence[Decimal] = (),
    window: PreparedWindow | None = None,
) -> BudgetState:
    """Position a budget against actual spend.

    `already_crossed` suppresses re-firing thresholds that have already alerted -
    without it, a budget past 80% alerts every single evaluation cycle, and an
    alerting system that repeats itself gets filtered into a folder nobody reads.

    Pass `window` to reuse a `PreparedWindow` across budgets sharing a period and
    currency; `evaluate_all` does this automatically.
    """
    needed = {*budget.scope, contributor_dimension}
    if window is None:
        if records is None:
            raise ValueError("evaluate() needs either records or a prepared window")
        window = prepare_window(
            records, budget.period, budget.currency, as_of=as_of, fx=fx, dimensions=needed
        )
    elif window.period is not budget.period or window.currency != budget.currency:
        raise ValueError(
            f"prepared window is {window.period}/{window.currency}, "
            f"budget needs {budget.period}/{budget.currency}"
        )
    elif not needed <= window.index.keys():
        raise ValueError(
            f"prepared window lacks indexed dimensions {sorted(needed - window.index.keys())}; "
            "pass them via prepare_window(dimensions=...)"
        )

    now, start, end = window.now, window.start, window.end
    recent_cutoff = window.recent_cutoff

    spent = Decimal(0)
    contributions: dict[str, Decimal] = {}
    recent_spend = Decimal(0)
    matched = 0

    rows = window.rows
    contributor_values = window.dim_values[contributor_dimension]

    for position in window.candidates(budget.scope):
        record, amount = rows[position]

        spent += amount
        matched += 1

        key = contributor_values[position] or "unattributed"
        contributions[key] = contributions.get(key, Decimal(0)) + amount

        if record.period_start >= recent_cutoff:
            recent_spend += amount

    days_total = Decimal((end - start).total_seconds()) / Decimal(86400)
    elapsed_seconds = max((min(now, end) - start).total_seconds(), 0.0)
    days_elapsed = Decimal(elapsed_seconds) / Decimal(86400)

    burn = spent / days_elapsed if days_elapsed > 0 else Decimal(0)

    recent_days = Decimal((min(now, end) - recent_cutoff).total_seconds()) / Decimal(86400)
    recent_burn = recent_spend / recent_days if recent_days > 0 else Decimal(0)

    forecast = (burn * days_total).quantize(Decimal("0.01"))
    remaining = budget.amount - spent
    pct = (spent / budget.amount) if budget.amount else Decimal(0)
    overage = max(forecast - budget.amount, Decimal(0)).quantize(Decimal("0.01"))

    # Exhaustion uses the RECENT rate deliberately. If spend is accelerating, the
    # period average flatters the date and the warning arrives too late to act on.
    projection_rate = recent_burn if recent_burn > 0 else burn
    exhausted_on: date | None = None
    if remaining > 0 and projection_rate > 0:
        days_left = remaining / projection_rate
        candidate = now + timedelta(days=float(days_left))
        if candidate < end:
            exhausted_on = (candidate + IST).date()
    elif remaining <= 0:
        exhausted_on = (now + IST).date()

    crossed = tuple(
        t for t in sorted(budget.thresholds) if pct >= t and t not in set(already_crossed)
    )

    return BudgetState(
        budget=budget,
        period_start=start,
        period_end=end,
        as_of=now,
        spent=spent.quantize(Decimal("0.01")),
        remaining=remaining.quantize(Decimal("0.01")),
        pct_used=pct,
        days_elapsed=days_elapsed,
        days_total=days_total,
        burn_rate_per_day=burn.quantize(Decimal("0.01")),
        recent_burn_rate_per_day=recent_burn.quantize(Decimal("0.01")),
        forecast_period_end=forecast,
        projected_overage=overage,
        exhausted_on=exhausted_on,
        status=_status(pct, budget.thresholds),
        crossed_thresholds=crossed,
        contributors=tuple(sorted(contributions.items(), key=lambda kv: -kv[1])[:10]),
        record_count=matched,
    )


def evaluate_all(
    budgets: Iterable[Budget],
    records: Sequence[UsageRecord],
    *,
    as_of: datetime | None = None,
    fx: FxTable | None = None,
    **kwargs,
) -> list[BudgetState]:
    """Evaluate many budgets, worst first - that is the order anyone reads them in.

    Budgets are grouped by (period, currency) so the record set is windowed and
    currency-converted once per group rather than once per budget. Most estates use
    one period and one currency, so this is usually a single pass over the data no
    matter how many budgets are configured.
    """
    grouped: dict[tuple[BudgetPeriod, str], list[Budget]] = {}
    for budget in budgets:
        grouped.setdefault((budget.period, budget.currency.upper()), []).append(budget)

    contributor = kwargs.get("contributor_dimension", "project_id")

    states: list[BudgetState] = []
    for (period, currency), group in grouped.items():
        dimensions = {contributor}
        for budget in group:
            dimensions.update(budget.scope)

        window = prepare_window(
            records, period, currency, as_of=as_of, fx=fx, dimensions=dimensions
        )
        states.extend(evaluate(b, window=window, **kwargs) for b in group)

    states.sort(key=lambda s: (-s.pct_used, s.budget.name))
    return states


def _status(pct: Decimal, thresholds: Sequence[Decimal]) -> BudgetStatus:
    if pct >= 1:
        return BudgetStatus.EXCEEDED
    ordered = sorted(thresholds)
    critical = ordered[-1] if ordered else Decimal("1.0")
    warning = ordered[-2] if len(ordered) >= 2 else Decimal("0.8")
    if pct >= critical:
        return BudgetStatus.CRITICAL
    if pct >= warning:
        return BudgetStatus.WARNING
    return BudgetStatus.OK


def _to_budget_currency(record: UsageRecord, currency: str, fx: FxTable | None) -> Decimal:
    if record.currency.upper() == currency.upper():
        return record.billed_cost
    table = fx or FxTable()
    on = record.fx_rate_date or record.period_start.date()
    return table.convert(record.billed_cost, record.currency, currency, on)


# --- enforcement (dry-run first, always) --------------------------------------


@dataclass(frozen=True, slots=True)
class EnforcementDecision:
    """What *would* happen. Dry-run is the default and the only way anyone agrees to
    grant write scope - they need to watch it be right before they let it act."""

    budget_id: str
    budget_name: str
    action: EnforcementAction
    reason: str
    scope: Mapping[str, str]
    would_affect: tuple[str, ...]
    spent: Decimal
    limit: Decimal
    currency: str
    dry_run: bool = True

    def explain(self) -> str:
        prefix = "WOULD" if self.dry_run else "WILL"
        targets = ", ".join(self.would_affect[:5]) or "no identified targets"
        return (
            f"{prefix} {self.action.upper()} - {self.budget_name} "
            f"({format_inr(self.spent)} of {format_inr(self.limit)}). "
            f"{self.reason} Targets: {targets}."
        )


def decide_enforcement(
    state: BudgetState,
    records: Iterable[UsageRecord],
    *,
    dry_run: bool = True,
) -> EnforcementDecision | None:
    """Whether a budget breach triggers an action, and against what.

    `would_affect` lists the credentials the action would hit. It is computed even in
    dry-run because that list is the entire content of the conversation where a
    customer decides whether to grant write access - "this would have revoked these
    three keys" is answerable; "trust us" is not.
    """
    if state.budget.enforcement is EnforcementAction.ALERT_ONLY:
        return None
    if state.status is not BudgetStatus.EXCEEDED:
        return None

    targets: list[str] = []
    for record in records:
        if not (state.period_start <= record.period_start < state.period_end):
            continue
        if not state.budget.matches(record):
            continue
        credential = record.api_key_id or record.user_id or record.project_id
        if credential and credential not in targets:
            targets.append(credential)

    return EnforcementDecision(
        budget_id=state.budget.id,
        budget_name=state.budget.name,
        action=state.budget.enforcement,
        reason=f"Budget exceeded at {state.pct_used:.0%} of limit.",
        scope=state.budget.scope,
        would_affect=tuple(targets),
        spent=state.spent,
        limit=state.budget.amount,
        currency=state.budget.currency,
        dry_run=dry_run,
    )
