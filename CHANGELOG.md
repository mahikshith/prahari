# Changelog

All notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is [SemVer](https://semver.org/).

Architectural and licence decisions are recorded here as well as code changes — per `docs/OSS_INVENTORY.md`, any adoption of an ELv2/BSL/SSPL dependency requires an explicit entry.

## [Unreleased]

### Security — full-codebase review, all findings fixed
Written up in `docs/SECURITY_REVIEW.md`; each is pinned by a regression test in `tests/test_security.py`.

- **High — SQL injection via the BigQuery table identifier.** Table names cannot be bound parameters, so `project.dataset.table` is interpolated into the query; it was unvalidated. Harmless from an env var, exploitable once per-tenant config supplies it in the multi-tenant control plane. Now allowlisted to `[A-Za-z0-9_-]` plus the legacy domain-scoped project form.
- **High — non-finite costs drove false enforcement.** `Decimal` accepts `Infinity`, which compares greater than every budget limit, so a malformed upstream response would mark all budgets exceeded and, under `HARD_STOP`, revoke production credentials. `NaN` propagated silently through every `sum()` and raised far from its cause. Added `core/money.py` plus a `UsageRecord` validator at the single choke point.
- **Medium — price registry failed open.** Checksum verification was skipped when the `.sha256` file was absent, so deleting it was enough to swap the pricing data that drives every cost figure and enforcement decision. Now a hard error, compared with `hmac.compare_digest`.
- **Medium — admin keys leaked through HTTP exceptions.** `raise_for_status()` produces an error holding the request, whose headers contain the admin key; any error tracker or `exc_info` log line would exfiltrate it. Replaced with `raise_for_status_safely()` → `ProviderHTTPError`, carrying only status, path and a truncated body, raised `from None`.
- **Low — report output not gitignored.** `out/` will hold real spend figures once connectors are live.

### Performance
- **Budget evaluation: 5 budgets 46 ms → 17 ms, 40 budgets 386 ms → 84 ms.** Marginal cost per budget fell 9.7 ms → 1.9 ms. Budgets are grouped by `(period, currency)` so windowing and currency conversion happen once; `PreparedWindow` then carries an inverted `dimension → value → row indices` index, so a scoped budget visits only its own rows instead of all of them. Correctness pinned by tests comparing the indexed path against a naive scan across six scope shapes.
- **Bounded detector state.** `Baseline.hour_of_week_spend` was uncapped — 9,600 entries after a 400-day replay, with `expected_spend` averaging an ever-longer list. Capped at 8 samples per hour-of-week slot; `hourly_spend` is now a `deque(maxlen=…)` since `list.pop(0)` is O(n).
- Cached FX rate lookups and `premium_models()`.

### Added — budgets, allocation insights, FX
- **Budget engine** (`core/budget.py`). Budgets scoped by an arbitrary set of dimensions rather than a single enum, so every shape customers ask for falls out of one model — org-wide, per-project, per-service, per-cost-centre, per-user, per-credential, and the composite case (₹2 lakh on Cloud Run *inside* one project). Burn rate, linear forecast, projected overage, exhaustion date, threshold crossing with re-fire suppression, and top contributors.
- **Enforcement policy with dry-run default** (`decide_enforcement`). `ALERT_ONLY` / `THROTTLE` / `HARD_STOP`. `would_affect` lists the credentials an action would hit and is computed even in dry-run, because that list is the entire content of the conversation where a customer decides whether to grant write access.
- **Consumption insights** (`core/insights.py`). Per-user token consumption with blended ₹/M-token, top and bottom consumers by any dimension, period-over-period movers ranked by absolute change, allocation coverage against the 85% target (F3.2), and the AI-vs-cloud category split.
- **Dated FX** (`core/fx.py`). INR budgets against USD provider costs, using the rate in force on the transaction date. Never interpolates forward, never guesses a missing rate. Indian digit grouping and lakh/crore scaling.
- **Synthetic fleet** (`synth/fleet.py`) — four projects, four services, five users, a month of ordinary spend, with a deliberate Cloud Run blowout, a single catastrophic BigQuery query day, and an unlabelled slice so allocation coverage reports an honest number.
- `scripts/report.py` — the FinOps-lead view end to end.

### Fixed
- **Budget periods now close on IST calendar boundaries, and the fleet scenario is aligned to them.** Indian finance closes on IST; computing month bounds in UTC put 5.5 hours of spend in the following month. The synthetic fleet spanned a UTC month, so `as_of` landed in August and every budget evaluated against a nearly empty period while still reporting a confident number. Two regression tests pin it.

### Added — GCP coverage
- **GCP BigQuery billing export connector** covering every GCP service in one query: Vertex AI, BigQuery, Cloud Run, Compute, Storage, egress. Net-of-credits cost arithmetic, `_PARTITIONTIME` pruning, hourly buckets keyed on usage time rather than export time, billing-account currency preserved (Indian accounts export INR natively), `ai`/`data`/`compute` service classification, and unit economics for the two services customers ask about most after AI — BigQuery TiB scanned and Cloud Run vCPU-hours.
- `scripts/setup_remote.ps1` — creates the **private** GitHub repo and pushes. Refuses to run if `.env` is tracked or if a pre-existing repo is public.

### Fixed
- **`detection_key` fallback skipped `project_id`.** GCP's billing export carries no caller identity, so every project would have collapsed into a single org-wide baseline — a noisy project would mask an attack in a quiet one. Found by a test written specifically to pin the "no caller identity" limitation.

### Discovered
- **A11 — the GCP billing export has no caller identity.** It knows project, service, SKU and resource; never who called. GCP detection from billing alone is therefore project-level, and `DORMANT_KEY_WAKE` / `NEW_GEO` cannot work from it at all. Credential-level detection on GCP requires a second connector over Cloud Audit Logs (`principalEmail`, `callerIp`). The connector shipped here is the allocation half; the detection half is still missing.

### Added — autonomous session, 2026-08-15
- Incident backtest (`scripts/backtest_incident.py`) producing the Stage 0 artifact: detection at ₹72,359, ten days and ₹5.84 crore before the invoice. Runs on synthetic data calibrated to published LLMjacking rates.
- Synthetic incident generator (`src/prahari/synth/incident.py`) — two credentials: a legitimate control and a stale decommissioned key that leaks.
- `UsageRecord` → `Observation` aggregation with gap filling (`detect/aggregate.py`).
- Anthropic and OpenAI connectors, with mocked tests against the documented API shapes.
- LiteLLM price registry vendored at pinned SHA `4ea5749` (2,427 models), sha256-verified on load.
- `ASSUMPTIONS.md` — the autonomous-mode contract: every assumption logged with blast radius and how to verify.
- GTM artifacts: case study, 30-call discovery script, gate tracker.

### Fixed — two real bugs, found while wiring the backtest
- **`detection_key` included model and region.** An attacker switching models received a fresh, empty baseline — precisely the evasion `MODEL_ESCALATION` exists to catch. Baselines are now per-credential.
- **Gap-filled zero hours refreshed `Baseline.last_seen`**, so `DORMANT_KEY_WAKE` could never fire. `last_seen` now tracks activity rather than observations; zero hours still feed the spend baseline so the norm stays honest.

### Changed
- **Unified platform recorded as the North Star** — all cloud cost (BigQuery, Cloud Run, GKE, storage), not only AI. AI cross-provider remains the wedge. Entering from AI and expanding into cloud is the opposite of every incumbent's path and the better one: the security moat only exists on the AI side, and cloud then becomes an expansion sale rather than a displacement fight.
- `premium_models()` now requires a provider — unfiltered, re-hosted variants (`wandb/`, `watsonx/`) dwarf the frontier models and `MODEL_ESCALATION` would fire on nothing.
- Synthetic scenario moved to `gemini-2.5-*`; `gemini-1.5-*` has been deprecated out of the upstream registry.

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
