"""Connector contract.

One module per provider. All provider weirdness — pagination, rate limits, retries,
naming, unit quirks — is resolved here. If `core` ever needs a provider-specific
branch, the connector is wrong (docs/ARCHITECTURE.md, design rule 1).

Every connector must be:
  - **idempotent** — re-running the same window produces the same records
  - **backfillable** — any date range, because onboarding opens with "show me last quarter"
  - **honest about gaps** — partial windows are flagged, never silently gap-filled
  - **credential-clean** — secrets from env only; never logged, persisted, or in a repr
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from prahari.core.models import Provider, UsageRecord


class ProviderHTTPError(RuntimeError):
    """A provider HTTP failure, stripped of anything sensitive.

    `httpx.HTTPStatusError` keeps a reference to the originating request, and that
    request's headers hold the admin API key. Anything that serialises the exception
    - an error tracker, a log line with `exc_info`, a traceback rendered with locals -
    exfiltrates the credential to a third party.

    Connectors therefore convert HTTP failures into this type at the boundary. It
    carries the status code (callers need it to distinguish 401 from 500) and the
    request path, and nothing else.
    """

    def __init__(self, status_code: int, path: str) -> None:
        self.status_code = status_code
        self.path = path
        super().__init__(f"provider returned {status_code} for {path}")


def raise_for_status_safely(response: httpx.Response, path: str) -> None:
    """`raise_for_status`, without dragging credentials into the traceback."""
    if response.is_success:
        return

    # Provider error bodies can echo credentials or customer content.
    raise ProviderHTTPError(response.status_code, path) from None


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Connector configuration.

    Note there is no credential field. Connectors read secrets from the environment at
    call time so that a config object can be logged, serialised, or included in an
    error report without leaking anything.
    """

    provider: Provider
    account_id: str
    poll_interval: timedelta = timedelta(minutes=5)
    max_lookback: timedelta = timedelta(days=90)
    extra: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Outcome of one fetch window, including what we could not get.

    `is_complete=False` propagates to `Completeness.PARTIAL` on the records. This
    matters more than it looks: our sub-hour detection claim depends on knowing
    whether a window has settled, and asserting a confident number from an
    incomplete window is how we would permanently lose a finance buyer.
    """

    records: list[UsageRecord]
    window_start: datetime
    window_end: datetime
    is_complete: bool = True
    warnings: list[str] | None = None


class Connector(ABC):
    """Base class for all provider connectors."""

    provider: Provider

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    async def fetch(self, start: datetime, end: datetime) -> FetchResult:
        """Pull usage for [start, end). Both must be timezone-aware UTC.

        Implementations must tolerate being called for a window already fetched, and
        for a window that does not exist yet (return empty, not an error).
        """

    @abstractmethod
    async def verify_credentials(self) -> bool:
        """Cheap read-only call confirming credentials work and carry the needed scope.

        Called during onboarding so a customer learns about a missing permission in
        the first minute rather than after a silent overnight backfill.
        """

    async def stream(self, start: datetime, end: datetime) -> AsyncIterator[UsageRecord]:
        """Convenience iterator over a fetch window."""
        result = await self.fetch(start, end)
        for record in result.records:
            yield record

    def reconciliation_period(self, at: datetime) -> tuple[datetime, datetime]:
        """The billing period containing `at`, for invoice reconciliation (F4).

        Calendar month by default; override where a provider bills otherwise.
        """
        start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=32)).replace(day=1)
        return start, end
