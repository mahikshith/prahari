"""Collector daemon - the thing that actually runs.

Until now everything was a script somebody had to invoke. A design partner cannot run
a script; they run a container that keeps working while they sleep, and that is what
this is.

Design decisions worth defending:

**Watermarks, not fixed windows.** Each collector resumes from where it last got a
*settled* answer. A crash mid-cycle costs one cycle, not a backfill.

**Never collect right up to now.** Providers backfill their own data for minutes to
hours. Collecting a still-filling window and treating it as final produces a total
that changes tomorrow - the fastest way to lose a finance buyer. Each collector has
a `settling_lag`, and the watermark only advances past data the provider considers
complete.

**One slow provider must not stall the others.** Collectors run concurrently, and
failures are isolated per collector with exponential backoff. A GCP outage should not
stop Anthropic detection, which is the fast path that catches attacks.

**Detection runs on what was just collected, against baselines from the store.**
Alerts are deduplicated by the store, so a restart cannot re-page anybody.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import signal
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from prahari.connectors.base import Connector, ProviderConfig, ProviderHTTPError
from prahari.core.budget import evaluate_all
from prahari.core.config import CollectorConfig, Config
from prahari.core.models import Provider, UsageRecord
from prahari.detect.aggregate import observations_from_records
from prahari.detect.rules import Detector
from prahari.notify.router import Router
from prahari.pricing.registry import premium_models
from prahari.store.duck import Store

log = logging.getLogger("prahari.collector")

MAX_BACKOFF = timedelta(minutes=30)
MAX_WINDOW = timedelta(days=2)
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
        if not self.collectors:
            return 60.0
        soonest = min(c.next_run for c in self.collectors)
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
                    message = f"{state.config.name}: {type(outcome).__name__}: {outcome}"
                    log.warning("collection failed - %s", message)
                    state.schedule_failure(now, message)
                    result.failures.append(message)
                else:
                    fresh.extend(outcome)
                    state.schedule_success(now)

            result.collected = len(fresh)

        if self.config.detection.enabled:
            raised, notified = self._detect()
            result.alerts_raised, result.alerts_notified = raised, notified

        result.budget_notifications = self._check_budgets()
        return result

    async def _collect(self, state: CollectorState, now: datetime) -> list[UsageRecord]:
        start, end = self._window(state, now)
        if start >= end:
            return []

        log.debug("%s: fetching %s -> %s", state.config.name, start, end)
        try:
            fetched = await state.connector.fetch(start, end)
        except ProviderHTTPError as exc:
            # Already sanitized of credentials by the connector layer.
            raise RuntimeError(f"HTTP {exc.status_code} from {exc.path}") from None

        if fetched.records:
            self.store.upsert_records(fetched.records)
            state.records_collected += len(fetched.records)

        if fetched.warnings:
            for warning in fetched.warnings[:5]:
                log.warning("%s: %s", state.config.name, warning)

        # Only advance past data the provider considers settled. An incomplete window
        # must be re-fetched, or we would permanently under-report it.
        if fetched.is_complete:
            self.store.set_watermark(state.config.name, end)

        return fetched.records

    def _window(self, state: CollectorState, now: datetime) -> tuple[datetime, datetime]:
        end = now - state.config.settling_lag
        watermark = self.store.watermark(state.config.name)
        start = watermark or (end - state.config.initial_lookback)
        # Cap the span so recovering from a long outage takes several ordinary cycles
        # instead of one query large enough to time out forever.
        return start, min(end, start + MAX_WINDOW)

    # --- detection ------------------------------------------------------------

    def _detect(self) -> tuple[int, int]:
        """Replay a rolling window so baselines are rebuilt from persisted history.

        Stateless by design: the detector holds no memory across restarts, so a
        restart cannot silently lose a baseline and let an ongoing attack look normal.
        Alert deduplication in the store makes the replay safe to repeat.
        """
        now = datetime.now(UTC)
        history = self.store.records(start=now - timedelta(days=30), end=now)
        if not history:
            return 0, 0

        detector = Detector(premium_models=self._premium)
        raised = notified = 0
        recent_cutoff = now - timedelta(hours=6)

        for observation in observations_from_records(history):
            for alert in detector.process(observation):
                # Only act on recent alerts. Replaying 30 days of history would
                # otherwise re-raise every historical anomaly on first run.
                if alert.at < recent_cutoff:
                    continue
                if not self.store.record_alert(alert):
                    continue  # already seen; never page twice for one event
                raised += 1
                if self.router.send_alert(alert):
                    self.store.mark_notified(alert)
                    notified += 1

        return raised, notified

    # --- budgets --------------------------------------------------------------

    def _check_budgets(self) -> int:
        budgets = self.config.to_budgets()
        if not budgets:
            return 0

        now = datetime.now(UTC)
        records = self.store.records(start=now - timedelta(days=95), end=now)
        if not records:
            return 0

        sent = 0
        for state in evaluate_all(budgets, records, as_of=now):
            already = self.store.crossed_thresholds(state.budget.id, state.period_start)
            newly = [
                t
                for t in state.budget.thresholds
                if state.pct_used >= t and t not in set(already)
            ]
            if not newly:
                continue

            for threshold in newly:
                self.store.mark_threshold_crossed(state.budget.id, state.period_start, threshold)
            if self.router.send_budget(state, newly):
                sent += 1

        return sent


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
