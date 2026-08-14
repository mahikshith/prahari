# Requirements

Derived from the market research (`MARKET_RESEARCH.md`) and the ₹6 crore incident. Each requirement names the gap it closes so we can tell when scope is drifting.

## Users

| Persona | Cares about | Buys because |
|---|---|---|
| **FinOps / CloudOps lead** (primary user) | Per-team allocation, chargeback, forecast, invoice reconciliation | Cannot currently answer "what did team X spend on AI last month" without a spreadsheet exercise |
| **CFO / Finance controller** (economic buyer) | Total AI spend, INR + GST reconciliation, budget vs actual, GCC↔HQ split | Budget overruns arrive as a surprise invoice, 30 days late |
| **CISO / Security lead** (second budget) | Credential abuse, shadow AI, blast radius, time-to-contain | LLMjacking. One leaked key = ₹6 crore |
| **Platform / Eng lead** (champion) | Per-service and per-agent cost, runaway agent loops | Gets blamed for the bill without the data to defend it |

## Functional requirements

### F1 — Agentless ingestion (closes: instrumentation gap)
Connect and pull with **zero code changes** in the customer's applications.

| Source | Mechanism | Freshness | Priority |
|---|---|---|---|
| Anthropic | Usage & Cost Admin API (`/v1/organizations/usage_report/messages`), admin key | **~5 min**, 1 poll/min | **P0** |
| OpenAI | Org usage + costs API, admin key | near-real-time | **P0** |
| GCP Vertex / Gemini | BigQuery billing export + Cloud Monitoring | export lag 4–24h; monitoring minutes | **P0** (the ₹6cr surface) |
| AWS Bedrock | CloudWatch metrics (fast) + CUR (authoritative) | dual-feed | P1 |
| Azure OpenAI | Cost Management export (FOCUS) + Azure Monitor | minutes–hours | P1 |
| GitHub Copilot | Usage metrics API **+ enterprise billing connection** | daily | P1 |
| M365 Copilot | Graph usage reports | daily | P2 |
| Claude Code / Cursor | Admin analytics APIs | daily | P2 |
| Shadow AI | Okta/Entra SSO logs + corporate card feed | daily | P2 |

**F1.1** Every connector is idempotent and re-runnable for an arbitrary date range.
**F1.2** Credentials are read from environment only — never persisted, never logged.
**F1.3** A connector must degrade honestly: partial data is labelled partial (FOCUS 1.3 recency/completeness flags), never silently gap-filled.

### F2 — Normalisation (closes: multi-provider pricing chaos)
**F2.1** Every record normalises to a FOCUS 1.3-aligned `UsageRecord`.
**F2.2** Costs use **provider-reported billed amounts** where available; estimation from the price registry is a labelled fallback, never mixed silently into a billed total.
**F2.3** Handle cache reads/writes, batch tiers, and provider service tiers as distinct cost components — these are where naive tools produce wrong numbers.
**F2.4** Multi-currency: store amount + currency + FX date. INR presentation with GST treatment separated from base cost.

### F3 — Allocation (closes: "who spent this")
**F3.1** Map every record to a team / cost centre via API key, project, workspace, cloud tag, or user identity.
**F3.2** **Unallocated is a first-class, visible number.** Hiding it is how existing tools lie. Target <15%.
**F3.3** GCC↔HQ dual allocation: one record can carry both a local cost centre and a parent entity, for transfer-pricing documentation.
**F3.4** Per-employee rollup joining seats (Copilot/Cursor licences) with API consumption.

### F4 — Reconciliation (closes: trust)
**F4.1** For each provider and billing period, compare computed total against the actual invoice.
**F4.2** **Variance must be ≤2%.** A connector failing this does not ship.
**F4.3** Variance is displayed in-product, not buried. Finance buyers trust a tool that admits its error bar.

### F5 — Detection (the moat)
**F5.1** Maintain rolling baselines per API key, identity, model, and region.
**F5.2** Fire on the LLMjacking fingerprint — each rule independently named and explainable:
  - `SPEND_SPIKE` — 1h spend > 3.2× the 7-day hourly average for that key
  - `DORMANT_KEY_WAKE` — first use of a key idle ≥30 days
  - `NEW_GEO` — new country/ASN for a known key
  - `MODEL_ESCALATION` — abrupt switch to the most expensive available model
  - `RESALE_PATTERN` — sustained near-max context at non-business hours
**F5.3** Alerts must state: which rule, what baseline, what observed, estimated spend so far, and projected 24h exposure **in INR**.
**F5.4** Seasonality-aware — engineering usage has a strong weekday pattern. Alerting every Monday destroys trust faster than missing an incident.
**F5.5** Target: **median detection < 60 minutes** from anomaly onset, against a 24h+ billing-export baseline.

### F6 — Enforcement (what makes it a control plane)
**F6.1** Budget hard-stops at org / team / key level.
**F6.2** One-click and policy-driven key revocation via provider admin APIs.
**F6.3** Every enforcement action is opt-in, confirmed, reversible where the provider allows, and **audit-logged with actor and reason**.
**F6.4** Dry-run mode: show exactly what would have been revoked, without acting. Nobody grants write access before seeing this.

### F7 — Reporting
Per-team / per-employee / per-agent chargeback · budget vs actual with forecast · overlapping-tool detection (teams paying for Claude Code + Copilot + Cursor simultaneously) · INR/GST reconciliation pack · GCC↔HQ transfer-pricing export.

## Non-functional requirements

| # | Requirement | Rationale |
|---|---|---|
| **N1** | **Self-hosted collector.** Customer runs it in their VPC; credentials never cross our boundary; only aggregates leave | We ask for admin credentials — that makes us a higher-value target than our customers. Also the DPDP story |
| **N2** | **India data residency option** | DPDP hard deadline May 2027 + RBI localisation. This is the structural advantage over Torii/Flexera |
| **N3** | Read-only default; write scopes separately granted per action | First-sale objection killer |
| **N4** | Full audit log of every read and every enforcement action | Bank and GCC security review will demand it |
| **N5** | Detection explainable without ML expertise | A CFO must understand why an alert fired |
| **N6** | Money as `Decimal`, never float; UTC storage, IST display | Correctness at the only place customers check us |
| **N7** | Backfill any date range on demand | Onboarding starts with "show me last quarter" |

## Out of scope — actively defended

Gateway/proxy in the request path · SDK/trace instrumentation · model routing or prompt optimisation · GPU cluster rightsizing · general multi-cloud FinOps beyond AI.

Each is owned by a well-funded incumbent (Palo Alto/Portkey, Langfuse/Datadog, Martian, nOps/Cast AI, CloudZero/Vantage/Finout). Entering any of them trades our only defensible position for a fight we lose.

## Acceptance for v0 (the backtest)

Not the product — the **sales artifact**. Done when it can state, from the company's own historical GCP billing data:

> *"This would have fired at ₹X spent, N hours before the invoice revealed it."*

plus a reconciliation showing ≤2% variance against a real invoice.
