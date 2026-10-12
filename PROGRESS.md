# Prahari progress

**Updated:** 2026-10-12.
**Stage:** pilot foundation repair; live-source/customer acceptance pending.
**Repository:** GitHub remote exists at https://github.com/mahikshith/prahari.
**Working branch:** codex/prahari-pilot-foundation.
**Hourly user/account cost feature:** feasibility/integration work deferred at the founder's request on 2026-10-12; resume from the checklist in [PILOT_PLAN.md](docs/PILOT_PLAN.md) before implementation.
**Final integrated verification:** 334 tests passed in 12.44s; Ruff, dependency-lock and whitespace checks passed on 2026-10-12. Synthetic backtest smoke passed. Docker is unavailable; no container build/runtime or live-provider checks were performed.

Read [CLAUDE.md](CLAUDE.md) → [docs/DECISIONS.md](docs/DECISIONS.md) for current direction. Historical 47/205-test counts and local-only/no-remote notes are not current verification evidence.

## Local implementation

The repository contains Python/DuckDB persistence, collector scheduling, OpenAI/Anthropic usage/cost connectors, GCP billing ingestion, explainable detection, budget/insight calculations, console/Slack/SMTP notifications and container configuration.

The current changes address:

- Nullable unknown cost and source/provenance through connectors, storage, reports, budgets and detection; incomplete money cannot authorize monetary enforcement.
- Precise Decimal accumulation, aware UTC time and explicit dated daemon FX; provider-specific cached-token/cost/unit handling.
- Durable per-channel alert/budget retries, persisted acknowledgements and retry backoff.
- Provisional GCP billing scans, separate scan state, one-day overlap and invoice/cost-type record identity.
- Last activity outside the rolling 30-day detection replay.
- Error/body credential exposure, notification transport and build/runtime boundaries.
- Exact pricing-registry byte preservation and single enabled organization per shared admin-provider credential.

Regression fixtures accompany these changes. The integrated results above do not establish live provider, invoice or customer outcomes. [Decision entries D007–D022](docs/DECISIONS.md) retain the implementation rationale and acceptance limits. Back up an existing store before the schema-v2 upgrade; a downgrade migration is not supplied.

## Product and research records

The pilot is GCP + OpenAI, one shared core for both buyer groups, customer-owned India deployment first and optional gateway telemetry/control later. The hybrid decision supersedes the older agentless-only preference.

[Current pilot plan](docs/PILOT_PLAN.md) records the repository assessment and phased acceptance. [Market research](docs/MARKET_RESEARCH.md) distinguishes source evidence, vendor capabilities and pilot hypotheses. [Network telemetry](docs/NETWORK_TELEMETRY.md) is a sourced metadata-only plan. The [case study](gtm/case-study-incident.md) separates the founder report from synthetic scenarios and avoids measured-savings claims.

[Critical OSS assessment](docs/OSS_ASSESSMENT.md) records inspected editions, reported upstream issues and conformance trials; defects were not reproduced locally. [India regulation](docs/INDIA_REGULATION.md) separates enacted/commenced duties, sector scope and unresolved applicability; it is not a compliance certification.

## Remaining acceptance and work

1. Build/run the container in an available Docker environment; local suite/lint/lock/registry checks have passed.
2. Obtain authorized founder/customer GCP + OpenAI fixtures and measure field coverage/freshness. Employer data remains separately gated.
3. Add GCP audit correlation and source-completeness evidence; billing alone cannot establish credential-level cost.
4. Reconcile settled provider invoices, including corrections older than the one-day overlap.
5. Run paid design-partner discovery/pilots with written success criteria.
6. Implement and validate scoped gateway budget admission and provider response in a sandbox before live controls.
7. Evaluate one-workload network metadata ingestion after source acceptance, using existing logs first.

No live cloud logging/network policies, gateway deployment or provider credential revocation has been enabled. No production false-positive rate, detection SLA, avoided loss, certification or customer willingness-to-pay has been established.

## Local checks

```powershell
uv sync --extra dev
uv run python -m pytest -q
uv run ruff check src tests scripts
uv run prahari validate -c prahari.example.yaml
uv run python scripts/backtest_incident.py
```

The example config parses and correctly reports missing OpenAI/Anthropic admin keys (exit 1); an optional GCP key-file path is no longer treated as mandatory. Actual ADC authentication requires provider verification. The registry SHA-256 remains `e7c0872654c7af4adc8a2b52b4a10a5e70e88e8e9c119f78c52d18ec8e1bd616`.

The backtest and report use synthetic fixtures. The backtest emits explicit bucket-timing, no-response and no-proven-avoided-loss fields. Missing credentials or FX are configuration/coverage results, not evidence that an account has no spend.
