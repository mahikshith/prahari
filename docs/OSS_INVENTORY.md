# Open Source We Reuse

**Consistency review: 2026-10-12.** This design catalog includes deferred targets, not a shipped-feature inventory. Current scope and outcomes are in [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](../PROGRESS.md): GCP + OpenAI, hybrid collection, customer-owned India cloud first, and live-source/response acceptance still required.

Check existing components before writing new code. This August candidate inventory is not a complete dependency license audit; verify pinned versions, commercial directories, transitive licenses and redistribution notices before adoption.

## Tier 1 — Use directly, these are large wins

### LiteLLM price registry — `model_prices_and_context_window.json`
`github.com/BerriAI/litellm` · **MIT** · **The single biggest build-avoidance win.**

Canonical community pricing registry for 400+ models: input/output price per token, context windows, provider mappings, cache and batch tiers. Maintaining this ourselves would be a permanent tax — provider pricing changes weekly and every competitor is quietly fighting the same battle.

> **Security note, mandatory:** LiteLLM's **PyPI package** suffered a confirmed supply-chain attack in March 2026 (backdoored builds with a credential-stealing payload). We are building a product that handles AI credentials — that is precisely the payload's target.
> **Current collector choice:** vendor JSON with pinned provenance/checksum and preserve exact bytes via .gitattributes; do not add the PyPI package to the collector. The [maintainer incident report](https://docs.litellm.ai/blog/security-update-march-2026) identifies affected PyPI versions and says official Proxy Docker/GitHub source were not impacted. Any separately reused gateway still needs its own recorded dependency/security decision; hybrid scope does not silently approve a supplier.

### FOCUS 1.3 — FinOps Open Cost & Usage Specification
`focus.finops.org` · **Linux Foundation / open spec** · ratified 5 Dec 2025

FOCUS is a terminology/normalization target; the prototype is not certified conformant. Provider export versions and gaps differ, so retain explicit mappings. The [FOCUS FAQ](https://focus.finops.org/faqs/) explains adoption is provider-controlled; [version 1.3](https://focus.finops.org/docs/specification/v1-3/) is licensed CC-BY-4.0 and includes recency/completeness concepts.

Adopting FOCUS also means a FinOps-literate buyer recognises our schema on sight. That is a sales asset, not just an engineering one.

### Microsoft FinOps Toolkit
`github.com/microsoft/finops-toolkit` · **MIT**

Free reference implementation for exactly our hardest Azure problem: turning Azure OpenAI **token** consumption into FOCUS-aligned unit economics. Includes Cost Management export configs, FinOps Hubs IaC, and Power BI templates. Read their token→unit-economics approach before writing the Azure connector.

### dlt (data load tool)
`dlthub.com` · **Apache 2.0**

Python-first ingestion framework: automatic schema inference and evolution, incremental loading, pipeline state. This is exactly the connector problem — provider payloads mutate, and we must backfill arbitrary ranges idempotently. Hand-rolling this is weeks of work we'd get wrong.

### DuckDB
**MIT** — embedded columnar analytics. Reads Parquet/CSV/JSON directly. The backtest and every reconciliation run go through it. Zero ops.

### tokencost
`github.com/AgentOps-AI/tokencost` · **MIT**

Token counting + cost estimation for 400+ models, itself sourced from the LiteLLM registry. Use for *forward estimation* (what will this cost) where we need it. Our billed-cost path stays on provider-reported numbers — never estimate what the provider will tell you exactly.

## Tier 2 — Use for specific jobs

| Project | Licence | Use for |
|---|---|---|
| **statsmodels** (STL decomposition) | BSD | Weekly/daily seasonality in spend baselines. Engineering teams have a very strong weekday pattern — naive thresholds will alert every Monday |
| **Gitleaks** / **TruffleHog** | Verify pinned MIT / AGPL terms | Candidate secret scanning; process separation alone is not a license safe harbor. Review integration, modifications and distribution before adoption |
| **Grafana OSS** / **Metabase** | AGPL / AGPL | Internal dashboards only, run as separate services. Never embedded or redistributed |
| **cloud-cost-analyzer** (`ssp-data`) | check repo | Reference blueprint: multi-cloud cost with dlt + DuckDB. Read the architecture, don't take a dependency |
| **OpenCost** (CNCF) | Apache 2.0 | Kubernetes/GPU cost allocation. Only when a customer has self-hosted GPU inference — deferred |

## Tier 3 — Evaluated and rejected (with reasons)

| Project | Why not |
|---|---|
| **Steampipe** | Genuinely excellent — SQL over live cloud APIs, 150+ plugins. **AGPL.** Fine as a personal exploration tool during discovery; do not embed it in the product or link against it |
| **CloudQuery** | Deferred candidate. Verify exact component/version/license and intended commercial use before adoption; a source-available license is not a blanket prohibition on all commercial use |
| **Langfuse / Helicone / Portkey** | Optional tracing/gateway reuse candidates under the selected hybrid design. Routed coverage misses direct-key bypass; combine with audit/billing evidence. No full additional stack or supplier is approved by this inventory |
| **Prophet** | Overkill and slow for spend baselines, and opaque. EWMA + STL is more explainable to a CFO and faster |
| **PyOD / dtaianomaly** | Research-grade breadth we don't need. Our detection is 5 named rules, not a model zoo. Revisit only if the rules provably underperform |

## Licence rules for this repo

1. **MIT / Apache 2.0 / BSD** — generally permissive; verify the exact component/version and preserve required notices.
2. **AGPL** — review the actual combined-work, modification, network-service and distribution boundaries. Shelling out/deploying separately is not a universal exemption; see [GNU guidance](https://www.gnu.org/licenses/gpl-faq.en.html).
3. **ELv2 / BSL / SSPL and commercial editions** — review applicable terms and record adoption with evidence in DECISIONS.md and CHANGELOG.md.
4. Every new dependency gets a line in this file with its licence. No exceptions — an enterprise security questionnaire will ask for exactly this list, and having it ready is worth days of sales cycle.
