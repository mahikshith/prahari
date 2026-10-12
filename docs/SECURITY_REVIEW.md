# Security Review — 2026-08-15

**Consistency review: 2026-10-12.** This design catalog includes deferred targets, not a shipped-feature inventory. Current scope and outcomes are in [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](../PROGRESS.md): GCP + OpenAI, hybrid collection, customer-owned India cloud first, and live-source/response acceptance still required.

Historical 2026-08-15 review and synthetic benchmark notes, with material corrections below. Current targeted changes and regression evidence are tracked in DECISIONS.md/PROGRESS.md; this is not a current full-codebase assurance or certification.

This doubles as the answer to the security questionnaire an Indian bank or GCC will
send during procurement — the questions are always some version of "what does your
tool do with our credentials, and how do you know."

**Threat model.** Prahari holds read-only admin credentials for a customer's AI and
cloud providers. Future provider response requires separately authorized write permissions; no revocation adapter/live action is enabled. That makes it a higher-value
target than most of its customers: a compromise yields organisation-wide inference
credentials, which is exactly the commodity the LLMjacking market exists to trade.
Two consequences drive the architecture — the collector runs inside the customer's
environment to limit central credential exposure, and policy evaluation is dry-run. Provider calls, notification destinations and runtime compromise remain separate risks.

---

## Findings

### S1 · SQL injection via the BigQuery table identifier — **High**

`connectors/gcp.py` interpolated `project.dataset.table` directly into the query
string. BigQuery cannot bind a table name as a parameter, so interpolation is
unavoidable — but the value was unvalidated.

Today it comes from environment variables, which limits exposure. In the multi-tenant
control plane it will arrive from per-tenant configuration, at which point a tenant
could alter query semantics within the caller's granted permissions; cross-tenant impact depends on isolation and IAM:

```
GCP_BILLING_TABLE = "t`) UNION SELECT * FROM `other-tenant.billing.export"
```

**Fixed.** `_validate_identifier` allowlists `[A-Za-z0-9_-]` (plus the legacy
`domain.com:project` form, and only where a project is expected). That rejects
backticks, quotes, semicolons, whitespace and comment markers as a class, without
needing to reason about BigQuery's escaping rules.

### S2 · Non-finite costs drive false enforcement — **High**

`Decimal` accepts `NaN` and `Infinity`, and both were reaching us straight from
provider payloads (`Decimal(str(row["gross_cost"]))`). BigQuery `FLOAT64` can hold
either legitimately.

```python
Decimal("Infinity") > Decimal(any_budget_limit)   # True
Decimal("NaN")      > Decimal(any_budget_limit)   # raises InvalidOperation
sum([Decimal(1), Decimal("NaN")])                 # NaN, silently
```

An infinite cost can misclassify budget status. The current HARD_STOP policy result does not revoke credentials; a future action adapter would turn bad input into an availability risk. Reject the input before that path exists. `NaN` is quieter and
harder to debug: it survives every `sum()` in the aggregation path, then raises far
from the record that caused it.

**Fixed.** `core/money.py` parses provider amounts once, at the boundary, rejecting
non-finite values and implausible magnitudes. A `field_validator` on `UsageRecord`
enforces the same rule at the single choke point every record passes through.

### S3 · Price registry failed open when its checksum was missing — **Medium**

`pricing/registry.py` verified the vendored LiteLLM data *only if* the `.sha256` file
existed. An attacker able to write the vendor directory needed only to delete the
checksum to swap the pricing data — which drives every cost figure, every budget
evaluation, and therefore every enforcement decision.

Given that this file is vendored precisely *because* the upstream PyPI package shipped
a credential stealer in March 2026, failing open here defeated the point of vendoring.

**Fixed.** Missing checksum is now a hard error. Comparison uses
`hmac.compare_digest`.

### S4 · Admin keys leaked through HTTP exceptions — **Medium**

Both API connectors called `response.raise_for_status()`. The resulting
`httpx.HTTPStatusError` holds a reference to the originating request, and that
request's headers contain `x-api-key: sk-ant-admin-…` / `Authorization: Bearer …`.

A downstream error tracker can expose request headers when serializing exception attributes or stack-frame locals. Leak behavior depends on its capture/export configuration; ordinary exception sanitization is not a blanket guarantee.

**Fixed.** `raise_for_status_safely()` converts HTTP failures into `ProviderHTTPError`,
carrying only status and path; response bodies are excluded because they can echo secrets/customer content. Raised from None to suppress ordinary exception chaining. Stack-frame/heap/local capture can still expose live values and must be disabled or redacted independently.

