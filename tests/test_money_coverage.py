"""Unknown prices stay unknown; precision and credential attribution stay honest."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from prahari.core.budget import (
    Budget,
    BudgetStatus,
    EnforcementAction,
    decide_enforcement,
    evaluate,
)
from prahari.core.config import Config
from prahari.core.fx import FxError, FxRate, FxTable
from prahari.core.insights import (
    aggregate_by,
    ai_vs_cloud_split,
    allocation_coverage,
    per_user_consumption,
)
from prahari.core.models import Completeness, CostBasis, Provider, UsageRecord
from prahari.notify.router import Router

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def record(cost, **overrides):
    fields = {
        "provider": Provider.OPENAI,
        "account_id": "org-1",
        "api_key_id": "key-1",
        "project_id": "project-1",
        "model": "customer-model",
        "billed_cost": cost,
        "currency": "INR",
        "period_start": NOW - timedelta(hours=1),
        "period_end": NOW,
        "ingested_at": NOW,
        "source": "test",
    }
    fields.update(overrides)
    return UsageRecord.model_validate(fields)


def test_unpriced_usage_is_distinct_from_provider_reported_zero():
    missing, zero = record(None), record(Decimal(0))
    assert missing.billed_cost is None
    assert missing.cost_basis is CostBasis.UNPRICED
    assert zero.billed_cost == 0
    assert zero.cost_basis is CostBasis.PROVIDER_REPORTED
    assert UsageRecord.model_validate_json(missing.model_dump_json()).billed_cost is None


def test_estimate_basis_is_independent_of_usage_window_completeness():
    estimated = record(
        Decimal("12.50"), cost_basis=CostBasis.ESTIMATED, completeness=Completeness.FINAL
    )
    assert estimated.is_estimated is True
    assert estimated.completeness is Completeness.FINAL
    assert record(Decimal("12.50"), completeness=Completeness.ESTIMATED).is_estimated is True


def test_unpriced_basis_cannot_claim_a_numeric_cost():
    with pytest.raises(ValueError, match="unpriced usage"):
        record(Decimal(0), cost_basis=CostBasis.UNPRICED)


def test_incomplete_budget_keeps_known_subtotal_and_prevents_enforcement():
    budget = Budget(
        id="project-cap",
        name="Project cap",
        amount=Decimal("100"),
        currency="INR",
        scope={"project_id": "project-1"},
        enforcement=EnforcementAction.HARD_STOP,
    )
    records = [record(Decimal("500")), record(None)]
    state = evaluate(budget, records, as_of=NOW, fx=FxTable([]))

    assert state.status is BudgetStatus.EXCEEDED
    assert state.spent == Decimal("500.00")
    assert state.record_count == 2
    assert state.unpriced_records == 1
    assert "INCOMPLETE" in state.explain()
    assert decide_enforcement(state, records, dry_run=False) is None


def test_unpriced_usage_outside_budget_scope_does_not_block_known_budget():
    budget = Budget(
        id="project-cap",
        name="Project cap",
        amount=Decimal("100"),
        currency="INR",
        scope={"project_id": "project-1"},
        enforcement=EnforcementAction.HARD_STOP,
    )
    records = [record(Decimal("500")), record(None, project_id="other-project")]
    state = evaluate(budget, records, as_of=NOW, fx=FxTable([]))
    assert state.unpriced_records == 0
    assert decide_enforcement(state, records) is not None


@pytest.mark.parametrize(
    ("report", "arguments"),
    [
        (aggregate_by, ("project_id",)),
        (per_user_consumption, ()),
        (allocation_coverage, ()),
        (ai_vs_cloud_split, ()),
    ],
)
def test_financial_reports_reject_incomplete_cost_coverage(report, arguments):
    records = [record(Decimal("500")), record(None)]
    with pytest.raises(ValueError, match="monetary report is incomplete"):
        report(records, *arguments, currency="INR", fx=FxTable([]))


def test_small_charges_keep_precision_until_total_is_presented():
    table = FxTable([FxRate("USD", "INR", Decimal("85.50"), date(2026, 10, 1), "invoice")])
    assert table.convert(Decimal("0.0001"), "USD", "INR", NOW.date()) == Decimal("0.008550")
    records = [record(Decimal("0.0001"), currency="USD") for _ in range(100)]
    [row] = aggregate_by(records, "project_id", currency="INR", fx=table)
    assert row.cost == Decimal("0.86")
    budget = Budget(id="cap", name="Cap", amount=Decimal("100"), currency="INR")
    assert evaluate(budget, records, as_of=NOW, fx=table).spent == Decimal("0.86")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "0", "-1"])
def test_fx_rates_reject_non_finite_or_non_positive_values(bad):
    with pytest.raises(ValueError, match="finite and positive"):
        FxRate("USD", "INR", Decimal(bad), NOW.date(), "invoice")


@pytest.mark.parametrize(("base", "quote"), [("US", "INR"), ("USD", "I1R"), ("ÜSD", "INR")])
def test_fx_rates_reject_invalid_currency_codes(base, quote):
    with pytest.raises(ValueError, match="three-letter codes"):
        FxRate(base, quote, Decimal("85.50"), NOW.date(), "invoice")


def test_fx_rates_normalize_codes_for_lookups():
    rate = FxRate("usd", "inr", Decimal("85.50"), NOW.date(), "invoice")
    assert (rate.base, rate.quote) == ("USD", "INR")
    assert FxTable([rate]).convert(Decimal("2"), "USD", "INR", NOW.date()) == Decimal("171.00")


def test_config_rejects_invalid_fx_rate_at_input_boundary():
    with pytest.raises(ValueError, match="finite"):
        Config.model_validate(
            {
                "fx_rates": [
                    {
                        "base": "USD",
                        "quote": "INR",
                        "rate": "NaN",
                        "as_of": "2026-10-01",
                        "source": "invoice",
                    }
                ]
            }
        )


def test_all_record_timestamps_normalize_to_utc_before_dates_are_used():
    local = datetime(2026, 10, 12, 0, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    usage = record(
        Decimal("1"),
        period_start=local,
        period_end=local + timedelta(hours=1),
        ingested_at=local + timedelta(hours=2),
    )
    assert usage.period_start == datetime(2026, 10, 11, 18, 45, tzinfo=UTC)
    assert usage.period_start.date() == date(2026, 10, 11)
    assert all(
        value.tzinfo is UTC for value in (usage.period_start, usage.period_end, usage.ingested_at)
    )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_shared_admin_credentials_reject_multiple_enabled_organizations(provider):
    with pytest.raises(ValueError, match=f"only one enabled {provider} collector"):
        Config.model_validate(
            {
                "collectors": [
                    {"provider": provider, "account_id": "organization-a"},
                    {"provider": provider, "account_id": "organization-b"},
                ]
            }
        )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_disabled_organization_does_not_consume_shared_credential_slot(provider):
    config = Config.model_validate(
        {
            "collectors": [
                {"provider": provider, "account_id": "organization-a"},
                {"provider": provider, "account_id": "organization-b", "enabled": False},
            ]
        }
    )
    assert len(config.enabled_collectors) == 1


def test_one_organization_per_admin_provider_can_run_together():
    config = Config.model_validate(
        {
            "collectors": [
                {"provider": "openai", "account_id": "organization-a"},
                {"provider": "anthropic", "account_id": "organization-b"},
            ]
        }
    )
    assert len(config.enabled_collectors) == 2


def test_currency_labels_match_native_budget_without_fx():
    budget = Budget(
        id="usd-cap",
        name="USD cap",
        amount=Decimal("100"),
        currency="usd",
        enforcement=EnforcementAction.HARD_STOP,
    )
    records = [record(Decimal("125"), currency="USD")]
    state = evaluate(budget, records, as_of=NOW, fx=FxTable())
    assert budget.currency == "USD"
    assert "USD 125.00 of USD 100.00" in state.explain()
    message = Router([]).budget_message(state, [Decimal(1)])
    assert "remaining:  USD -25.00" in message.body
    decision = decide_enforcement(state, records)
    assert decision is not None
    assert "USD 125.00 of USD 100.00" in decision.explain()
    assert "Rs " not in message.body + decision.explain()


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "0", "-1"])
def test_budget_amount_rejects_non_finite_or_non_positive_values(bad):
    with pytest.raises(ValueError, match="finite and positive"):
        Budget(id="cap", name="Cap", amount=Decimal(bad))


def test_default_fx_table_has_no_invented_exchange_rate():
    with pytest.raises(FxError, match="no USD->INR rate"):
        FxTable().convert(Decimal(1), "USD", "INR", NOW.date())
