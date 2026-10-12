"""Detection engine - the moat.

Five named rules matching the LLMjacking fingerprint. Deliberately statistical and
rule-based rather than learned: a CFO must be able to read why an alert fired, and
"the model said so" does not survive a budget conversation. That is a product
requirement (docs/REQUIREMENTS.md F5), not a preference.

Reference rates, from Sysdig's LLMjacking research: a single hijacked account
sustained $46,080/day on Claude 2.x and exceeded $100,000/day on Claude 3 Opus.
Against a 24h+ billing-export lag, daily-granularity tools cannot catch this even
in principle. Our target is a median detection under 60 minutes.
"""

from __future__ import annotations

import statistics
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from prahari.core.fx import FxError, FxTable

# --- tunables -----------------------------------------------------------------
# Defaults are starting points, to be calibrated against the backtest and real
# design-partner data. Each is a false-positive/miss tradeoff we must own explicitly.
# See ASSUMPTIONS.md A7.

SPEND_SPIKE_MULTIPLE = Decimal("3.2")
"""1h spend vs the deseasonalised 7-day hourly mean. 3.2x is the widely-cited
starting threshold; calibrate before trusting it."""

SPEND_SPIKE_MIN_ABSOLUTE = Decimal("50")
"""Floor in USD. Without this, a key that normally spends $0.10/hr alerts at $0.35 -
technically a 3.5x spike, operationally noise."""

DORMANCY_DAYS = 30
BASELINE_WINDOW_HOURS = 24 * 7
MIN_BASELINE_SAMPLES = 24
"""Below this we have no defensible baseline. Emit a low-confidence verdict rather
than a confident wrong one."""

BUSINESS_HOURS_IST = range(9, 21)
RESALE_CONTEXT_UTILISATION = 0.85
RESALE_MIN_HOURS = 3

SEASONAL_SAMPLES_PER_SLOT = 8
"""Weeks of history kept per hour-of-week slot.

Bounded deliberately. This dict was previously uncapped and grew one entry per
observation forever - 9,600 entries after a 400-day replay, and `expected_spend`
averaging an ever-longer list. Eight weeks is enough to establish a weekday pattern
and keeps the structure at a fixed 168 x 8."""

DetectionKey = tuple[str, str]
"""(provider, credential). Deliberately excludes model and region - see
UsageRecord.detection_key for why partitioning by model would be an evasion hole."""


class Rule(StrEnum):
    SPEND_SPIKE = "SPEND_SPIKE"
    DORMANT_KEY_WAKE = "DORMANT_KEY_WAKE"
    NEW_GEO = "NEW_GEO"
    MODEL_ESCALATION = "MODEL_ESCALATION"
    RESALE_PATTERN = "RESALE_PATTERN"
    COST_UNAVAILABLE = "COST_UNAVAILABLE"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Observation:
    """One hour of activity for one credential."""

    detection_key: DetectionKey
    hour: datetime
    spend: Decimal
    tokens: int
    requests: int
    region: str | None = None
    country: str | None = None
    asn: str | None = None
    model: str | None = None
    max_context_utilisation: float = 0.0
    currency: str = "USD"
    """Carried through to the alert. Previously hardcoded to USD in every rule, which
    labelled an Indian estate's rupee figures as dollars - an 84x misstatement in the
    one number the alert exists to convey."""
    unpriced_records: int = 0

    def __post_init__(self) -> None:
        if self.hour.tzinfo is None:
            raise ValueError("Observation.hour must be timezone-aware (UTC)")
        object.__setattr__(self, "hour", self.hour.astimezone(UTC))
        object.__setattr__(self, "currency", self.currency.upper())

    @property
    def cost_complete(self) -> bool:
        return self.unpriced_records == 0

    @property
    def has_activity(self) -> bool:
        return self.spend > 0 or self.tokens > 0 or self.requests > 0


