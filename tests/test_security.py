"""Security regression tests.

Each of these pins a specific vulnerability found in review. They are grouped by the
finding rather than by module, so that if one ever fails it is obvious what got
reintroduced and why it mattered.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from prahari.connectors.base import ProviderHTTPError, raise_for_status_safely
from prahari.connectors.gcp import _validate_identifier
from prahari.core.models import Provider, UsageRecord
from prahari.core.money import MAX_REASONABLE, MoneyError, parse_money

NOW = datetime(2026, 6, 1, tzinfo=UTC)


# --- S1: SQL injection via BigQuery table identifier --------------------------


class TestIdentifierValidation:
    """BigQuery table names cannot be bound parameters, so they are interpolated
    into SQL. In the multi-tenant control plane that identifier arrives from
    per-tenant config, making it an injection sink."""

    @pytest.mark.parametrize(
        "payload",
        [
            "t`; DROP TABLE users--",
            "x`) UNION SELECT * FROM `secrets",
            "table name with spaces",
            "tab\nnewline",
            "'; DELETE FROM t; --",
            "a`b",
            "../../etc/passwd",
            "",
            "t" * 2000,
        ],
    )
    def test_rejects_injection_payloads(self, payload):
        with pytest.raises(ValueError, match="not a valid BigQuery identifier"):
            _validate_identifier(payload, "billing_table")

    @pytest.mark.parametrize(
        "value", ["gcp_billing_export_v1_01ABCD", "my-project-123", "dataset_1", "A-b_9"]
    )
    def test_accepts_legitimate_identifiers(self, value):
        assert _validate_identifier(value, "field") == value

    def test_dotted_value_rejected_unless_domain_scoped(self):
        """A dot would let a caller redirect the query to a different dataset."""
        with pytest.raises(ValueError):
            _validate_identifier("proj.other_dataset", "billing_table")

    def test_legacy_domain_scoped_project_allowed_only_where_expected(self):
        assert _validate_identifier("example.com:proj", "p", allow_domain=True)
        with pytest.raises(ValueError):
            _validate_identifier("example.com:proj", "billing_dataset")


# --- S2: non-finite money -----------------------------------------------------


class TestMoneyValidation:
    """`Decimal("Infinity") > Decimal(any_limit)` is True, so an infinite cost from a
    malformed upstream response marks every budget exceeded - and under HARD_STOP
    that drives credential revocation against production. NaN is quieter: it survives
    every sum() and raises far from the record that caused it."""

    @pytest.mark.parametrize("bad", ["Infinity", "-Infinity", "NaN", "sNaN"])
    def test_parse_money_rejects_non_finite(self, bad):
        with pytest.raises(MoneyError, match="non-finite"):
            parse_money(bad, field="cost")

    def test_parse_money_rejects_float_infinity(self):
        with pytest.raises(MoneyError, match="non-finite"):
            parse_money(float("inf"), field="cost")

    def test_parse_money_rejects_implausible_magnitude(self):
        with pytest.raises(MoneyError, match="implausible"):
            parse_money(MAX_REASONABLE * 10, field="cost")

    def test_parse_money_rejects_garbage_rather_than_defaulting_to_zero(self):
        """Silently defaulting a malformed cost to zero understates the bill - the
        failure mode a customer notices last and forgives least."""
        with pytest.raises(MoneyError, match="not a number"):
            parse_money("twelve rupees", field="cost")

    def test_missing_value_uses_default_only_when_given(self):
        assert parse_money(None, field="c", default=Decimal(0)) == Decimal(0)
        with pytest.raises(MoneyError, match="missing"):
            parse_money(None, field="c")

    def test_avoids_binary_float_error(self):
        assert parse_money(0.1, field="c") == Decimal("0.1")

    @pytest.mark.parametrize("bad", ["Infinity", "-Infinity", "NaN"])
    def test_model_boundary_rejects_non_finite_cost(self, bad):
        """Defence in depth: every record passes through this one choke point."""
        with pytest.raises(ValueError, match="finite"):
            UsageRecord(
                provider=Provider.OPENAI,
                account_id="a",
                billed_cost=Decimal(bad),
                period_start=NOW,
                period_end=NOW,
                ingested_at=NOW,
                source="t",
            )

    def test_model_boundary_rejects_non_finite_list_cost(self):
        with pytest.raises(ValueError, match="finite"):
            UsageRecord(
                provider=Provider.OPENAI,
                account_id="a",
                billed_cost=Decimal(1),
                list_cost=Decimal("Infinity"),
                period_start=NOW,
                period_end=NOW,
                ingested_at=NOW,
                source="t",
            )


# --- S3: pricing registry must fail closed ------------------------------------


class TestRegistryFailsClosed:
    def test_refuses_to_load_without_a_checksum(self, monkeypatch):
        """An attacker who can write the vendor directory would otherwise only need
        to delete the .sha256 to swap the price data - which drives every cost figure
        and every enforcement decision."""
        import prahari.pricing.registry as registry

        monkeypatch.setattr(registry, "CHECKSUM_PATH", Path("definitely-absent.sha256"))
        registry._load_raw.cache_clear()
        try:
            with pytest.raises(registry.RegistryError, match="checksum missing"):
                registry._load_raw()
        finally:
            registry._load_raw.cache_clear()

    def test_refuses_to_load_on_checksum_mismatch(self, monkeypatch, tmp_path):
        import prahari.pricing.registry as registry

        bad = tmp_path / "wrong.sha256"
        bad.write_text("0" * 64 + "  model_prices.json\n", encoding="utf-8")
        monkeypatch.setattr(registry, "CHECKSUM_PATH", bad)
        registry._load_raw.cache_clear()
        try:
            with pytest.raises(registry.RegistryError, match="checksum mismatch"):
                registry._load_raw()
        finally:
            registry._load_raw.cache_clear()


# --- S4: credentials must not ride out inside exceptions ----------------------


class TestErrorsCarryNoCredentials:
    """`httpx.HTTPStatusError` keeps a reference to the request, and the request's
    headers hold the admin key. Anything that serialises the exception - an error
    tracker, a log line with exc_info, a traceback with locals - exfiltrates the
    credential to a third party."""

    SECRET = "sk-ant-admin-DO-NOT-LEAK"

    def _response(self, status: int, text: str = "nope") -> httpx.Response:
        request = httpx.Request(
            "GET",
            "https://api.anthropic.com/v1/organizations/usage_report/messages",
            headers={"x-api-key": self.SECRET, "authorization": f"Bearer {self.SECRET}"},
        )
        return httpx.Response(status, request=request, text=text)

    def test_sanitized_error_does_not_contain_the_key(self):
        with pytest.raises(ProviderHTTPError) as caught:
            raise_for_status_safely(self._response(401), "/v1/x")

        exc = caught.value
        blob = " ".join([repr(exc), str(exc), repr(exc.__dict__), repr(exc.args)])
        assert self.SECRET not in blob

    def test_provider_body_cannot_echo_credentials_or_customer_content(self):
        content = "private customer prompt"
        with pytest.raises(ProviderHTTPError) as caught:
            raise_for_status_safely(self._response(400, f"{self.SECRET}: {content}"), "/v1/x")
        blob = repr(caught.value) + repr(caught.value.__dict__) + repr(caught.value.args)
        assert self.SECRET not in blob
        assert content not in blob

    def test_sanitized_error_drops_the_request_object(self):
        with pytest.raises(ProviderHTTPError) as caught:
            raise_for_status_safely(self._response(500), "/v1/x")

        assert not hasattr(caught.value, "request")
        assert not hasattr(caught.value, "response")

    def test_chained_context_is_suppressed(self):
        """`raise ... from None` - otherwise __cause__ could reattach the original."""
        with pytest.raises(ProviderHTTPError) as caught:
            raise_for_status_safely(self._response(403), "/v1/x")
        assert caught.value.__cause__ is None

    def test_status_code_survives_for_callers(self):
        """verify_credentials needs to distinguish 401 from 500."""
        with pytest.raises(ProviderHTTPError) as caught:
            raise_for_status_safely(self._response(403), "/v1/x")
        assert caught.value.status_code == 403

    def test_success_passes_through(self):
        request = httpx.Request("GET", "https://example.com/x")
        raise_for_status_safely(httpx.Response(200, request=request), "/x")


# --- S5: detector state must stay bounded -------------------------------------


class TestBoundedDetectorState:
    def test_seasonal_history_does_not_grow_without_limit(self):
        """Previously one entry per observation forever - 9,600 after a 400-day
        replay, with `expected_spend` averaging an ever-longer list. A long-running
        collector would leak memory and slow down as it went."""
        from datetime import timedelta

        from prahari.detect.rules import (
            BASELINE_WINDOW_HOURS,
            SEASONAL_SAMPLES_PER_SLOT,
            Baseline,
            Observation,
        )

        baseline = Baseline(detection_key=("p", "k"))
        start = datetime(2026, 1, 1, tzinfo=UTC)
        for hour in range(24 * 400):
            baseline.observe(
                Observation(
                    detection_key=("p", "k"),
                    hour=start + timedelta(hours=hour),
                    spend=Decimal("1"),
                    tokens=0,
                    requests=0,
                )
            )

        assert len(baseline.hourly_spend) == BASELINE_WINDOW_HOURS
        total = sum(len(v) for v in baseline.hour_of_week_spend.values())
        assert total <= 168 * SEASONAL_SAMPLES_PER_SLOT
