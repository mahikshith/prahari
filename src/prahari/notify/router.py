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
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from prahari.core.budget import BudgetState
from prahari.core.config import AlertConfig
from prahari.core.fx import format_inr
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

        request = urllib.request.Request(
            self._url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
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

        email = EmailMessage()
        email["Subject"] = f"[Prahari] {message.title}"
        email["From"] = self._from
        email["To"] = ", ".join(self._to)
        email.set_content(message.body)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._username and self._password:
                    smtp.login(self._username, self._password)
                smtp.send_message(email)
            return True
        except (smtplib.SMTPException, OSError):
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
        if config.slack.enabled and (url := config.slack.webhook_url):
            channels.append(SlackChannel(url))
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

    def send(self, message: Message) -> bool:
        """True if at least one channel accepted it.

        Partial success counts: if Slack is down but email worked, the alert reached
        a human, which is the only thing that matters.
        """
        if _SEVERITY_ORDER[message.severity] < _SEVERITY_ORDER[self.min_severity]:
            return False
        return any(channel.send(message) for channel in self.channels)

    def send_alert(self, alert: Alert) -> bool:
        provider, credential = alert.detection_key
        return self.send(
            Message(
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
        )

    def send_budget(self, state: BudgetState, crossed: list) -> bool:
        thresholds = ", ".join(f"{t:.0%}" for t in crossed) or "-"
        severity = Severity.CRITICAL if state.pct_used >= 1 else Severity.WARNING
        return self.send(
            Message(
                title=f"Budget {state.status}: {state.budget.name}",
                body="\n".join(
                    [
                        state.explain(),
                        f"scope:      {state.budget.describe_scope}",
                        f"crossed:    {thresholds}",
                        f"remaining:  {format_inr(state.remaining)}",
                        f"owner:      {state.budget.owner or 'unassigned'}",
                    ]
                ),
                severity=severity,
            )
        )
