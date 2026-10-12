"""Configuration.

Budgets, connectors, allocation and alert routing were hardcoded in `scripts/`. A
design partner must be able to configure their own estate without touching Python -
that is the difference between a script we run for them and a product they run.

Two rules that shape this file:

**No secrets in config.** Credentials are named, never valued: config says
`ANTHROPIC_ADMIN_KEY`, the environment supplies it. That keeps the config file
committable, shareable in a support thread, and safe in a bug report.

**Validate loudly at load, not lazily at use.** A typo in a budget scope should fail
`prahari validate` in the first minute, not silently match zero records for a month
and quietly under-report a budget that was actually breached.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prahari.core.budget import (
    SCOPE_DIMENSIONS,
    Budget,
    BudgetPeriod,
    EnforcementAction,
)
from prahari.core.fx import FxRate, FxTable
from prahari.core.models import Provider

_DURATION = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(value: str | int | timedelta) -> timedelta:
    """`"5m"`, `"1h"`, `"30s"`, `"7d"`, or bare seconds."""
    if isinstance(value, timedelta):
        return value
    if isinstance(value, int):
        return timedelta(seconds=value)

    match = _DURATION.match(str(value))
    if not match:
        raise ValueError(f"invalid duration {value!r}; expected forms like '30s', '5m', '2h', '1d'")
    amount, unit = match.groups()
    return timedelta(**{_UNITS[unit.lower()]: int(amount)})


class StoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "data/warehouse/prahari.duckdb"


class CollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider
    account_id: str
    enabled: bool = True
    poll_interval: timedelta = timedelta(minutes=15)
    initial_lookback: timedelta = timedelta(days=7)
    """How far back to reach on the very first run, before a watermark exists."""
    settling_lag: timedelta = timedelta(minutes=10)
    """Never collect closer to now than this. Providers backfill their own data for a
    while; treating a still-filling window as final produces a total that changes
    tomorrow, which is how a finance buyer stops trusting us."""
    extra: dict[str, str] = Field(default_factory=dict)

    @field_validator("poll_interval", "initial_lookback", "settling_lag", mode="before")
    @classmethod
    def _durations(cls, v: Any) -> timedelta:
        return parse_duration(v)

    @model_validator(mode="after")
    def _anthropic_poll_floor(self) -> CollectorConfig:
        # Anthropic documents a 1/minute poll limit. Going faster earns a 429 and
        # buys nothing, since the data itself lands in ~5 minutes.
        if self.provider is Provider.ANTHROPIC and self.poll_interval < timedelta(minutes=1):
            raise ValueError("anthropic poll_interval must be at least 1m (documented API limit)")
        return self

    @property
    def name(self) -> str:
        return f"{self.provider.value}:{self.account_id}"


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    amount: Decimal
    currency: str = "INR"
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    scope: dict[str, str] = Field(default_factory=dict)
    thresholds: list[Decimal] = Field(
        default_factory=lambda: [Decimal("0.5"), Decimal("0.8"), Decimal("1.0")]
    )
    enforcement: EnforcementAction = EnforcementAction.ALERT_ONLY
    owner: str | None = None

    @field_validator("scope")
    @classmethod
    def _known_dimensions(cls, v: dict[str, str]) -> dict[str, str]:
        unknown = set(v) - SCOPE_DIMENSIONS
        if unknown:
            raise ValueError(
                f"unknown scope dimension(s) {sorted(unknown)}; "
                f"valid: {', '.join(sorted(SCOPE_DIMENSIONS))}"
            )
        return v

    @field_validator("thresholds")
    @classmethod
    def _fractions(cls, v: list[Decimal]) -> list[Decimal]:
        for threshold in v:
            if not (Decimal(0) < threshold <= Decimal(2)):
                raise ValueError(
                    f"threshold {threshold} must be a fraction like 0.8, not a percent"
                )
        return sorted(v)

    def to_budget(self) -> Budget:
        return Budget(
            id=self.id,
            name=self.name,
            amount=self.amount,
            scope=self.scope,
            currency=self.currency,
            period=self.period,
            thresholds=tuple(self.thresholds),
            enforcement=self.enforcement,
            owner=self.owner,
        )


class SlackConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    webhook_url_env: str = "PRAHARI_SLACK_WEBHOOK"
    # Off by default, matching SMTP. Defaulting to on meant `missing_env()` demanded
    # a webhook from every install that never asked for Slack, which trains people
    # to ignore the startup warning - the opposite of what it is for.
    enabled: bool = False

    @property
    def webhook_url(self) -> str | None:
        return os.environ.get(self.webhook_url_env) or None


class SmtpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    host: str = "localhost"
    port: int = 587
    use_tls: bool = True
    username_env: str = "PRAHARI_SMTP_USER"
    password_env: str = "PRAHARI_SMTP_PASSWORD"
    from_address: str = "prahari@localhost"
    to_addresses: list[str] = Field(default_factory=list)

    @property
    def username(self) -> str | None:
        return os.environ.get(self.username_env) or None

    @property
    def password(self) -> str | None:
        return os.environ.get(self.password_env) or None


class AlertConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_severity: str = "warning"
    console: bool = True
    slack: SlackConfig = Field(default_factory=SlackConfig)
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)

    @field_validator("min_severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in {"info", "warning", "critical"}:
            raise ValueError("min_severity must be one of: info, warning, critical")
        return v


class DetectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    premium_model_providers: list[str] = Field(default_factory=lambda: ["anthropic", "openai"])
    """Which providers to pull premium model lists from for MODEL_ESCALATION."""


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store: StoreConfig = Field(default_factory=StoreConfig)
    collectors: list[CollectorConfig] = Field(default_factory=list)
    budgets: list[BudgetConfig] = Field(default_factory=list)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    display_currency: str = "INR"
    fx_rates: list[FxRate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> Config:
        for label, ids in (
            ("budget id", [b.id for b in self.budgets]),
            ("collector", [c.name for c in self.collectors]),
        ):
            duplicates = {i for i in ids if ids.count(i) > 1}
            if duplicates:
                raise ValueError(f"duplicate {label}(s): {sorted(duplicates)}")
        for provider in (Provider.OPENAI, Provider.ANTHROPIC):
            if sum(c.enabled and c.provider is provider for c in self.collectors) > 1:
                raise ValueError(
                    f"only one enabled {provider.value} collector is supported per process; "
                    "the admin credential is shared"
                )
        return self

    @property
    def enabled_collectors(self) -> list[CollectorConfig]:
        return [c for c in self.collectors if c.enabled]

    def to_budgets(self) -> list[Budget]:
        return [b.to_budget() for b in self.budgets]

    def fx_table(self) -> FxTable:
        return FxTable(self.fx_rates)

    def missing_env(self) -> list[str]:
        """Environment variables the config references but which are not set.

        Reported at startup so a misconfiguration surfaces immediately rather than as
        a silent no-op overnight.
        """
        required: list[str] = []
        for collector in self.enabled_collectors:
            required.extend(_REQUIRED_ENV.get(collector.provider, ()))
        if self.alerts.slack.enabled:
            required.append(self.alerts.slack.webhook_url_env)
        if self.alerts.smtp.enabled:
            required.extend([self.alerts.smtp.username_env, self.alerts.smtp.password_env])

        return sorted({name for name in required if not os.environ.get(name)})


_REQUIRED_ENV: dict[Provider, tuple[str, ...]] = {
    Provider.ANTHROPIC: ("ANTHROPIC_ADMIN_KEY",),
    Provider.OPENAI: ("OPENAI_ADMIN_KEY",),
}
# GCP ADC can resolve workload identity without a credential-file environment variable.


def load(path: str | Path) -> Config:
    """Load and validate. Raises with a readable message on any problem."""
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"config not found: {file}")

    raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a YAML mapping, got {type(raw).__name__}")

    config = Config.model_validate(raw)
    if store_path := os.environ.get("PRAHARI_DUCKDB_PATH"):
        config.store.path = store_path
    return config
