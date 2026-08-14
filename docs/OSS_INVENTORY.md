# Open Source We Reuse

**Check this file before writing anything from scratch.** Researched Aug 2026. Licence column is load-bearing — we are building a commercial product, and two entries below are licence traps.

## Tier 1 — Use directly, these are large wins

### LiteLLM price registry — `model_prices_and_context_window.json`
`github.com/BerriAI/litellm` · **MIT** · **The single biggest build-avoidance win.**

Canonical community pricing registry for 400+ models: input/output price per token, context windows, provider mappings, cache and batch tiers. Maintaining this ourselves would be a permanent tax — provider pricing changes weekly and every competitor is quietly fighting the same battle.

> **Security note, mandatory:** LiteLLM's **PyPI package** suffered a confirmed supply-chain attack in March 2026 (backdoored builds with a credential-stealing payload). We are building a product that handles AI credentials — that is precisely the payload's target.
> **Therefore: vendor the JSON file only. Do not `pip install litellm`.** Pin a commit SHA, checksum it, and refresh through a reviewed PR. See `src/prahari/pricing/`.

### FOCUS 1.3 — FinOps Open Cost & Usage Specification
`focus.finops.org` · **Linux Foundation / open spec** · ratified 5 Dec 2025

Our normalisation target. Critically, **AWS, Azure, GCP, Oracle, Alibaba and 6+ others now emit native FOCUS-conformant billing exports** — so for cloud AI spend we consume a standard rather than writing bespoke parsers per provider. 1.3 adds contract commitments, shared-cost splitting, and data recency/completeness flags (that last one matters for our latency claims).

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
| **Gitleaks** / **TruffleHog** | MIT / AGPL* | Secret scanning for the credential-leak side. *TruffleHog is AGPL — shell out to the binary, never link it into our code* |
| **Grafana OSS** / **Metabase** | AGPL / AGPL | Internal dashboards only, run as separate services. Never embedded or redistributed |
| **cloud-cost-analyzer** (`ssp-data`) | check repo | Reference blueprint: multi-cloud cost with dlt + DuckDB. Read the architecture, don't take a dependency |
| **OpenCost** (CNCF) | Apache 2.0 | Kubernetes/GPU cost allocation. Only when a customer has self-hosted GPU inference — deferred |

## Tier 3 — Evaluated and rejected (with reasons)

| Project | Why not |
|---|---|
| **Steampipe** | Genuinely excellent — SQL over live cloud APIs, 150+ plugins. **AGPL.** Fine as a personal exploration tool during discovery; do not embed it in the product or link against it |
| **CloudQuery** | Strong FinOps-oriented ELT, 70+ integrations, but core licensing moved to ELv2/commercial. Not safe to build a commercial product on. Verify current terms before reconsidering |
| **LangFuse / Helicone / Portkey** | Wrong layer entirely — trace/gateway, requires instrumentation, and blind to a stolen credential calling a provider directly. That blindness is our whole differentiator; adopting them would inherit it |
| **Prophet** | Overkill and slow for spend baselines, and opaque. EWMA + STL is more explainable to a CFO and faster |
| **PyOD / dtaianomaly** | Research-grade breadth we don't need. Our detection is 5 named rules, not a model zoo. Revisit only if the rules provably underperform |

## Licence rules for this repo

1. **MIT / Apache 2.0 / BSD** — free to use and link.
2. **AGPL** — only as a separately-run process we shell out to or deploy alongside. Never linked, never embedded, never redistributed inside our image.
3. **ELv2 / BSL / SSPL** — do not adopt without an explicit written decision recorded in `CHANGELOG.md`.
4. Every new dependency gets a line in this file with its licence. No exceptions — an enterprise security questionnaire will ask for exactly this list, and having it ready is worth days of sales cycle.
