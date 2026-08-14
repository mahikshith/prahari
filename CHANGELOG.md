# Changelog

All notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is [SemVer](https://semver.org/).

Architectural and licence decisions are recorded here as well as code changes — per `docs/OSS_INVENTORY.md`, any adoption of an ELv2/BSL/SSPL dependency requires an explicit entry.

## [Unreleased]

### Added
- Market research memo covering market size, the four competitor layers, unclaimed gaps, investor appetite and India-domestic reality (`docs/MARKET_RESEARCH.md`)
- Open-source inventory with licence audit — what we reuse vs build (`docs/OSS_INVENTORY.md`)
- Requirements derived from the ₹6 crore incident and the research (`docs/REQUIREMENTS.md`)
- Architecture: self-hosted collector shape, 7-stage pipeline, FOCUS-aligned data model (`docs/ARCHITECTURE.md`)
- Staged project plan, each stage ending in a sales artifact (`docs/PROJECT_PLAN.md`)
- Go/no-go decision gates (`docs/DECISION_GATES.md`)
- Project scaffold, git repo, `CLAUDE.md`, `CONTEXT.md`, `PROGRESS.md`

### Decisions
- **Scope:** visibility **and** enforcement, sequenced — visibility is the entry product, enforcement is the moat. Not an either/or; the second requires the first.
- **Geography:** India-domestic first, contingent on Gate 3 (DPDP/residency raised unprompted in discovery).
- **Architecture:** agentless only. No gateway in the request path, no SDK instrumentation — both are blind to a stolen credential calling a provider directly, which is exactly the case we exist to catch.
- **Security:** self-hosted collector. Customer credentials never cross our boundary. This is a security decision before it is a sales one.
- **Stack:** Python data plane (uv, FastAPI, Pydantic v2, dlt, DuckDB, Postgres). Streamlit for the throwaway v0 tool; Next.js + shadcn/ui + Tremor for the product UI when there are paying design partners.
- **Normalisation target:** FOCUS 1.3 (ratified 5 Dec 2025), rather than a bespoke schema.
- **Licence:** vendor the LiteLLM `model_prices_and_context_window.json` registry (MIT) with a pinned commit SHA and checksum. **Do not install the `litellm` PyPI package** — it suffered a confirmed supply-chain attack in March 2026 delivering a credential-stealing payload, and this product handles AI credentials.
- **Rejected:** Steampipe (AGPL, cannot embed), CloudQuery (ELv2/commercial core), Prophet and PyOD (opacity and overkill — explainability is a product requirement).