@dataclass(slots=True)
class Baseline:
    """Rolling per-credential history. Deseasonalised because engineering usage has a
    hard weekday pattern - a naive threshold alerts every Monday morning, and a
    detector that cries wolf weekly gets muted, which is the same as not existing."""

    detection_key: DetectionKey
    hourly_spend: deque[Decimal | None] = field(
        default_factory=lambda: deque(maxlen=BASELINE_WINDOW_HOURS)
    )
    """A deque with maxlen: the window evicts from the left on every append, and
    `list.pop(0)` is O(n) while `deque` eviction is O(1)."""

    hour_of_week_spend: dict[int, deque[Decimal | None]] = field(default_factory=dict)
    last_seen: datetime | None = None
    known_countries: set[str] = field(default_factory=set)
    known_asns: set[str] = field(default_factory=set)
    known_models: set[str] = field(default_factory=set)
    currency: str | None = None

    def observe(self, obs: Observation) -> None:
        if self.currency is not None and self.currency != obs.currency:
            raise ValueError(f"currency changed for {self.detection_key}")
        self.currency = obs.currency
        spend = obs.spend if obs.cost_complete else None
        self.hourly_spend.append(spend)

        how = _hour_of_week(obs.hour)
        slot = self.hour_of_week_spend.get(how)
        if slot is None:
            slot = deque(maxlen=SEASONAL_SAMPLES_PER_SLOT)
            self.hour_of_week_spend[how] = slot
        slot.append(spend)

        # Gap-filled hours have no activity; free or unpriced requests still count as use.
        if obs.has_activity:
            self.last_seen = obs.hour

        if obs.country:
            self.known_countries.add(obs.country)
        if obs.asn:
            self.known_asns.add(obs.asn)
        if obs.model:
            self.known_models.add(obs.model)

    @property
    def sample_count(self) -> int:
        return sum(value is not None for value in self.hourly_spend)

    @property
    def cost_complete(self) -> bool:
        return all(value is not None for value in self.hourly_spend)

    @property
    def is_established(self) -> bool:
        return self.sample_count >= MIN_BASELINE_SAMPLES

    def expected_spend(self, at: datetime) -> Decimal:
        """Expected hourly spend, seasonally adjusted when we have enough same-slot
        history. Falls back to the flat mean, which is honest rather than clever."""
        if not self.hourly_spend:
            return Decimal(0)

        seasonal = [v for v in self.hour_of_week_spend.get(_hour_of_week(at), []) if v is not None]
        known = [v for v in self.hourly_spend if v is not None]
        series = seasonal if len(seasonal) >= 3 else known
        if not series:
            return Decimal(0)
        return Decimal(str(statistics.fmean(float(x) for x in series)))

    def spend_stdev(self) -> Decimal:
        known = [v for v in self.hourly_spend if v is not None]
        if len(known) < 2:
            return Decimal(0)
        return Decimal(str(statistics.stdev(float(x) for x in known)))


@dataclass(frozen=True, slots=True)
class Alert:
    """Everything needed to justify the alert to a CFO, in the alert itself.

    `projected_24h` is the number that gets acted on: at the observed rate, this is
    the exposure if nobody intervenes. Sysdig's documented cases put that between
    $46K and $100K+ per day, which is what makes containment urgent rather than
    something to review on Monday.
    """

    rule: Rule
    severity: Severity
    detection_key: DetectionKey
    at: datetime
    observed: Decimal | None
    baseline: Decimal | None
    multiple: Decimal | None
    spend_so_far: Decimal | None
    projected_24h: Decimal | None
    currency: str
    evidence: dict[str, object]
    confidence: str = "high"

    @property
    def credential(self) -> str:
        return self.detection_key[1]

    def explain(self) -> str:
        if self.rule is Rule.COST_UNAVAILABLE:
            return (
                f"[{self.rule}] key={self.credential} | {self.evidence['reason']} | "
                "monetary anomaly rules abstained; cost and exposure are not asserted"
            )
        subtotal_label = (
            "spent so far" if self.evidence.get("cumulative_cost_complete", True)
            else "known spend subtotal; earlier usage remains unpriced"
        )
        parts = [
            f"[{self.rule}] key={self.credential}",
            f"observed {self.observed} {self.currency}/hr",
            f"baseline {self.baseline} {self.currency}/hr"
            + (f" ({self.multiple}x)" if self.multiple is not None else ""),
            f"{subtotal_label} {self.spend_so_far} {self.currency}",
            f"projected 24h exposure {self.projected_24h} {self.currency}",
        ]
        return " | ".join(parts)


