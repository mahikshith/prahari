"""Model price registry.

Sourced from LiteLLM's `model_prices_and_context_window.json` (MIT) — the de-facto
community registry for 400+ models. Maintaining our own would be a permanent tax:
provider pricing moves weekly.

SECURITY — read before changing anything here.
    The LiteLLM *PyPI package* suffered a confirmed supply-chain attack in March 2026,
    shipping backdoored builds with a credential-stealing payload. This product handles
    AI admin credentials, which is precisely that payload's target.

    Therefore we vendor the JSON data file only, pinned to a commit SHA and verified by
    checksum. `litellm` must never appear in our dependency tree. Refresh via
    `scripts/fetch_pricing_registry.py` and review the diff like any other code change.

Billed cost from a provider always wins. This registry serves two narrower jobs:
estimation where a provider reports tokens but not cost, and forward projection in
alerts. Estimated records are flagged `Completeness.ESTIMATED` and never merge
silently into a billed total (docs/REQUIREMENTS.md F2.2).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from prahari.core.models import TokenCounts

VENDORED_PATH = Path(__file__).parent / "vendor" / "model_prices.json"
CHECKSUM_PATH = Path(__file__).parent / "vendor" / "model_prices.sha256"


class RegistryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Per-token prices, in USD. LiteLLM stores these as cost-per-token already."""

    model: str
    input_cost_per_token: Decimal
    output_cost_per_token: Decimal
    cache_read_cost_per_token: Decimal | None = None
    cache_write_cost_per_token: Decimal | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    provider: str | None = None

    def estimate(self, tokens: TokenCounts) -> Decimal:
        """Estimated USD cost. Falls back to the input rate for cache reads when the
        registry has no explicit cache pricing — an overestimate, which is the safe
        direction for an alert but wrong for a bill, hence the ESTIMATED flag."""
        cache_read_rate = self.cache_read_cost_per_token or self.input_cost_per_token
        cache_write_rate = self.cache_write_cost_per_token or self.input_cost_per_token

        return (
            self.input_cost_per_token * tokens.input_tokens
            + self.output_cost_per_token * (tokens.output_tokens + tokens.reasoning_tokens)
            + cache_read_rate * tokens.cache_read_tokens
            + cache_write_rate * tokens.cache_write_tokens
        )


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    # str() first: float→Decimal directly inherits binary float error, and these are
    # rates we multiply by millions of tokens.
    return Decimal(str(value))


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, dict]:
    if not VENDORED_PATH.exists():
        raise RegistryError(
            f"Price registry not vendored at {VENDORED_PATH}. "
            "Run: python scripts/fetch_pricing_registry.py"
        )

    raw_bytes = VENDORED_PATH.read_bytes()

    if CHECKSUM_PATH.exists():
        expected = CHECKSUM_PATH.read_text(encoding="utf-8").split()[0].strip()
        actual = hashlib.sha256(raw_bytes).hexdigest()
        if actual != expected:
            raise RegistryError(
                "Price registry checksum mismatch — refusing to load.\n"
                f"  expected {expected}\n  actual   {actual}\n"
                "Re-run scripts/fetch_pricing_registry.py and review the diff."
            )

    data = json.loads(raw_bytes)
    # LiteLLM ships a 'sample_spec' pseudo-entry documenting the schema.
    return {k: v for k, v in data.items() if k != "sample_spec" and isinstance(v, dict)}


@lru_cache(maxsize=2048)
def lookup(model: str, provider: str | None = None) -> ModelPrice | None:
    """Resolve a model name to prices.

    Providers name the same model differently across surfaces — `claude-opus-4` direct
    vs `anthropic.claude-opus-4-v1:0` on Bedrock vs a Vertex publisher path. We try
    exact, then provider-qualified, then a suffix match.
    """
    data = _load_raw()

    candidates = [model]
    if provider:
        candidates.append(f"{provider}/{model}")
    for name in candidates:
        if name in data:
            return _build(name, data[name])

    # Suffix match, longest first — prefers the most specific alias.
    tail = model.split("/")[-1].split(":")[0]
    matches = sorted(
        (k for k in data if k.split("/")[-1].split(":")[0] == tail), key=len, reverse=True
    )
    if matches:
        return _build(matches[0], data[matches[0]])

    return None


def _build(name: str, entry: dict) -> ModelPrice | None:
    input_cost = _dec(entry.get("input_cost_per_token"))
    output_cost = _dec(entry.get("output_cost_per_token"))
    if input_cost is None or output_cost is None:
        return None  # embedding/audio entries without token pricing

    return ModelPrice(
        model=name,
        input_cost_per_token=input_cost,
        output_cost_per_token=output_cost,
        cache_read_cost_per_token=_dec(entry.get("cache_read_input_token_cost")),
        cache_write_cost_per_token=_dec(entry.get("cache_creation_input_token_cost")),
        max_input_tokens=entry.get("max_input_tokens"),
        max_output_tokens=entry.get("max_output_tokens"),
        provider=entry.get("litellm_provider"),
    )


def premium_models(provider: str, top_n: int = 15) -> set[str]:
    """The most expensive models by output rate for one provider - input to the
    MODEL_ESCALATION rule. Attackers reselling stolen access optimise for output
    quality, not cost; they did not pay for it.

    `provider` is required deliberately. The registry contains re-hosted variants
    (wandb/, watsonx/, deepinfra/) whose per-token rates dwarf the frontier models,
    so an unfiltered "most expensive" list is dominated by models nobody in the
    customer's org has ever called - which would make the rule fire on nothing.
    """
    data = _load_raw()
    priced = [
        (name, _dec(e.get("output_cost_per_token")))
        for name, e in data.items()
        if e.get("output_cost_per_token") and e.get("litellm_provider") == provider
    ]
    priced.sort(key=lambda p: p[1] or Decimal(0), reverse=True)
    return {name for name, _ in priced[:top_n]}
