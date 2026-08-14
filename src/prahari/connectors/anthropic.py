"""Anthropic connector - Usage & Cost Admin API.

The fastest surface we have. Data lands within ~5 minutes and the API permits one
poll per minute, against competitors' daily granularity and cloud billing exports'
4-24h lag. That gap is the detection-latency claim, so this connector is the one that
proves the product thesis.

Two endpoints, deliberately used for different jobs:
  /v1/organizations/usage_report/messages  - token counts, ~5 min fresh. DETECTION.
  /v1/organizations/cost_report            - billed amounts, coarser. RECONCILIATION.

Usage arrives sooner than cost, so detection runs on tokens priced from the registry
(flagged ESTIMATED) while the billing truth catches up. Never mix the two into one
total - see docs/REQUIREMENTS.md F2.2.

Requires an Admin API key (`sk-ant-admin...`), not a normal API key. Only org admins
can provision one, and they are unavailable on individual accounts - which is itself
a first-call qualifying question.

NOT YET EXERCISED against the live API - see ASSUMPTIONS.md A8.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from prahari.connectors.base import Connector, FetchResult, ProviderConfig
from prahari.core.models import (
    ChargeCategory,
    Completeness,
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)
from prahari.pricing.registry import lookup

BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"

USAGE_PATH = "/v1/organizations/usage_report/messages"
COST_PATH = "/v1/organizations/cost_report"

MAX_PAGES = 500
"""Hard stop. A pagination bug that loops forever against a metered API is an
expensive way to learn about a pagination bug."""


class AnthropicConnector(Connector):
    provider = Provider.ANTHROPIC

    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self._client = client

    # --- plumbing -------------------------------------------------------------

    def _admin_key(self) -> str:
        key = os.environ.get("ANTHROPIC_ADMIN_KEY", "")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_ADMIN_KEY is not set. This must be an Admin API key "
                "(sk-ant-admin...), not a normal API key."
            )
        return key

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._admin_key(),
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    async def _paginate(self, path: str, params: dict[str, Any]) -> AsyncIterator[dict]:
        """Walk `next_page` cursors, yielding each time bucket.

        Credentials are attached per-request and never stored on the instance, so a
        connector object can be logged or serialised without leaking anything.
        """
        client = self._client or httpx.AsyncClient(base_url=BASE_URL, timeout=60)
        owns_client = self._client is None

        try:
            page: str | None = None
            for _ in range(MAX_PAGES):
                query = dict(params)
                if page:
                    query["page"] = page

                resp = await client.get(path, params=query, headers=self._headers())
                resp.raise_for_status()
                body = resp.json()

                for bucket in body.get("data", []):
                    yield bucket

                if not body.get("has_more"):
                    return
                page = body.get("next_page")
                if not page:
                    return
            raise RuntimeError(f"Pagination exceeded {MAX_PAGES} pages for {path}")
        finally:
            if owns_client:
                await client.aclose()

    # --- fetch ----------------------------------------------------------------

    async def fetch(self, start: datetime, end: datetime) -> FetchResult:
        """Hourly usage for [start, end), priced from the registry.

        Hourly buckets rather than daily: daily granularity cannot catch an attack
        that burns six figures in a day, which is the entire reason this product
        exists.
        """
        _require_utc(start, end)

        params = {
            "starting_at": _iso(start),
            "ending_at": _iso(end),
            "bucket_width": "1h",
            "group_by[]": ["api_key_id", "model", "workspace_id", "service_tier"],
            "limit": 1000,
        }

        records: list[UsageRecord] = []
        warnings: list[str] = []
        now = datetime.now(UTC)

        async for bucket in self._paginate(USAGE_PATH, params):
            bucket_start = _parse(bucket["starting_at"])
            bucket_end = _parse(bucket["ending_at"])

            # Anthropic's own docs note data lands within ~5 minutes. A bucket younger
            # than that is still filling; flag it rather than asserting a total.
            settled = (now - bucket_end) > timedelta(minutes=10)

            for result in bucket.get("results", []):
                record = self._to_record(result, bucket_start, bucket_end, settled, now)
                if record is not None:
                    records.append(record)
                else:
                    warnings.append(
                        f"unpriced model {result.get('model')!r} at {bucket_start:%Y-%m-%d %H:%M}"
                    )

        return FetchResult(
            records=records,
            window_start=start,
            window_end=end,
            is_complete=not warnings and end < now - timedelta(minutes=10),
            warnings=warnings or None,
        )

    def _to_record(
        self,
        result: dict,
        bucket_start: datetime,
        bucket_end: datetime,
        settled: bool,
        now: datetime,
    ) -> UsageRecord | None:
        model = result.get("model")

        tokens = TokenCounts(
            input_tokens=int(result.get("uncached_input_tokens", 0) or 0),
            output_tokens=int(result.get("output_tokens", 0) or 0),
            cache_read_tokens=int(result.get("cache_read_input_tokens", 0) or 0),
            cache_write_tokens=_cache_creation_total(result),
            requests=int(result.get("num_requests", 0) or 0),
        )

        price = lookup(model, provider="anthropic") if model else None
        if price is None:
            return None

        # Components stay separate. Collapsing them early is where naive tools produce
        # wrong totals, and wrong totals fail the <=2% reconciliation gate.
        costs = CostComponents(
            input_cost=price.input_cost_per_token * tokens.input_tokens,
            output_cost=price.output_cost_per_token * tokens.output_tokens,
            cache_read_cost=(price.cache_read_cost_per_token or price.input_cost_per_token)
            * tokens.cache_read_tokens,
            cache_write_cost=(price.cache_write_cost_per_token or price.input_cost_per_token)
            * tokens.cache_write_tokens,
        )

        return UsageRecord(
            provider=Provider.ANTHROPIC,
            account_id=self.config.account_id,
            api_key_id=result.get("api_key_id"),
            workspace_id=result.get("workspace_id"),
            model=model,
            service_tier=result.get("service_tier"),
            charge_category=ChargeCategory.USAGE,
            tokens=tokens,
            costs=costs,
            # Estimated from the registry: the usage endpoint reports tokens, not
            # money. cost_report() supplies billed truth on a slower cadence.
            billed_cost=costs.total,
            currency="USD",
            period_start=bucket_start,
            period_end=bucket_end,
            ingested_at=now,
            source=f"anthropic:{USAGE_PATH}",
            completeness=Completeness.ESTIMATED if settled else Completeness.PARTIAL,
            extensions={"priced_from": "registry", "settled": settled},
        )

    # --- reconciliation -------------------------------------------------------

    async def cost_report(self, start: datetime, end: datetime) -> dict[str, Decimal]:
        """Billed amounts by day - the authority for invoice reconciliation (F4).

        Kept separate from `fetch` on purpose: this is what we compare our estimates
        against, and a tool that quietly reconciles itself against itself proves
        nothing.
        """
        _require_utc(start, end)

        params = {
            "starting_at": _iso(start),
            "ending_at": _iso(end),
            "bucket_width": "1d",
            "limit": 1000,
        }

        totals: dict[str, Decimal] = {}
        async for bucket in self._paginate(COST_PATH, params):
            day = _parse(bucket["starting_at"]).date().isoformat()
            for result in bucket.get("results", []):
                amount = Decimal(str(result.get("amount", "0")))
                totals[day] = totals.get(day, Decimal(0)) + amount
        return totals

    async def verify_credentials(self) -> bool:
        """Cheapest possible authenticated read.

        Called during onboarding so a customer learns about a missing scope in the
        first minute rather than after a silent overnight backfill.
        """
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=1)
        try:
            async for _ in self._paginate(
                USAGE_PATH,
                {
                    "starting_at": _iso(start),
                    "ending_at": _iso(end),
                    "bucket_width": "1h",
                    "limit": 1,
                },
            ):
                break
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                return False
            raise


def _cache_creation_total(result: dict) -> int:
    """Cache-creation tokens are reported either flat or split by TTL depending on
    endpoint version. Handle both rather than silently reading zero."""
    if (flat := result.get("cache_creation_input_tokens")) is not None:
        return int(flat or 0)
    nested = result.get("cache_creation") or {}
    return sum(int(v or 0) for v in nested.values()) if isinstance(nested, dict) else 0


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _require_utc(*values: datetime) -> None:
    for v in values:
        if v.tzinfo is None:
            raise ValueError("fetch window must be timezone-aware UTC")
