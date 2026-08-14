"""Detection rule tests.

These run with no credentials and no network — which is the point. The detection
logic is the moat, so it should be the most-tested thing in the repo long before any
connector exists.

The LLMjacking scenario is modelled on Sysdig's documented rates: a hijacked account
sustaining tens of thousands of dollars per day against a baseline of near-nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from prahari.detect.rules import (
    MIN_BASELINE_SAMPLES,
    Detector,
    Observation,
    Rule,
    Severity,
)

KEY = ("gcp_vertex", "sa-robotics-prod@example.iam")
START = datetime(2026, 6, 1, tzinfo=UTC)


def obs(hour_offset: int, spend: str, **kw) -> Observation:
    return Observation(
        detection_key=kw.pop("key", KEY),
        hour=START + timedelta(hours=hour_offset),
        spend=Decimal(spend),
        tokens=kw.pop("tokens", 10_000),
        requests=kw.pop("requests", 100),
        country=kw.pop("country", "IN"),
        model=kw.pop("model", "gemini-1.5-pro"),
        **kw,
    )


def warm_up(det: Detector, hours: int = MIN_BASELINE_SAMPLES + 8, spend: str = "20") -> int:
    """Establish a steady baseline. Returns the next free hour offset."""
    for h in range(hours):
        det.process(obs(h, spend))
    return hours


class TestSpendSpike:
    def test_fires_on_sustained_multiple(self):
        det = Detector()
        h = warm_up(det)
        alerts = det.process(obs(h, "500"))  # 25x baseline of 20

        spikes = [a for a in alerts if a.rule is Rule.SPEND_SPIKE]
        assert len(spikes) == 1
        assert spikes[0].severity is Severity.CRITICAL
        assert spikes[0].multiple == Decimal("25.00")

    def test_projects_24h_exposure(self):
        det = Detector()
        h = warm_up(det)
        alert = next(a for a in det.process(obs(h, "2000")) if a.rule is Rule.SPEND_SPIKE)

        # This is the number that drives containment urgency.
        assert alert.projected_24h == Decimal("48000.00")

    def test_absolute_floor_suppresses_trivial_spikes(self):
        """A key spending $0.10/hr going to $5 is a 50x spike and operationally noise."""
        det = Detector()
        for h in range(MIN_BASELINE_SAMPLES + 8):
            det.process(obs(h, "0.10"))

        alerts = det.process(obs(40, "5"))
        assert not [a for a in alerts if a.rule is Rule.SPEND_SPIKE]

    def test_silent_without_established_baseline(self):
        """Fewer than MIN_BASELINE_SAMPLES hours is not a defensible baseline."""
        det = Detector()
        det.process(obs(0, "20"))
        assert not [a for a in det.process(obs(1, "5000")) if a.rule is Rule.SPEND_SPIKE]

    def test_spike_does_not_poison_baseline_immediately(self):
        """Regression guard: rules must evaluate against the baseline BEFORE the
        observation is folded in, or hour two of an attack looks normal."""
        det = Detector()
        h = warm_up(det)
        det.process(obs(h, "5000"))
        second = det.process(obs(h + 1, "5000"))

        assert [a for a in second if a.rule is Rule.SPEND_SPIKE], (
            "second hour of an ongoing attack must still alert"
        )


class TestDormantKeyWake:
    def test_fires_after_dormancy(self):
        """The ₹6 crore shape: a credential harvested earlier, monetised later."""
        det = Detector()
        h = warm_up(det)
        alerts = det.process(obs(h + 24 * 45, "800"))  # 45 days idle

        woke = [a for a in alerts if a.rule is Rule.DORMANT_KEY_WAKE]
        assert len(woke) == 1
        assert woke[0].severity is Severity.CRITICAL
        assert woke[0].evidence["idle_days"] == 45

    def test_quiet_on_normal_gaps(self):
        det = Detector()
        h = warm_up(det)
        alerts = det.process(obs(h + 72, "20"))  # a long weekend
        assert not [a for a in alerts if a.rule is Rule.DORMANT_KEY_WAKE]


class TestNewGeo:
    def test_fires_on_unseen_country(self):
        det = Detector()
        h = warm_up(det)
        alerts = det.process(obs(h, "600", country="RU"))

        geo = [a for a in alerts if a.rule is Rule.NEW_GEO]
        assert len(geo) == 1
        assert geo[0].evidence["new_country"] == "RU"
        assert geo[0].severity is Severity.CRITICAL

    def test_abstains_when_origin_unknown(self):
        """Where the provider does not expose caller origin the rule stays silent
        rather than guessing. A detector that fabricates evidence is worse than one
        that abstains."""
        det = Detector()
        for h in range(MIN_BASELINE_SAMPLES + 8):
            det.process(obs(h, "20", country=None))

        alerts = det.process(obs(40, "600", country=None))
        assert not [a for a in alerts if a.rule is Rule.NEW_GEO]


class TestModelEscalation:
    def test_fires_on_switch_to_premium(self):
        det = Detector(premium_models={"claude-opus-4"})
        h = warm_up(det)
        alerts = det.process(obs(h, "300", model="claude-opus-4", key=KEY))

        assert [a for a in alerts if a.rule is Rule.MODEL_ESCALATION]

    def test_quiet_on_non_premium_switch(self):
        det = Detector(premium_models={"claude-opus-4"})
        h = warm_up(det)
        alerts = det.process(obs(h, "300", model="gemini-1.5-flash"))
        assert not [a for a in alerts if a.rule is Rule.MODEL_ESCALATION]


class TestDetectionKeyIsPerCredential:
    """Regression guard for a real bug: the key originally included model and region,
    which handed an attacker a fresh empty baseline the moment they switched models."""

    def test_model_switch_keeps_the_same_baseline(self):
        det = Detector(premium_models={"claude-opus-4"})
        h = warm_up(det)

        alerts = det.process(obs(h, "700", model="claude-opus-4"))

        # A new-model observation must still be judged against the credential's
        # existing baseline, not a fresh one.
        assert [a for a in alerts if a.rule is Rule.SPEND_SPIKE]
        assert [a for a in alerts if a.rule is Rule.MODEL_ESCALATION]

    def test_region_switch_keeps_the_same_baseline(self):
        det = Detector()
        h = warm_up(det)
        alerts = det.process(obs(h, "700", region="europe-west4"))
        assert [a for a in alerts if a.rule is Rule.SPEND_SPIKE]


class TestBaselineTracksActivityNotObservations:
    """Zero-spend hours keep the spend baseline honest but must not refresh
    `last_seen` — otherwise gap-filled quiet hours mask dormancy forever."""

    def test_zero_hours_do_not_reset_dormancy(self):
        det = Detector()
        h = warm_up(det)

        # 40 days of gap-filled silence.
        for gap in range(24 * 40):
            det.process(obs(h + gap, "0"))

        alerts = det.process(obs(h + 24 * 40, "900"))
        assert [a for a in alerts if a.rule is Rule.DORMANT_KEY_WAKE]

    def test_zero_hours_still_enter_the_spend_baseline(self):
        det = Detector()
        for h in range(24):
            det.process(obs(h, "100"))
        for h in range(24, 48):
            det.process(obs(h, "0"))

        bl = det.baseline_for(KEY)
        assert bl is not None
        assert bl.sample_count == 48
        # Mean must reflect the quiet hours, not just the busy ones.
        assert bl.expected_spend(START + timedelta(hours=48)) < Decimal("100")


class TestAlertExplainability:
    def test_explain_names_rule_baseline_and_exposure(self):
        """F5.3 — a CFO must be able to read why it fired, from the alert alone."""
        det = Detector()
        h = warm_up(det)
        alert = next(a for a in det.process(obs(h, "900")) if a.rule is Rule.SPEND_SPIKE)

        text = alert.explain()
        assert "SPEND_SPIKE" in text
        assert "baseline" in text
        assert "projected 24h exposure" in text
        assert alert.credential == KEY[1]

    def test_evidence_records_sample_count(self):
        det = Detector()
        h = warm_up(det)
        alert = next(a for a in det.process(obs(h, "900")) if a.rule is Rule.SPEND_SPIKE)
        assert alert.evidence["samples"] >= MIN_BASELINE_SAMPLES


class TestObservationValidation:
    def test_rejects_naive_datetime(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            Observation(
                detection_key=KEY,
                hour=datetime(2026, 6, 1),  # noqa: DTZ001 — deliberate
                spend=Decimal("1"),
                tokens=0,
                requests=0,
            )
