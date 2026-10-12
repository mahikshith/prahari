# Requirements

**Consistency review: 2026-10-12.** This design catalog includes deferred targets, not a shipped-feature inventory. Current scope and outcomes are in [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](../PROGRESS.md): GCP + OpenAI, hybrid collection, customer-owned India cloud first, and live-source/response acceptance still required.

Derived from [market evidence](MARKET_RESEARCH.md) and the founder-reported weekend service-account exposure (roughly ₹6–7 crore cost/exposure). Each requirement names the gap it closes so we can tell when scope is drifting.

## Users

| Persona | Cares about | Buys because |
|---|---|---|
| **FinOps / CloudOps lead** (primary user) | Per-team allocation, chargeback, forecast, invoice reconciliation | Cannot currently answer "what did team X spend on AI last month" without a spreadsheet exercise |
| **CFO / Finance controller** (potential economic buyer) | Total AI spend, INR + GST reconciliation, budget vs actual, GCC↔HQ split | Late or fragmented evidence prevents timely attribution; verify actual buying authority |
| **CISO / Security lead** (second budget) | Credential abuse, shadow AI, blast radius, time-to-contain | Credential abuse/runaway usage; the founder's reported exposure is not a typical incident loss |
| **Platform / Eng lead** (champion) | Per-service and per-agent cost, runaway agent loops | Gets blamed for the bill without the data to defend it |

## Functional requirements

### F1 — Hybrid ingestion
Agentless admin/billing collection avoids application changes where sources permit; optional reused gateway telemetry requires routing/integration. GCP + OpenAI are P0. Existing Anthropic support remains, and all other catalog entries are deferred; listed bucket sizes/poll schedules are not source-freshness guarantees.

| Source | Mechanism | Freshness | Priority |
|---|---|---|---|
| Anthropic | Usage & Cost Admin API, admin key | Measure observed delay; existing connector | Deferred pilot expansion |
| OpenAI | Org usage + costs API, admin key; optional gateway usage | Verify source availability separately from aggregation | **P0** |
| GCP Vertex / Gemini | BigQuery billing export + planned audit/gateway correlation | Billing export has no latency guarantee; verify each method/source | **P0** |
| AWS Bedrock | CloudWatch metrics (fast) + CUR (authoritative) | dual-feed | P1 |
| Azure OpenAI | Cost Management export (FOCUS) + Azure Monitor | minutes–hours | P1 |
| GitHub Copilot | Usage metrics API **+ enterprise billing connection** | daily | P1 |
| M365 Copilot | Graph usage reports | daily | P2 |
| Claude Code / Cursor | Admin analytics APIs | daily | P2 |
| Shadow AI | Okta/Entra SSO logs + corporate card feed | daily | P2 |

**F1.1** Every connector is idempotent and re-runnable for an arbitrary date range.
**F1.2** Credential values stay customer-controlled and outside config/Git/logs; env references or customer-provided credential files are supported. Do not capture traceback locals, raw headers or response bodies.
**F1.3** Flag partial/provisional source windows and distinguish unknown prices from known zero. FOCUS alignment is a terminology target, not certified conformance.

### F2 — Normalisation (closes: multi-provider pricing chaos)
**F2.1** Records use a FOCUS-aligned prototype `UsageRecord`; provider-specific mapping and conformance validation remain required.
**F2.2** Prefer provider-reported amounts; label price-registry estimates with cost basis, and keep unavailable cost null. Reports cannot present known subtotals as complete totals; incomplete money blocks monetary enforcement.
**F2.3** Handle cache reads/writes, batch tiers, and provider service tiers as distinct cost components — these are where naive tools produce wrong numbers.
**F2.4** Multi-currency: store amount + currency + FX date. INR presentation with GST treatment separated from base cost.

### F3 — Allocation (closes: "who spent this")
**F3.1** Map records where trusted key/project/workspace/tag/user evidence exists; leave other records unallocated. Shared keys and project/time joins do not prove employee or per-key cost.
**F3.2** **Unallocated is a first-class, visible number.** Hiding it is how existing tools lie. Target <15%.
**F3.3** GCC↔HQ dual allocation: one record can carry both a local cost centre and a parent entity, for transfer-pricing documentation.
**F3.4** Per-employee rollup joining seats (Copilot/Cursor licences) with API consumption.

