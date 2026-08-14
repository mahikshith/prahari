"""Synthetic LLMjacking incident generator.

**Everything this module produces is SYNTHETIC.** It exists because the real GCP
billing export for the ₹6 crore incident is not accessible yet (see ASSUMPTIONS.md A1).
Any figure derived from it must be labelled as modelled — never shown to a prospect as
if it were measured. One such slip destroys the credibility the artifact exists to build.

Calibration comes from published research, not invention:
  - Sysdig: $46,080/day sustained on a hijacked Claude 2.x account; >$100,000/day on
    Claude 3 Opus.
  - A documented Gemini key leak produced $82,000 in ~48 hours against a ~$200/month
    baseline.
  - CSA / Pillar Security "Operation Bizarre Bazaar": harvest → validate → resell via
    reverse proxy. That pipeline is why abuse traffic looks uniform, runs around the
    clock, and maxes context — it is machine demand, not human demand.

The scenario models two service accounts deliberately:

  `sa-robotics-prod`  — legitimate, busy, strong weekday/business-hours shape.
                        The control. A detector that alerts on this is useless.
  `sa-batch-legacy`   — a stale key with broad Vertex permissions, used every few
                        weeks by a batch job. This is the one that leaks.

That second profile is the realistic leak vector: not the key you watch, but the
forgotten one with too much permission sitting in a config that got pasted into a chat.
It also makes DORMANT_KEY_WAKE fire honestly — a key in daily use never could.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from prahari.core.models import (
    ChargeCategory,
    Completeness,
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)

IST_OFFSET = timedelta(hours=5, minutes=30)

# ₹/USD used only for artifact presentation. Production must use RBI reference rates
# dated to the transaction — see ASSUMPTIONS.md A6.
INR_PER_USD = Decimal("84")


@dataclass(frozen=True, slots=True)
class Scenario:
    """Knobs for the modelled incident. Defaults reconcile to ~$700K ≈ ₹5.9 crore."""

    seed: int = 20260815
    start: datetime = datetime(2026, 4, 1, tzinfo=UTC)

    baseline_days: int = 60
    """Legitimate history before the attack. Must exceed the detector's baseline
    window so we are testing detection, not cold-start behaviour."""

    attack_start_day: int = 62
    attack_days: int = 10
    invoice_discovery_day: int = 72
    """When the invoice actually surfaced the spend - and therefore when the attack
    stopped, because discovery is what ended it. Defaults to coincide with
    `attack_start_day + attack_days` for that reason.

    The gap between attack onset and this day is the entire value proposition: every
    rupee in it is exposure that sub-hour detection would have prevented."""

    attack_hourly_usd: Decimal = Decimal("2917")
    """≈$70K/day — between Sysdig's Claude 2.x ($46K) and Opus (>$100K) figures."""

    attack_ramp_usd: Decimal = Decimal("800")
    """First hour, before the operation scales up."""

    legit_account: str = "sa-robotics-prod@example.iam.gserviceaccount.com"
    stale_account: str = "sa-batch-legacy@example.iam.gserviceaccount.com"

    legit_model: str = "gemini-1.5-flash"
    attack_model: str = "gemini-1.5-pro"
    """Escalation to a premium model: attackers reselling access optimise for output
    quality, not cost. They did not pay for it."""

    home_country: str = "IN"
    attack_country: str = "RU"
    home_asn: str = "AS55836"
    attack_asn: str = "AS204601"

    include_legit_burst: bool = True
    """A real deploy-day spike on the control account. Included deliberately: an
    artifact that reports its own false positives is more credible than one claiming
    perfection, and a detector nobody trusts gets muted."""

    legit_burst_day: int = 40

    batch_interval_days: int = 21
    batch_decommissioned_day: int = 30
    """The batch job was retired and nobody revoked its key.

    This is the realistic provenance of a stale credential with broad permissions -
    not an oversight in a system someone watches, but a leftover from a system nobody
    watches any more. It is also what makes the key genuinely dormant for >30 days,
    which is what DORMANT_KEY_WAKE needs to fire honestly."""

    _premium: frozenset[str] = field(default_factory=lambda: frozenset({"gemini-1.5-pro"}))


def _ist_hour(dt: datetime) -> int:
    return (dt + IST_OFFSET).hour


def _ist_weekday(dt: datetime) -> int:
    return (dt + IST_OFFSET).weekday()


def _legit_hourly_usd(dt: datetime, rng: random.Random) -> Decimal:
    """Human-shaped demand: weekday business hours in IST, quiet nights and weekends.

    This shape is the reason baselines must be deseasonalised. A flat threshold on
    this series alerts every Monday morning.
    """
    hour, weekday = _ist_hour(dt), _ist_weekday(dt)

    if weekday >= 5:
        base = rng.uniform(2.0, 8.0)
    elif 9 <= hour < 19:
        base = rng.uniform(22.0, 46.0)
    elif 19 <= hour < 22 or 7 <= hour < 9:
        base = rng.uniform(8.0, 20.0)
    else:
        base = rng.uniform(0.4, 3.0)

    return Decimal(str(round(base, 4)))


