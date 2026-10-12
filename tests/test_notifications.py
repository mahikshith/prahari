"""Notification fan-out, durable retry selection and authenticated SMTP."""

import ssl
from unittest.mock import patch

import pytest

from prahari.core.config import AlertConfig
from prahari.detect.rules import Severity
from prahari.notify.router import Message, Router, SmtpChannel

MESSAGE = Message("Spend spike", "Investigate service account sa-1", Severity.CRITICAL)


class RecordingChannel:
    def __init__(self, name, result=True):
        self.name = name
        self.result = result
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_success_does_not_short_circuit_other_channels():
    channels = [RecordingChannel(name) for name in ("console", "slack", "smtp")]
    router = Router(channels)

    assert router.deliver(MESSAGE) == {"console": True, "slack": True, "smtp": True}
    assert all(channel.sent == [MESSAGE] for channel in channels)
    assert router.channel_names == ("console", "slack", "smtp")
    assert router.required_channels == ("slack", "smtp")


def test_console_success_does_not_acknowledge_remote_failure():
    console, slack = RecordingChannel("console"), RecordingChannel("slack", False)
    assert Router([console, slack]).send(MESSAGE) is False
    assert console.sent == slack.sent == [MESSAGE]
    assert Router([RecordingChannel("console")]).send(MESSAGE) is True


def test_partial_remote_success_preserves_compatibility():
    slack, smtp = RecordingChannel("slack"), RecordingChannel("smtp", False)
    assert Router([slack, smtp]).send(MESSAGE) is True
    assert slack.sent == smtp.sent == [MESSAGE]


def test_retry_attempts_only_requested_pending_channel():
    console, slack, smtp = [RecordingChannel(name) for name in ("console", "slack", "smtp")]
    router = Router([console, slack, smtp])

    assert router.deliver(MESSAGE, channels={"smtp"}) == {"smtp": True}
    assert not console.sent and not slack.sent
    assert smtp.sent == [MESSAGE]
    assert router.deliver(MESSAGE, channels=set()) == {}


def test_channel_exception_is_isolated_without_logging_secrets(capsys):
    failed = RecordingChannel("slack", RuntimeError("webhook-secret"))
    working = RecordingChannel("smtp")
    assert Router([failed, working]).deliver(MESSAGE) == {"slack": False, "smtp": True}
    captured = capsys.readouterr()
    assert "webhook-secret" not in captured.out + captured.err


def test_delivery_preserves_severity_floor():
    channel = RecordingChannel("slack")
    router = Router([channel], min_severity=Severity.CRITICAL)
    assert router.deliver(Message("t", "b", Severity.WARNING)) == {}
    assert not channel.sent


def test_configured_console_does_not_suppress_slack(monkeypatch):
    monkeypatch.setenv("PRAHARI_SLACK_WEBHOOK", "https://hooks.slack.com/services/test")
    config = AlertConfig.model_validate({"slack": {"enabled": True}})
    with (
        patch("prahari.notify.router.ConsoleChannel.send", return_value=True) as console,
        patch("prahari.notify.router.SlackChannel.send", return_value=False) as slack,
    ):
        assert Router.from_config(config).send(MESSAGE) is False
        console.assert_called_once()
        slack.assert_called_once()


def test_missing_slack_credentials_do_not_turn_into_console_only_success(monkeypatch):
    monkeypatch.delenv("PRAHARI_SLACK_WEBHOOK", raising=False)
    config = AlertConfig.model_validate({"slack": {"enabled": True}})
    with (
        patch("prahari.notify.router.ConsoleChannel.send", return_value=True),
        patch("prahari.notify.router.urllib.request.urlopen") as urlopen,
    ):
        router = Router.from_config(config)
        assert router.required_channels == ("slack",)
        assert router.send(MESSAGE) is False
        urlopen.assert_not_called()


def smtp_channel(**kwargs):
    return SmtpChannel(
        "smtp.example.com",
        587,
        "prahari@example.com",
        ["security@example.com"],
        username="user",
        password="password",
        **kwargs,
    )


def test_smtp_verifies_ca_and_hostname_before_credentials():
    with patch("prahari.notify.router.smtplib.SMTP") as factory:
        smtp = factory.return_value.__enter__.return_value
        assert smtp_channel().send(MESSAGE) is True
        context = smtp.starttls.call_args.kwargs["context"]
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
        smtp.login.assert_called_once_with("user", "password")
        smtp.send_message.assert_called_once()


def test_smtp_certificate_failure_never_logs_in_or_sends():
    with patch("prahari.notify.router.smtplib.SMTP") as factory:
        smtp = factory.return_value.__enter__.return_value
        smtp.starttls.side_effect = ssl.SSLCertVerificationError("untrusted relay")
        assert smtp_channel().send(MESSAGE) is False
        smtp.login.assert_not_called()
        smtp.send_message.assert_not_called()


@pytest.mark.parametrize("title", ["line\nbreak", "line\r\nbreak"])
def test_malformed_header_fails_without_opening_smtp(title):
    with patch("prahari.notify.router.smtplib.SMTP") as factory:
        assert smtp_channel().send(Message(title, "body", Severity.CRITICAL)) is False
        factory.assert_not_called()
