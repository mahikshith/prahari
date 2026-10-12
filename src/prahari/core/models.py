"""Core data model.

`UsageRecord` is the contract between connectors and everything downstream. Provider
quirks are resolved in the connector; core never sees them.

Aligned to FOCUS 1.3 (ratified 2025-12-05) where a FOCUS column exists — see
docs/ARCHITECTURE.md. Using the standard's vocabulary means a FinOps-literate buyer
recognises our schema on sight, which is a sales asset as much as an engineering one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prahari.core.money import is_safe_money


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
    """Source-window completeness, separate from cost provenance.

    Connector age heuristics do not establish a provider delivery/completeness SLA.
    """

    FINAL = "final"  # provider considers this billed and settled
    PARTIAL = "partial"  # window still accumulating
    ESTIMATED = "estimated"  # we derived cost from the price registry


class CostBasis(StrEnum):
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNPRICED = "unpriced"


class TokenCounts(BaseModel):
    """Kept separate rather than summed. Cache and batch tiers price differently, and
    collapsing them early is where naive tools produce wrong totals."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    requests: int = Field(default=0, ge=0)

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

    @field_validator("*")
    @classmethod
    def _finite_components(cls, v: Decimal) -> Decimal:
        if not is_safe_money(v):
            raise ValueError("cost components must be finite and plausible")
        return v

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
    billed_cost: Decimal | None = Field(
        description="Amount in currency; cost_basis identifies estimates and unavailable prices."
    )
    cost_basis: CostBasis = CostBasis.PROVIDER_REPORTED
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
        return v.astimezone(UTC)

    @field_validator("billed_cost", "list_cost")
    @classmethod
    def _require_finite_money(cls, v: Decimal | None) -> Decimal | None:
        """Reject NaN and Infinity at the single choke point every record passes.

        `Decimal("Infinity") > Decimal(any_budget)` is True, so an infinite cost from
        a malformed upstream response would mark every budget exceeded and, under
        a future action executor, drive incorrect credential revocation. NaN is quieter:
        it survives every `sum()` in the aggregation path and then raises far from
        the record that caused it. See core/money.py.
        """
        if v is not None and not is_safe_money(v):
            raise ValueError(f"cost must be finite and plausible, got {v}")
        return v

    @model_validator(mode="after")
    def _check_period(self) -> UsageRecord:
        if self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        return self

    @model_validator(mode="after")
    def _check_cost_basis(self) -> UsageRecord:
        if self.billed_cost is None:
            object.__setattr__(self, "cost_basis", CostBasis.UNPRICED)
        elif self.cost_basis is CostBasis.UNPRICED:
            raise ValueError("unpriced usage must have billed_cost=None")
        elif self.completeness is Completeness.ESTIMATED:
            object.__setattr__(self, "cost_basis", CostBasis.ESTIMATED)
        return self

    @property
    def is_allocated(self) -> bool:
        return self.allocation_method is not AllocationMethod.UNALLOCATED

    @property
    def is_estimated(self) -> bool:
        return self.cost_basis is CostBasis.ESTIMATED

    @property
    def detection_key(self) -> tuple[str, str]:
        """Baseline grouping key for `detect`: **(provider, credential)**.

        Deliberately excludes model and region. A spend baseline belongs to the
        *credential*, not the credential-model pair — partitioning by model would hand
        an attacker a fresh, empty baseline the moment they switched models, which is
        precisely the escalation we exist to catch. Model and region are observation
        attributes consumed by MODEL_ESCALATION and NEW_GEO instead.

        Falls back through decreasing specificity when a provider exposes no key id.
        `project_id` is in that chain deliberately: GCP's billing export carries no
        caller identity at all, so the project is the finest grain available there.
        Skipping it would collapse every project in an organisation into one baseline,
        and a single noisy project would then mask an attack in a quiet one.
        """
        return (
            self.provider.value,
            self.api_key_id or self.user_id or self.project_id or self.account_id,
        )
