"""OpenAI connector - Organization Usage & Costs API.

Same two-endpoint split as Anthropic, for the same reason: usage reports tokens at
hourly resolution (detection), costs reports money at daily resolution only
(reconciliation). Never merge them into one total.

Two shape differences from Anthropic worth knowing before debugging anything here:
  - times are **unix epoch seconds**, not ISO-8601
  - `/organization/costs` supports **only** `bucket_width=1d`

That daily-only cost endpoint is precisely why detection cannot run on billed
amounts. It is also, conveniently, why every competitor reporting from billing data
is structurally 24h late.

Requires an org admin key with `api.usage.read` and `api.costs.read`.

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

BASE_URL = "https://api.openai.com"
USAGE_PATH = "/v1/organization/usage/completions"
COSTS_PATH = "/v1/organization/costs"

MAX_PAGES = 500


class OpenAIConnector(Connector):
    provider = Provider.OPENAI

    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self._client = client

    def _headers(self) -> dict[str, str]:
        key = os.environ.get("OPENAI_ADMIN_KEY", "")
        if not key:
            raise RuntimeError(
                "OPENAI_ADMIN_KEY is not set. Needs an organization admin key with "
                "api.usage.read and api.costs.read."
            )
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async def _paginate(self, path: str, params: dict[str, Any]) -> AsyncIterator[dict]:
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

    async def fetch(self, start: datetime, end: datetime) -> FetchResult:
        _require_utc(start, end)

        params = {
            "start_time": _epoch(start),
            "end_time": _epoch(end),
            "bucket_width": "1h",
            "group_by[]": ["api_key_id", "model", "project_id", "user_id"],
            "limit": 180,  # API caps 1h buckets per page
        }

        records: list[UsageRecord] = []
        warnings: list[str] = []
        now = datetime.now(UTC)

        async for bucket in self._paginate(USAGE_PATH, params):
            bucket_start = _from_epoch(bucket["start_time"])
            bucket_end = _from_epoch(bucket["end_time"])
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

        cached = int(result.get("input_cached_tokens", 0) or 0)
        total_input = int(result.get("input_tokens", 0) or 0)

        # OpenAI's `input_tokens` is inclusive of cached tokens. Subtracting matters:
        # cached reads are priced at a fraction of fresh input, so double-counting
        # them here would overstate cost by exactly the discount we exist to track.
        uncached_input = max(0, total_input - cached)

        tokens = TokenCounts(
            input_tokens=uncached_input,
            output_tokens=int(result.get("output_tokens", 0) or 0),
            cache_read_tokens=cached,
            requests=int(result.get("num_model_requests", 0) or 0),
        )

        price = lookup(model, provider="openai") if model else None
        if price is None:
            return None

        costs = CostComponents(
            input_cost=price.input_cost_per_token * tokens.input_tokens,
            output_cost=price.output_cost_per_token * tokens.output_tokens,
            cache_read_cost=(price.cache_read_cost_per_token or price.input_cost_per_token)
            * tokens.cache_read_tokens,
        )

        return UsageRecord(
            provider=Provider.OPENAI,
            account_id=self.config.account_id,
            api_key_id=result.get("api_key_id"),
            user_id=result.get("user_id"),
            project_id=result.get("project_id"),
            model=model,
            charge_category=ChargeCategory.USAGE,
            tokens=tokens,
            costs=costs,
            billed_cost=costs.total,
            currency="USD",
            period_start=bucket_start,
            period_end=bucket_end,
            ingested_at=now,
            source=f"openai:{USAGE_PATH}",
            completeness=Completeness.ESTIMATED if settled else Completeness.PARTIAL,
            extensions={
                "priced_from": "registry",
                "batch": result.get("batch"),
                "settled": settled,
            },
        )

    async def cost_report(self, start: datetime, end: datetime) -> dict[str, Decimal]:
        """Billed amounts by day. Daily granularity is the API's only option here -
        which is exactly why detection runs on the usage endpoint instead."""
        _require_utc(start, end)

        params = {
            "start_time": _epoch(start),
            "end_time": _epoch(end),
            "bucket_width": "1d",
            "limit": 180,
        }

        totals: dict[str, Decimal] = {}
        async for bucket in self._paginate(COSTS_PATH, params):
            day = _from_epoch(bucket["start_time"]).date().isoformat()
            for result in bucket.get("results", []):
                amount = result.get("amount") or {}
                value = Decimal(str(amount.get("value", "0")))
                totals[day] = totals.get(day, Decimal(0)) + value
        return totals

    async def verify_credentials(self) -> bool:
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=1)
        try:
            async for _ in self._paginate(
                USAGE_PATH,
                {
                    "start_time": _epoch(start),
                    "end_time": _epoch(end),
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


def _epoch(dt: datetime) -> int:
    return int(dt.astimezone(UTC).timestamp())


def _from_epoch(value: int | float) -> datetime:
    return datetime.fromtimestamp(int(value), tz=UTC)


def _require_utc(*values: datetime) -> None:
    for v in values:
        if v.tzinfo is None:
            raise ValueError("fetch window must be timezone-aware UTC")
