# Prahari

**प्रहरी — sentinel.** An AI spend control plane.

> See every rupee of AI spend across every provider — and stop it within the hour when it goes wrong.

---

## The problem

A single leaked GCP service account key cost one company **~₹6 crore**. It's not an anomaly — it's a category called **LLMjacking**, and AI-targeted credential theft rose **376%** between Q4 2025 and Q1 2026. Sysdig has documented hijacked accounts burning **$46K–$100K per day**.

Meanwhile 98% of FinOps teams now manage AI spend, 73% of AI projects blow their budget, and the tools they use report on a **daily** cadence — structurally incapable of catching an attack that drains six figures in a day.

Cost tools see the bill but not the identity. Security tools see the credential but never the money. Prahari closes that loop.

## What it does

**Visibility** — agentless, cross-provider. Anthropic, OpenAI, GCP Vertex, AWS Bedrock, Azure OpenAI, GitHub Copilot, M365 Copilot, plus shadow AI from SSO and card feeds. Normalised to FOCUS 1.3, allocated to teams and cost centres, reconciled against the actual invoice in INR with GST.

**Detection** — rolling per-key, per-identity baselines with sub-hour resolution. Five named, explainable rules matching the LLMjacking fingerprint. Target: median detection under 60 minutes, against a 24-hour billing-export baseline.

**Enforcement** — budget hard-stops and automated key revocation. Opt-in, dry-run first, fully audit-logged.

## How it's different

- **Agentless.** No SDK, no proxy in the request path. Gateways and tracing tools only see traffic developers deliberately route through them — they are blind to a stolen credential calling a provider directly. That blindness is the whole gap.
- **Self-hosted collector.** Runs in your VPC. Your admin credentials never cross our boundary; only aggregated cost records do.
- **Explainable.** Every alert states the rule, the baseline, the observation, and the projected 24-hour exposure in rupees. No black boxes in front of a CFO.

## Status

**Pre-product.** Currently building the backtest against a real incident, and running buyer discovery against explicit go/no-go gates. See [PROGRESS.md](PROGRESS.md).

## Docs

| | |
|---|---|
| [CONTEXT.md](CONTEXT.md) | Why this exists, decisions made, the load-bearing assumption |
| [PROGRESS.md](PROGRESS.md) | Current state, next actions, blockers |
| [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md) | Market, competitors, gaps, investor appetite, India reality |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Functional and non-functional requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Deployment shape, pipeline, data model |
| [docs/TECH_STACK.md](docs/TECH_STACK.md) | Stack choices and rationale |
| [docs/OSS_INVENTORY.md](docs/OSS_INVENTORY.md) | What we reuse instead of building, with licence audit |
| **[docs/MVP_ROADMAP.md](docs/MVP_ROADMAP.md)** | **What's left to build, in order, with dependencies** |
| [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | Staging philosophy and standing risks |
| [docs/DECISION_GATES.md](docs/DECISION_GATES.md) | The five gates that decide whether this gets built |
| [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) | Security findings and fixes; latency work |

## Setup

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv python install 3.12
uv sync
```

---

*Prahari is a working codename.*
