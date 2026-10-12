"""Detection must preserve unpriced activity and compare money in its actual currency."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from prahari.core.fx import FxRate, FxTable
from prahari.core.models import Provider, TokenCounts, UsageRecord
from prahari.detect.aggregate import observations_from_records
from prahari.detect.rules import Baseline, Detector, Observation, Rule, Severity

HOUR = datetime(2026, 6, 1, tzinfo=UTC)
KEY = ("openai", "key-1")


def record(cost, *, hour=HOUR, currency="USD", model="standard"):
    return UsageRecord(
        provider=Provider.OPENAI,
        account_id="org",
        api_key_id=KEY[1],
        model=model,
        tokens=TokenCounts(input_tokens=100, output_tokens=10, requests=1),
        billed_cost=None if cost is None else Decimal(cost),
        currency=currency,
        period_start=hour,
        period_end=hour + timedelta(hours=1),
        ingested_at=hour + timedelta(hours=1),
        source="test",
    )


def observation(hour=0, spend="20", *, currency="USD", **kwargs):
    return Observation(
        detection_key=KEY,
        hour=HOUR + timedelta(hours=hour),
        spend=Decimal(spend),
        tokens=100,
        requests=1,
        currency=currency,
        **kwargs,
    )


def configured_fx():
    return FxTable([FxRate("USD", "INR", Decimal("85"), HOUR.date(), "test")])


def warm_up(detector, *, currency="USD"):
    for hour in range(32):
        detector.process(observation(hour, currency=currency, country="IN"))


def test_rollup_retains_unpriced_activity_and_known_subtotal():
    obs = observations_from_records([record("10"), record(None, model="unpriced")])[0]
    assert obs.detection_key == KEY
    assert obs.spend == Decimal("10")
    assert obs.unpriced_records == 1
    assert not obs.cost_complete
    assert obs.tokens == 220
    assert obs.requests == 2


def test_all_unpriced_usage_emits_warning_without_fabricated_money():
    obs = observations_from_records([record(None)])[0]
    detector = Detector()
    alert, = detector.process(obs)
    assert alert.rule is Rule.COST_UNAVAILABLE
    assert alert.severity is Severity.WARNING
    assert alert.observed is None
    assert alert.baseline is None
    assert alert.spend_so_far is None
    assert alert.projected_24h is None
    assert alert.evidence["unpriced_records"] == 1
    assert alert.evidence["tokens"] == 110
    assert "price unavailable" in alert.explain()
    assert "projected 24h" not in alert.explain()
    assert "0 USD" not in alert.explain()
    assert detector.baseline_for(KEY).last_seen == HOUR


def test_incomplete_cost_abstains_from_spend_spike():
    detector = Detector()
    warm_up(detector)
    alerts = detector.process(observation(32, "5000", unpriced_records=1))
    assert [a.rule for a in alerts] == [Rule.COST_UNAVAILABLE]


def test_unknown_hours_are_not_zero_cost_baseline_samples():
    baseline = Baseline(KEY)
    baseline.observe(observation(0, "100"))
    baseline.observe(observation(1, "0", unpriced_records=1))
    assert baseline.sample_count == 1
    assert not baseline.cost_complete
    assert baseline.expected_spend(HOUR + timedelta(hours=2)) == Decimal("100")
    assert baseline.last_seen == HOUR + timedelta(hours=1)


def test_pricing_gaps_in_baseline_abstain_until_they_leave_the_rolling_window():
    detector = Detector()
    warm_up(detector)
    detector.process(observation(32, "0", unpriced_records=1))
    assert [a.rule for a in detector.process(observation(33, "5000"))] == [
        Rule.COST_UNAVAILABLE
    ]
    for hour in range(34, 202):
        detector.process(observation(hour))
    alert = next(a for a in detector.process(observation(202, "5000"))
                 if a.rule is Rule.SPEND_SPIKE)
    assert "known spend subtotal" in alert.explain()
    assert alert.evidence["cumulative_cost_complete"] is False


def test_rupee_spikes_use_the_usd_absolute_floor():
    detector = Detector(fx=configured_fx())
    warm_up(detector, currency="INR")
    assert not detector.process(observation(32, "100", currency="INR"))
    assert not detector.process(observation(33, "4249", currency="INR"))
    alerts = detector.process(observation(34, "4250", currency="INR"))
    assert any(a.rule is Rule.SPEND_SPIKE for a in alerts)


@pytest.mark.parametrize("spend,severity", [
    ("100", Severity.WARNING), ("4250", Severity.CRITICAL),
])
def test_rupee_new_geo_severity_uses_configured_fx(spend, severity):
    detector = Detector(fx=configured_fx())
    warm_up(detector, currency="INR")
    alert = next(a for a in detector.process(observation(32, spend, currency="INR", country="RU"))
                 if a.rule is Rule.NEW_GEO)
    assert alert.severity is severity


def test_missing_fx_emits_coverage_without_spend_critical_alerts():
    detector = Detector()
    warm_up(detector, currency="INR")
    alerts = detector.process(observation(32, "5000", currency="INR", country="RU"))
    assert [a.rule for a in alerts] == [Rule.COST_UNAVAILABLE]
    assert all(a.severity is Severity.WARNING for a in alerts)
    assert "no configured USD to INR FX rate" in alerts[0].explain()
    assert alerts[0].projected_24h is None


def test_future_fx_rate_does_not_price_past_thresholds():
    table = FxTable([FxRate("USD", "INR", Decimal("85"),
                          (HOUR + timedelta(days=1)).date(), "test")])
    alert, = Detector(fx=table).process(observation(currency="INR"))
    assert alert.rule is Rule.COST_UNAVAILABLE


def test_gap_filled_silence_does_not_emit_missing_fx_warnings():
    quiet = Observation(KEY, HOUR, Decimal(0), tokens=0, requests=0, currency="INR")
    assert Detector().process(quiet) == []


def test_fx_threshold_date_is_utc():
    local_midnight = HOUR.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
    obs = Observation(KEY, local_midnight, Decimal("5000"), 100, 1, currency="INR")
    assert obs.hour.date() == (HOUR - timedelta(days=1)).date()
    alert, = Detector(fx=configured_fx()).process(obs)
    assert alert.rule is Rule.COST_UNAVAILABLE


def test_same_hour_mixed_currency_rollup_is_rejected():
    with pytest.raises(ValueError, match="mixed currencies"):
        observations_from_records([record("10"), record("850", currency="INR")])


def test_currency_changes_do_not_enter_an_existing_baseline():
    detector = Detector(fx=configured_fx())
    detector.process(observation())
    with pytest.raises(ValueError, match="currency changed"):
        detector.process(observation(1, "1700", currency="INR"))
    assert detector.baseline_for(KEY).sample_count == 1
    assert detector.cumulative_spend(KEY) == Decimal("20")


def test_gap_fill_retains_rupee_currency_and_does_not_invent_activity():
    series = observations_from_records([
        record("10", currency="INR"),
        record("10", currency="INR", hour=HOUR + timedelta(hours=2)),
    ])
    gap = series[1]
    assert gap.currency == "INR"
    assert not gap.has_activity
    baseline = Baseline(KEY)
    baseline.observe(series[0])
    baseline.observe(gap)
    assert baseline.last_seen == HOUR


def test_seeded_activity_catches_dormancy_outside_replay_window():
    detector = Detector(last_activity={KEY: HOUR - timedelta(days=41)})
    alert, = detector.process(observation(spend="100"))
    assert alert.rule is Rule.DORMANT_KEY_WAKE
    assert alert.evidence["idle_days"] == 41


def test_free_requests_count_as_activity_for_dormancy():
    detector = Detector(last_activity={KEY: HOUR - timedelta(days=41)})
    alert, = detector.process(observation(spend="0"))
    assert alert.rule is Rule.DORMANT_KEY_WAKE
    assert detector.baseline_for(KEY).last_seen == HOUR


def test_seed_rejects_naive_activity_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        Detector(last_activity={KEY: datetime(2026, 1, 1)})
