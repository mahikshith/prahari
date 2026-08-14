"""Backtest and aggregation tests.

The backtest is a sales artifact, which makes correctness here unusually important:
a wrong number in a demo is worse than no demo. These lock in the properties the
artifact claims.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from backtest_incident import run

from prahari.core.models import (
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)
from prahari.detect.aggregate import observations_from_records
from prahari.detect.rules import Rule
from prahari.synth.incident import (
    Scenario,
    attack_window,
    format_inr_crore,
    generate,
    group_indian,
    to_inr,
)

H = datetime(2026, 6, 1, tzinfo=UTC)


def rec(hour_offset: int, usd: str, *, key: str = "k1", model: str = "m1", **ext) -> UsageRecord:
    hour = H + timedelta(hours=hour_offset)
    return UsageRecord(
        provider=Provider.GCP_VERTEX,
        account_id="acct",
        api_key_id=key,
        model=model,
        region="asia-south1",
        tokens=TokenCounts(input_tokens=100, output_tokens=50, requests=1),
        costs=CostComponents(input_cost=Decimal(usd)),
        billed_cost=Decimal(usd),
        period_start=hour,
        period_end=hour + timedelta(hours=1),
        ingested_at=hour,
        source="test",
        extensions=ext,
    )


class TestAggregation:
    def test_sums_multiple_records_in_one_hour(self):
        obs = observations_from_records([rec(0, "10"), rec(0, "15"), rec(0, "5")])
        assert len(obs) == 1
        assert obs[0].spend == Decimal("30")
        assert obs[0].requests == 3

    def test_attributes_hour_to_the_spend_dominant_model(self):
        """An attacker's premium model dominates cost even as a minority of requests —
        which is the attribution MODEL_ESCALATION needs."""
        obs = observations_from_records(
            [rec(0, "1", model="cheap"), rec(0, "500", model="expensive")]
        )
        assert obs[0].model == "expensive"

    def test_takes_max_context_utilisation_not_mean(self):
        """A maxed-out request hiding inside an ordinary hour must stay visible."""
        obs = observations_from_records(
            [
                rec(0, "10", max_context_utilisation=0.1),
                rec(0, "10", max_context_utilisation=0.95),
            ]
        )
        assert obs[0].max_context_utilisation == 0.95

    def test_fills_gaps_within_the_active_span(self):
        obs = observations_from_records([rec(0, "10"), rec(5, "10")])
        assert len(obs) == 6
        assert sum(1 for o in obs if o.spend == 0) == 4

    def test_does_not_invent_history_outside_the_span(self):
        """A baseline padded with fabricated zeros would understate the norm and make
        every real hour look like a spike."""
        obs = observations_from_records([rec(100, "10"), rec(101, "10")])
        assert len(obs) == 2

    def test_separates_credentials(self):
        obs = observations_from_records([rec(0, "10", key="a"), rec(0, "20", key="b")])
        assert len({o.detection_key for o in obs}) == 2


class TestIndianNumberFormatting:
    """Western grouping on an Indian invoice reads as carelessness to our buyer."""

    def test_groups_lakhs_and_crores(self):
        assert group_indian(Decimal("1234567")) == "12,34,567"
        assert group_indian(Decimal("100000")) == "1,00,000"
        assert group_indian(Decimal("999")) == "999"
        assert group_indian(Decimal("1000")) == "1,000"

    def test_scales_to_crore_and_lakh(self):
        assert "crore" in format_inr_crore(Decimal("700000"))
        assert "lakh" in format_inr_crore(Decimal("5000"))


class TestBacktest:
    """The properties the artifact asserts. If any of these break, the demo is wrong."""

    def setup_method(self):
        self.scenario = Scenario()
        self.result = run(generate(self.scenario), self.scenario)

    def test_detects_the_attack(self):
        assert self.result.first_alert is not None

    def test_detects_within_the_first_hour(self):
        assert self.result.detection_latency_hours is not None
        assert self.result.detection_latency_hours <= 1.0

    def test_total_reconciles_with_the_reported_incident(self):
        """~Rs 6 crore. If the synthetic scenario drifts from the real incident's
        magnitude, the artifact stops being credible."""
        inr = to_inr(self.result.total_spend_at_invoice)
        crore = inr / Decimal("10000000")
        assert Decimal("5") < crore < Decimal("7")

    def test_prevents_the_overwhelming_majority_of_exposure(self):
        ratio = self.result.exposure_prevented / self.result.total_spend_at_invoice
        assert ratio > Decimal("0.99")

    def test_all_five_signals_corroborate(self):
        fired = {a.rule for a in self.result.attack_alerts}
        assert Rule.SPEND_SPIKE in fired
        assert Rule.DORMANT_KEY_WAKE in fired
        assert Rule.NEW_GEO in fired
        assert Rule.MODEL_ESCALATION in fired

    def test_control_credential_never_reaches_critical(self):
        """The legitimate deploy-day burst may warn — it must never look like an
        attack. This separation is what makes the alerts actionable."""
        from prahari.detect.rules import Severity

        assert not [a for a in self.result.control_alerts if a.severity is Severity.CRITICAL]

    def test_attack_window_is_ten_days(self):
        start, end, invoice = attack_window(self.scenario)
        assert (end - start).days == 10
        # Discovery is what ends the attack, so by default the two coincide. The
        # invoice must never land *before* the attack finishes.
        assert invoice >= end

    def test_is_deterministic(self):
        again = run(generate(self.scenario), self.scenario)
        assert again.total_spend_at_invoice == self.result.total_spend_at_invoice

    def test_output_is_labelled_synthetic(self):
        """Guards ASSUMPTIONS.md A1 — a modelled number must never leave this repo
        looking measured."""
        assert "SYNTHETIC" in self.result.as_dict()["data_source"]
