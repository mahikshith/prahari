"""Synthetic multi-project fleet - for exercising budgets, rankings and allocation.

**SYNTHETIC.** Companion to `incident.py`, which models one attack in detail. This
models the boring steady state around it: several projects, several services, several
people, a month of ordinary spend. You need both, because a control plane has to be
demonstrably quiet on normal traffic before anyone cares that it catches attacks.

Deliberately built in:
  - a project quietly blowing a service-level budget (`customer-api` on Cloud Run),
    so budget breach and enforcement dry-run have something real to fire on
  - one BigQuery project with a single catastrophic query day, because that is the
    most common non-AI cost surprise and it should not look like an attack
  - a slice of spend with no cost-centre label, so `allocation_coverage` reports an
    honest number below 100% rather than a flattering one
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from prahari.core.models import (
    AllocationMethod,
    ChargeCategory,
    Completeness,
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)

IST = timedelta(hours=5, minutes=30)


@dataclass(frozen=True, slots=True)
class ProjectSpec:
    project_id: str
    project_name: str
    cost_centre: str | None
    services: tuple[str, ...]
    scale: float
    users: tuple[str, ...] = ()


DEFAULT_PROJECTS: tuple[ProjectSpec, ...] = (
    ProjectSpec(
        "robotics-prod",
        "Robotics Production",
        "cc-robotics",
        ("Vertex AI", "Cloud Run", "BigQuery"),
        scale=1.0,
        users=("arjun.m@example.com", "priya.s@example.com", "vikram.r@example.com"),
    ),
    ProjectSpec(
        "data-platform",
        "Data Platform",
        "cc-data",
        ("BigQuery", "Cloud Run", "Cloud Storage"),
        scale=0.85,
        users=("neha.k@example.com", "arjun.m@example.com"),
    ),
    ProjectSpec(
        "customer-api",
        "Customer API",
        "cc-product",
        ("Cloud Run", "Vertex AI"),
        scale=0.55,
        users=("rahul.d@example.com", "priya.s@example.com"),
    ),
    # No cost centre: this is the slice that shows up as unallocated, on purpose.
    ProjectSpec(
        "ml-sandbox",
        "ML Sandbox",
        None,
        ("Vertex AI", "Cloud Storage"),
        scale=0.2,
        users=("intern.a@example.com",),
    ),
)

SERVICE_CATEGORY = {
    "Vertex AI": "ai",
    "BigQuery": "data",
    "Cloud Run": "compute",
    "Cloud Storage": "other",
}

SERVICE_SKU = {
    "Vertex AI": "Gemini 2.5 Flash Input Tokens",
    "BigQuery": "Analysis",
    "Cloud Run": "CPU Allocation Time",
    "Cloud Storage": "Standard Storage IN",
}

# Rs/hour at scale 1.0, before diurnal and weekday shaping.
SERVICE_BASE_INR = {
    "Vertex AI": Decimal("900"),
    "BigQuery": Decimal("1400"),
    "Cloud Run": Decimal("650"),
    "Cloud Storage": Decimal("120"),
}


@dataclass(frozen=True, slots=True)
class FleetScenario:
    seed: int = 771026

    start: datetime = datetime(2026, 6, 30, 18, 30, tzinfo=UTC)
    """00:00 IST on 1 July - **not** midnight UTC.

    Budget periods close on IST calendar boundaries because that is when Indian
    finance closes. A scenario aligned to UTC spills its last 5.5 hours into the next
    IST month, which silently evaluates budgets against a nearly empty period. This
    caught us once already; the offset is deliberate."""

    days: int = 31
    projects: tuple[ProjectSpec, ...] = DEFAULT_PROJECTS

    cloud_run_blowout_project: str = "customer-api"
    cloud_run_blowout_from_day: int = 12
    cloud_run_blowout_multiple: float = 4.2
    """A deploy that shipped a hot loop. Costs stay elevated because nobody noticed -
    which is the ordinary, non-malicious way budgets die."""

    bigquery_bad_query_project: str = "data-platform"
    bigquery_bad_query_day: int = 19
    bigquery_bad_query_multiple: float = 26.0
    """One unpartitioned full-table scan. Enormous, single-day, and emphatically not
    an attack - the detector should treat it differently."""

    _rng: random.Random = field(default_factory=lambda: random.Random(0), compare=False)


def _shape(hour: datetime, rng: random.Random) -> float:
    """Human working-pattern multiplier, in IST."""
    local = hour + IST
    if local.weekday() >= 5:
        return rng.uniform(0.12, 0.30)
    if 10 <= local.hour < 19:
        return rng.uniform(0.85, 1.30)
    if 7 <= local.hour < 10 or 19 <= local.hour < 22:
        return rng.uniform(0.40, 0.75)
    return rng.uniform(0.05, 0.20)


def generate(scenario: FleetScenario | None = None) -> list[UsageRecord]:
    sc = scenario or FleetScenario()
    rng = random.Random(sc.seed)
    records: list[UsageRecord] = []
    now = sc.start + timedelta(days=sc.days)

    for day in range(sc.days):
        for hour_of_day in range(24):
            hour = sc.start + timedelta(days=day, hours=hour_of_day)

            for project in sc.projects:
                for service in project.services:
                    inr = (
                        SERVICE_BASE_INR[service]
                        * Decimal(str(project.scale))
                        * Decimal(str(round(_shape(hour, rng), 4)))
                    )

                    if (
                        service == "Cloud Run"
                        and project.project_id == sc.cloud_run_blowout_project
                        and day >= sc.cloud_run_blowout_from_day
                    ):
                        inr *= Decimal(str(sc.cloud_run_blowout_multiple))

                    if (
                        service == "BigQuery"
                        and project.project_id == sc.bigquery_bad_query_project
                        and day == sc.bigquery_bad_query_day
                        and 11 <= hour_of_day <= 13
                    ):
                        inr *= Decimal(str(sc.bigquery_bad_query_multiple))

                    if inr <= 0:
                        continue

                    records.append(
                        _record(
                            project=project,
                            service=service,
                            hour=hour,
                            inr=inr.quantize(Decimal("0.0001")),
                            rng=rng,
                            now=now,
                        )
                    )

    return records


def _record(
    *,
    project: ProjectSpec,
    service: str,
    hour: datetime,
    inr: Decimal,
    rng: random.Random,
    now: datetime,
) -> UsageRecord:
    category = SERVICE_CATEGORY[service]
    is_ai = category == "ai"

    tokens = TokenCounts()
    user: str | None = None
    if is_ai:
        # Rs -> tokens at a plausible blended Gemini Flash rate. Illustrative.
        total = int(inr * Decimal(str(rng.uniform(2400, 3600))))
        output = int(total * rng.uniform(0.15, 0.30))
        cached = int(total * rng.uniform(0.05, 0.20))
        tokens = TokenCounts(
            input_tokens=max(0, total - output - cached),
            output_tokens=output,
            cache_read_tokens=cached,
            requests=max(1, int(inr / Decimal("12"))),
        )
        user = rng.choice(project.users) if project.users else None

    return UsageRecord(
        provider=Provider.GCP_VERTEX,
        account_id="billing-acct-synthetic",
        user_id=user,
        project_id=project.project_id,
        model="Gemini 2.5 Flash" if is_ai else None,
        operation=SERVICE_SKU[service],
        region="asia-south1",
        charge_category=ChargeCategory.USAGE,
        tokens=tokens,
        costs=CostComponents(other=inr),
        billed_cost=inr,
        currency="INR",
        period_start=hour,
        period_end=hour + timedelta(hours=1),
        ingested_at=now,
        cost_centre=project.cost_centre,
        allocation_method=(
            AllocationMethod.RESOURCE_TAG if project.cost_centre else AllocationMethod.UNALLOCATED
        ),
        source="synthetic:fleet",
        completeness=Completeness.FINAL,
        extensions={
            "synthetic": True,
            "service": service,
            "service_category": category,
            "sku": SERVICE_SKU[service],
            "project_name": project.project_name,
        },
    )


def prior_period(scenario: FleetScenario | None = None) -> list[UsageRecord]:
    """The month before, without the blowouts - the baseline `movers` compares to."""
    sc = scenario or FleetScenario()
    quiet = FleetScenario(
        seed=sc.seed + 1,
        start=sc.start - timedelta(days=30),
        days=30,
        projects=sc.projects,
        cloud_run_blowout_from_day=10_000,
        bigquery_bad_query_day=-1,
    )
    return generate(quiet)
