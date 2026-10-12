"""Connector tests against mocked provider responses.

These validate our handling of the **documented** API shapes. They are design
validation, not proof of correctness - real billing APIs routinely differ from their
docs in pagination and edge cases, and neither connector has met a live endpoint yet
(ASSUMPTIONS.md A8). Expect a round of fixes on first real call.

What they do lock in is the stuff that silently corrupts a bill: cached-token
double-counting, cache-creation shape drift, partial-window flagging, and pagination
that never terminates.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx

from prahari.connectors.anthropic import AnthropicConnector
from prahari.connectors.base import ProviderConfig
from prahari.connectors.openai import OpenAIConnector
from prahari.core.models import Completeness, CostBasis, Provider
from prahari.core.money import MoneyError

# Old enough that every window is settled, so tests don't depend on wall-clock.
SETTLED_START = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
SETTLED_END = SETTLED_START + timedelta(hours=2)


@pytest.fixture(autouse=True)
def _admin_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "sk-ant-admin-test")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "sk-admin-test")


def anthropic_bucket(start: datetime, results: list[dict]) -> dict:
    return {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
    }


def openai_bucket(start: datetime, results: list[dict]) -> dict:
    return {
        "start_time": int(start.timestamp()),
        "end_time": int((start + timedelta(hours=1)).timestamp()),
        "results": results,
    }


# --- Anthropic ----------------------------------------------------------------


class TestAnthropicConnector:
    @respx.mock
    @pytest.mark.asyncio
    async def test_maps_tokens_and_prices_from_registry(self):
        respx.get("https://api.anthropic.com/v1/organizations/usage_report/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        anthropic_bucket(
                            SETTLED_START,
                            [
                                {
                                    "model": "claude-sonnet-4-5-20250929",
                                    "api_key_id": "apikey_01",
                                    "workspace_id": "wrkspc_01",
                                    "service_tier": "standard",
                                    "uncached_input_tokens": 1_000_000,
                                    "output_tokens": 200_000,
                                    "cache_read_input_tokens": 500_000,
                                    "cache_creation_input_tokens": 100_000,
                                    "num_requests": 42,
                                }
                            ],
                        )
                    ],
                    "has_more": False,
                },
            )
        )

        conn = AnthropicConnector(
            ProviderConfig(provider=Provider.ANTHROPIC, account_id="org_test")
        )
        result = await conn.fetch(SETTLED_START, SETTLED_END)

        assert len(result.records) == 1
        rec = result.records[0]
        assert rec.api_key_id == "apikey_01"
        assert rec.tokens.input_tokens == 1_000_000
        assert rec.tokens.cache_write_tokens == 100_000
        assert rec.tokens.requests == 42
        # Sonnet 4.5 is $3/M input.
        assert rec.costs.input_cost == pytest.approx(3.0, rel=1e-6)
        assert rec.billed_cost > 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_split_cache_creation_shape(self):
        """Cache-creation is reported flat or nested by TTL depending on endpoint
        version. Reading zero from the nested shape would silently undercount."""
        respx.get("https://api.anthropic.com/v1/organizations/usage_report/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        anthropic_bucket(
                            SETTLED_START,
                            [
                                {
                                    "model": "claude-sonnet-4-5-20250929",
                                    "api_key_id": "apikey_01",
                                    "uncached_input_tokens": 10,
                                    "output_tokens": 10,
                                    "cache_creation": {
                                        "ephemeral_5m_input_tokens": 30_000,
                                        "ephemeral_1h_input_tokens": 20_000,
                                    },
                                }
                            ],
                        )
                    ],
                    "has_more": False,
                },
            )
        )

        conn = AnthropicConnector(
            ProviderConfig(provider=Provider.ANTHROPIC, account_id="org_test")
        )
        result = await conn.fetch(SETTLED_START, SETTLED_END)
        assert result.records[0].tokens.cache_write_tokens == 50_000

    @respx.mock
    @pytest.mark.asyncio
    async def test_follows_pagination(self):
        route = respx.get(
            "https://api.anthropic.com/v1/organizations/usage_report/messages"
        )
        route.side_effect = [
            httpx.Response(
                200,
                json={
                    "data": [
                        anthropic_bucket(
                            SETTLED_START,
                            [
                                {
                                    "model": "claude-sonnet-4-5-20250929",
                                    "api_key_id": "k1",
                                    "uncached_input_tokens": 100,
                                    "output_tokens": 10,
                                }
                            ],
                        )
                    ],
                    "has_more": True,
                    "next_page": "page_2",
                },
            ),
            httpx.Response(
                200,
                json={
                    "data": [
                        anthropic_bucket(
                            SETTLED_START + timedelta(hours=1),
                            [
                                {
                                    "model": "claude-sonnet-4-5-20250929",
                                    "api_key_id": "k2",
                                    "uncached_input_tokens": 200,
                                    "output_tokens": 20,
                                }
                            ],
                        )
                    ],
                    "has_more": False,
                },
            ),
        ]

        conn = AnthropicConnector(
            ProviderConfig(provider=Provider.ANTHROPIC, account_id="org_test")
        )
        result = await conn.fetch(SETTLED_START, SETTLED_END)
        assert {r.api_key_id for r in result.records} == {"k1", "k2"}
        assert route.calls[0].request.url.params["limit"] == "168"
        assert route.calls[1].request.url.params["page"] == "page_2"

    @respx.mock
    @pytest.mark.asyncio
    async def test_cost_report_converts_fractional_cents_across_pages(self):
        route = respx.get("https://api.anthropic.com/v1/organizations/cost_report")
        route.side_effect = [
            httpx.Response(
                200,
                json={
                    "data": [anthropic_bucket(SETTLED_START, [
                        {"amount": "123.78912", "currency": "USD"},
                    ])],
                    "has_more": True,
                    "next_page": "cost_page_2",
                },
            ),
            httpx.Response(
                200,
                json={
                    "data": [anthropic_bucket(SETTLED_START, [
                        {"amount": "-23.78912", "currency": "USD"},
                    ])],
                    "has_more": False,
                },
            ),
        ]
        conn = AnthropicConnector(ProviderConfig(provider=Provider.ANTHROPIC, account_id="org"))
        totals = await conn.cost_report(SETTLED_START, SETTLED_START + timedelta(days=1))
        assert totals == {"2026-06-01": Decimal("1")}
        assert route.calls[0].request.url.params["limit"] == "31"
        assert route.calls[1].request.url.params["page"] == "cost_page_2"

    @respx.mock
    @pytest.mark.asyncio
    @pytest.mark.parametrize("amount", [None, "", "NaN", "Infinity", "invalid", "1e16"])
    async def test_cost_report_rejects_invalid_amounts(self, amount):
        respx.get("https://api.anthropic.com/v1/organizations/cost_report").mock(
            return_value=httpx.Response(200, json={
                "data": [anthropic_bucket(SETTLED_START, [{"amount": amount, "currency": "USD"}])],
                "has_more": False,
            })
        )
        conn = AnthropicConnector(ProviderConfig(provider=Provider.ANTHROPIC, account_id="org"))
        with pytest.raises(MoneyError):
            await conn.cost_report(SETTLED_START, SETTLED_END)

    @respx.mock
    @pytest.mark.asyncio
    @pytest.mark.parametrize("currency", [None, "INR"])
    async def test_cost_report_rejects_missing_or_unsupported_currency(self, currency):
        respx.get("https://api.anthropic.com/v1/organizations/cost_report").mock(
            return_value=httpx.Response(200, json={
                "data": [anthropic_bucket(SETTLED_START, [
                    {"amount": "100", "currency": currency},
                ])],
                "has_more": False,
            })
        )
        conn = AnthropicConnector(ProviderConfig(provider=Provider.ANTHROPIC, account_id="org"))
        with pytest.raises(ValueError, match="must use USD"):
            await conn.cost_report(SETTLED_START, SETTLED_END)

    @respx.mock
    @pytest.mark.asyncio
    async def test_preserves_unpriced_models_with_unknown_cost(self):
        respx.get("https://api.anthropic.com/v1/organizations/usage_report/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        anthropic_bucket(
                            SETTLED_START,
                            [
                                {
                                    "model": "claude-model-from-the-future",
                                    "api_key_id": "k1",
                                    "uncached_input_tokens": 100,
                                    "output_tokens": 10,
                                }
                            ],
                        )
                    ],
                    "has_more": False,
                },
            )
        )

        conn = AnthropicConnector(
            ProviderConfig(provider=Provider.ANTHROPIC, account_id="org_test")
        )
        result = await conn.fetch(SETTLED_START, SETTLED_END)

        rec = result.records[0]
        assert rec.api_key_id == "k1"
        assert rec.model == "claude-model-from-the-future"
        assert rec.tokens.total_tokens == 110
        assert rec.billed_cost is None
        assert rec.cost_basis is CostBasis.UNPRICED
        assert result.warnings and "claude-model-from-the-future" in result.warnings[0]
        assert result.is_complete is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_recent_window_is_marked_partial(self):
        """A bucket younger than the provider's ~5 min settling lag is still filling.
        Asserting a confident total from it is how we would lose a finance buyer."""
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        respx.get("https://api.anthropic.com/v1/organizations/usage_report/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        anthropic_bucket(
                            now,
                            [
                                {
                                    "model": "claude-sonnet-4-5-20250929",
                                    "api_key_id": "k1",
                                    "uncached_input_tokens": 100,
                                    "output_tokens": 10,
                                }
                            ],
                        )
                    ],
                    "has_more": False,
                },
            )
        )

        conn = AnthropicConnector(
            ProviderConfig(provider=Provider.ANTHROPIC, account_id="org_test")
        )
        result = await conn.fetch(now, now + timedelta(hours=1))
        assert result.records[0].completeness is Completeness.PARTIAL
        assert result.records[0].cost_basis is CostBasis.ESTIMATED
        assert result.records[0].is_estimated

    @respx.mock
    @pytest.mark.asyncio
    async def test_verify_credentials_false_on_401(self):
        respx.get("https://api.anthropic.com/v1/organizations/usage_report/messages").mock(
            return_value=httpx.Response(401, json={"error": "unauthorised"})
        )
        conn = AnthropicConnector(
            ProviderConfig(provider=Provider.ANTHROPIC, account_id="org_test")
        )
        assert await conn.verify_credentials() is False

    @pytest.mark.asyncio
    async def test_missing_key_raises_before_any_request(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)
        conn = AnthropicConnector(
            ProviderConfig(provider=Provider.ANTHROPIC, account_id="org_test")
        )
        with pytest.raises(RuntimeError, match="Admin API key"):
            await conn.fetch(SETTLED_START, SETTLED_END)


# --- OpenAI -------------------------------------------------------------------


class TestOpenAIConnector:
    @respx.mock
    @pytest.mark.asyncio
    async def test_preserves_unpriced_model_identity_and_usage(self):
        respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
            return_value=httpx.Response(200, json={
                "data": [openai_bucket(SETTLED_START, [{
                    "model": "unpriced-future-model", "api_key_id": "key_unknown",
                    "project_id": "project_unknown", "input_tokens": 100,
                    "output_tokens": 10, "num_model_requests": 3,
                }])],
                "has_more": False,
            })
        )
        conn = OpenAIConnector(ProviderConfig(provider=Provider.OPENAI, account_id="org"))
        result = await conn.fetch(SETTLED_START, SETTLED_END)
        rec = result.records[0]
        assert rec.api_key_id == "key_unknown"
        assert rec.project_id == "project_unknown"
        assert rec.tokens.total_tokens == 110
        assert rec.tokens.requests == 3
        assert rec.billed_cost is None
        assert rec.cost_basis is CostBasis.UNPRICED
        assert result.warnings and "unpriced-future-model" in result.warnings[0]

    @respx.mock
    @pytest.mark.asyncio
    async def test_subtracts_cached_tokens_from_input(self):
        """OpenAI's `input_tokens` is INCLUSIVE of cached tokens. Double-counting
        them overstates cost by exactly the cache discount we exist to surface."""
        respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        openai_bucket(
                            SETTLED_START,
                            [
                                {
                                    "model": "gpt-4o",
                                    "api_key_id": "key_abc",
                                    "project_id": "proj_1",
                                    "input_tokens": 1_000_000,
                                    "input_cached_tokens": 400_000,
                                    "output_tokens": 100_000,
                                    "num_model_requests": 7,
                                }
                            ],
                        )
                    ],
                    "has_more": False,
                },
            )
        )

        conn = OpenAIConnector(ProviderConfig(provider=Provider.OPENAI, account_id="org_test"))
        result = await conn.fetch(SETTLED_START, SETTLED_END)

        rec = result.records[0]
        assert rec.tokens.input_tokens == 600_000
        assert rec.tokens.cache_read_tokens == 400_000
        assert rec.tokens.total_tokens == 1_100_000

    @respx.mock
    @pytest.mark.asyncio
    async def test_uses_epoch_seconds_not_iso(self):
        route = respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
            return_value=httpx.Response(200, json={"data": [], "has_more": False})
        )
        conn = OpenAIConnector(ProviderConfig(provider=Provider.OPENAI, account_id="org_test"))
        await conn.fetch(SETTLED_START, SETTLED_END)

        params = route.calls[0].request.url.params
        assert params["start_time"] == str(int(SETTLED_START.timestamp()))
        assert params["bucket_width"] == "1h"

    @respx.mock
    @pytest.mark.asyncio
    async def test_cost_report_sums_by_day(self):
        respx.get("https://api.openai.com/v1/organization/costs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "start_time": int(SETTLED_START.timestamp()),
                            "end_time": int((SETTLED_START + timedelta(days=1)).timestamp()),
                            "results": [
                                {"amount": {"value": 120.50, "currency": "usd"}},
                                {"amount": {"value": 9.50, "currency": "usd"}},
                            ],
                        }
                    ],
                    "has_more": False,
                },
            )
        )

        conn = OpenAIConnector(ProviderConfig(provider=Provider.OPENAI, account_id="org_test"))
        totals = await conn.cost_report(SETTLED_START, SETTLED_START + timedelta(days=1))
        assert totals["2026-06-01"] == Decimal("130.0")

    @respx.mock
    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [None, "", "NaN", "Infinity", "invalid", "1e16"])
    async def test_cost_report_rejects_invalid_amounts(self, value):
        respx.get("https://api.openai.com/v1/organization/costs").mock(
            return_value=httpx.Response(200, json={
                "data": [openai_bucket(SETTLED_START, [
                    {"amount": {"value": value, "currency": "usd"}},
                ])],
                "has_more": False,
            })
        )
        conn = OpenAIConnector(ProviderConfig(provider=Provider.OPENAI, account_id="org"))
        with pytest.raises(MoneyError):
            await conn.cost_report(SETTLED_START, SETTLED_END)

    @respx.mock
    @pytest.mark.asyncio
    @pytest.mark.parametrize("currency", [None, "inr"])
    async def test_cost_report_rejects_missing_or_unsupported_currency(self, currency):
        respx.get("https://api.openai.com/v1/organization/costs").mock(
            return_value=httpx.Response(200, json={
                "data": [openai_bucket(SETTLED_START, [
                    {"amount": {"value": "1", "currency": currency}},
                ])],
                "has_more": False,
            })
        )
        conn = OpenAIConnector(ProviderConfig(provider=Provider.OPENAI, account_id="org"))
        with pytest.raises(ValueError, match="must use USD"):
            await conn.cost_report(SETTLED_START, SETTLED_END)


class TestWindowValidation:
    @pytest.mark.asyncio
    async def test_rejects_naive_datetimes(self):
        conn = OpenAIConnector(ProviderConfig(provider=Provider.OPENAI, account_id="org"))
        with pytest.raises(ValueError, match="timezone-aware"):
            await conn.fetch(datetime(2026, 6, 1), datetime(2026, 6, 2))


def test_env_keys_are_never_held_on_the_instance():
    """A connector object must be safe to log or serialise. Credentials are read at
    call time, never stored."""
    conn = AnthropicConnector(ProviderConfig(provider=Provider.ANTHROPIC, account_id="org"))
    blob = repr(conn.__dict__) + repr(conn.config)
    assert os.environ.get("ANTHROPIC_ADMIN_KEY", "sentinel") not in blob
