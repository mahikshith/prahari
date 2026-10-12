# Architecture

**Consistency review: 2026-10-12.** This design catalog includes deferred targets, not a shipped-feature inventory. Current scope and outcomes are in [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](../PROGRESS.md): GCP + OpenAI, hybrid collection, customer-owned India cloud first, and live-source/response acceptance still required.

## Deployment shape

The diagram below is the earlier proposed SaaS/control-plane shape, not the current deployment. The foundation is a local customer-held Python/DuckDB collector. An optional reused gateway is selected for later routed telemetry/admission; India SaaS, PostgreSQL and multi-tenancy remain deferred.

```
┌─ CUSTOMER VPC ────────────────────────────────┐      ┌─ PRAHARI CLOUD ──────────┐
│                                               │      │                          │
│  ┌─────────────┐   customer-held keys        │      │   Control plane          │
│  │  Collector  │   used for provider auth    │      │   - alert routing        │
│  │  (Docker)   │                              │      │   - dashboards           │
│  └──────┬──────┘                              │      │   - policy config        │
│         │ pulls (read-only)                   │      │   - audit log            │
│    ┌────┴────┬─────────┬──────────┐           │      │                          │
│  Anthropic  OpenAI   GCP/BQ   Azure/AWS       │      │   Stores ONLY:           │
│    Admin    Costs    export     FOCUS         │      │   aggregated cost/usage  │
│         │                                     │      │   records + metadata     │
│         ▼                                     │      │                          │
│   normalise → allocate → detect               │──────▶   No credentials.        │
│         │                                     │ aggs │   No prompts.            │
│         ▼                                     │ only │   No completions.        │
│   local DuckDB / Postgres                     │      │                          │
└───────────────────────────────────────────────┘      └──────────────────────────┘
```

**Why this shape.** We ask customers for admin API keys. A breach of a centralised store would expose every customer's AI credentials to exactly the LLMjacking market we're defending against — we'd be the highest-value target in the category. Customer-held credentials reduce centralized exposure but do not eliminate runtime compromise or prove compliance. Review provider transfers, logs, backups, notifications and support paths, plus applicable law/contracts, separately.

It also collapses the hardest enterprise objection ("you want our root billing credentials?") into "you run our container."

## Pipeline

```
fetch → validate → normalise → price → allocate → store → detect → alert → (enforce)
```

Each stage is independently testable. Provider weirdness is confined to `fetch`; everything downstream sees clean records.

### 1. `fetch` — `connectors/`
One module per provider, each exposing:

```python
async def fetch(self, start: datetime, end: datetime) -> FetchResult
```

The current connector returns normalized records and window/completeness evidence. Re-fetching supported ranges is idempotent; provider rate limits, retained history and source delays must be verified. Billing reconciliation is a separate settled-period check.

### 2. `normalise` — `core/`
Raw payload → **FOCUS 1.3-aligned `UsageRecord`**. Where a FOCUS column exists, use its name. Provider-specific extras go in a typed `extensions` field, never as loose top-level keys.

Cost components stay **separate**, not summed early: `input`, `output`, `cache_read`, `cache_write`, `batch_discount`, `tier_adjustment`. This is where naive tools produce wrong totals, and wrong totals fail F4.2.

### 3. `price` — `pricing/`
Provider-reported billed cost wins whenever available. The vendored LiteLLM registry is used for (a) estimation where a provider reports tokens but not cost, and (b) forward projection in alerts. **Cost basis distinguishes provider-reported, estimated and unpriced records. Unknown cost stays null; a known subtotal is not a complete billed total.**

### 4. `allocate` — `core/`
Resolve each record to a cost centre via a precedence chain:

```
explicit key→team mapping  >  cloud resource tag  >  project/workspace  >  user identity  >  UNALLOCATED
```

`UNALLOCATED` is a real bucket, surfaced prominently. Hiding it is how existing tools mislead. Supports dual assignment (local cost centre + parent entity) for GCC↔HQ transfer-pricing.

### 5. `store` — `store/`
- **DuckDB** — local analytics, the ₹6cr backtest, reconciliation runs. Embedded, zero-ops.
- **Postgres (deferred)** — consider for multi-tenant/concurrent app state or a selected gateway requirement.

Interface is a thin adapter so the backtest and the product share query code.

### 6. `detect` — `detect/`
Bounded rolling/seasonal baselines are keyed per credential or supported source fallback. Model changes must not create a fresh baseline. Persisted last activity before the replay window supports dormancy across restarts; STL is not claimed as current detector behavior.

Named anomaly rules and a cost-coverage warning return a structured verdict. The following is a conceptual sketch; current types in src/prahari/detect/rules.py are authoritative:

```python
Alert(rule, key_id, baseline, observed, multiple,
      spend_so_far_inr, projected_24h_inr, evidence)
```

No black-box models in the alert path. A CFO must be able to read why it fired — that is a product requirement, not a preference.

### 7. `enforce` — deferred to v1
Planned gateway admission for routed calls and supported provider response adapters. Current policy evaluation is dry-run; no live blocking/revocation is enabled. Validate concurrency, in-flight spend, bypass, authorization, audit and actual response effect in a sandbox first.

## Data model sketch

The sketch is conceptual, not a certified FOCUS schema. Current UsageRecord fields/types in src/prahari/core/models.py are authoritative.

```python
UsageRecord:
    # identity
    provider, account_id, api_key_id, user_id, project_id
    # what
    model, operation, region, service_tier
    # quantity
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, requests
    # money  (Decimal, never float)
    billed_cost: Decimal | None, cost_basis, list_cost, currency, fx_rate_date
    # when  (UTC, TIMESTAMPTZ)
    period_start, period_end, ingested_at
    # allocation
    cost_centre, parent_entity, allocation_method, is_allocated
    # provenance
    source, completeness
    extensions: dict
```

Completeness records source-window uncertainty; cost basis separately records whether money is known/estimated. GCP billing remains provisional and its scan cursor is not a settled watermark. Neither prototype field establishes FOCUS conformance or a detection SLA.

## Design rules

1. **Provider quirks never leak past `fetch`.** If core needs a provider `if`, the connector is wrong.
2. **Never sum cost components early.** Keep them separate until presentation.
3. **`Decimal` for money, always.** Float arithmetic on currency is a correctness bug waiting for an invoice comparison.
4. **Everything backfillable.** Onboarding opens with "show me last quarter."
5. **Validate provider shapes at the boundary.** Current connectors fetch manually; an installed ingestion library is not proof that its schema-evolution mechanism is used.
6. **Backtest and product share the query layer.** The demo must run the same code as the product, or it isn't a demo.

## Notification and network evidence

Persist retries/acknowledgements per channel; console output does not acknowledge configured remote delivery. At-least-once delivery can duplicate after a crash between remote acceptance and local persistence. Network observations remain separate from money; [NETWORK_TELEMETRY.md](NETWORK_TELEMETRY.md) defines metadata, sampling and external-key-bypass limits.
