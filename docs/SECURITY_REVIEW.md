# Security Review — 2026-08-15

Review of the full codebase, not just a diff. Every finding below is fixed and pinned
by a regression test in `tests/test_security.py`.

This doubles as the answer to the security questionnaire an Indian bank or GCC will
send during procurement — the questions are always some version of "what does your
tool do with our credentials, and how do you know."

**Threat model.** Prahari holds read-only admin credentials for a customer's AI and
cloud providers, and can be configured to revoke keys. That makes it a higher-value
target than most of its customers: a compromise yields organisation-wide inference
credentials, which is exactly the commodity the LLMjacking market exists to trade.
Two consequences drive the architecture — the collector runs inside the customer's
VPC so credentials never cross our boundary, and enforcement is dry-run by default.

---

## Findings

### S1 · SQL injection via the BigQuery table identifier — **High**

`connectors/gcp.py` interpolated `project.dataset.table` directly into the query
string. BigQuery cannot bind a table name as a parameter, so interpolation is
unavoidable — but the value was unvalidated.

Today it comes from environment variables, which limits exposure. In the multi-tenant
control plane it will arrive from per-tenant configuration, at which point a tenant
could read or destroy another tenant's data:

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

An infinite cost marks **every budget exceeded**. With `EnforcementAction.HARD_STOP`
configured, that revokes production credentials — a self-inflicted availability
incident triggered by an upstream response we never validated. `NaN` is quieter and
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

Nothing in our code logs it — but everything downstream does. An error tracker
capturing exception attributes, a log line with `exc_info=True`, or a traceback
rendered with locals all exfiltrate the customer's organisation-wide admin credential
to a third-party service.

**Fixed.** `raise_for_status_safely()` converts HTTP failures into `ProviderHTTPError`,
carrying only the status code, the request path, and a truncated body. Raised
`from None` so the original cannot be reattached via `__cause__`.

### S5 · Report output was not gitignored — **Low**

`scripts/report.py --json` and the backtest write to `out/`, which was untracked by
`.gitignore`. Harmless while everything is synthetic; the moment connectors run
against a customer, that directory holds real spend figures and project names.

**Fixed.** `out/` ignored, alongside scratch benchmark files.

---

## Reviewed and found sound

- **Credentials are never stored on connector instances.** Read from the environment
  at call time, so a config object can be logged or serialised safely. Pinned by test.
- **`MAX_PAGES` bounds pagination** — a cursor bug against a metered API cannot loop
  forever.
- **Scope dimensions are an allowlist**, so `getattr(record, dimension)` cannot reach
  arbitrary attributes.
- **`.gitignore` covers `.env`, service-account JSON, key material and `data/`**, and
  `scripts/setup_remote.ps1` refuses to push if `.env` is tracked or the remote repo
  is public.
- **No secrets in error messages.** The "not configured" errors name the environment
  variable, never its value.

## Known gaps, accepted for now

| Gap | Why it is acceptable today | Trigger to fix |
|---|---|---|
| No authn/authz layer | Single-user CLI; no server exists yet | Before the first multi-tenant deployment |
| No audit log for reads | Nothing is exposed over a network | Same — required by N4 |
| `fetch_pricing_registry.py` follows redirects | Runs manually against a pinned GitHub SHA, checksum-verified after | If it ever runs automatically |
| Enforcement has no rate limit or circuit breaker | Dry-run only; nothing acts yet | Before the first real revoke |
| FX rates are placeholders | Synthetic data only | Before any customer-facing figure (A6) |

---

# Latency Review

Measured before optimising, then re-measured. All figures on the 7,440-record
synthetic fleet, this machine.

## The problem: budget evaluation scaled with budgets × records

| Budgets | Before | After | |
|---|---|---|---|
| 5 | 46.1 ms | **16.6 ms** | 2.8× |
| 40 | 385.7 ms | **84.0 ms** | 4.6× |

Marginal cost per budget fell from **9.7 ms to 1.9 ms**. At production scale — a few
hundred thousand records and dozens of budgets — the original would have taken tens of
seconds per evaluation cycle, which rules out the sub-hour detection loop entirely.

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
