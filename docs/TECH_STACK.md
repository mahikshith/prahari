# Tech Stack

Chosen on fit, not on what happened to be installed. Everything here is free or has a permanent free tier at our scale. Install steps at the bottom.

## Decisions

### Data plane — Python 3.12+

Not a preference, a fit argument: every cloud and AI provider SDK is Python-first, `dlt` is Python, the stats/anomaly ecosystem is Python, and the LiteLLM price registry is trivially consumable from Python. Nothing else is close for this workload.

| Concern | Choice | Why |
|---|---|---|
| Package/env manager | **uv** | 10–100× faster than pip, single tool for envs + deps + lockfile. Replaces pip/venv/poetry outright |
| API | **FastAPI** | Async (connectors are I/O-bound), OpenAPI for free, Pydantic-native |
| Schemas/validation | **Pydantic v2** | FOCUS records are schema-heavy and provider payloads are messy; validation at the boundary is worth it |
| Ingestion | **dlt** (Apache 2.0) | Auto schema inference + evolution, incremental loading, pipeline state. Solves exactly the connector-backfill problem we'd otherwise hand-roll |
| Analytical store (local + backtest) | **DuckDB** | Zero-ops, columnar, reads Parquet/CSV/JSON directly, embedded. Perfect for the ₹6cr backtest and reconciliation runs |
| App store (multi-tenant) | **Postgres** (Neon free tier) | Permanent free tier, 3 GiB/branch, branching for dev. Add TimescaleDB only if time-series volume actually demands it |
| Scheduling | **APScheduler** now → **Dagster** later | APScheduler is enough for a handful of connectors. Move to Dagster when backfills, retries and lineage stop being tractable — not before |
| Detection maths | **statsmodels** (STL) + hand-rolled EWMA/z-score | Explainability is a product requirement. No black-box models in the alert path |
| HTTP | **httpx** | Async, retries, timeouts; matches FastAPI's model |
| Testing | **pytest** + **respx** | respx mocks httpx cleanly — critical since we cannot hit real billing APIs in CI |
| Lint/format | **ruff** | Replaces black + isort + flake8, one tool |

### Product UI — Next.js (later, not v0)

Two different artifacts, do not conflate them:

- **v0 backtest / internal tool: Streamlit.** Days, not weeks. It's a sales artifact you demo once per call, then throw away. Building a React app for this is a waste.
- **Actual product: Next.js + TypeScript + shadcn/ui + Tremor.** You are selling to GCC finance leads and bank CISOs. Streamlit looks like a demo and will cost you deals. **Tremor** is purpose-built for financial/KPI dashboards, so we get the chart vocabulary free. Requires Node — install when we get there, not now.

### Distribution — Docker

The collector ships as a **Docker image** the customer runs inside their own VPC. This is the whole security and DPDP story: their credentials never cross our boundary. It also sidesteps "will your Python app run in our environment" entirely.

*(Considered Go for a single static binary — genuinely easier for a customer's security team to accept. Rejected: doubles our language surface, and Docker solves distribution just as well at a fraction of the cost.)*

### Deferred until there is a customer

| Concern | Choice when needed | Trigger |
|---|---|---|
| Auth + enterprise SSO | **WorkOS AuthKit** (free tier covers SSO/SAML) | First customer that asks for SAML — enterprise India will ask early |
| Secrets, if ever stored our side | Cloud KMS envelope encryption or **Vault** | Only if self-hosted collector proves unworkable. Default remains: we never hold customer keys |
| Warehouse at scale | **ClickHouse** | When DuckDB/Postgres stops keeping up. Not before |
| Orchestration | **Dagster** | When connector backfills need lineage and retries |

## Cost

₹0 through the entire validation phase. GitHub free (private repo), GitHub Actions free tier, Neon free tier, DuckDB local, all libraries OSS. The only spend is the AI API calls we make while testing — which is, appropriately, exactly the thing we're building to measure.

## Install (when ready to code)

```powershell
# uv — package + env manager
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Python 3.12 via uv (leaves the existing 3.10 alone)
uv python install 3.12

# Project env + deps
cd C:\Users\mahik\Prahari
uv sync
```

Node/Next.js only when we start the product UI — deliberately not now.
