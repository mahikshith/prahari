# Tech Stack

**Consistency review: 2026-10-12.** This design catalog includes deferred targets, not a shipped-feature inventory. Current scope and outcomes are in [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](../PROGRESS.md): GCP + OpenAI, hybrid collection, customer-owned India cloud first, and live-source/response acceptance still required.

Existing foundation choices and later candidates are distinguished below. Hosting, query/log ingestion, notifications and inference can incur costs; vendor free tiers require current verification.

## Decisions

### Data plane — Python 3.12+

Python retains the existing collector, validation, analytics and provider integration code. Rewriting it adds maintenance without establishing pilot value.

| Concern | Choice | Why |
|---|---|---|
| Package/env manager | **uv** | 10–100× faster than pip, single tool for envs + deps + lockfile. Replaces pip/venv/poetry outright |
| API | **FastAPI (later candidate)** | Optional dependency; the current foundation is a CLI/daemon, not a hosted API |
| Schemas/validation | **Pydantic v2** | FOCUS records are schema-heavy and provider payloads are messy; validation at the boundary is worth it |
| Ingestion | **Existing manual provider connectors** | Reuse current fetch, watermark and retry logic; installed dlt is not an implemented ingestion pipeline |
| Analytical store (local + backtest) | **DuckDB** | Zero-ops, columnar, reads Parquet/CSV/JSON directly, embedded. Perfect for the ₹6cr backtest and reconciliation runs |
| App store (later) | **PostgreSQL** | Add for actual tenancy/concurrency or selected-gateway needs; deployment and India placement require separate review |
| Scheduling | **Existing asyncio daemon** | Reuse collector scheduling, settling lag and durable state; no scheduler migration without a demonstrated need |
| Detection | **Current named rules and bounded rolling/seasonal baselines** | Explainable prototype; calibrate real data before adopting additional statistical models |
| HTTP | **httpx** | Async, retries, timeouts; matches FastAPI's model |
| Testing | **pytest** + **respx** | respx mocks httpx cleanly — critical since we cannot hit real billing APIs in CI |
| Lint/format | **ruff** | Replaces black + isort + flake8, one tool |

### Product UI — Next.js (later, not v0)

Two different artifacts, do not conflate them:

- **v0 backtest / internal tool: Streamlit.** Days, not weeks. It's a sales artifact you demo once per call, then throw away. Building a React app for this is a waste.
- **Production UI candidates:** Next.js/TypeScript and existing component/chart libraries, only after paid-pilot requirements establish a need. A framework choice does not establish customer buying behavior.

### Distribution — Docker

The collector ships as a Docker image for customer-owned India infrastructure. Review credentials, runtime/build inputs, logging, backups, notifications and support destinations separately. Container/VPC placement reduces some exposure but does not establish DPDP compliance or provider processing residency.

*(Considered Go for a single static binary — genuinely easier for a customer's security team to accept. Rejected: doubles our language surface, and Docker solves distribution just as well at a fraction of the cost.)*

### Deferred until there is a customer

| Concern | Choice when needed | Trigger |
|---|---|---|
| Auth + enterprise SSO | Customer IAM/SSO or reviewed provider | Before exposing a service/UI; check pricing, capabilities and metadata destinations |
| Secrets, if ever stored our side | Cloud KMS envelope encryption or **Vault** | Only if self-hosted collector proves unworkable. Default remains: we never hold customer keys |
| Warehouse at scale | **ClickHouse** | When DuckDB/Postgres stops keeping up. Not before |
| Orchestration | **Dagster** | When connector backfills need lineage and retries |

## Cost

Local synthetic checks can be inexpensive. Live validation can bill inference, BigQuery queries, logging/storage, hosting and notifications. Set a sandbox budget and measure overhead; do not promise ₹0 or assume a hosted free tier provides India placement.

## Install (when ready to code)

```powershell
# uv — package + env manager
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Python 3.12 via uv (leaves the existing 3.10 alone)
uv python install 3.12

# Project env + deps
cd C:\Users\mahik\Music\aiops
uv sync --extra dev
```

Node/Next.js only when we start the product UI — deliberately not now.

**FX:** daemon defaults contain no demo rates. Configure finite positive dated rates with provenance in customer YAML; missing conversion remains a coverage/configuration gap. **Gateway:** optional reuse is planned under D004; no live gateway or controls have been deployed.