def _record(
    *,
    account: str,
    hour: datetime,
    usd: Decimal,
    model: str,
    country: str,
    asn: str,
    context_utilisation: float,
    rng: random.Random,
    source: str,
) -> UsageRecord:
    """One hour of usage. Token counts are derived from spend at a plausible blended
    rate — they are illustrative, not a pricing claim."""
    total_tokens = int(usd * Decimal(str(rng.uniform(180_000, 260_000))))
    output_tokens = int(total_tokens * rng.uniform(0.18, 0.32))
    input_tokens = total_tokens - output_tokens

    # Split spend across components the way a real bill does, so downstream code
    # exercises the same shape it will see in production.
    output_cost = (usd * Decimal("0.62")).quantize(Decimal("0.000001"))
    input_cost = (usd - output_cost).quantize(Decimal("0.000001"))

    return UsageRecord(
        provider=Provider.GCP_VERTEX,
        account_id="synthetic-project",
        api_key_id=account,
        model=model,
        region="asia-south1",
        charge_category=ChargeCategory.USAGE,
        tokens=TokenCounts(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=max(1, int(usd * Decimal(str(rng.uniform(2.0, 6.0))))),
        ),
        costs=CostComponents(input_cost=input_cost, output_cost=output_cost),
        billed_cost=usd,
        currency="USD",
        period_start=hour,
        period_end=hour + timedelta(hours=1),
        ingested_at=hour + timedelta(minutes=5),
        source=source,
        completeness=Completeness.FINAL,
        extensions={
            "synthetic": True,
            "country": country,
            "asn": asn,
            "max_context_utilisation": round(context_utilisation, 3),
        },
    )


def generate(scenario: Scenario | None = None) -> list[UsageRecord]:
    """Produce hourly records for both accounts across the full window.

    Returns records in chronological order, exactly as a connector backfill would.
    """
    sc = scenario or Scenario()
    rng = random.Random(sc.seed)
    records: list[UsageRecord] = []

    total_hours = sc.invoice_discovery_day * 24
    attack_start_h = sc.attack_start_day * 24
    attack_end_h = attack_start_h + sc.attack_days * 24
    burst_start_h = sc.legit_burst_day * 24 + 10  # ~15:30 IST, a plausible deploy window

    for h in range(total_hours):
        hour = sc.start + timedelta(hours=h)

        # --- control account: legitimate throughout ---
        usd = _legit_hourly_usd(hour, rng)
        if sc.include_legit_burst and burst_start_h <= h < burst_start_h + 5:
            # A real evaluation run. Large, brief, from the usual place, on the usual
            # model. This SHOULD look different from an attack, and the artifact
            # reports honestly if it doesn't.
            usd *= Decimal(str(rng.uniform(4.5, 6.5)))

        records.append(
            _record(
                account=sc.legit_account,
                hour=hour,
                usd=usd.quantize(Decimal("0.0001")),
                model=sc.legit_model,
                country=sc.home_country,
                asn=sc.home_asn,
                context_utilisation=rng.uniform(0.15, 0.55),
                rng=rng,
                source="synthetic:legit",
            )
        )

        # --- stale account: rare batch runs, then the attack ---
        if h < attack_start_h:
            # Runs every few weeks until the job is decommissioned, after which the
            # key is simply forgotten. The long silence that follows is what makes
            # the eventual wake-up detectable.
            decommissioned_h = sc.batch_decommissioned_day * 24
            in_batch_window = (h % (24 * sc.batch_interval_days)) < 4
            if in_batch_window and h < decommissioned_h:
                records.append(
                    _record(
                        account=sc.stale_account,
                        hour=hour,
                        usd=Decimal(str(round(rng.uniform(3.0, 11.0), 4))),
                        model=sc.legit_model,
                        country=sc.home_country,
                        asn=sc.home_asn,
                        context_utilisation=rng.uniform(0.2, 0.4),
                        rng=rng,
                        source="synthetic:batch",
                    )
                )
        elif h < attack_end_h:
            offset = h - attack_start_h
            if offset == 0:
                usd = sc.attack_ramp_usd
            else:
                # Sustained and uniform — machine demand has no diurnal shape.
                usd = sc.attack_hourly_usd * Decimal(str(rng.uniform(0.88, 1.12)))

            records.append(
                _record(
                    account=sc.stale_account,
                    hour=hour,
                    usd=usd.quantize(Decimal("0.0001")),
                    model=sc.attack_model,
                    country=sc.attack_country,
                    asn=sc.attack_asn,
                    context_utilisation=rng.uniform(0.88, 0.98),
                    rng=rng,
                    source="synthetic:attack",
                )
            )

    return records


def attack_window(scenario: Scenario | None = None) -> tuple[datetime, datetime, datetime]:
    """(attack_start, attack_end, invoice_discovery) — ground truth for scoring."""
    sc = scenario or Scenario()
    return (
        sc.start + timedelta(days=sc.attack_start_day),
        sc.start + timedelta(days=sc.attack_start_day + sc.attack_days),
        sc.start + timedelta(days=sc.invoice_discovery_day),
    )


def to_inr(usd: Decimal) -> Decimal:
    return (usd * INR_PER_USD).quantize(Decimal("0.01"))


def group_indian(amount: Decimal) -> str:
    """Indian digit grouping: 1234567 -> '12,34,567'.

    Last three digits, then pairs. Western grouping on an Indian invoice reads as
    carelessness to the buyer we are selling to.
    """
    digits = f"{int(amount.quantize(Decimal('1')))}"
    sign, digits = ("-", digits[1:]) if digits.startswith("-") else ("", digits)
    if len(digits) <= 3:
        return sign + digits

    head, tail = digits[:-3], digits[-3:]
    pairs = []
    while len(head) > 2:
        head, pair = head[:-2], head[-2:]
        pairs.insert(0, pair)
    if head:
        pairs.insert(0, head)
    return sign + ",".join([*pairs, tail])


def format_inr_crore(usd: Decimal) -> str:
    """Indian numbering, because the buyer thinks in crore and lakh, not millions."""
    inr = to_inr(usd)
    crore = inr / Decimal("10000000")
    lakh = inr / Decimal("100000")
    if crore >= 1:
        return f"Rs {crore.quantize(Decimal('0.01'))} crore"
    if lakh >= 1:
        return f"Rs {lakh.quantize(Decimal('0.01'))} lakh"
    return f"Rs {group_indian(inr)}"
