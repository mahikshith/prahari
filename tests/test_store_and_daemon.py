"""Store, config, notification and daemon tests.

These cover the plumbing that turns the analysis code into something a design partner
can leave running. The properties that matter are all about *not* doing something
twice: not double-counting a re-fetched window, not paging twice for one event, not
rewinding a watermark.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from prahari.core.budget import BudgetPeriod, EnforcementAction
from prahari.core.config import Config, load, parse_duration
from prahari.core.models import Completeness, CostComponents, Provider, TokenCounts, UsageRecord
from prahari.detect.rules import Alert, Rule, Severity
from prahari.notify.router import ConsoleChannel, Message, Router
from prahari.store.duck import Store, alert_id, record_id

H = datetime(2026, 7, 1, tzinfo=UTC)


def rec(
    hour: int = 0,
    inr: str = "100",
    *,
    key: str = "k1",
    partial: bool = False,
    base: datetime = H,
) -> UsageRecord:
    at = base + timedelta(hours=hour)
    return UsageRecord(
        provider=Provider.GCP_VERTEX,
        account_id="acct",
        api_key_id=key,
        project_id="proj-a",
        model="gemini-2.5-flash",
        region="asia-south1",
        tokens=TokenCounts(input_tokens=1000, output_tokens=200, requests=5),
        costs=CostComponents(other=Decimal(inr)),
        billed_cost=Decimal(inr),
        currency="INR",
        period_start=at,
        period_end=at + timedelta(hours=1),
        ingested_at=at,
        cost_centre="cc-1",
        source="test",
        completeness=Completeness.PARTIAL if partial else Completeness.FINAL,
        extensions={"service": "Vertex AI", "service_category": "ai"},
    )


@pytest.fixture
def store():
    with Store() as s:
        yield s


# --- store --------------------------------------------------------------------


class TestRecordIdentity:
    def test_is_stable_across_calls(self):
        assert record_id(rec()) == record_id(rec())

    def test_differs_by_hour(self):
        assert record_id(rec(0)) != record_id(rec(1))

    def test_differs_by_credential(self):
        assert record_id(rec(key="a")) != record_id(rec(key="b"))

    def test_is_independent_of_cost(self):
        """Identity is the natural key, not the value - that is what lets a corrected
        figure replace the original instead of appending beside it."""
        assert record_id(rec(inr="100")) == record_id(rec(inr="999"))


class TestUpsertIsIdempotent:
    def test_reinserting_does_not_double_count(self, store):
        records = [rec(h) for h in range(24)]
        store.upsert_records(records)
        store.upsert_records(records)
        store.upsert_records(records)

        assert store.count() == 24
        assert store.total_cost(H, H + timedelta(days=1)) == Decimal("2400")

    def test_partial_window_is_replaced_by_final(self, store):
        """An hour fetched while still filling must be overwritten, not added to."""
        store.upsert_records([rec(0, "50", partial=True)])
        store.upsert_records([rec(0, "120", partial=False)])

        assert store.count() == 1
        [stored] = store.records()
        assert stored.billed_cost == Decimal("120")
        assert stored.completeness is Completeness.FINAL

    def test_empty_batch_is_a_no_op(self, store):
        assert store.upsert_records([]) == 0


class TestRoundTrip:
    def test_preserves_decimal_currency_and_tz(self, store):
        store.upsert_records([rec(0, "1234.5678")])
        [back] = store.records()

        assert back.billed_cost == Decimal("1234.5678")
        assert back.currency == "INR"
        assert back.period_start == H
        assert back.period_start.tzinfo is not None

    def test_preserves_tokens_extensions_and_allocation(self, store):
        store.upsert_records([rec()])
        [back] = store.records()

        assert back.tokens.input_tokens == 1000
        assert back.extensions["service"] == "Vertex AI"
        assert back.cost_centre == "cc-1"

    def test_settled_only_excludes_filling_windows(self, store):
        store.upsert_records([rec(0, key="a"), rec(1, key="b", partial=True)])
        assert len(store.records()) == 2
        assert len(store.records(settled_only=True)) == 1

    def test_filters_by_window_and_provider(self, store):
        store.upsert_records([rec(h) for h in range(48)])
        assert len(store.records(start=H, end=H + timedelta(hours=10))) == 10
        assert len(store.records(providers=[Provider.OPENAI])) == 0


class TestWatermarks:
    def test_absent_until_set(self, store):
        assert store.watermark("anthropic:org1") is None

    def test_advances(self, store):
        store.set_watermark("c", H)
        store.set_watermark("c", H + timedelta(hours=5))
        assert store.watermark("c") == H + timedelta(hours=5)

    def test_never_rewinds(self, store):
        """A backfill of older data must not rewind live collection, or the next
        cycle re-fetches everything since and achieves nothing."""
        store.set_watermark("c", H + timedelta(days=5))
        store.set_watermark("c", H)
        assert store.watermark("c") == H + timedelta(days=5)


def make_alert(hour: int = 3, rule: Rule = Rule.SPEND_SPIKE, key: str = "sa-1") -> Alert:
    return Alert(
        rule=rule,
        severity=Severity.CRITICAL,
        detection_key=("gcp_vertex", key),
        at=H + timedelta(hours=hour),
        observed=Decimal(900),
        baseline=Decimal(20),
        multiple=Decimal(45),
        spend_so_far=Decimal(900),
        projected_24h=Decimal(21600),
        currency="USD",
        evidence={"samples": 40},
    )


class TestAlertDeduplication:
    def test_same_event_records_once(self, store):
        alert = make_alert()
        assert store.record_alert(alert) is True
        assert store.record_alert(alert) is False

    def test_identity_is_rule_credential_and_hour(self):
        assert alert_id(make_alert(3)) != alert_id(make_alert(4))
        assert alert_id(make_alert(rule=Rule.NEW_GEO)) != alert_id(
            make_alert(rule=Rule.SPEND_SPIKE)
        )
        assert alert_id(make_alert(key="a")) != alert_id(make_alert(key="b"))

    def test_pending_queue_drains_on_notify(self, store):
        alert = make_alert()
        store.record_alert(alert)
        assert len(store.pending_alerts()) == 1

        store.mark_notified(alert)
        assert store.pending_alerts() == []

    def test_pending_alert_rehydrates(self, store):
        from prahari.store.duck import alert_from_row

        store.record_alert(make_alert())
        [row] = store.pending_alerts()
        restored = alert_from_row(row)

        assert restored.rule is Rule.SPEND_SPIKE
        assert restored.detection_key == ("gcp_vertex", "sa-1")
        assert restored.projected_24h == Decimal(21600)


class TestAlertCurrency:
    def test_inr_records_produce_inr_alerts(self):
        """Regression: every rule hardcoded currency="USD", so an Indian estate saw
        its rupee figures labelled as dollars - an 84x misstatement of the one number
        the alert exists to convey."""
        from prahari.detect.aggregate import observations_from_records
        from prahari.detect.rules import Detector

        records = [rec(h, "20") for h in range(40)] + [rec(40, "5000")]
        detector = Detector()
        alerts = [
            a
            for obs in observations_from_records(records)
            for a in detector.process(obs)
        ]

        assert alerts
        assert all(a.currency == "INR" for a in alerts)
        assert "INR" in alerts[-1].explain()


class TestBudgetThresholdState:
    def test_crossing_is_recorded_once(self, store):
        assert store.mark_threshold_crossed("b", H, Decimal("0.8")) is True
        assert store.mark_threshold_crossed("b", H, Decimal("0.8")) is False

    def test_thresholds_are_scoped_per_period(self, store):
        store.mark_threshold_crossed("b", H, Decimal("0.8"))
        next_month = H + timedelta(days=31)
        assert store.mark_threshold_crossed("b", next_month, Decimal("0.8")) is True
        assert store.crossed_thresholds("b", H) == [Decimal("0.8")]


# --- config -------------------------------------------------------------------


class TestDurationParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [("30s", timedelta(seconds=30)), ("5m", timedelta(minutes=5)),
         ("2h", timedelta(hours=2)), ("7d", timedelta(days=7)), (90, timedelta(seconds=90))],
    )
    def test_valid(self, text, expected):
        assert parse_duration(text) == expected

    @pytest.mark.parametrize("bad", ["", "5", "5 weeks", "abc", "-5m"])
    def test_invalid_is_rejected(self, bad):
        with pytest.raises(ValueError, match="invalid duration"):
            parse_duration(bad)


class TestConfigValidation:
    def test_example_config_is_valid(self):
        """The file we hand a design partner must actually parse."""
        cfg = load("prahari.example.yaml")
        assert len(cfg.collectors) == 3
        assert len(cfg.budgets) == 3

    def test_unknown_scope_dimension_is_caught_at_load(self):
        """A typo must fail validation in the first minute, not silently match zero
        records for a month and under-report a budget that was actually breached."""
        with pytest.raises(ValueError, match="unknown scope dimension"):
            Config.model_validate(
                {"budgets": [{"id": "b", "name": "x", "amount": 1, "scope": {"projct_id": "a"}}]}
            )

    def test_typo_in_a_top_level_key_is_rejected(self):
        with pytest.raises(ValueError):
            Config.model_validate({"collectrs": []})

    def test_percent_style_threshold_is_rejected(self):
        with pytest.raises(ValueError, match="fraction"):
            Config.model_validate(
                {"budgets": [{"id": "b", "name": "x", "amount": 1, "thresholds": [80]}]}
            )

    def test_duplicate_budget_ids_are_rejected(self):
        with pytest.raises(ValueError, match="duplicate budget id"):
            Config.model_validate(
                {
                    "budgets": [
                        {"id": "same", "name": "a", "amount": 1},
                        {"id": "same", "name": "b", "amount": 2},
                    ]
                }
            )

    def test_anthropic_poll_floor_is_enforced(self):
        """Anthropic documents a 1/minute limit; faster earns a 429 and buys nothing."""
        with pytest.raises(ValueError, match="at least 1m"):
            Config.model_validate(
                {
                    "collectors": [
                        {"provider": "anthropic", "account_id": "o", "poll_interval": "10s"}
                    ]
                }
            )

    def test_missing_env_is_reported_not_guessed(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)
        cfg = Config.model_validate(
            {"collectors": [{"provider": "anthropic", "account_id": "o"}]}
        )
        assert "ANTHROPIC_ADMIN_KEY" in cfg.missing_env()

    def test_disabled_collectors_do_not_demand_credentials(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)
        cfg = Config.model_validate(
            {"collectors": [{"provider": "anthropic", "account_id": "o", "enabled": False}]}
        )
        assert cfg.missing_env() == []

    def test_budget_config_converts_to_a_budget(self):
        cfg = Config.model_validate(
            {
                "budgets": [
                    {
                        "id": "b",
                        "name": "Cloud Run cap",
                        "amount": "200000",
                        "scope": {"project_id": "customer-api", "service": "Cloud Run"},
                        "enforcement": "hard_stop",
                    }
                ]
            }
        )
        [budget] = cfg.to_budgets()
        assert budget.amount == Decimal("200000")
        assert budget.enforcement is EnforcementAction.HARD_STOP
        assert budget.period is BudgetPeriod.MONTHLY


class TestConfigHoldsNoSecrets:
    def test_credentials_are_named_not_valued(self, monkeypatch):
        """The config file must stay safe to commit or paste into a bug report."""
        monkeypatch.setenv("MY_HOOK", "https://hooks.slack.com/services/SECRET")
        cfg = Config.model_validate({"alerts": {"slack": {"webhook_url_env": "MY_HOOK"}}})

        assert "SECRET" not in cfg.model_dump_json()
        assert cfg.alerts.slack.webhook_url == "https://hooks.slack.com/services/SECRET"


# --- notification -------------------------------------------------------------


class Recording:
    name = "recording"

    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.sent: list[Message] = []

    def send(self, message: Message) -> bool:
        self.sent.append(message)
        return self.succeed


class TestRouter:
    def test_respects_the_severity_floor(self):
        channel = Recording()
        router = Router([channel], min_severity=Severity.CRITICAL)

        assert router.send(Message("t", "b", Severity.WARNING)) is False
        assert channel.sent == []
        assert router.send(Message("t", "b", Severity.CRITICAL)) is True

    def test_partial_success_counts(self):
        """If Slack is down but email worked, a human was reached - which is the only
        thing that matters."""
        broken, working = Recording(succeed=False), Recording(succeed=True)
        router = Router([broken, working], min_severity=Severity.INFO)
        assert router.send(Message("t", "b", Severity.WARNING)) is True

    def test_total_failure_reports_false(self):
        router = Router([Recording(succeed=False)], min_severity=Severity.INFO)
        assert router.send(Message("t", "b", Severity.WARNING)) is False

    def test_alert_body_carries_the_explanation(self):
        channel = Recording()
        Router([channel], min_severity=Severity.INFO).send_alert(make_alert())

        [message] = channel.sent
        assert "SPEND_SPIKE" in message.title
        assert "projected 24h exposure" in message.body

    def test_console_channel_never_raises(self, capsys):
        assert ConsoleChannel().send(Message("t", "b", Severity.INFO)) is True
        assert "t" in capsys.readouterr().out


# --- daemon -------------------------------------------------------------------


class TestDaemonCycle:
    def _config(self, tmp_path) -> Config:
        return Config.model_validate(
            {
                "store": {"path": str(tmp_path / "t.duckdb")},
                "collectors": [],
                "budgets": [
                    {
                        "id": "tiny",
                        "name": "Tiny budget",
                        "amount": "500",
                        "scope": {"project_id": "proj-a"},
                        "thresholds": [0.5, 1.0],
                    }
                ],
                "alerts": {"console": False, "min_severity": "info"},
            }
        )

    @pytest.mark.asyncio
    async def test_budget_breach_notifies_once(self, tmp_path):
        """Records must sit in the *current* budget period - the daemon evaluates
        where the money is being spent now, not history."""
        from prahari.collector.daemon import Daemon
        from prahari.core.budget import period_bounds

        cfg = self._config(tmp_path)
        channel = Recording()
        period_start, _ = period_bounds(BudgetPeriod.MONTHLY, datetime.now(UTC))

        with Store(cfg.store.path) as store:
            # Rs 2400 against a Rs 500 budget.
            store.upsert_records([rec(h, "100", base=period_start) for h in range(24)])
            daemon = Daemon(cfg, store, Router([channel], min_severity=Severity.INFO))

            first = await daemon.cycle()
            assert first.budget_notifications == 1
            assert "Tiny budget" in channel.sent[0].title

            # Second cycle: same breach, no new page. An alerting system that repeats
            # itself gets muted, which is the same as having none.
            second = await daemon.cycle()
            assert second.budget_notifications == 0

    @pytest.mark.asyncio
    async def test_cycle_with_no_data_is_quiet(self, tmp_path):
        from prahari.collector.daemon import Daemon

        cfg = self._config(tmp_path)
        channel = Recording()
        with Store(cfg.store.path) as store:
            result = await Daemon(cfg, store, Router([channel])).cycle()

        assert result.collected == 0
        assert result.budget_notifications == 0
        assert channel.sent == []

    @pytest.mark.asyncio
    async def test_collector_failure_is_isolated_and_backs_off(self, tmp_path):
        """One provider outage must not stop the others, especially not the fast
        Anthropic path that catches attacks."""
        from prahari.collector.daemon import CollectorState, Daemon

        cfg = self._config(tmp_path)
        with Store(cfg.store.path) as store:
            daemon = Daemon(cfg, store, Router([Recording()]))

            class Boom:
                async def fetch(self, start, end):
                    raise RuntimeError("provider is down")

            from prahari.core.config import CollectorConfig

            state = CollectorState(
                config=CollectorConfig(provider=Provider.OPENAI, account_id="o"),
                connector=Boom(),
                next_run=datetime.now(UTC) - timedelta(seconds=1),
            )
            daemon.collectors = [state]

            result = await daemon.cycle()

            assert len(result.failures) == 1
            assert "provider is down" in result.failures[0]
            assert state.consecutive_failures == 1
            assert state.next_run > datetime.now(UTC)

            await daemon.cycle()  # not yet due, so no second attempt
            assert state.consecutive_failures == 1

    def test_window_respects_settling_lag_and_watermark(self, tmp_path):
        from prahari.collector.daemon import MAX_WINDOW, CollectorState, Daemon
        from prahari.core.config import CollectorConfig

        cfg = self._config(tmp_path)
        with Store(cfg.store.path) as store:
            daemon = Daemon(cfg, store, Router([Recording()]))
            collector_cfg = CollectorConfig(
                provider=Provider.OPENAI,
                account_id="o",
                settling_lag=timedelta(minutes=30),
                initial_lookback=timedelta(days=3),
            )
            state = CollectorState(
                config=collector_cfg, connector=object(), next_run=datetime.now(UTC)
            )
            now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

            # First run: reaches back `initial_lookback`, but the span is capped, so
            # a 3-day backfill arrives over two cycles rather than one huge query.
            start, end = daemon._window(state, now)
            assert start == now - timedelta(minutes=30) - timedelta(days=3)
            assert end - start == MAX_WINDOW

            # A long outage catches up in capped increments, not one huge query.
            # (Separate collector name: `set_watermark` refuses to rewind, so this
            # cannot reuse one that has already advanced.)
            outage = CollectorConfig(
                provider=Provider.OPENAI, account_id="outage", settling_lag=timedelta(minutes=30)
            )
            outage_state = CollectorState(
                config=outage, connector=object(), next_run=datetime.now(UTC)
            )
            store.set_watermark(outage.name, now - timedelta(days=30))
            start, end = daemon._window(outage_state, now)
            assert end - start == MAX_WINDOW

            # Once caught up, the window ends exactly at the settling lag.
            store.set_watermark(collector_cfg.name, now - timedelta(hours=4))
            start, end = daemon._window(state, now)
            assert start == now - timedelta(hours=4)
            assert end == now - timedelta(minutes=30)
