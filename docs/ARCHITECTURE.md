# Architecture

## Deployment shape (this is the product's security story)

```
┌─ CUSTOMER VPC ────────────────────────────────┐      ┌─ PRAHARI CLOUD ──────────┐
│                                               │      │                          │
│  ┌─────────────┐   admin keys never leave     │      │   Control plane          │
│  │  Collector  │   this boundary              │      │   - alert routing        │
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

**Why this shape.** We ask customers for admin API keys. A breach of a centralised store would expose every customer's AI credentials to exactly the LLMjacking market we're defending against — we'd be the highest-value target in the category. Keeping credentials inside the customer boundary removes that risk class entirely, and simultaneously delivers the DPDP/RBI data-residency argument that is our structural advantage over Torii and Flexera.

It also collapses the hardest enterprise objection ("you want our root billing credentials?") into "you run our container."

## Pipeline

```
fetch → validate → normalise → price → allocate → store → detect → alert → (enforce)
```

Each stage is independently testable. Provider weirdness is confined to `fetch`; everything downstream sees clean records.

### 1. `fetch` — `connectors/`
One module per provider, each exposing:

```python
def fetch(start: datetime, end: datetime, cfg: ProviderConfig) -> Iterator[RawRecord]
```

Idempotent, re-runnable for any range. Rate-limit and retry handling lives here. Anthropic permits 1 poll/min — poll at that cadence for detection, and reconcile daily for billing truth.

### 2. `normalise` — `core/`
Raw payload → **FOCUS 1.3-aligned `UsageRecord`**. Where a FOCUS column exists, use its name. Provider-specific extras go in a typed `extensions` field, never as loose top-level keys.

Cost components stay **separate**, not summed early: `input`, `output`, `cache_read`, `cache_write`, `batch_discount`, `tier_adjustment`. This is where naive tools produce wrong totals, and wrong totals fail F4.2.

### 3. `price` — `pricing/`
Provider-reported billed cost wins whenever available. The vendored LiteLLM registry is used for (a) estimation where a provider reports tokens but not cost, and (b) forward projection in alerts. **Estimated records carry an `is_estimated` flag and never merge silently into a billed total.**

### 4. `allocate` — `core/`
Resolve each record to a cost centre via a precedence chain:

```
explicit key→team mapping  >  cloud resource tag  >  project/workspace  >  user identity  >  UNALLOCATED
```

`UNALLOCATED` is a real bucket, surfaced prominently. Hiding it is how existing tools mislead. Supports dual assignment (local cost centre + parent entity) for GCC↔HQ transfer-pricing.

### 5. `store` — `store/`
- **DuckDB** — local analytics, the ₹6cr backtest, reconciliation runs. Embedded, zero-ops.
- **Postgres** — app state, config, allocation rules, audit log.

Interface is a thin adapter so the backtest and the product share query code.

### 6. `detect` — `detect/`
Rolling baselines keyed by `(api_key, identity, model, region)`. **EWMA + z-score against an STL-deseasonalised series** — engineering usage has a hard weekday pattern, and a naive threshold alerts every Monday.

Five named rules (F5.2). Each returns a structured verdict:

```python
Alert(rule, key_id, baseline, observed, multiple,
      spend_so_far_inr, projected_24h_inr, evidence)
```

No black-box models in the alert path. A CFO must be able to read why it fired — that is a product requirement, not a preference.

### 7. `enforce` — deferred to v1
Budget hard-stops and key revocation via provider admin APIs. Always: opt-in, dry-run first, confirmed, audit-logged with actor and reason. Nobody grants write scope before seeing a clean dry-run.

## Data model (core)

```python
UsageRecord:
    # identity
    provider, account_id, api_key_id, user_id, project_id
    # what
    model, operation, region, service_tier
    # quantity
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, requests
    # money  (Decimal, never float)
    billed_cost, list_cost, currency, fx_rate_date, is_estimated
    # when  (UTC, TIMESTAMPTZ)
    period_start, period_end, ingested_at
    # allocation
    cost_centre, parent_entity, allocation_method, is_allocated
    # provenance
    source, is_partial, completeness_flag
    extensions: dict
```

`is_partial` / `completeness_flag` map to FOCUS 1.3's data-recency fields. They matter: our detection-latency claim depends on knowing whether a window is complete, and asserting a number from an incomplete window is how we'd lose a finance buyer permanently.

## Design rules

1. **Provider quirks never leak past `fetch`.** If core needs a provider `if`, the connector is wrong.
2. **Never sum cost components early.** Keep them separate until presentation.
3. **`Decimal` for money, always.** Float arithmetic on currency is a correctness bug waiting for an invoice comparison.
4. **Everything backfillable.** Onboarding opens with "show me last quarter."
5. **Fail loud on schema drift.** dlt's schema evolution tells us when a provider changed shape — surface it rather than absorbing it silently.
6. **Backtest and product share the query layer.** The demo must run the same code as the product, or it isn't a demo.