### F4 — Reconciliation (closes: trust)
**F4.1** For each provider and billing period, compare computed total against the actual invoice.
**F4.2** **Variance must be ≤2%.** A connector failing this does not ship.
**F4.3** Variance is displayed in-product, not buried. Finance buyers trust a tool that admits its error bar.

### F5 — Detection (the moat)
**F5.1** Maintain bounded baselines per credential (or the source's supported project/account fallback), retaining last activity outside the 30-day replay. Model/region are evidence, not separate credential baselines.
**F5.2** Fire on the LLMjacking fingerprint — each rule independently named and explainable:
  - `SPEND_SPIKE` — 1h spend > 3.2× the 7-day hourly average for that key
  - `DORMANT_KEY_WAKE` — first use of a key idle ≥30 days
  - `NEW_GEO` — new country/ASN for a known key
  - `MODEL_ESCALATION` — abrupt switch to the most expensive available model
  - `RESALE_PATTERN` — sustained near-max context at non-business hours
**F5.3** Alerts state rule, baseline, observation and source/coverage. Show monetary estimates/projections only with known cost and configured dated FX; otherwise issue a coverage warning without fabricated money.
**F5.4** Seasonality-aware — engineering usage has a strong weekday pattern. Alerting every Monday destroys trust faster than missing an incident.
**F5.5** Sub-hour detection is a pilot hypothesis, measured from event onset with source and ingestion delay separately visible. Billing-only paths cannot establish this target or a fixed 24-hour incumbent baseline.

### F6 — Enforcement (what makes it a control plane)
**F6.1** Planned budget admission/blocking for routed calls at supported scopes; validate concurrent reservations, in-flight exposure and unavailable accounting state. Gateway bypass is a separate risk.
**F6.2** Planned scoped provider response via verified supported APIs; no live revocation is implemented/enabled in the foundation. Confirm actual effect on issued tokens, other users and retries.
**F6.3** Every enforcement action is opt-in, confirmed, reversible where the provider allows, and **audit-logged with actor and reason**.
**F6.4** Dry-run mode: show exactly what would have been revoked, without acting. Nobody grants write access before seeing this.

### F7 — Reporting
Per-team / per-employee / per-agent chargeback · budget vs actual with forecast · overlapping-tool detection (teams paying for Claude Code + Copilot + Cursor simultaneously) · INR/GST reconciliation pack · GCC↔HQ transfer-pricing export.

## Non-functional requirements

| # | Requirement | Rationale |
|---|---|---|
| **N1** | Customer-owned India deployment first; separately document provider, log, backup, notification and support destinations | Limit credential/data exposure; VPC placement alone does not establish compliance |
| **N2** | Evidence of storage, routing and provider processing commitments | Applicable law/contracts vary; DPDP is not a blanket India-localization requirement and IPs do not prove ML geography |
| **N3** | Read-only default; write scopes separately granted per action | First-sale objection killer |
| **N4** | Full audit log of every read and every enforcement action | Bank and GCC security review will demand it |
| **N5** | Detection explainable without ML expertise | A CFO must understand why an alert fired |
| **N6** | Money as `Decimal`, never float; UTC storage, IST display | Correctness at the only place customers check us |
| **N7** | Backfill any date range on demand | Onboarding starts with "show me last quarter" |

## Out of scope — actively defended

Building a new gateway/SDK, model routing/prompt optimization, GPU rightsizing and broad multi-cloud FinOps are deferred. Reusing a gateway for the selected hybrid pilot is in the design scope; deployment and controls still require validation.

## Acceptance for v0 (the backtest)

The existing v0 is a synthetic replay. A separately authorized real replay requires usage/audit identity and source-availability evidence as well as billing; billing alone cannot reconstruct per-service-account detection. Only then may a qualified counterfactual state:

> *"This would have fired at ₹X spent, N hours before the invoice revealed it."*

plus settled-invoice reconciliation targeting ≤2% explained variance. This still does not prove actual money saved or production prevention.
