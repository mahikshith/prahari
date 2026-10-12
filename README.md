# Prahari

Prahari (प्रहरी, sentinel) is an AI spend observability and control prototype. It aims to join cost, trusted identity, coverage gaps and incident response across providers.

The founder reports a weekend service-account exposure followed by unauthorized Gemini use and roughly ₹6–7 crore of cost/exposure. The [incident story](gtm/case-study-incident.md) separates that report from synthetic detection scenarios. Simulated exposure is not measured money saved.

## Current scope and status

The first pilot targets **GCP + OpenAI**, for startup/midmarket and regulated enterprise buyers using one shared core. Deployment starts in the customer's India cloud; India-hosted SaaS follows later.

The repository contains a Python/DuckDB collector, OpenAI/Anthropic usage connectors, GCP billing ingestion, explainable detection, budget analysis, notifications and synthetic replays. The existing Anthropic connector remains, but it does not expand the selected pilot scope.

The hybrid design combines agentless audit/billing evidence with an optional reused gateway for routed telemetry and budget admission. GCP audit correlation, live gateway blocking, provider response actions and network collection are planned. No live controls or cloud logging are enabled by this change.

Financial records distinguish provider-reported cost, estimates and unknown prices. Missing cost remains unknown; incomplete money cannot justify monetary enforcement. GCP billing is provisional and lacks caller identity. Shared credentials cannot establish employee attribution without additional trusted evidence.

**Validation:** 334 local tests pass, with Ruff and dependency-lock checks passing. Live provider, customer deployment and invoice acceptance are pending. See [PROGRESS.md](PROGRESS.md). India hosting and endpoint/IP evidence do not establish legal compliance or physical inference geography.

## Start locally

Use Python 3.12+ and uv:

```powershell
uv sync --extra dev
uv run prahari validate -c prahari.example.yaml
uv run prahari status -c prahari.example.yaml
uv run python -m pytest -q
uv run ruff check src tests scripts
uv run python scripts/backtest_incident.py
```

Validation reports missing credentials when none are configured. Keep credentials outside Git and use your own authorized sandbox for live checks. Cross-currency operation requires explicit FX rates with date/source; synthetic examples supply their own rates.

## Project records

| Document | Purpose |
|---|---|
| [Decision log](docs/DECISIONS.md) | Stable dated decisions, rationale, tradeoffs and expected/actual outcomes |
| [Current pilot plan](docs/PILOT_PLAN.md) | Repository assessment, phased work, acceptance evidence and failure paths |
| [Context](CONTEXT.md) / [Progress](PROGRESS.md) | Current direction and implementation/validation status |
| [Market research](docs/MARKET_RESEARCH.md) / [Decision gates](docs/DECISION_GATES.md) | Competitor evidence and pilot/renewal tests |
| [Architecture](docs/ARCHITECTURE.md) / [Requirements](docs/REQUIREMENTS.md) | Evidence, accounting and deployment contracts |
| [MVP roadmap](docs/MVP_ROADMAP.md) / [Project plan](docs/PROJECT_PLAN.md) | Historical work breakdowns and standing risks |
| [Network telemetry](docs/NETWORK_TELEMETRY.md) | IP/DNS/flow evidence and coverage limits |
| [Tech stack](docs/TECH_STACK.md) / [OSS inventory](docs/OSS_INVENTORY.md) | Reuse choices, licenses and deployment dependencies |
| [Critical OSS assessment](docs/OSS_ASSESSMENT.md) | Verified editions, documented limits, selected upstream issues and conformance trials |
| [India regulation](docs/INDIA_REGULATION.md) | Commencement, sector applicability, residency and data-flow evidence |
| [Security review](docs/SECURITY_REVIEW.md) / [Changelog](CHANGELOG.md) | Findings and development history |

Prahari remains a working codename.
