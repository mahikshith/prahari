"""Alert delivery.

An alert nobody receives is not detection. The engine has been computing perfectly
good alerts and printing them to a terminal nobody was watching.

Delivery is deliberately dumb: the message body already exists. `Alert.explain()` and
`BudgetState.explain()` were written to be read by a CFO, so the notifier formats
rather than composes.

Deduplication lives in the store, not here. `Store.record_alert()` returns False for
an alert already seen, and the router only sends on True. That means a restart, a
re-evaluation, or two overlapping collection cycles cannot produce a duplicate page -
and an alerting system that repeats itself gets muted, which is operationally the
same as having none.
"""

from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from prahari.core.budget import BudgetState
from prahari.core.config import AlertConfig
from prahari.core.fx import format_money
from prahari.detect.rules import Alert, Severity

_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}

_EMOJI = {Severity.INFO: "•", Severity.WARNING: "▲", Severity.CRITICAL: "■"}


@dataclass(frozen=True, slots=True)
class Message:
    title: str
    body: str
    severity: Severity

    def as_text(self) -> str:
        return f"{_EMOJI[self.severity]} {self.title}\n{self.body}"


class Channel(Protocol):
    name: str

    def send(self, message: Message) -> bool:
        """Return True on success. Must never raise - a broken notifier must not take
        down the collector, and undelivered alerts stay queued in the store."""


class ConsoleChannel:
    name = "console"

    def send(self, message: Message) -> bool:
        print(f"\n{message.as_text()}\n", flush=True)
        return True


class SlackChannel:
    """Incoming webhook. Uses urllib rather than adding an HTTP client to the
    collector's dependency surface for one POST."""

    name = "slack"

    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        self._url = webhook_url
        self._timeout = timeout

    def send(self, message: Message) -> bool:
        payload = json.dumps(
            {
                "text": f"{_EMOJI[message.severity]} *{message.title}*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{_EMOJI[message.severity]} *{message.title}*\n"
                            f"```{message.body}```",
                        },
                    }
                ],
            }
        ).encode()

        try:
            request = urllib.request.Request(
                self._url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, OSError, ValueError):
            # Deliberately swallowed: the alert stays unnotified in the store and is
            # retried next cycle. Never log the exception body - a webhook URL is a
            # bearer credential and appears in URLError messages.
            return False


class SmtpChannel:
    name = "smtp"

    def __init__(
        self,
        host: str,
        port: int,
        from_address: str,
        to_addresses: list[str],
        *,
        use_tls: bool = True,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._host, self._port = host, port
        self._from, self._to = from_address, to_addresses
        self._use_tls, self._username, self._password = use_tls, username, password
        self._timeout = timeout

    def send(self, message: Message) -> bool:
        if not self._to:
            return False

        try:
            email = EmailMessage()
            email["Subject"] = f"[Prahari] {message.title}"
            email["From"] = self._from
            email["To"] = ", ".join(self._to)
            email.set_content(message.body)

            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                if self._username and self._password:
                    smtp.login(self._username, self._password)
                smtp.send_message(email)
            return True
        except (smtplib.SMTPException, OSError, ValueError):
            return False


class Router:
    """Fans a message out to every configured channel above the severity floor."""

    def __init__(self, channels: list[Channel], min_severity: Severity = Severity.WARNING) -> None:
        self.channels = channels
        self.min_severity = min_severity

    @classmethod
    def from_config(cls, config: AlertConfig) -> Router:
        channels: list[Channel] = []
        if config.console:
            channels.append(ConsoleChannel())
        if config.slack.enabled:
            channels.append(SlackChannel(config.slack.webhook_url or ""))
        if config.smtp.enabled:
            channels.append(
                SmtpChannel(
                    host=config.smtp.host,
                    port=config.smtp.port,
                    from_address=config.smtp.from_address,
                    to_addresses=config.smtp.to_addresses,
                    use_tls=config.smtp.use_tls,
                    username=config.smtp.username,
                    password=config.smtp.password,
                )
            )
        return cls(channels, Severity(config.min_severity))

    @property
    def channel_names(self) -> tuple[str, ...]:
        return tuple(channel.name for channel in self.channels)

    @property
    def required_channels(self) -> tuple[str, ...]:
        return tuple(name for name in self.channel_names if name != "console") or self.channel_names

    def deliver(self, message: Message, channels: set[str] | None = None) -> dict[str, bool]:
        """Attempt selected channels and report each result for durable retries."""
        if _SEVERITY_ORDER[message.severity] < _SEVERITY_ORDER[self.min_severity]:
            return {}
        results: dict[str, bool] = {}
        for channel in self.channels:
            if channels is not None and channel.name not in channels:
                continue
            try:
                results[channel.name] = channel.send(message)
            except Exception:
                # Exception text can contain webhook or SMTP credentials.
                results[channel.name] = False
        return results

    def send(self, message: Message) -> bool:
        """Compatibility result: any external success, or console-only success."""
        results = self.deliver(message)
        return any(results.get(name, False) for name in self.required_channels)

    def alert_message(self, alert: Alert) -> Message:
        provider, credential = alert.detection_key
        return Message(
            title=f"{alert.rule} on {credential}",
            body="\n".join(
                [
                    alert.explain(),
                    f"provider: {provider}",
                    f"time:     {alert.at:%Y-%m-%d %H:%M} UTC",
                    f"evidence: {json.dumps(alert.evidence, default=str)}",
                ]
            ),
            severity=alert.severity,
        )

    def budget_message(self, state: BudgetState, crossed: list) -> Message:
        thresholds = ", ".join(f"{t:.0%}" for t in crossed) or "-"
        severity = Severity.CRITICAL if state.pct_used >= 1 else Severity.WARNING
        return Message(
            title=f"Budget {state.status}: {state.budget.name}",
            body="\n".join(
                [
                    state.explain(),
                    f"scope:      {state.budget.describe_scope}",
                    f"crossed:    {thresholds}",
                    f"remaining:  {format_money(state.remaining, state.budget.currency)}",
                    f"owner:      {state.budget.owner or 'unassigned'}",
                ]
            ),
            severity=severity,
        )

    def send_alert(self, alert: Alert) -> bool:
        return self.send(self.alert_message(alert))

    def send_budget(self, state: BudgetState, crossed: list) -> bool:
        return self.send(self.budget_message(state, crossed))
