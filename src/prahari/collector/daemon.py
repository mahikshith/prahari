"""Collector daemon - the thing that actually runs.

Until now everything was a script somebody had to invoke. A design partner cannot run
a script; they run a container that keeps working while they sleep, and that is what
this is.

Design decisions worth defending:

**Durable scan state.** Billing scans advance provisionally with a bounded overlap;
other connectors advance their settled watermark only on a complete result.

**Source completeness is explicit.** Each collector has a configured delay, which
does not prove finality. GCP billing stays provisional; usage connectors currently
use age heuristics that still require live validation.

**Bounded concurrent collection.** Failures are isolated with backoff; each fetch has
a deadline so provider waits cannot indefinitely delay local detection and delivery.

**Detection runs on what was just collected, against baselines from the store.**
Alerts are deduplicated and delivery is persisted per channel. An ambiguous crash
after remote acceptance can still cause a duplicate delivery.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import signal
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from prahari.connectors.base import Connector, ProviderConfig, ProviderHTTPError
from prahari.core.budget import evaluate_all
from prahari.core.config import CollectorConfig, Config
from prahari.core.fx import FxError
from prahari.core.models import ChargeCategory, Provider, UsageRecord
from prahari.detect.aggregate import observations_from_records
from prahari.detect.rules import Detector, Severity
from prahari.notify.router import Message, Router
from prahari.pricing.registry import premium_models
from prahari.store.duck import Store, alert_from_row

log = logging.getLogger("prahari.collector")

MAX_BACKOFF = timedelta(minutes=30)
MAX_WINDOW = timedelta(days=2)
FETCH_TIMEOUT_SECONDS = 60
"""Cap on a single fetch. A long outage should catch up over several cycles rather
than issuing one enormous query that times out and never succeeds."""


def build_connector(config: CollectorConfig) -> Connector:
    """Provider -> connector. Imported lazily so a missing optional extra (say the
    GCP libraries) only breaks the collector that needs it."""
    provider_config = ProviderConfig(
        provider=config.provider,
        account_id=config.account_id,
        poll_interval=config.poll_interval,
        extra=config.extra or None,
    )

    if config.provider is Provider.ANTHROPIC:
        from prahari.connectors.anthropic import AnthropicConnector

        return AnthropicConnector(provider_config)
    if config.provider is Provider.OPENAI:
        from prahari.connectors.openai import OpenAIConnector

        return OpenAIConnector(provider_config)
    if config.provider is Provider.GCP_VERTEX:
        from prahari.connectors.gcp import GCPBillingConnector

        return GCPBillingConnector(provider_config)

    raise ValueError(f"no connector implemented for {config.provider}")


@dataclass
class CollectorState:
    """Per-collector runtime state, including failure backoff."""

    config: CollectorConfig
    connector: Connector
    next_run: datetime
    consecutive_failures: int = 0
    last_error: str | None = None
    records_collected: int = 0

    def schedule_success(self, now: datetime) -> None:
        self.consecutive_failures = 0
        self.last_error = None
        self.next_run = now + self.config.poll_interval

    def schedule_failure(self, now: datetime, error: str) -> None:
        self.consecutive_failures += 1
        self.last_error = error
        # Exponential with jitter. Jitter matters: several collectors failing on the
        # same network blip would otherwise retry in lockstep forever.
        backoff = min(
            self.config.poll_interval * (2**self.consecutive_failures),
            MAX_BACKOFF,
        )
        jitter = backoff * random.uniform(0, 0.2)
        self.next_run = now + backoff + jitter


@dataclass
class CycleResult:
    collected: int = 0
    alerts_raised: int = 0
    alerts_notified: int = 0
    budget_notifications: int = 0
    failures: list[str] = field(default_factory=list)


class Daemon:
    def __init__(self, config: Config, store: Store, router: Router) -> None:
        self.config = config
        self.store = store
        self.router = router
        self._stopping = asyncio.Event()

        now = datetime.now(UTC)
        self.collectors = [
            CollectorState(config=c, connector=build_connector(c), next_run=now)
            for c in config.enabled_collectors
        ]

        self._premium: set[str] = set()
        for provider in config.detection.premium_model_providers:
            with contextlib.suppress(Exception):
                self._premium |= premium_models(provider)

    # --- lifecycle ------------------------------------------------------------

    def request_stop(self) -> None:
        log.info("shutdown requested; finishing current cycle")
        self._stopping.set()

    async def run(self) -> None:
        """Loop until stopped. Sleeps until the earliest due collector rather than
        polling on a fixed tick, so an idle daemon costs nothing."""
        log.info(
            "starting with %d collector(s): %s",
            len(self.collectors),
            ", ".join(c.config.name for c in self.collectors),
        )
        if missing := self.config.missing_env():
            log.warning("missing environment variables: %s", ", ".join(missing))

        while not self._stopping.is_set():
            result = await self.cycle()
            if result.collected or result.alerts_raised or result.failures:
                log.info(
                    "cycle: %d records, %d alerts (%d sent), %d budget notices, %d failures",
                    result.collected,
                    result.alerts_raised,
                    result.alerts_notified,
                    result.budget_notifications,
                    len(result.failures),
                )

            delay = self._seconds_until_next_due()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=delay)

        log.info("stopped")

    def _seconds_until_next_due(self) -> float:
        due = [c.next_run for c in self.collectors]
        notification_due = self.store.next_notification_due(self.router.channel_names)
        if notification_due:
            due.append(notification_due)
        if not due:
            return 60.0
        soonest = min(due)
        return max(1.0, min(60.0, (soonest - datetime.now(UTC)).total_seconds()))

    # --- one pass -------------------------------------------------------------

    async def cycle(self) -> CycleResult:
        now = datetime.now(UTC)
        due = [c for c in self.collectors if c.next_run <= now]
        result = CycleResult()

        if due:
            outcomes = await asyncio.gather(
                *(self._collect(state, now) for state in due), return_exceptions=True
            )

            fresh: list[UsageRecord] = []
            for state, outcome in zip(due, outcomes, strict=True):
                if isinstance(outcome, BaseException):
                    # Isolated per collector: one provider outage must not stop the
                    # others, especially not the fast Anthropic detection path.
                    message = f"{state.config.name}: {type(outcome).__name__}; collection failed"
                    log.warning("collection failed - %s", message)
                    state.schedule_failure(now, message)
                    result.failures.append(message)
                else:
                    fresh.extend(outcome)
                    state.schedule_success(now)

            result.collected = len(fresh)

        if self.config.detection.enabled:
            try:
                result.alerts_raised = self._detect()
            except (FxError, ValueError) as exc:
                result.failures.append(f"detection unavailable: {type(exc).__name__}")
                log.warning("detection unavailable: %s", type(exc).__name__)

        try:
            self._check_budgets()
        except (FxError, ValueError) as exc:
            result.failures.append(f"budget evaluation unavailable: {type(exc).__name__}")
            log.warning("budget evaluation unavailable: %s", type(exc).__name__)
        delivered = self._deliver_notifications()
        result.alerts_notified = delivered["alert"]
        result.budget_notifications = delivered["budget"]
        return result

    async def _collect(self, state: CollectorState, now: datetime) -> list[UsageRecord]:
        start, end = self._window(state, now)
        if start >= end:
            return []

        log.debug("%s: fetching %s -> %s", state.config.name, start, end)
        try:
            async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
                fetched = await state.connector.fetch(start, end)
        except ProviderHTTPError as exc:
            # Already sanitized of credentials by the connector layer.
            raise RuntimeError(f"HTTP {exc.status_code} from {exc.path}") from None

        if fetched.records:
            mode = "backfill" if end < now - timedelta(days=1) else "live"
            records = [
                record.model_copy(
                    update={"extensions": {**record.extensions, "collection_mode": mode}}
                )
                for record in fetched.records
            ]
            self.store.upsert_records(records)
            state.records_collected += len(fetched.records)

        if fetched.warnings:
            for warning in fetched.warnings[:5]:
                log.warning("%s: %s", state.config.name, warning)

        # Only advance past data the provider considers settled. An incomplete window
        # must be re-fetched, or we would permanently under-report it.
        if fetched.is_complete:
            self.store.set_watermark(state.config.name, end)
        if state.config.provider is Provider.GCP_VERTEX:
            self.store.set_watermark(f"{state.config.name}:scan", end)

        return fetched.records

    def _window(self, state: CollectorState, now: datetime) -> tuple[datetime, datetime]:
        end = now - state.config.settling_lag
        is_billing = state.config.provider is Provider.GCP_VERTEX
        watermark = self.store.watermark(
            f"{state.config.name}:scan" if is_billing else state.config.name
        )
        start = watermark or (end - state.config.initial_lookback)
        if is_billing and watermark and end - watermark < timedelta(days=1):
            # shortcut: refresh one day; invoice reconciliation must recover older corrections.
            start -= timedelta(days=1)
        # Cap the span so recovering from a long outage takes several ordinary cycles
        # instead of one query large enough to time out forever.
        return start, min(end, start + MAX_WINDOW)

    # --- detection ------------------------------------------------------------

    def _detect(self) -> int:
        """Replay a rolling window so baselines are rebuilt from persisted history.

        Stateless by design: the detector holds no memory across restarts, so a
        restart cannot silently lose a baseline and let an ongoing attack look normal.
        Alert deduplication in the store makes the replay safe to repeat.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=30)
        history = [
            record
            for record in self.store.records(start=cutoff, end=now)
            if record.charge_category is ChargeCategory.USAGE
            and (
                record.provider is not Provider.GCP_VERTEX
                or record.extensions.get("service_category") == "ai"
                or record.model is not None
                or record.tokens.total_tokens > 0
            )
        ]
        if not history:
            return 0

        detector = Detector(
            premium_models=self._premium,
            fx=self.config.fx_table(),
            last_activity=self.store.last_activity_before(cutoff),
        )
        raised = 0
        recent_cutoff = now - timedelta(hours=6)
        live_hours = {
            (record.detection_key, record.period_start.replace(minute=0, second=0, microsecond=0))
            for record in history
            if record.ingested_at >= recent_cutoff
            and record.extensions.get("collection_mode") == "live"
        }

        for observation in observations_from_records(history):
            for alert in detector.process(observation):
                # Only act on recent alerts. Replaying 30 days of history would
                # otherwise re-raise every historical anomaly on first run.
                if alert.at < recent_cutoff and (alert.detection_key, alert.at) not in live_hours:
                    continue
                if alert.at < recent_cutoff:
                    alert = replace(
                        alert,
                        evidence={
                            **alert.evidence,
                            "delayed_source": True,
                            "source_delay_seconds": int((now - alert.at).total_seconds()),
                        },
                    )
                if not self.store.record_alert(alert):
                    continue  # already seen; never page twice for one event
                raised += 1

        return raised

    # --- budgets --------------------------------------------------------------

    def _check_budgets(self) -> None:
        budgets = self.config.to_budgets()
        if not budgets:
            return

        now = datetime.now(UTC)
        records = self.store.records(start=now - timedelta(days=95), end=now)
        if not records:
            return

        for state in evaluate_all(budgets, records, as_of=now, fx=self.config.fx_table()):
            already = self.store.crossed_thresholds(state.budget.id, state.period_start)
            newly = [
                t for t in state.budget.thresholds if state.pct_used >= t and t not in set(already)
            ]
            for threshold in newly:
                self.store.mark_threshold_crossed(state.budget.id, state.period_start, threshold)
            pending = self.store.unqueued_thresholds(state.budget.id, state.period_start)
            if pending and self.router.channel_names:
                self.store.queue_budget(
                    state.budget.id,
                    state.period_start,
                    pending,
                    self.router.budget_message(state, pending),
                    self.router.channel_names,
                )

    def _deliver_notifications(self) -> dict[str, int]:
        counts = {"alert": 0, "budget": 0}
        for row in self.store.pending_alerts(unqueued_only=True):
            alert = alert_from_row(row)
            self.store.queue_notification(
                row["alert_id"],
                "alert",
                self.router.alert_message(alert),
                self.router.channel_names,
            )

        now = datetime.now(UTC)
        groups: dict[str, list[dict]] = {}
        for row in self.store.pending_notifications(now, channels=self.router.channel_names):
            groups.setdefault(row["event_id"], []).append(row)
        for event_id, rows in groups.items():
            first = rows[0]
            message = Message(first["title"], first["body"], Severity(first["severity"]))
            results = self.router.deliver(message, {row["channel"] for row in rows})
            for row in rows:
                self.store.record_delivery(
                    event_id, row["channel"], results.get(row["channel"], False), now
                )
        for event_id, kind in self.store.unacknowledged_notifications():
            if self.store.notification_complete(event_id):
                self.store.acknowledge_notification(event_id, kind)
                counts[kind] += 1
        return counts


def install_signal_handlers(daemon: Daemon, loop: asyncio.AbstractEventLoop) -> None:
    """Ctrl-C and `docker stop` should finish the cycle, not sever it mid-write."""
    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, daemon.request_stop)
        except NotImplementedError:
            # Windows has no add_signal_handler for the proactor loop.
            signal.signal(sig, lambda *_: daemon.request_stop())


async def run_daemon(config: Config, store: Store, router: Router) -> None:
    daemon = Daemon(config, store, router)
    install_signal_handlers(daemon, asyncio.get_running_loop())
    await daemon.run()


def collectors_for(config: Config) -> Sequence[str]:
    return [c.name for c in config.enabled_collectors]
