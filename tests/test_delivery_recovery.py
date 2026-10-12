from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from prahari.collector.daemon import CollectorState, Daemon
from prahari.connectors.base import FetchResult
from prahari.core.budget import Budget, evaluate_all
from prahari.core.config import CollectorConfig, Config
from prahari.core.fx import FxTable
from prahari.core.models import CostBasis, Provider, TokenCounts, UsageRecord
from prahari.detect.rules import Alert, Rule, Severity
from prahari.notify.router import Message, Router
from prahari.store.duck import _COLUMNS, Store, alert_from_row, alert_id, record_id


def record(at: datetime, cost: Decimal | None = Decimal("100"), **updates) -> UsageRecord:
    return UsageRecord(
        provider=Provider.GCP_VERTEX,
        account_id="test-account",
        api_key_id="test-key",
        project_id="test-project",
        model="test-model",
        tokens=TokenCounts(requests=1),
        billed_cost=cost,
        currency="INR",
        period_start=at,
        period_end=at + timedelta(hours=1),
        ingested_at=datetime.now(UTC),
        source="test",
        **updates,
    )


class Recording:
    def __init__(self, name: str, success: bool = True):
        self.name = name
        self.success = success
        self.messages: list[Message] = []

    def send(self, message: Message) -> bool:
        self.messages.append(message)
        return self.success


def make_alert() -> Alert:
    return Alert(
        rule=Rule.SPEND_SPIKE,
        severity=Severity.CRITICAL,
        detection_key=("gcp_vertex", "test-key"),
        at=datetime.now(UTC),
        observed=Decimal("100"),
        baseline=Decimal("1"),
        multiple=Decimal("100"),
        spend_so_far=Decimal("100"),
        projected_24h=Decimal("2400"),
        currency="INR",
        evidence={},
        confidence="medium",
    )


def retry_now(store: Store) -> None:
    store._con.execute("UPDATE notification_outbox SET next_attempt = ?", [datetime.now(UTC)])


@pytest.mark.asyncio
async def test_failed_alert_survives_restart_and_only_failed_channel_retries(tmp_path):
    path = tmp_path / "alerts.duckdb"
    cfg = Config.model_validate({"collectors": [], "detection": {"enabled": False}})
    console, slack, smtp = Recording("console"), Recording("slack", False), Recording("smtp")
    with Store(path) as store:
        alert = make_alert()
        store.record_alert(alert)
        result = await Daemon(cfg, store, Router([console, slack, smtp])).cycle()
        assert result.alerts_notified == 0
        assert len(store.pending_alerts()) == 1
        assert len(console.messages) == len(slack.messages) == len(smtp.messages) == 1
        assert store.pending_alerts()[0]["confidence"] == "medium"
    slack.success = True
    with Store(path) as store:
        retry_now(store)
        result = await Daemon(cfg, store, Router([console, slack, smtp])).cycle()
        assert result.alerts_notified == 1
        assert not store.pending_alerts()
        assert len(console.messages) == len(smtp.messages) == 1
        assert len(slack.messages) == 2
        assert (
            await Daemon(cfg, store, Router([console, slack, smtp])).cycle()
        ).alerts_notified == 0


