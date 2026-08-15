"""Cost report - consumption, rankings, budgets, enforcement dry-run.

The FinOps-lead view: who is spending, on what, which budgets are in trouble, and
what would happen if enforcement were switched on.

Runs on the synthetic fleet (`synth/fleet.py`) until real connector data is wired in.
The analysis code is the same either way - only the source changes.

Usage:
    uv run python scripts/report.py
    uv run python scripts/report.py --json out/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prahari.core.budget import (
    Budget,
    BudgetPeriod,
    EnforcementAction,
    decide_enforcement,
    evaluate_all,
)
from prahari.core.fx import format_inr
from prahari.core.insights import (
    ai_vs_cloud_split,
    allocation_coverage,
    bottom_consumers,
    movers,
    per_user_consumption,
    top_consumers,
)
from prahari.synth.fleet import FleetScenario, generate, prior_period

W = 78
BAR = "=" * W


def head(title: str) -> None:
    print(f"\n{BAR}\n  {title}\n{BAR}")


def default_budgets() -> list[Budget]:
    """Budget shapes customers actually ask for, including the composite scope -
    a rupee limit on one service inside one project."""
    return [
        Budget(
            id="bud-org-ai",
            name="Organisation AI spend",
            amount=Decimal("6000000"),  # Rs 60 lakh
            scope={"service_category": "ai"},
            period=BudgetPeriod.MONTHLY,
            owner="cto@example.com",
        ),
        Budget(
            id="bud-customer-api-run",
            name="Customer API - Cloud Run",
            amount=Decimal("200000"),  # Rs 2 lakh
            scope={"project_id": "customer-api", "service": "Cloud Run"},
            period=BudgetPeriod.MONTHLY,
            enforcement=EnforcementAction.HARD_STOP,
            owner="rahul.d@example.com",
        ),
        Budget(
            id="bud-data-bq",
            name="Data Platform - BigQuery",
            amount=Decimal("1500000"),  # Rs 15 lakh
            scope={"project_id": "data-platform", "service": "BigQuery"},
            period=BudgetPeriod.MONTHLY,
            enforcement=EnforcementAction.THROTTLE,
            owner="neha.k@example.com",
        ),
        Budget(
            id="bud-sandbox",
            name="ML Sandbox (all services)",
            amount=Decimal("400000"),  # Rs 4 lakh
            scope={"project_id": "ml-sandbox"},
            period=BudgetPeriod.MONTHLY,
        ),
        Budget(
            id="bud-cc-robotics",
            name="Robotics cost centre",
            amount=Decimal("5000000"),  # Rs 50 lakh
            scope={"cost_centre": "cc-robotics"},
            period=BudgetPeriod.MONTHLY,
        ),
    ]


def consumption_table(rows, *, show_tokens: bool = False) -> None:
    for row in rows:
        line = f"    {row.key:<34} {format_inr(row.cost):>16}  {row.share:>6.1%}"
        if show_tokens and row.total_tokens:
            rate = row.cost_per_million_tokens
            line += f"  {row.total_tokens / 1e6:>8.1f}M tok"
            if rate is not None:
                line += f"  Rs {rate}/M"
        print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    scenario = FleetScenario()
    records = generate(scenario)
    previous = prior_period(scenario)
    as_of = scenario.start + timedelta(days=scenario.days) - timedelta(hours=1)

    print(f"\n{len(records):,} synthetic records | {scenario.days} days "
          f"| *** SYNTHETIC DATA ***")

    # --- where the money goes -------------------------------------------------
    head("SPEND BY CATEGORY")
    split = ai_vs_cloud_split(records)
    total = sum(split.values(), Decimal(0))
    for category, amount in split.items():
        share = (amount / total) if total else Decimal(0)
        print(f"    {category:<34} {format_inr(amount):>16}  {share:>6.1%}")
    print(f"    {'TOTAL':<34} {format_inr(total):>16}")
    print("\n  AI is the wedge; the rest is the North Star. Same pipeline, one query.")

    head("TOP PROJECTS")
    consumption_table(top_consumers(records, "project_id", n=10))

    head("LOWEST-SPEND PROJECTS (excluding zero)")
    consumption_table(bottom_consumers(records, "project_id", n=5))
    print("\n  A provisioned project at near-zero spend is a stalled rollout or an")
    print("  unused licence. Both are money.")

    head("TOP SERVICES")
    consumption_table(top_consumers(records, "service", n=10))

    # --- people ---------------------------------------------------------------
    head("PER-USER CONSUMPTION (AI)")
    # AI records only. Infrastructure spend has no user attached, and mixing it in
    # would bury every real person under a huge "(unattributed)" row.
    ai_records = [r for r in records if r.extensions.get("service_category") == "ai"]
    print(f"    {'user':<34} {'cost':>16}  {'share':>6}  {'tokens':>10}  blended")
    consumption_table(per_user_consumption(ai_records)[:10], show_tokens=True)
    print("\n  Blended Rs/M-token is the efficiency number: two people on the same")
    print("  workload with a 3x gap are making different model choices.")

    # --- what changed ---------------------------------------------------------
    head("BIGGEST MOVERS vs PRIOR PERIOD")
    for m in movers(records, previous, "project_id", n=6):
        pct = "new" if m.is_new else (f"{m.pct_change:+.0%}" if m.pct_change is not None else "-")
        arrow = "UP  " if m.delta > 0 else "DOWN"
        print(f"    {arrow} {m.key:<28} {format_inr(m.delta):>16}  {pct:>8}"
              f"   ({format_inr(m.prior)} -> {format_inr(m.current)})")

    # --- budgets --------------------------------------------------------------
    head("BUDGETS")
    budgets = default_budgets()
    states = evaluate_all(budgets, records, as_of=as_of)

    for st in states:
        marker = {"ok": "  ", "warning": "! ", "critical": "!!", "exceeded": "XX"}[st.status]
        print(f"\n  {marker} {st.budget.name}  [{st.budget.describe_scope}]")
        print(f"       spent    {format_inr(st.spent):>16} of {format_inr(st.budget.amount)}"
              f"   ({st.pct_used:.0%})")
        print(f"       burn     {format_inr(st.burn_rate_per_day, scale=False):>16}/day"
              f"   (last 7d: {format_inr(st.recent_burn_rate_per_day, scale=False)}/day)")
        print(f"       forecast {format_inr(st.forecast_period_end):>16} at period end")
        if st.projected_overage > 0:
            print(f"       OVERAGE  {format_inr(st.projected_overage):>16} projected")
        if st.exhausted_on:
            print(f"       exhausted on {st.exhausted_on.isoformat()}")
        if st.is_accelerating:
            print("       ACCELERATING - recent burn well above period average")
        if st.contributors:
            top = ", ".join(f"{k} {format_inr(v)}" for k, v in st.contributors[:3])
            print(f"       drivers  {top}")

    # --- enforcement ----------------------------------------------------------
    head("ENFORCEMENT - DRY RUN")
    decisions = [d for st in states if (d := decide_enforcement(st, records)) is not None]
    if not decisions:
        print("    No budget in a state that would trigger enforcement.")
    for d in decisions:
        print(f"\n    {d.explain()}")
    print("\n  Dry-run is the default. 'This would have revoked these keys' is")
    print("  answerable; 'trust us' is not, and nobody grants write scope without it.")

    # --- honesty --------------------------------------------------------------
    head("ALLOCATION COVERAGE")
    cov = allocation_coverage(records)
    print(f"    total        {format_inr(cov.total):>16}")
    print(f"    allocated    {format_inr(cov.allocated):>16}  ({cov.coverage:.1%})")
    print(f"    UNALLOCATED  {format_inr(cov.unallocated):>16}"
          f"  ({1 - cov.coverage:.1%})")
    print(f"\n    Target is >85% allocated (F3.2): "
          f"{'MET' if cov.meets_target else 'NOT MET'}")
    print("    Surfaced, not buried. A buyer who finds unattributed spend on their")
    print("    own stops believing every other number we show them.\n")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "data_source": "SYNTHETIC - synth/fleet.py",
                    "total_inr": str(total),
                    "category_split": {k: str(v) for k, v in split.items()},
                    "allocation_coverage": str(cov.coverage),
                    "budgets": [
                        {
                            "id": st.budget.id,
                            "name": st.budget.name,
                            "scope": dict(st.budget.scope),
                            "status": str(st.status),
                            "spent_inr": str(st.spent),
                            "limit_inr": str(st.budget.amount),
                            "pct_used": str(st.pct_used),
                            "forecast_inr": str(st.forecast_period_end),
                            "projected_overage_inr": str(st.projected_overage),
                            "exhausted_on": st.exhausted_on.isoformat()
                            if st.exhausted_on
                            else None,
                            "accelerating": st.is_accelerating,
                        }
                        for st in states
                    ],
                    "enforcement_dry_run": [
                        {
                            "budget_id": d.budget_id,
                            "action": str(d.action),
                            "would_affect": list(d.would_affect),
                        }
                        for d in decisions
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  Structured result -> {args.json}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
