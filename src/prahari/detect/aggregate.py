"""UsageRecord -> Observation.

Connectors emit records at the finest grain a provider exposes - often several per
hour per credential, split by model, operation, or service tier. The detector needs
one observation per credential per hour, so this is where that roll-up happens.

Deliberately a separate stage: it is the only place that decides how sub-hour detail
collapses, and those choices matter. Taking `max` on context utilisation rather than
the mean, for instance, is what lets RESALE_PATTERN see a maxed-out request hiding
inside an hour of otherwise ordinary traffic.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal

from prahari.core.models import UsageRecord
from prahari.detect.rules import DetectionKey, Observation


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def observations_from_records(
    records: Iterable[UsageRecord],
    *,
    fill_gaps: bool = True,
) -> list[Observation]:
    """Roll records up to hourly observations, chronologically ordered.

    `fill_gaps` inserts zero-spend hours between a credential's first and last
    activity, so the baseline reflects the real norm. Without it, a credential that
    runs four hours a month has a baseline computed only from its busy hours, and its
    "expected" spend is wildly overstated - which suppresses exactly the spike we need
    to catch.

    Zero hours are fed to the baseline but do **not** refresh `last_seen`, which
    tracks activity rather than observations. That separation is what lets a
    gap-filled series still trigger DORMANT_KEY_WAKE (see `Baseline.observe`).
    """
    buckets: dict[tuple[DetectionKey, datetime], list[UsageRecord]] = defaultdict(list)

    for rec in records:
        buckets[(rec.detection_key, _floor_hour(rec.period_start))].append(rec)

    observations = [_collapse(key, hour, group) for (key, hour), group in buckets.items()]

    if fill_gaps:
        observations = _fill_zero_hours(observations)

    observations.sort(key=lambda o: (o.hour, o.detection_key))
    return observations


def _collapse(key: DetectionKey, hour: datetime, group: list[UsageRecord]) -> Observation:
    spend = sum((r.billed_cost for r in group), Decimal(0))

    # Attribute the hour to whatever drove most of the spend. An attacker's premium
    # model dominates cost even when it is a minority of requests, which is exactly
    # the attribution we want for MODEL_ESCALATION.
    dominant = max(group, key=lambda r: r.billed_cost)

    def ext(name: str):
        for rec in sorted(group, key=lambda r: r.billed_cost, reverse=True):
            if (value := rec.extensions.get(name)) is not None:
                return value
        return None

    utilisations = [
        float(r.extensions.get("max_context_utilisation", 0.0) or 0.0) for r in group
    ]

    return Observation(
        detection_key=key,
        hour=hour,
        spend=spend,
        tokens=sum(r.tokens.total_tokens for r in group),
        requests=sum(r.tokens.requests for r in group),
        region=dominant.region,
        country=ext("country"),
        asn=ext("asn"),
        model=dominant.model,
        max_context_utilisation=max(utilisations, default=0.0),
        # Taken from the spend-dominant record. Alerts quote this currency, and
        # labelling a rupee figure as dollars misstates the one number the alert
        # exists to convey.
        currency=dominant.currency,
    )


def _fill_zero_hours(observations: list[Observation]) -> list[Observation]:
    """Insert zero-spend hours inside each credential's active span.

    Bounded to the observed span on purpose - we do not invent history before a
    credential existed, and a baseline padded with fabricated zeros would understate
    the norm and make every real hour look like a spike.
    """
    by_key: dict[DetectionKey, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_key[obs.detection_key].append(obs)

    filled: list[Observation] = []
    for key, series in by_key.items():
        series.sort(key=lambda o: o.hour)
        seen = {o.hour for o in series}
        filled.extend(series)

        cursor = series[0].hour
        last = series[-1].hour
        while cursor < last:
            cursor += timedelta(hours=1)
            if cursor not in seen:
                filled.append(
                    Observation(
                        detection_key=key,
                        hour=cursor,
                        spend=Decimal(0),
                        tokens=0,
                        requests=0,
                    )
                )

    return filled