@pytest.mark.asyncio
async def test_failed_budget_survives_restart_without_records(tmp_path):
    path = tmp_path / "budgets.duckdb"
    cfg = Config.model_validate(
        {
            "collectors": [],
            "detection": {"enabled": False},
            "budgets": [{"id": "budget", "name": "test", "amount": "50"}],
        }
    )
    channel = Recording("slack", False)
    with Store(path) as store:
        store.upsert_records([record(datetime.now(UTC))])
        assert (await Daemon(cfg, store, Router([channel])).cycle()).budget_notifications == 0
        assert len(channel.messages) == 1
        assert store._con.execute("SELECT count(*) FROM budget_thresholds").fetchone()[0] == 3
        assert (
            store._con.execute(
                "SELECT count(*) FROM budget_thresholds WHERE notified_at IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        store._con.execute("DELETE FROM usage_records")
    channel.success = True
    with Store(path) as store:
        retry_now(store)
        assert (await Daemon(cfg, store, Router([channel])).cycle()).budget_notifications == 1
        assert len(channel.messages) == 2
        assert (
            store._con.execute(
                "SELECT count(*) FROM budget_thresholds WHERE notified_at IS NOT NULL"
            ).fetchone()[0]
            == 3
        )


@pytest.mark.asyncio
async def test_retry_backoff_does_not_spin_or_repeat_success():
    cfg = Config.model_validate({"collectors": [], "detection": {"enabled": False}})
    channel = Recording("slack", False)
    with Store() as store:
        store.record_alert(make_alert())
        daemon = Daemon(cfg, store, Router([channel]))
        await daemon.cycle()
        await daemon.cycle()
        assert len(channel.messages) == 1
        assert daemon._seconds_until_next_due() > 1


@pytest.mark.asyncio
async def test_crash_after_delivery_before_ack_is_recovered_without_resend():
    cfg = Config.model_validate({"collectors": [], "detection": {"enabled": False}})
    channel = Recording("slack")
    with Store() as store:
        alert = make_alert()
        store.record_alert(alert)
        router = Router([channel])
        eid = alert_id(alert)
        store.queue_notification(eid, "alert", router.alert_message(alert), ["slack"])
        store.record_delivery(eid, "slack", True, datetime.now(UTC))
        assert (await Daemon(cfg, store, router).cycle()).alerts_notified == 1
        assert not channel.messages


@pytest.mark.asyncio
async def test_live_dormancy_uses_activity_before_rolling_window():
    now = datetime.now(UTC)
    cfg = Config.model_validate(
        {
            "collectors": [],
            "detection": {"premium_model_providers": []},
            "fx_rates": [
                {
                    "base": "USD",
                    "quote": "INR",
                    "rate": "85",
                    "as_of": (now - timedelta(days=50)).date(),
                    "source": "test",
                }
            ],
        }
    )
    channel = Recording("slack")
    with Store() as store:
        store.upsert_records([record(now - timedelta(days=41)), record(now - timedelta(minutes=1))])
        assert (await Daemon(cfg, store, Router([channel])).cycle()).alerts_raised >= 1
        assert any("DORMANT_KEY_WAKE" in message.title for message in channel.messages)


def test_store_preserves_unknown_cost_and_refuses_complete_total():
    with Store() as store:
        at = datetime.now(UTC)
        store.upsert_records([record(at, None)])
        [restored] = store.records()
        assert restored.billed_cost is None
        assert restored.cost_basis is CostBasis.UNPRICED
        with pytest.raises(ValueError, match="incomplete"):
            store.total_cost(at - timedelta(seconds=1), at + timedelta(hours=2))


def test_invoice_month_and_charge_type_do_not_overwrite_each_other():
    with Store() as store:
        at = datetime.now(UTC)
        first = record(at, extensions={"invoice_month": "202609", "cost_type": "regular"})
        second = record(at, extensions={"invoice_month": "202610", "cost_type": "regular"})
        third = record(at, extensions={"invoice_month": "202610", "cost_type": "adjustment"})
        store.upsert_records([first, second, third])
        store.upsert_records([first, second, third])
        assert store.count() == 3


def test_notification_targets_are_frozen_and_console_never_acknowledges_old_slack_failure():
    with Store() as store:
        message = Message("test", "metadata", Severity.CRITICAL)
        store.queue_notification("event", "alert", message, ["console", "slack"])
        store.record_delivery("event", "console", True, datetime.now(UTC))
        store.queue_notification("event", "alert", message, ["console"])
        assert not store.notification_complete("event")
        store.queue_notification("event", "alert", message, ["console", "slack", "smtp"])
        assert {
            row[0]
            for row in store._con.execute("SELECT channel FROM notification_outbox").fetchall()
        } == {"console", "slack"}
        store.record_delivery("event", "slack", True, datetime.now(UTC))
        assert store.notification_complete("event")


@pytest.mark.asyncio
async def test_removed_channel_backlog_cannot_starve_active_delivery():
    cfg = Config.model_validate({"collectors": [], "detection": {"enabled": False}})
    channel = Recording("slack")
    with Store() as store:
        for i in range(100):
            store.queue_notification(
                str(i), "alert", Message("old", "metadata", Severity.WARNING), ["retired-channel"]
            )
        store.record_alert(make_alert())
        assert (await Daemon(cfg, store, Router([channel])).cycle()).alerts_notified == 1
        assert len(channel.messages) == 1


@pytest.mark.asyncio
async def test_queued_warnings_do_not_block_new_critical_alert():
    cfg = Config.model_validate({"collectors": [], "detection": {"enabled": False}})
    channel = Recording("slack")
    router = Router([channel], min_severity=Severity.CRITICAL)
    with Store() as store:
        for i in range(100):
            old = replace(
                make_alert(), severity=Severity.WARNING, detection_key=("gcp_vertex", f"old-{i}")
            )
            store.record_alert(old)
            store.queue_notification(alert_id(old), "alert", router.alert_message(old), ["slack"])
        store.record_alert(make_alert())
        assert (await Daemon(cfg, store, router).cycle()).alerts_notified == 1
        assert len(channel.messages) == 1
        assert channel.messages[0].severity is Severity.CRITICAL


def test_gcp_aggregation_grain_retains_service_and_project_name():
    with Store() as store:
        at = datetime.now(UTC)
        rows = [
            record(
                at,
                extensions={
                    "invoice_month": "202610",
                    "cost_type": "regular",
                    "service": service,
                    "project_name": project,
                },
            )
            for service, project in [("a", "old"), ("b", "old"), ("a", "renamed")]
        ]
        store.upsert_records(rows)
        store.upsert_records(rows)
        assert store.count() == 3


def test_refetch_replaces_old_gcp_aggregate_instead_of_double_counting_new_invoice_groups():
    with Store() as store:
        at = datetime.now(UTC)
        old = record(at, extensions={"service": "Vertex AI"})
        other = old.model_copy(update={"account_id": "other-account"})
        store.upsert_records([old, other])
        first = old.model_copy(
            update={
                "billed_cost": Decimal("60"),
                "extensions": {
                    "service": "Vertex AI",
                    "invoice_month": "202609",
                    "cost_type": "regular",
                },
            }
        )
        second = old.model_copy(
            update={
                "billed_cost": Decimal("40"),
                "extensions": {
                    "service": "Vertex AI",
                    "invoice_month": "202610",
                    "cost_type": "regular",
                },
            }
        )
        store.upsert_records([first, second])
        assert store.count() == 3
        assert store.total_cost(at - timedelta(seconds=1), at + timedelta(hours=2)) == Decimal(
            "200"
        )


def test_unrelated_missing_fx_does_not_disable_a_native_currency_project_budget():
    at = datetime.now(UTC)
    local = record(at)
    external = record(at).model_copy(update={"currency": "USD", "project_id": "other-project"})
    states = evaluate_all(
        [
            Budget("native", "Native", Decimal("50"), scope={"project_id": "test-project"}),
            Budget("org", "Org", Decimal("500")),
        ],
        [local, external],
        as_of=at + timedelta(seconds=1),
        fx=FxTable([]),
    )
    by_id = {state.budget.id: state for state in states}
    assert by_id["native"].spent == Decimal("100")
    assert by_id["native"].unpriced_records == 0
    assert by_id["org"].unpriced_records == 1


def test_unknown_cost_alert_roundtrip_does_not_invent_zero_cost():
    with Store() as store:
        alert = replace(
            make_alert(),
            rule=Rule.COST_UNAVAILABLE,
            observed=None,
            baseline=None,
            spend_so_far=None,
            projected_24h=None,
            evidence={"reason": "unpriced model"},
        )
        store.record_alert(alert)
        [row] = store.pending_alerts()
        restored = alert_from_row(row)
        assert restored.observed is None
        assert restored.projected_24h is None
        assert "projected 24h" not in restored.explain()


@pytest.mark.asyncio
async def test_stalled_provider_deadline_preserves_alert_delivery(monkeypatch):
    import asyncio

    import prahari.collector.daemon as module

    monkeypatch.setattr(module, "FETCH_TIMEOUT_SECONDS", 0.01)
    cfg = Config.model_validate({"collectors": [], "detection": {"enabled": False}})

    class Stalled:
        async def fetch(self, start, end):
            await asyncio.Event().wait()

    channel = Recording("slack")
    with Store() as store:
        store.record_alert(make_alert())
        daemon = Daemon(cfg, store, Router([channel]))
        daemon.collectors = [
            CollectorState(
                config=CollectorConfig(provider=Provider.OPENAI, account_id="test"),
                connector=Stalled(),
                next_run=datetime.now(UTC) - timedelta(seconds=1),
            )
        ]
        result = await daemon.cycle()
        assert len(result.failures) == 1
        assert "TimeoutError" in result.failures[0]
        assert result.alerts_notified == 1


@pytest.mark.parametrize("fail_migration", [False, True])
def test_v1_store_migration_preserves_data_and_rekeys_idempotently(
    tmp_path, monkeypatch, fail_migration
):
    path = tmp_path / "legacy.duckdb"
    at = datetime.now(UTC)
    rec = record(at)
    with Store() as memory:
        values = dict(zip(_COLUMNS, memory._to_row(rec), strict=True))
    values.pop("cost_basis")
    old_key = [
        str(getattr(rec, name) or "")
        for name in (
            "provider",
            "account_id",
            "api_key_id",
            "user_id",
            "project_id",
            "workspace_id",
            "model",
            "operation",
            "region",
            "service_tier",
            "source",
        )
    ]
    old_key.append(at.isoformat())
    values["record_id"] = hashlib.sha256("\x1f".join(old_key).encode()).hexdigest()[:32]
    with duckdb.connect(str(path)) as old:
        old.execute((Path(__file__).parent / "fixtures/schema_v1.sql").read_text())
        old.execute("INSERT INTO schema_meta VALUES (?,?)", [1, at])
        old.register("legacy_row", pd.DataFrame([values]))
        old.execute("INSERT INTO usage_records BY NAME SELECT * FROM legacy_row")
        old.execute("INSERT INTO watermarks VALUES (?,?,?)", ["test", at, at])
    if fail_migration:

        def fail_conversion(self, value):
            raise RuntimeError("injected migration failure")

        with monkeypatch.context() as patch:
            patch.setattr(Store, "_to_row", fail_conversion)
            with pytest.raises(RuntimeError, match="injected migration failure"):
                Store(path)
        with duckdb.connect(str(path)) as untouched:
            assert untouched.execute("SELECT max(version) FROM schema_meta").fetchone()[0] == 1
            assert untouched.execute("SELECT count(*) FROM usage_records").fetchone()[0] == 1
    with Store(path) as migrated:
        assert migrated.count() == 1
        assert migrated.watermark("test") == at
        assert migrated.records()[0].billed_cost == Decimal("100")
        assert migrated._con.execute("SELECT record_id FROM usage_records").fetchone()[
            0
        ] == record_id(rec)
        migrated.upsert_records([rec])
        assert migrated.count() == 1
    with Store(path) as reopened:
        assert reopened.count() == 1


@pytest.mark.asyncio
async def test_provisional_gcp_scanning_progresses_and_refreshes_recent_window():
    cfg = Config.model_validate({"collectors": [], "detection": {"enabled": False}})
    collector = CollectorConfig(provider=Provider.GCP_VERTEX, account_id="test")

    class Provisional:
        async def fetch(self, start, end):
            return FetchResult(records=[], window_start=start, window_end=end, is_complete=False)

    now = datetime.now(UTC)
    state = CollectorState(config=collector, connector=Provisional(), next_run=now)
    with Store() as store:
        daemon = Daemon(cfg, store, Router([]))
        _start, end = daemon._window(state, now)
        await daemon._collect(state, now)
        assert store.watermark(collector.name) is None
        assert store.watermark(f"{collector.name}:scan") == end
        next_start, next_end = daemon._window(state, now)
        assert next_start == end
        assert next_end > end
        latest = now - collector.settling_lag
        store.set_watermark(f"{collector.name}:scan", latest)
        recent_start, recent_end = daemon._window(state, now + timedelta(minutes=15))
        assert recent_start == latest - timedelta(days=1)
        assert recent_end > latest