### S5 · Report output was not gitignored — **Low**

`scripts/report.py --json` and the backtest write to `out/`, which was untracked by
`.gitignore`. Harmless while everything is synthetic; the moment connectors run
against a customer, that directory holds real spend figures and project names.

**Fixed.** `out/` ignored, alongside scratch benchmark files.

---

## Reviewed and found sound

- **Configuration excludes credential values.** OpenAI/Anthropic read environment
  credentials at call time; SDK clients may hold live credentials in memory.
  Do not capture heap/locals or serialize runtime clients; inspect logging policy separately.
- **`MAX_PAGES` bounds pagination** — a cursor bug against a metered API cannot loop
  forever.
- **Scope dimensions are an allowlist**, so `getattr(record, dimension)` cannot reach
  arbitrary attributes.
- **`.gitignore` covers `.env`, service-account JSON, key material and `data/`**, and
  `scripts/setup_remote.ps1` refuses to push if `.env` is tracked or the remote repo
  is public.
- **Reduced exception exposure.** Configuration errors name variables, not their values, and provider error objects exclude bodies/headers. This does not authorize raw response logging or traceback-local capture.

## Known gaps, accepted for now

| Gap | Why it is acceptable today | Trigger to fix |
|---|---|---|
| No authn/authz layer | Single-user CLI; no server exists yet | Before any remotely accessible UI/API or multi-tenant deployment |
| No audit log for reads | Nothing is exposed over a network | Same — required by N4 |
| `fetch_pricing_registry.py` follows redirects | Runs manually against a pinned GitHub SHA, checksum-verified after | If it ever runs automatically |
| Enforcement has no rate limit or circuit breaker | Dry-run only; nothing acts yet | Before the first real revoke |
| FX placeholder risk resolved 2026-10-12 | Runtime FX defaults are empty; dated rates with provenance must be configured | Verify customer rate source and invoice treatment before cross-currency acceptance |

---

# Latency Review

Measured before optimising, then re-measured. All figures on the 7,440-record
synthetic fleet, this machine.

## The problem: budget evaluation scaled with budgets × records

| Budgets | Before | After | |
|---|---|---|---|
| 5 | 46.1 ms | **16.6 ms** | 2.8× |
| 40 | 385.7 ms | **84.0 ms** | 4.6× |

Marginal cost per budget in that historical synthetic benchmark fell from **9.7 ms to 1.9 ms**. These measurements do not establish current production throughput or detection latency; source availability and delivery timing must be measured separately.

Three changes, in increasing order of how much they mattered:

1. **Window once, not per budget.** Budgets are grouped by `(period, currency)` so the
   record set is filtered to the period and currency-converted a single time.
2. **Cache FX lookups.** The same `(pair, date)` was bisected thousands of times per
   report. Cached in `FxTable`, invalidated on `add()`. Cross-currency aggregation
   went 5.8 ms → 4.7 ms per 2,000 records.
3. **Invert the index.** Windowing alone still had every budget touching every row.
   `PreparedWindow` now indexes `dimension → value → row indices`, so a budget scoped
   to one project intersects a couple of posting lists and visits only its own rows.
   Smallest posting list is intersected first. This was the change that actually
   moved the number.

Correctness is pinned by tests asserting the indexed path returns results identical
to a naive scan, across six scope shapes including empty and non-matching scopes.

## Unbounded detector state — memory and latency

`Baseline.hour_of_week_spend` was never trimmed: one entry per observation, forever.
A 400-day replay accumulated **9,600 entries**, and `expected_spend` averaged an
ever-lengthening list on every call. A long-running collector would have leaked memory
and slowed down as it went.

Capped at 8 samples per hour-of-week slot — enough to establish a weekday pattern,
fixed at 168 × 8 = 1,344 entries. `hourly_spend` became a `deque(maxlen=…)`, since
`list.pop(0)` is O(n) and deque eviction is O(1).

Also cached `premium_models()`, which scanned 2,427 models on every call.

## Measured and deliberately left alone

- **`Detector.process`: ~10 µs per observation.** Fast enough that the polling
  interval, not the CPU, is the constraint.
- **`expected_spend` is called 0.9× per observation**, not the ~4× I assumed before
  measuring — most rules return early. No optimisation warranted.
- **Synthetic data generation dominates the benchmark** (155 ms) and is test-only.
