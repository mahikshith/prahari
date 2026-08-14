# PROGRESS

*What's done, what's next, what's blocked. Update every session.*

**Last updated:** 2026-08-15
**Current stage:** Stage 0 — the ₹6 crore backtest (see [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md))

---

## Done

### 2026-08-15 — Research and scaffold
- [x] Full market research: market size, competitors across 4 layers, gaps, investor appetite, India reality → [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md)
- [x] Open-source inventory — what we reuse vs build, with licence audit → [docs/OSS_INVENTORY.md](docs/OSS_INVENTORY.md)
- [x] Tech stack decided on fit → [docs/TECH_STACK.md](docs/TECH_STACK.md)
- [x] Requirements derived from the incident + research → [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
- [x] Architecture: self-hosted collector shape, pipeline, data model → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [x] Staged plan, each stage ending in a sales artifact → [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)
- [x] Go/no-go gates → [docs/DECISION_GATES.md](docs/DECISION_GATES.md)
- [x] Repo scaffolded, git initialised

---

## Next up

**Stage 0 — the backtest.** In order:

1. [ ] **Confirm data access.** Can we query the GCP BigQuery billing export covering the incident window? What retention is set?
2. [ ] **Settle the IP/data-use position** if this is employer data. Blocks everything downstream.
3. [ ] Install the toolchain — `uv`, Python 3.12, `uv sync` (see [docs/TECH_STACK.md](docs/TECH_STACK.md))
4. [ ] Vendor the LiteLLM price registry with pinned SHA + checksum (**do not `pip install litellm`** — Mar 2026 supply-chain attack; see OSS inventory)
5. [ ] `scripts/backtest_incident.py` — hourly spend reconstruction per service account in DuckDB
6. [ ] Implement `SPEND_SPIKE`, `DORMANT_KEY_WAKE`, `NEW_GEO` against that series
7. [ ] Timeline chart: spend curve, detection point, invoice-discovery point, rupees between them
8. [ ] `gtm/case-study-incident.md` — anonymised write-up

**In parallel, not blocked on code:**

9. [ ] `gtm/discovery-script.md` — question set for the 30 calls
10. [ ] `gtm/gate-tracker.md` — running score against the five gates

---

## Blocked

| Item | Blocked on | Who |
|---|---|---|
| Backtest | GCP billing export access for the incident window | Mahikshith |
| Anything touching employer data | IP / data-use position | Mahikshith |

---

## Decision log

| Date | Decision |
|---|---|
| 2026-08-15 | Both visibility **and** enforcement, sequenced — visibility lands, enforcement is the moat |
| 2026-08-15 | India-domestic first, contingent on Gate 3 (DPDP/residency raised unprompted) |
| 2026-08-15 | Agentless only — no gateway, no SDK instrumentation |
| 2026-08-15 | Self-hosted collector; we never store customer credentials |
| 2026-08-15 | Python data plane; Streamlit for the throwaway v0 tool, Next.js for the real product UI |
| 2026-08-15 | Vendor LiteLLM pricing JSON, never install the package (supply-chain attack) |
| 2026-08-15 | Backtest before product — the artifact opens 30 doors, the product opens none yet |