def _hour_of_week(dt: datetime) -> int:
    return dt.weekday() * 24 + dt.hour


def _project_24h(hourly: Decimal) -> Decimal:
    return (hourly * 24).quantize(Decimal("0.01"))


# --- rules --------------------------------------------------------------------


def spend_spike(
    obs: Observation, bl: Baseline, spend_so_far: Decimal, minimum_absolute: Decimal | None = None
) -> Alert | None:
    """Hourly spend far above the seasonally-adjusted norm for this credential.

    The workhorse rule: it catches both LLMjacking and runaway agent loops, which
    look nearly identical from the billing side.
    """
    if not obs.cost_complete or not bl.cost_complete or not bl.is_established:
        return None
    if minimum_absolute is None and obs.currency == "USD":
        minimum_absolute = SPEND_SPIKE_MIN_ABSOLUTE
    if minimum_absolute is None or obs.spend < minimum_absolute:
        return None

    expected = bl.expected_spend(obs.hour)
    if expected <= 0:
        # No prior spend at all, but a material amount now. Real, and worth saying so.
        return Alert(
            rule=Rule.SPEND_SPIKE,
            severity=Severity.CRITICAL,
            detection_key=obs.detection_key,
            at=obs.hour,
            observed=obs.spend,
            baseline=Decimal(0),
            multiple=None,
            spend_so_far=spend_so_far,
            projected_24h=_project_24h(obs.spend),
            currency=obs.currency,
            evidence={
                "reason": "no prior spend on this credential",
                "samples": bl.sample_count,
                "model": obs.model,
                "region": obs.region,
            },
        )

    multiple = (obs.spend / expected).quantize(Decimal("0.01"))
    if multiple < SPEND_SPIKE_MULTIPLE:
        return None

    return Alert(
        rule=Rule.SPEND_SPIKE,
        severity=Severity.CRITICAL if multiple >= 10 else Severity.WARNING,
        detection_key=obs.detection_key,
        at=obs.hour,
        observed=obs.spend,
        baseline=expected.quantize(Decimal("0.01")),
        multiple=multiple,
        spend_so_far=spend_so_far,
        projected_24h=_project_24h(obs.spend),
        currency=obs.currency,
        evidence={
            "threshold": str(SPEND_SPIKE_MULTIPLE),
            "stdev": str(bl.spend_stdev()),
            "samples": bl.sample_count,
            "seasonally_adjusted": len(bl.hour_of_week_spend.get(_hour_of_week(obs.hour), []))
            >= 3,
            "model": obs.model,
            "region": obs.region,
        },
    )


def dormant_key_wake(obs: Observation, bl: Baseline, spend_so_far: Decimal) -> Alert | None:
    """A credential idle for weeks suddenly transacting.

    High signal, low noise: this is the classic shape of a credential harvested some
    time ago and only now monetised - exactly the incident pattern. It only works
    because the baseline is per-credential; a key in daily use can never go dormant.
    """
    if not obs.cost_complete or bl.last_seen is None or not obs.has_activity:
        return None

    idle = obs.hour - bl.last_seen
    if idle < timedelta(days=DORMANCY_DAYS):
        return None

    return Alert(
        rule=Rule.DORMANT_KEY_WAKE,
        severity=Severity.CRITICAL,
        detection_key=obs.detection_key,
        at=obs.hour,
        observed=obs.spend,
        baseline=bl.expected_spend(obs.hour).quantize(Decimal("0.01")),
        multiple=None,
        spend_so_far=spend_so_far,
        projected_24h=_project_24h(obs.spend),
        currency=obs.currency,
        evidence={
            "idle_days": idle.days,
            "last_seen": bl.last_seen.isoformat(),
            "model": obs.model,
        },
    )


