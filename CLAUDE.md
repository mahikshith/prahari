# CLAUDE.md

## Purpose and current scope

Prahari is an AI spend observability/control prototype. The founder reports weekend unauthorized Gemini use after service-account exposure, with roughly ₹6–7 crore of cost/exposure. Detailed incident facts, paid losses and employer-data permission remain unverified. Synthetic replays are always labeled synthetic.

The current pilot is GCP + OpenAI, built by a solo founder with AI assistance. Startup/midmarket and regulated enterprise buyers share one core. Customer-owned India cloud deployment comes first; India-hosted SaaS comes later. Broad cloud FinOps, SaaS-seat discovery, other providers and certifications are later work.

Read [docs/DECISIONS.md](docs/DECISIONS.md) for accepted decisions and their evidence/outcomes. [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md) contains the competitive evidence and product hypotheses; do not repeat historical “no competitors” or blanket DPDP localization claims.

## Architecture decisions

- **Hybrid:** agentless audit/billing collection plus an optional reused gateway for routed request telemetry and budget admission. The founder's choice explicitly supersedes the older agentless-only/no-gateway/no-SDK preference. A direct stolen-key call can bypass the gateway.
- **Existing foundation:** retain Python, DuckDB, provider connectors, collector scheduling, explainable rules and notifications. PostgreSQL/production SaaS follows a demonstrated tenancy/concurrency or gateway need.
- **Evidence:** keep estimated, provider-reported and unpriced costs distinct. Null cost is not zero. Preserve timing, source completeness and attribution uncertainty; project/time joins do not prove exact credential spend.
- **Safety:** read-only collection and dry-run policy decisions first. Live provider revocation, gateway blocking and cloud/network controls require their scoped implementation and sandbox validation; none is enabled in the foundation change.
- **Network:** metadata only; no packet payload interception or TLS decryption. See [docs/NETWORK_TELEMETRY.md](docs/NETWORK_TELEMETRY.md). IP endpoints cannot prove physical processing region.
- **Deployment:** customer-held credentials/data with explicit notification, backup and support destinations. India hosting is a product choice, not a compliance certificate.

## Engineering conventions

- Money uses finite Decimal values and stays precise until presentation. Preserve amount, currency, cost basis and source.
- Store aware UTC timestamps. Apply IST calendar boundaries where the budget contract requires them. Supply daemon FX rates with date and source; never substitute synthetic demo rates for customer FX.
- Keep provider unit, pagination and payload quirks at connector boundaries. FOCUS terminology is an alignment target, not a conformance claim.
- Collection is idempotent and backfillable. GCP export scans remain provisional, with a bounded overlap; older corrections require invoice-period reconciliation.
- Preserve notification delivery results per channel. Retry durable failures; console output does not acknowledge configured remote delivery. At-least-once delivery can duplicate after a crash between remote acceptance and local persistence.
- Keep secrets out of config values, logs, exceptions, build inputs and Git. GCP credential files remain customer-provided. Provider errors expose status/path, not headers or response bodies.
- Require protected delivery for remote notifications. Do not suppress certificate errors or downgrade authenticated SMTP to plaintext.
- Preserve the exact checksum-verified pricing registry bytes. Review provenance and license scope before any dependency/gateway adoption.
- Current shared OpenAI/Anthropic environment credentials support one enabled organization per provider/process. Do not claim multi-organization credential isolation.

## Working records and validation

Read CLAUDE.md → [PROGRESS.md](PROGRESS.md) → [docs/DECISIONS.md](docs/DECISIONS.md), then relevant requirements and architecture. Older [ASSUMPTIONS.md](ASSUMPTIONS.md) entries are historical pending verification; current decisions supersede conflicting preferences.

Update progress and the relevant stable decision ID when behavior or evidence changes. Record expected and actual outcomes separately. Add focused regression checks for non-trivial money/security/recovery changes; final suite/lint and live acceptance are distinct. Do not infer production reliability from fixtures.

Use authorized feature branches and preserve unrelated work. Repository publishing/commits follow the current human authorization; historical local-only/private-repo notes are not current access facts. Never use employer information without its separate authorization.
