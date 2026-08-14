# CLAUDE.md — Prahari

> Working codename. **Prahari** (प्रहरी) = sentinel / watchman. Provisional; rename is cheap right now, expensive after the first customer.

## What this is

An **AI spend control plane**: agentless, cross-provider visibility into AI token and seat cost, plus sub-hour detection and automated containment of credential abuse (LLMjacking).

**One line:** *See every rupee of AI spend across every provider — and stop it within the hour when it goes wrong.*

## Why it exists

Mahikshith's company lost **~₹6 crore (~$700K)** when a GCP service account key leaked into an LLM chat and was used from outside the organisation. AI spend is scattered across Claude Code, Copilot Studio, M365 Copilot, Gemini, and GCP/Vertex service accounts. No tool on the market connects *leaked credential → anomalous inference spend → containment → rupee impact*.

Full market research: [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md). Read it before proposing strategy changes.

## The wedge (do not drift from this)

| Layer | Purpose | Status |
|---|---|---|
| **Visibility** (entry) | Cross-provider tokens + seats + cloud AI + shadow AI, allocated to teams/cost centres, reconciled to invoice in INR/GST | Lands the deal |
| **Detection + enforcement** (moat) | Per-identity/per-key sub-hour baselines → LLMjacking alerts → budget hard-stops + auto key revocation | Retains the deal, unlocks the CISO budget |

You cannot build the moat without the entry layer first. Ship in that order. Pitch both from day one.

## Non-negotiables

1. **Agentless.** Admin/usage APIs, billing exports, SSO logs, card feeds. No SDK instrumentation, no proxy in the request path. A stolen credential calling a provider directly is invisible to gateways and SDKs — that blindness is precisely our differentiator.
2. **Read-only by default.** Enforcement actions are opt-in, per-action, audit-logged, and never silent.
3. **Self-hosted collector.** Customer runs the collector in their own VPC; credentials never leave their boundary; only aggregated cost/usage records reach us. This is the security posture *and* the DPDP story *and* the reason a bank will say yes.
4. **Invoice reconciliation ≤2% variance.** A finance tool that disagrees with the invoice is dead on arrival. Every connector ships with a reconciliation test against a real invoice.
5. **Explainable detection.** A CFO must understand why an alert fired. EWMA + z-score + named rules beat a black-box model here, always.

## Explicitly NOT building

Gateway/proxy (Palo Alto owns it via Portkey; LiteLLM owns OSS) · SDK tracing (Langfuse/Datadog) · model routing/optimisation (Martian) · GPU cluster rightsizing (nOps/Cast AI) · generic multi-cloud FinOps (CloudZero/Vantage/Finout).

If a task starts drifting into these, stop and flag it.

## Stack

Python data plane, Next.js product UI. Full rationale and versions: [docs/TECH_STACK.md](docs/TECH_STACK.md).
Everything we reuse instead of building: [docs/OSS_INVENTORY.md](docs/OSS_INVENTORY.md). **Check this file before writing anything from scratch.**

## Repo layout

```
src/prahari/
  connectors/   one module per provider; each exposes fetch() -> list[UsageRecord]
  core/         FOCUS-aligned models, normalisation, allocation, config
  pricing/      vendored LiteLLM price registry + lookup
  detect/       baselines, rules, anomaly engine
  store/        DuckDB (local/backtest) and Postgres (app) adapters
app/            Streamlit backtest tool (v0, throwaway) → Next.js product UI later
scripts/        one-off analyses, the ₹6cr backtest, reconciliation runs
gtm/            case study, discovery scripts, gate tracking — sales artifacts, not code
docs/           everything durable
data/           gitignored. raw/ = provider pulls, warehouse/ = DuckDB files
```

## Conventions

- **Money:** store `Decimal`, never `float`. Persist `amount`, `currency`, and `fx_rate_date` separately. Never round before the final display step.
- **Time:** everything UTC in storage, `TIMESTAMPTZ`. Convert to IST only at the presentation layer.
- **Schema:** normalise to **FOCUS 1.3** column names wherever a FOCUS column exists. Don't invent a parallel vocabulary.
- **Connectors:** every one is idempotent and re-runnable for any date range. Assume you will backfill.
- **Credentials:** read from env only. Never written to disk, never logged, never committed. `.env` is gitignored — verify before every commit.
- **Provider quirks belong in the connector**, not in core. Core sees clean `UsageRecord`s only.

## Working style (Mahikshith)

Reason from the user backwards. Decide firmly and state the decision — don't present option menus without a recommendation. Keep [CONTEXT.md](CONTEXT.md) and [PROGRESS.md](PROGRESS.md) current; they are how a session picks up cold.

## Current state

See [PROGRESS.md](PROGRESS.md). At time of writing: repo scaffolded, no connectors yet. The first deliverable is the **₹6 crore backtest** (`scripts/`) — a sales artifact, not product code.