def new_geo(
    obs: Observation, bl: Baseline, spend_so_far: Decimal, minimum_absolute: Decimal | None = None
) -> Alert | None:
    """Known credential, never-before-seen country or network.

    Requires the provider or cloud audit log to expose caller origin. Where it is
    unavailable the rule stays silent rather than guessing - a detector that
    fabricates evidence is worse than one that abstains. See ASSUMPTIONS.md A5.
    """
    if not obs.cost_complete or not bl.is_established:
        return None

    novel: dict[str, object] = {}
    if obs.country and obs.country not in bl.known_countries:
        novel["new_country"] = obs.country
        novel["known_countries"] = sorted(bl.known_countries)
    if obs.asn and obs.asn not in bl.known_asns:
        novel["new_asn"] = obs.asn
    if not novel:
        return None
    if minimum_absolute is None and obs.currency == "USD":
        minimum_absolute = SPEND_SPIKE_MIN_ABSOLUTE

    return Alert(
        rule=Rule.NEW_GEO,
        severity=(
            Severity.CRITICAL
            if minimum_absolute is not None and obs.spend >= minimum_absolute
            else Severity.WARNING
        ),
        detection_key=obs.detection_key,
        at=obs.hour,
        observed=obs.spend,
        baseline=bl.expected_spend(obs.hour).quantize(Decimal("0.01")),
        multiple=None,
        spend_so_far=spend_so_far,
        projected_24h=_project_24h(obs.spend),
        currency=obs.currency,
        evidence=novel,
    )


def model_escalation(
    obs: Observation, bl: Baseline, spend_so_far: Decimal, premium_models: set[str]
) -> Alert | None:
    """Abrupt switch to a premium model on a credential that never used one.

    Attackers reselling access optimise for output quality, not cost - they did not
    pay for it. Legitimate teams migrate models gradually and deliberately.

    Only detectable because the baseline is per-credential rather than per-(key,model):
    partitioning by model would give the switch a fresh empty baseline instead.
    """
    if not obs.cost_complete or not bl.is_established or not obs.model:
        return None
    if obs.model in bl.known_models or obs.model not in premium_models:
        return None

    return Alert(
        rule=Rule.MODEL_ESCALATION,
        severity=Severity.WARNING,
        detection_key=obs.detection_key,
        at=obs.hour,
        observed=obs.spend,
        baseline=bl.expected_spend(obs.hour).quantize(Decimal("0.01")),
        multiple=None,
        spend_so_far=spend_so_far,
        projected_24h=_project_24h(obs.spend),
        currency=obs.currency,
        evidence={"new_model": obs.model, "previous_models": sorted(bl.known_models)},
    )


def resale_pattern(window: list[Observation], bl: Baseline, spend_so_far: Decimal) -> Alert | None:
    """Sustained near-maximum context outside business hours.

    The signature of a reverse-proxy resale operation: continuous, uniform, maxed-out
    requests with none of the diurnal shape of human-driven work.
    """
    if len(window) < RESALE_MIN_HOURS or any(
        not o.cost_complete for o in window[-RESALE_MIN_HOURS:]
    ):
        return None

    qualifying = [
        o
        for o in window[-RESALE_MIN_HOURS:]
        if o.max_context_utilisation >= RESALE_CONTEXT_UTILISATION
        and _to_ist_hour(o.hour) not in BUSINESS_HOURS_IST
        and o.spend > 0
    ]
    if len(qualifying) < RESALE_MIN_HOURS:
        return None

    latest = qualifying[-1]
    return Alert(
        rule=Rule.RESALE_PATTERN,
        severity=Severity.WARNING,
        detection_key=latest.detection_key,
        at=latest.hour,
        observed=latest.spend,
        baseline=bl.expected_spend(latest.hour).quantize(Decimal("0.01")),
        multiple=None,
        spend_so_far=spend_so_far,
        projected_24h=_project_24h(latest.spend),
        currency=latest.currency,
        evidence={
            "sustained_hours": len(qualifying),
            "context_utilisation": round(
                statistics.fmean(o.max_context_utilisation for o in qualifying), 3
            ),
            "outside_business_hours_ist": True,
        },
        confidence="medium",
    )


