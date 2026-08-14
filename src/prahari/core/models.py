"""Core data model.

`UsageRecord` is the contract between connectors and everything downstream. Provider
quirks are resolved in the connector; core never sees them.

Aligned to FOCUS 1.3 (ratified 2025-12-05) where a FOCUS column exists — see
docs/ARCHITECTURE.md. Using the standard's vocabulary means a FinOps-literate buyer
recognises our schema on sight, which is a sales asset as much as an engineering one.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GCP_VERTEX = "gcp_vertex"
    AWS_BEDROCK = "aws_bedrock"
    AZURE_OPENAI = "azure_openai"
    GITHUB_COPILOT = "github_copilot"
    M365_COPILOT = "m365_copilot"
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"


class ChargeCategory(StrEnum):
    """FOCUS ChargeCategory."""

    USAGE = "Usage"
    PURCHASE = "Purchase"  # seat licences
    TAX = "Tax"
    CREDIT = "Credit"
    ADJUSTMENT = "Adjustment"


class AllocationMethod(StrEnum):
    """How a record was mapped to a cost centre. Ordered by precedence — see
    `core.allocate`. Recorded per-record so customers can audit our attribution
    rather than take it on faith."""

    EXPLICIT_KEY_MAP = "explicit_key_map"
    RESOURCE_TAG = "resource_tag"
    PROJECT = "project"
    WORKSPACE = "workspace"
    USER_IDENTITY = "user_identity"
    UNALLOCATED = "unallocated"


class Completeness(StrEnum):
    """Whether the source window is settled. Load-bearing: our sub-hour detection
    claim depends on knowing this, and asserting a number from an incomplete window
    is how we would permanently lose a finance buyer."""

    FINAL = "final"  # provider considers this billed and settled
    PARTIAL = "partial"  # window still accumulating
    ESTIMATED = "estimated"  # we derived cost from the price registry


class TokenCounts(BaseModel):
    """Kept separate rather than summed. Cache and batch tiers price differently, and
    collapsing them early is where naive tools produce wrong totals."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    requests: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.reasoning_tokens
        )


class CostComponents(BaseModel):
    """Cost broken out by driver. Never pre-summed — presentation sums, storage does not.

    All amounts are `Decimal`. Float arithmetic on currency is a correctness bug waiting
    for an invoice comparison, and invoice comparison is our credibility gate (F4.2).
    """

    model_config = ConfigDict(frozen=True)

    input_cost: Decimal = Decimal(0)
    output_cost: Decimal = Decimal(0)
    cache_read_cost: Decimal = Decimal(0)
    cache_write_cost: Decimal = Decimal(0)
    seat_cost: Decimal = Decimal(0)
    batch_discount: Decimal = Decimal(0)  # negative
    tier_adjustment: Decimal = Decimal(0)
    other: Decimal = Decimal(0)

    @property
    def total(self) -> Decimal:
        return (
            self.input_cost
            + self.output_cost
            + self.cache_read_cost
            + self.cache_write_cost
            + self.seat_cost
            + self.batch_discount
            + self.tier_adjustment
            + self.other
        )


class UsageRecord(BaseModel):
    """One normalised unit of AI consumption.

    Grain is (provider, api_key_id | user_id, model, period). Connectors must emit at
    the finest grain the provider exposes — we can always roll up, never down, and the
    detection engine needs per-key resolution to work at all.
    """

    model_config = ConfigDict(frozen=True)

    # --- identity: who/what incurred this ---
    provider: Provider
    account_id: str = Field(description="Provider org/account/subscription id")
    api_key_id: str | None = Field(
        default=None,
        description="Key identifier, never the secret. Primary detection dimension.",
    )
    user_id: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None

    # --- what was consumed ---
    model: str | None = None
    operation: str | None = None
    region: str | None = None
    service_tier: str | None = None
    charge_category: ChargeCategory = ChargeCategory.USAGE

    tokens: TokenCounts = Field(default_factory=TokenCounts)
    seats: int = 0

    # --- money ---
    costs: CostComponents = Field(default_factory=CostComponents)
    billed_cost: Decimal = Field(
        description="Provider-reported billed amount. Authoritative when present."
    )
    list_cost: Decimal | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fx_rate_date: date | None = Field(
        default=None,
        description="Date of the FX rate used for INR presentation. Stored, not applied.",
    )

    # --- when (UTC always; IST only at presentation) ---
    period_start: datetime
    period_end: datetime
    ingested_at: datetime

    # --- allocation ---
    cost_centre: str | None = None
    parent_entity: str | None = Field(
        default=None,
        description="GCC↔HQ dual allocation for transfer-pricing documentation.",
    )
    allocation_method: AllocationMethod = AllocationMethod.UNALLOCATED

    # --- provenance ---
    source: str = Field(description="Which connector and endpoint produced this")
    completeness: Completeness = Completeness.FINAL
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator("period_start", "period_end", "ingested_at")
    @classmethod
    def _require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware and stored in UTC")
        return v

    @model_validator(mode="after")
    def _check_period(self) -> UsageRecord:
        if self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        return self

    @property
    def is_allocated(self) -> bool:
        return self.allocation_method is not AllocationMethod.UNALLOCATED

    @property
    def is_estimated(self) -> bool:
        return self.completeness is Completeness.ESTIMATED

    @property
    def detection_key(self) -> tuple[str, str]:
        """Baseline grouping key for `detect`: **(provider, credential)**.

        Deliberately excludes model and region. A spend baseline belongs to the
        *credential*, not the credential-model pair — partitioning by model would hand
        an attacker a fresh, empty baseline the moment they switched models, which is
        precisely the escalation we exist to catch. Model and region are observation
        attributes consumed by MODEL_ESCALATION and NEW_GEO instead.

        Falls back to user then account when the provider exposes no key id — coarser,
        but never silently absent.
        """
        return (self.provider.value, self.api_key_id or self.user_id or self.account_id)
