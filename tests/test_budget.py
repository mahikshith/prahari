"""Budget, FX and insights tests.

Money and calendar arithmetic, which is where a finance tool loses trust silently.
The IST boundary tests exist because that bug already bit once: the fleet scenario
spanned a UTC month, 5.5 hours spilled into the next IST month, and every budget
evaluated against a nearly empty period while still reporting a confident number.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from prahari.core.budget import (
    Budget,
    BudgetPeriod,
    BudgetStatus,
    EnforcementAction,
    decide_enforcement,
    evaluate,
    evaluate_all,
    period_bounds,
    prepare_window,
)
from prahari.core.fx import FxError, FxRate, FxTable, format_inr, group_indian
from prahari.core.insights import (
    aggregate_by,
    ai_vs_cloud_split,
    allocation_coverage,
    movers,
    per_user_consumption,
    top_consumers,
)
from prahari.core.models import (
    AllocationMethod,
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)

JULY_IST_START = datetime(2026, 6, 30, 18, 30, tzinfo=UTC)  # 1 Jul 00:00 IST


def rec(
    *,
    hour: datetime,
    inr: str = "1000",
    project: str = "p1",
    service: str = "Cloud Run",
    user: str | None = None,
    cost_centre: str | None = "cc-1",
    currency: str = "INR",
    tokens: TokenCounts | None = None,
) -> UsageRecord:
    return UsageRecord(
        provider=Provider.GCP_VERTEX,
        account_id="acct",
        project_id=project,
        user_id=user,
        tokens=tokens or TokenCounts(),
        costs=CostComponents(other=Decimal(inr)),
        billed_cost=Decimal(inr),
        currency=currency,
        period_start=hour,
        period_end=hour + timedelta(hours=1),
        ingested_at=hour,
        cost_centre=cost_centre,
        allocation_method=(
            AllocationMethod.RESOURCE_TAG if cost_centre else AllocationMethod.UNALLOCATED
        ),
        source="test",
        extensions={
            "service": service,
            "service_category": {"Cloud Run": "compute", "BigQuery": "data", "Vertex AI": "ai"}.get(
                service, "other"
            ),
        },
    )


# --- FX -----------------------------------------------------------------------


class TestFx:
    def test_uses_the_rate_in_force_on_the_transaction_date(self):
        table = FxTable(
            [
                FxRate("USD", "INR", Decimal("83.00"), date(2026, 1, 1), "t"),
                FxRate("USD", "INR", Decimal("85.00"), date(2026, 6, 1), "t"),
            ]
        )
        assert table.convert(Decimal("100"), "USD", "INR", date(2026, 3, 15)) == Decimal("8300.00")
        assert table.convert(Decimal("100"), "USD", "INR", date(2026, 7, 1)) == Decimal("8500.00")

    def test_never_interpolates_forward(self):
        """A rate published after the transaction did not exist when it happened.
        Using it means our number changes retroactively."""
        table = FxTable([FxRate("USD", "INR", Decimal("85"), date(2026, 6, 1), "t")])
        with pytest.raises(FxError, match="on or before"):
            table.convert(Decimal("100"), "USD", "INR", date(2026, 1, 1))

    def test_missing_pair_raises_rather_than_guessing(self):
        table = FxTable([FxRate("USD", "INR", Decimal("85"), date(2026, 1, 1), "t")])
        with pytest.raises(FxError, match="no EUR->INR"):
            table.convert(Decimal("100"), "EUR", "INR", date(2026, 6, 1))

    def test_derives_the_inverse_pair(self):
        table = FxTable([FxRate("USD", "INR", Decimal("80"), date(2026, 1, 1), "t")])
        assert table.convert(Decimal("800"), "INR", "USD", date(2026, 6, 1)) == Decimal("10.00")

    def test_identity_conversion_is_exact(self):
        assert FxTable().convert(Decimal("123.456"), "INR", "INR", date(2026, 6, 1)) == Decimal(
            "123.456"
        )


class TestIndianFormatting:
    def test_digit_grouping(self):
        assert group_indian(Decimal("1234567")) == "12,34,567"
        assert group_indian(Decimal("100000")) == "1,00,000"
        assert group_indian(Decimal("999")) == "999"
        assert group_indian(Decimal("-1234567")) == "-12,34,567"

    def test_scales_to_lakh_and_crore(self):
        assert "crore" in format_inr(Decimal("60000000"))
        assert "lakh" in format_inr(Decimal("200000"))
        assert format_inr(Decimal("5000")) == "Rs 5,000"

    def test_unscaled_keeps_full_digits(self):
        assert format_inr(Decimal("200000"), scale=False) == "Rs 2,00,000"


# --- period boundaries --------------------------------------------------------


class TestPeriodBounds:
    """Regression guards. Indian finance closes on IST boundaries; computing them in
    UTC puts 5.5 hours of spend in the wrong month, invisible until someone
    reconciles against a GST filing."""

    def test_monthly_period_starts_at_ist_midnight(self):
        start, end = period_bounds(BudgetPeriod.MONTHLY, datetime(2026, 7, 15, tzinfo=UTC))
        assert start == JULY_IST_START
        assert end == datetime(2026, 7, 31, 18, 30, tzinfo=UTC)

    def test_late_utc_july_belongs_to_august_in_ist(self):
        """23:00 UTC on 31 July is 04:30 IST on 1 August. This exact case broke the
        fleet scenario."""
        start, _ = period_bounds(BudgetPeriod.MONTHLY, datetime(2026, 7, 31, 23, 0, tzinfo=UTC))
        assert start == datetime(2026, 7, 31, 18, 30, tzinfo=UTC)  # 1 Aug 00:00 IST

    def test_daily_and_weekly_align_to_ist(self):
        d_start, d_end = period_bounds(BudgetPeriod.DAILY, datetime(2026, 7, 15, 12, tzinfo=UTC))
        assert (d_end - d_start) == timedelta(days=1)

        w_start, w_end = period_bounds(BudgetPeriod.WEEKLY, datetime(2026, 7, 15, 12, tzinfo=UTC))
        assert (w_end - w_start) == timedelta(days=7)
        assert (w_start + timedelta(hours=5, minutes=30)).weekday() == 0  # Monday IST

    def test_quarterly_spans_three_months(self):
        start, end = period_bounds(BudgetPeriod.QUARTERLY, datetime(2026, 8, 15, tzinfo=UTC))
        assert (start + timedelta(hours=5, minutes=30)).month == 7
        assert (end + timedelta(hours=5, minutes=30)).month == 10


# --- budget scope -------------------------------------------------------------


class TestBudgetScope:
    def test_composite_scope_requires_all_dimensions(self):
        """The shape Mahikshith asked for: Rs 2 lakh on Cloud Run inside one project."""
        budget = Budget(
            id="b",
            name="Cloud Run in customer-api",
            amount=Decimal("200000"),
            scope={"project_id": "customer-api", "service": "Cloud Run"},
        )
        hour = JULY_IST_START

        assert budget.matches(rec(hour=hour, project="customer-api", service="Cloud Run"))
        assert not budget.matches(rec(hour=hour, project="customer-api", service="BigQuery"))
        assert not budget.matches(rec(hour=hour, project="other", service="Cloud Run"))

    def test_empty_scope_is_organisation_wide(self):
        budget = Budget(id="b", name="all", amount=Decimal("1"))
        assert budget.matches(rec(hour=JULY_IST_START))
        assert budget.describe_scope == "organisation-wide"

    def test_unknown_dimension_is_rejected_at_construction(self):
        with pytest.raises(ValueError, match="unknown budget scope dimension"):
            Budget(id="b", name="x", amount=Decimal("1"), scope={"nonsense": "v"})

    def test_negative_amount_is_rejected(self):
        with pytest.raises(ValueError, match="must be positive"):
            Budget(id="b", name="x", amount=Decimal("-1"))


# --- budget evaluation --------------------------------------------------------


def month_of_records(n_hours: int, inr: str = "1000", **kw) -> list[UsageRecord]:
    return [rec(hour=JULY_IST_START + timedelta(hours=h), inr=inr, **kw) for h in range(n_hours)]


class TestBudgetEvaluation:
    def test_sums_only_records_inside_the_period(self):
        inside = month_of_records(10)
        outside = [rec(hour=JULY_IST_START - timedelta(hours=5), inr="99999")]
        budget = Budget(id="b", name="x", amount=Decimal("100000"))

        state = evaluate(
            budget, inside + outside, as_of=JULY_IST_START + timedelta(hours=10)
        )
        assert state.spent == Decimal("10000.00")
        assert state.record_count == 10

    def test_burn_rate_and_forecast(self):
        state = evaluate(
            Budget(id="b", name="x", amount=Decimal("1000000")),
            month_of_records(48, inr="1000"),
            as_of=JULY_IST_START + timedelta(days=2),
        )
        assert state.spent == Decimal("48000.00")
        assert state.burn_rate_per_day == Decimal("24000.00")
        # 31-day July -> 24000 * 31
        assert state.forecast_period_end == Decimal("744000.00")

    def test_projected_overage_when_forecast_exceeds_limit(self):
        state = evaluate(
            Budget(id="b", name="x", amount=Decimal("200000")),
            month_of_records(48, inr="1000"),
            as_of=JULY_IST_START + timedelta(days=2),
        )
        assert state.projected_overage == Decimal("544000.00")
        assert state.exhausted_on is not None

    def test_status_ladder(self):
        budget = Budget(id="b", name="x", amount=Decimal("10000"))
        as_of = JULY_IST_START + timedelta(days=2)

        assert evaluate(budget, month_of_records(1), as_of=as_of).status is BudgetStatus.OK
        assert evaluate(budget, month_of_records(9), as_of=as_of).status is BudgetStatus.WARNING
        assert evaluate(budget, month_of_records(20), as_of=as_of).status is BudgetStatus.EXCEEDED

    def test_already_crossed_thresholds_do_not_refire(self):
        """Without this, a budget past 80% alerts on every evaluation cycle and gets
        filtered into a folder nobody reads."""
        budget = Budget(id="b", name="x", amount=Decimal("10000"))
        as_of = JULY_IST_START + timedelta(days=2)

        first = evaluate(budget, month_of_records(9), as_of=as_of)
        assert Decimal("0.5") in first.crossed_thresholds
        assert Decimal("0.8") in first.crossed_thresholds

        again = evaluate(
            budget, month_of_records(9), as_of=as_of, already_crossed=first.crossed_thresholds
        )
        assert again.crossed_thresholds == ()

    def test_acceleration_flag(self):
        """Recent burn well above the period average - the budget is about to go
        wrong even though it currently looks fine."""
        quiet = [rec(hour=JULY_IST_START + timedelta(hours=h), inr="10") for h in range(24 * 20)]
        surge = [
            rec(hour=JULY_IST_START + timedelta(days=20, hours=h), inr="5000")
            for h in range(24 * 3)
        ]
        state = evaluate(
            Budget(id="b", name="x", amount=Decimal("100000000")),
            quiet + surge,
            as_of=JULY_IST_START + timedelta(days=23),
        )
        assert state.is_accelerating

    def test_converts_usd_records_into_an_inr_budget(self):
        usd = [
            rec(hour=JULY_IST_START + timedelta(hours=h), inr="100", currency="USD")
            for h in range(3)
        ]
        state = evaluate(
            Budget(id="b", name="x", amount=Decimal("100000"), currency="INR"),
            usd,
            as_of=JULY_IST_START + timedelta(hours=3),
        )
        # 300 USD at the July placeholder mark (84.30), not 300.
        assert state.spent > Decimal("25000")

    def test_contributors_are_ranked(self):
        records = month_of_records(5, inr="100", project="small") + month_of_records(
            5, inr="900", project="big"
        )
        state = evaluate(
            Budget(id="b", name="x", amount=Decimal("100000")),
            records,
            as_of=JULY_IST_START + timedelta(hours=5),
        )
        assert state.contributors[0][0] == "big"

    def test_evaluate_all_orders_worst_first(self):
        records = month_of_records(10, inr="1000")
        states = evaluate_all(
            [
                Budget(id="ok", name="roomy", amount=Decimal("10000000")),
                Budget(id="bad", name="tight", amount=Decimal("5000")),
            ],
            records,
            as_of=JULY_IST_START + timedelta(hours=10),
        )
        assert states[0].budget.id == "bad"


# --- enforcement --------------------------------------------------------------


class TestPreparedWindowIndex:
    """The inverted index is a pure optimisation, so the thing worth testing is that
    it changes nothing. Cost went from 386 ms to 84 ms for 40 budgets; that is only
    worth having if the answers are identical."""

    def _mixed_records(self):
        return (
            month_of_records(6, inr="100", project="a", service="Cloud Run")
            + month_of_records(6, inr="200", project="a", service="BigQuery")
            + month_of_records(6, inr="300", project="b", service="Cloud Run")
        )

    @pytest.mark.parametrize(
        "scope",
        [
            {},
            {"project_id": "a"},
            {"service": "Cloud Run"},
            {"project_id": "a", "service": "Cloud Run"},
            {"project_id": "nonexistent"},
            {"project_id": "a", "service": "nonexistent"},
        ],
    )
    def test_indexed_result_matches_a_naive_scan(self, scope):
        records = self._mixed_records()
        as_of = JULY_IST_START + timedelta(hours=6)
        budget = Budget(id="b", name="x", amount=Decimal("1000000"), scope=scope)

        indexed = evaluate(budget, records, as_of=as_of)

        expected = sum(
            (r.billed_cost for r in records if budget.matches(r)),
            Decimal(0),
        )
        assert indexed.spent == expected.quantize(Decimal("0.01"))

    def test_evaluate_all_matches_individual_evaluation(self):
        records = self._mixed_records()
        as_of = JULY_IST_START + timedelta(hours=6)
        budgets = [
            Budget(id="1", name="all", amount=Decimal("1000000")),
            Budget(id="2", name="a", amount=Decimal("1000000"), scope={"project_id": "a"}),
            Budget(
                id="3",
                name="a-run",
                amount=Decimal("1000000"),
                scope={"project_id": "a", "service": "Cloud Run"},
            ),
        ]

        batched = {s.budget.id: s.spent for s in evaluate_all(budgets, records, as_of=as_of)}
        one_by_one = {b.id: evaluate(b, records, as_of=as_of).spent for b in budgets}
        assert batched == one_by_one

    def test_unindexed_dimension_is_refused_rather_than_ignored(self):
        """Silently ignoring an unindexed scope constraint would over-report spend -
        the budget would look larger than it is and might trigger enforcement."""
        window = prepare_window(
            self._mixed_records(),
            BudgetPeriod.MONTHLY,
            "INR",
            as_of=JULY_IST_START + timedelta(hours=6),
            dimensions={"project_id"},
        )
        budget = Budget(id="b", name="x", amount=Decimal("1"), scope={"service": "Cloud Run"})

        with pytest.raises(ValueError, match="lacks indexed dimensions"):
            evaluate(budget, window=window)

    def test_window_period_currency_mismatch_is_refused(self):
        window = prepare_window(
            self._mixed_records(),
            BudgetPeriod.MONTHLY,
            "INR",
            as_of=JULY_IST_START,
            dimensions={"project_id"},
        )
        budget = Budget(
            id="b", name="x", amount=Decimal("1"), period=BudgetPeriod.DAILY
        )
        with pytest.raises(ValueError, match="prepared window is"):
            evaluate(budget, window=window)

    def test_evaluate_needs_records_or_a_window(self):
        with pytest.raises(ValueError, match="records or a prepared window"):
            evaluate(Budget(id="b", name="x", amount=Decimal("1")))


class TestEnforcement:
    def _state(self, action: EnforcementAction, hours: int, limit: str):
        return evaluate(
            Budget(id="b", name="x", amount=Decimal(limit), enforcement=action),
            month_of_records(hours, inr="1000", project="customer-api"),
            as_of=JULY_IST_START + timedelta(hours=hours),
        )

    def test_alert_only_never_enforces(self):
        state = self._state(EnforcementAction.ALERT_ONLY, 20, "5000")
        assert state.status is BudgetStatus.EXCEEDED
        assert decide_enforcement(state, []) is None

    def test_no_action_below_the_limit(self):
        state = self._state(EnforcementAction.HARD_STOP, 2, "500000")
        assert decide_enforcement(state, []) is None

    def test_hard_stop_fires_when_exceeded(self):
        records = month_of_records(20, inr="1000", project="customer-api")
        state = self._state(EnforcementAction.HARD_STOP, 20, "5000")
        decision = decide_enforcement(state, records)

        assert decision is not None
        assert decision.action is EnforcementAction.HARD_STOP
        assert decision.dry_run is True
        assert "customer-api" in decision.would_affect

    def test_dry_run_wording_is_conditional(self):
        """'This would have revoked these keys' is answerable; 'trust us' is not."""
        records = month_of_records(20, inr="1000", project="customer-api")
        state = self._state(EnforcementAction.HARD_STOP, 20, "5000")
        assert decide_enforcement(state, records).explain().startswith("WOULD")
        assert decide_enforcement(state, records, dry_run=False).explain().startswith("WILL")


# --- insights -----------------------------------------------------------------


class TestInsights:
    def test_aggregates_and_shares_sum_to_one(self):
        records = month_of_records(5, inr="100", project="a") + month_of_records(
            5, inr="300", project="b"
        )
        rows = aggregate_by(records, "project_id")

        assert rows[0].key == "b"
        assert sum(r.share for r in rows) == pytest.approx(1.0)

    def test_missing_dimension_is_bucketed_not_dropped(self):
        """Dropping would make shares add to 100% of a number that is not the total -
        exactly the quiet wrongness that loses a reconciliation."""
        records = month_of_records(2, inr="100", cost_centre=None) + month_of_records(
            2, inr="100", cost_centre="cc-1"
        )
        rows = aggregate_by(records, "cost_centre")
        assert "(unattributed)" in {r.key for r in rows}
        assert sum(r.cost for r in rows) == Decimal("400.00")

    def test_per_user_falls_back_to_credential(self):
        rows = per_user_consumption(month_of_records(3, inr="100", user="a@x.com"))
        assert rows[0].key == "a@x.com"

    def test_cost_per_million_tokens(self):
        records = [
            rec(
                hour=JULY_IST_START,
                inr="1000",
                service="Vertex AI",
                tokens=TokenCounts(input_tokens=1_000_000, output_tokens=1_000_000),
            )
        ]
        row = top_consumers(records, "project_id")[0]
        assert row.cost_per_million_tokens == Decimal("500.00")

    def test_cost_per_million_is_none_without_tokens(self):
        row = top_consumers(month_of_records(1), "project_id")[0]
        assert row.cost_per_million_tokens is None

    def test_movers_rank_by_absolute_change(self):
        """A project going Rs 100 -> Rs 400 is +300% and irrelevant; Rs 40 lakh ->
        Rs 55 lakh is +37% and the only thing worth discussing."""
        current = month_of_records(1, inr="400", project="tiny") + month_of_records(
            1, inr="5500000", project="huge"
        )
        prior = month_of_records(1, inr="100", project="tiny") + month_of_records(
            1, inr="4000000", project="huge"
        )
        result = movers(current, prior, "project_id")
        assert result[0].key == "huge"

    def test_new_line_item_has_no_percentage(self):
        current = month_of_records(1, inr="500", project="brand-new")
        result = movers(current, [], "project_id")
        assert result[0].is_new
        assert result[0].pct_change is None

    def test_allocation_coverage_surfaces_unallocated(self):
        records = month_of_records(3, inr="100", cost_centre="cc-1") + month_of_records(
            1, inr="100", cost_centre=None
        )
        cov = allocation_coverage(records)

        assert cov.total == Decimal("400.00")
        assert cov.unallocated == Decimal("100.00")
        assert cov.coverage == Decimal("0.75")
        assert cov.meets_target is False  # 75% < 85% target (F3.2)

    def test_ai_vs_cloud_split(self):
        records = (
            month_of_records(1, inr="100", service="Vertex AI")
            + month_of_records(1, inr="200", service="BigQuery")
            + month_of_records(1, inr="300", service="Cloud Run")
        )
        split = ai_vs_cloud_split(records)
        assert split["ai"] == Decimal("100.00")
        assert split["data"] == Decimal("200.00")
        assert split["compute"] == Decimal("300.00")


# --- end-to-end over the synthetic fleet --------------------------------------


class TestFleetScenario:
    def setup_method(self):
        from prahari.synth.fleet import FleetScenario, generate

        self.scenario = FleetScenario()
        self.records = generate(self.scenario)
        self.as_of = self.scenario.start + timedelta(days=self.scenario.days) - timedelta(hours=1)

    def test_fleet_sits_inside_one_ist_month(self):
        """Regression guard for the bug that made every budget evaluate against a
        nearly empty period."""
        start, end = period_bounds(BudgetPeriod.MONTHLY, self.as_of)
        in_period = [r for r in self.records if start <= r.period_start < end]
        assert len(in_period) / len(self.records) > 0.99

    def test_cloud_run_budget_is_breached_as_designed(self):
        state = evaluate(
            Budget(
                id="b",
                name="Customer API - Cloud Run",
                amount=Decimal("200000"),
                scope={"project_id": "customer-api", "service": "Cloud Run"},
                enforcement=EnforcementAction.HARD_STOP,
            ),
            self.records,
            as_of=self.as_of,
        )
        assert state.status is BudgetStatus.EXCEEDED
        assert decide_enforcement(state, self.records) is not None

    def test_unallocated_slice_is_visible(self):
        cov = allocation_coverage(self.records)
        assert Decimal("0") < cov.unallocated
        assert cov.coverage < Decimal("1")