def _to_ist_hour(dt: datetime) -> int:
    return (dt.astimezone(UTC) + timedelta(hours=5, minutes=30)).hour


# --- engine -------------------------------------------------------------------


class Detector:
    """Stateful across a replay or a live stream. Deliberately ordered: evaluate
    against the baseline *before* folding the observation in, or a spike teaches the
    baseline that spikes are normal and the second hour of an attack looks fine."""

    def __init__(
        self,
        premium_models: set[str] | None = None,
        *,
        fx: FxTable | None = None,
        last_activity: Mapping[DetectionKey, datetime] | None = None,
    ) -> None:
        self._baselines: dict[DetectionKey, Baseline] = {}
        self._windows: dict[DetectionKey, list[Observation]] = {}
        self._cumulative: dict[DetectionKey, Decimal] = {}
        self._premium_models = premium_models or set()
        self._fx = fx if fx is not None else FxTable([])
        self._last_activity = dict(last_activity or {})
        if any(at.tzinfo is None for at in self._last_activity.values()):
            raise ValueError("last_activity timestamps must be timezone-aware")
        self._unpriced_keys: set[DetectionKey] = set()

    def process(self, obs: Observation) -> list[Alert]:
        key = obs.detection_key
        bl = self._baselines.setdefault(
            key, Baseline(detection_key=key, last_seen=self._last_activity.get(key))
        )
        if bl.currency is not None and bl.currency != obs.currency:
            raise ValueError(f"currency changed for {key}: {bl.currency} to {obs.currency}")
        window = self._windows.setdefault(key, [])

        spend_so_far = self._cumulative.get(key, Decimal(0)) + obs.spend

        reason = None
        minimum_absolute = None
        if not obs.cost_complete:
            self._unpriced_keys.add(key)
            reason = f"price unavailable for {obs.unpriced_records} usage records"
        elif not bl.cost_complete:
            reason = "pricing gaps in baseline history prevent monetary anomaly comparisons"
        else:
            try:
                minimum_absolute = self._fx.convert(
                    SPEND_SPIKE_MIN_ABSOLUTE, "USD", obs.currency, obs.hour.date()
                )
            except FxError:
                reason = f"no configured USD to {obs.currency} FX rate for spend thresholds"

        alerts = []
        if reason is None:
            alerts = [
                a
                for a in (
                    spend_spike(obs, bl, spend_so_far, minimum_absolute),
                    dormant_key_wake(obs, bl, spend_so_far),
                    new_geo(obs, bl, spend_so_far, minimum_absolute),
                    model_escalation(obs, bl, spend_so_far, self._premium_models),
                    resale_pattern([*window, obs], bl, spend_so_far),
                )
                if a is not None
            ]
        elif obs.has_activity or not obs.cost_complete:
            alerts = [Alert(
                rule=Rule.COST_UNAVAILABLE,
                severity=Severity.WARNING,
                detection_key=key,
                at=obs.hour,
                observed=None,
                baseline=None,
                multiple=None,
                spend_so_far=None,
                projected_24h=None,
                currency=obs.currency,
                evidence={
                    "reason": reason,
                    "unpriced_records": obs.unpriced_records,
                    "tokens": obs.tokens,
                    "requests": obs.requests,
                },
            )]
        if key in self._unpriced_keys:
            alerts = [
                replace(a, evidence={**a.evidence, "cumulative_cost_complete": False})
                for a in alerts
            ]

        # Only now update state.
        bl.observe(obs)
        window.append(obs)
        if len(window) > RESALE_MIN_HOURS * 4:
            window.pop(0)
        self._cumulative[key] = spend_so_far

        return alerts

    def baseline_for(self, key: DetectionKey) -> Baseline | None:
        return self._baselines.get(key)

    def cumulative_spend(self, key: DetectionKey) -> Decimal:
        return self._cumulative.get(key, Decimal(0))
