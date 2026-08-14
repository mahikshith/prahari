"""Backtest: how early would Prahari have caught the incident?

Produces the one number that opens every discovery call and every investor meeting:

    "Would have fired at <X> spent - <N> hours before the invoice revealed <Y>."

Currently runs on SYNTHETIC data calibrated to published LLMjacking rates, because
the real GCP billing export is not accessible yet (ASSUMPTIONS.md A1). Every output
is labelled accordingly. When real data lands, only the loader changes - the
detection path is identical, which is the point.

Usage:
    uv run python scripts/backtest_incident.py
    uv run python scripts/backtest_incident.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prahari.core.models import UsageRecord
from prahari.detect.aggregate import observations_from_records
from prahari.detect.rules import Alert, Detector, Severity
from prahari.synth.incident import (
    Scenario,
    attack_window,
    format_inr_crore,
    generate,
    to_inr,
)

RULE = "=" * 78


@dataclass
class Result:
    attack_credential: str
    control_credential: str
    attack_start: datetime
    invoice_discovery: datetime
    first_alert: Alert | None
    detection_latency_hours: float | None
    spend_at_detection: Decimal
    total_spend_at_invoice: Decimal
    exposure_prevented: Decimal
    attack_alerts: list[Alert]
    control_alerts: list[Alert]

    def as_dict(self) -> dict:
        return {
            "data_source": "SYNTHETIC - calibrated to published LLMjacking rates",
            "attack_credential": self.attack_credential,
            "attack_start_utc": self.attack_start.isoformat(),
            "invoice_discovery_utc": self.invoice_discovery.isoformat(),
            "first_alert_utc": self.first_alert.at.isoformat() if self.first_alert else None,
            "first_alert_rule": str(self.first_alert.rule) if self.first_alert else None,
            "detection_latency_hours": self.detection_latency_hours,
            "spend_at_detection_usd": str(self.spend_at_detection),
            "spend_at_detection_inr": str(to_inr(self.spend_at_detection)),
            "total_spend_at_invoice_usd": str(self.total_spend_at_invoice),
            "total_spend_at_invoice_inr": str(to_inr(self.total_spend_at_invoice)),
            "exposure_prevented_usd": str(self.exposure_prevented),
            "exposure_prevented_inr": str(to_inr(self.exposure_prevented)),
            "attack_alert_count": len(self.attack_alerts),
            "control_alert_count": len(self.control_alerts),
            "rules_fired": sorted({str(a.rule) for a in self.attack_alerts}),
        }


def run(records: list[UsageRecord], scenario: Scenario) -> Result:
    attack_start, _attack_end, invoice_discovery = attack_window(scenario)

    observations = observations_from_records(records)
    detector = Detector(premium_models={scenario.attack_model})

    attack_key = ("gcp_vertex", scenario.stale_account)
    control_key = ("gcp_vertex", scenario.legit_account)

    attack_alerts: list[Alert] = []
    control_alerts: list[Alert] = []
    spend_at_detection = Decimal(0)
    first_alert: Alert | None = None

    for obs in observations:
        for alert in detector.process(obs):
            if alert.detection_key == attack_key and alert.at >= attack_start:
                attack_alerts.append(alert)
                if first_alert is None:
                    first_alert = alert
                    spend_at_detection = alert.spend_so_far
            elif alert.detection_key == control_key:
                control_alerts.append(alert)

    total_at_invoice = detector.cumulative_spend(attack_key)

    latency = None
    if first_alert is not None:
        latency = (first_alert.at - attack_start).total_seconds() / 3600

    return Result(
        attack_credential=scenario.stale_account,
        control_credential=scenario.legit_account,
        attack_start=attack_start,
        invoice_discovery=invoice_discovery,
        first_alert=first_alert,
        detection_latency_hours=latency,
        spend_at_detection=spend_at_detection,
        total_spend_at_invoice=total_at_invoice,
        exposure_prevented=total_at_invoice - spend_at_detection,
        attack_alerts=attack_alerts,
        control_alerts=control_alerts,
    )


def report(r: Result) -> None:
    print(RULE)
    print("  PRAHARI - INCIDENT BACKTEST")
    print("  *** SYNTHETIC DATA - modelled, not measured. See ASSUMPTIONS.md A1. ***")
    print(RULE)
    print()

    if r.first_alert is None:
        print("  NO DETECTION. The rules did not fire on the attack window.")
        print("  This is a genuine finding - investigate thresholds before proceeding.")
        return

    hours = r.detection_latency_hours or 0
    lead_hours = (r.invoice_discovery - r.first_alert.at).total_seconds() / 3600

    print(f"  Attack began         {r.attack_start:%Y-%m-%d %H:%M} UTC")
    print(f"  Prahari alerted      {r.first_alert.at:%Y-%m-%d %H:%M} UTC   "
          f"({hours:.0f}h after onset, rule: {r.first_alert.rule})")
    print(f"  Invoice revealed it  {r.invoice_discovery:%Y-%m-%d %H:%M} UTC")
    print()
    print(f"  Spend at detection   {format_inr_crore(r.spend_at_detection):>18}"
          f"   (${r.spend_at_detection:,.0f})")
    print(f"  Spend at invoice     {format_inr_crore(r.total_spend_at_invoice):>18}"
          f"   (${r.total_spend_at_invoice:,.0f})")
    print(f"  Exposure prevented   {format_inr_crore(r.exposure_prevented):>18}"
          f"   (${r.exposure_prevented:,.0f})")
    print()
    print(RULE)
    print(f"  Detected at {format_inr_crore(r.spend_at_detection)} spent - "
          f"{lead_hours / 24:.0f} days and {format_inr_crore(r.exposure_prevented)}")
    print("  before the invoice revealed it.")
    print(RULE)
    print()

    by_rule: dict[str, int] = {}
    for a in r.attack_alerts:
        by_rule[str(a.rule)] = by_rule.get(str(a.rule), 0) + 1

    print("  Rules fired on the compromised credential:")
    for rule, count in sorted(by_rule.items(), key=lambda kv: -kv[1]):
        print(f"    {rule:<20} {count:>4} alerts")
    print()

    print("  Corroborating signals in the first alert window:")
    for a in r.attack_alerts[:6]:
        if a.rule != r.first_alert.rule or a.at == r.first_alert.at:
            print(f"    [{a.at:%m-%d %H:%M}] {a.explain()[:110]}")
    print()

    crit = sum(1 for a in r.control_alerts if a.severity is Severity.CRITICAL)
    print(f"  Control credential ({r.control_credential.split('@')[0]}):")
    print(f"    {len(r.control_alerts)} alerts, {crit} critical")
    if r.control_alerts:
        print("    Reported deliberately - a detector that never admits a false")
        print("    positive is one nobody has calibrated.")
        for a in r.control_alerts[:3]:
            print(f"      [{a.at:%m-%d %H:%M}] {a.rule} ({a.severity})")
    else:
        print("    Clean - no alerts on legitimate traffic, including the deploy-day burst.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, help="Write structured result to this path")
    # Scenario uses slots=True, so defaults are not readable off the class.
    ap.add_argument("--seed", type=int, default=Scenario().seed)
    args = ap.parse_args()

    scenario = Scenario(seed=args.seed)
    records = generate(scenario)
    print(f"\nGenerated {len(records):,} synthetic hourly records "
          f"across 2 credentials, {scenario.invoice_discovery_day} days.\n")

    result = run(records, scenario)
    report(result)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
        print(f"  Structured result -> {args.json}\n")

    return 0 if result.first_alert is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
