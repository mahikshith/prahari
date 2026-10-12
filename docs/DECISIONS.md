# Prahari decision log

This is the durable record of material product and engineering decisions. It explains the observable rationale, why each choice matters, its tradeoff, and the expected and actual outcome. Stable IDs remain unchanged; superseded entries stay in history and point to their replacements.

**Recorded:** 2026-10-12. **Owner:** founder. **Branch:** codex/prahari-pilot-foundation.
**Validation summary:** on 2026-10-12, 334 local tests passed in 12.44s; Ruff, dependency-lock and whitespace checks passed. Synthetic backtest smoke passed; registry SHA-256 remains pinned. Docker is unavailable. Local regression fixtures are not live-provider, invoice or production validation.

Status means **accepted** for a product choice, **implemented locally** for a code change that passes local checks but awaits live acceptance, **recommended** for a proposed priority awaiting founder review, and **deferred** for work deliberately not enabled. Future changes must add a date and actual evidence rather than turn expected outcomes into claims.

## D001 GCP and OpenAI are the first pilot providers

**Date:** 2026-10-12. **Status:** accepted.
- **Decision and evidence:** prioritize GCP Vertex AI billing/audit coverage and OpenAI usage/costs, as selected by the founder. Keep the existing Anthropic connector without widening the pilot.
- **Rationale and importance:** reproduce the founding risk and show cross-provider value while limiting a solo founder's maintenance burden. Other providers and SaaS seats are deferred.
- **Expected outcome and acceptance:** live authorized fixtures establish field coverage, timing and invoice reconciliation for both providers.
- **Actual outcome:** connectors exist; live-source and invoice acceptance remain pending.

## D002 Two buyer groups share one core

**Date:** 2026-10-12. **Status:** accepted.
- **Decision and evidence:** startup/midmarket and regulated enterprise buyers use the same accounting, coverage, detection and policy core. The founder works with AI assistance.
- **Rationale and importance:** prevent two products and a service burden beyond the team's capacity. Enterprise evidence and deployment needs add requirements; they do not imply certifications.
- **Expected outcome and acceptance:** score discovery separately by segment; target three paid pilots and two renewals/expansions before broadening scope.
- **Actual outcome:** buyer and willingness-to-pay evidence is pending; targets are not traction.

## D003 Customer owned India deployment comes before SaaS

**Date:** 2026-10-12. **Status:** accepted.
- **Decision and evidence:** run the collector and its records in the customer's India cloud first; India-hosted SaaS is later.
- **Rationale and importance:** constrain credential/data exposure and simplify initial customer trust. It increases customer installation/support work.
- **Expected outcome and acceptance:** document storage, backups, keys, logs, notification and support destinations with each customer. Review applicable law/contracts separately.
- **Actual outcome:** container packaging exists; customer deployment and residency acceptance are pending. India hosting is not a compliance certificate.

## D004 Hybrid collection supersedes the agentless only ban

**Date:** 2026-10-12. **Status:** accepted.
- **Decision and evidence:** the founder selected agentless audit/billing collection plus an optional reused gateway for routed requests and budget admission. This supersedes the earlier no-gateway/no-SDK product preference.
- **Rationale and importance:** billing alone is delayed and lacks request identity; routed telemetry alone misses stolen-key bypass. Combining evidence exposes both coverage and control limits.
- **Expected outcome and acceptance:** one shared core labels source/provenance; controlled bypass and concurrent routed requests exercise separate detection and blocking paths.
- **Actual outcome:** the hybrid design is recorded. No live gateway or SDK rollout is implemented or enabled.

## D005 Keep Python and DuckDB for the foundation

**Date:** 2026-10-12. **Status:** accepted.
- **Decision and evidence:** retain the existing Python collector and DuckDB store. Add PostgreSQL when tenancy/concurrency or a selected gateway requires it; defer a separate production frontend.
- **Rationale and importance:** reuse working code and reduce operations. DuckDB's local deployment does not establish distributed or multi-tenant guarantees.
- **Expected outcome and acceptance:** deterministic local replay, durable state and repeatable installation; reevaluate storage at the next real deployment constraint.
- **Actual outcome:** Python/DuckDB implementation exists. PostgreSQL and production SaaS remain deferred.

## D006 Repair the foundation before enabling controls

**Date:** 2026-10-12. **Status:** accepted.
- **Decision and evidence:** address accounting, source completeness, notification recovery and credential handling with regression checks before live gateway/cloud/network controls.
- **Rationale and importance:** incorrect money or a lost alert undermines a spend-control product; premature response actions can disrupt legitimate workloads.
- **Expected outcome and acceptance:** final suite/lint pass, then live read-only source and sandbox response checks with explicit scope.
- **Actual outcome:** the 334-test suite and local lint/lock checks pass. No cloud logging, network enforcement or provider credential revocation has been enabled.

## D007 Unknown prices remain nullable with provenance

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** represent unavailable cost as a null billed_cost with cost_basis distinguishing unpriced, estimated and provider-reported records.
- **Rationale and importance:** zero is a valid known charge, not missing information. Keep known subtotals and activity without fabricating totals, spend baselines or financial enforcement.
- **Expected outcome and acceptance:** missing-price records survive persistence; coverage warnings appear; incomplete budgets cannot trigger monetary enforcement. Evidence: tests/test_money_coverage.py and tests/test_detection_coverage.py.
- **Actual outcome:** model, connector, persistence, budget/report and detection regressions pass in the integrated suite. Live reconciliation remains pending.

## D008 Preserve monetary precision and configure dated FX

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** keep Decimal precision until presentation; normalize timestamps to UTC; supply daemon FX rates explicitly with date and source. Do not use synthetic placeholder rates in customer operation.
- **Rationale and importance:** tiny charges accumulate; mixing currencies or future FX rates changes budgets and severity. Missing FX produces coverage evidence rather than invented conversion.
- **Expected outcome and acceptance:** validate finite positive rates, dated lookup, UTC boundaries and INR thresholds. Evidence: tests/test_money_coverage.py, tests/test_detection_coverage.py and tests/test_container_config.py.
- **Actual outcome:** explicit-rate, precision, currency and UTC regressions pass. Customer FX source acceptance remains pending.

## D009 Normalize provider units at the boundary

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** correct Anthropic cost-report cents to USD, OpenAI inclusive cached-token accounting and cost currency checks, and GCP credit/cost-type/invoice identity handling. Preserve raw units; token-storage quantities are not inference tokens.
- **Rationale and importance:** a correct total requires provider-specific semantics; one universal token formula misprices caches, credits and storage.
- **Expected outcome and acceptance:** fixtures check units, cached subsets, invoice adjustments and unsupported shapes. Evidence: tests/test_connectors.py and tests/test_gcp_connector.py.
- **Actual outcome:** local fixes are present. Provider account/invoice reconciliation remains pending.

## D010 Persist notification state per channel

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** use a durable outbox with per-channel results, retry delay and acknowledgement. Console output does not acknowledge configured remote delivery; persisted successful channels are not retried for another channel's failure.
- **Rationale and importance:** an alert in a terminal is not a received page. At-least-once delivery can still duplicate after remote acceptance but before local persistence; a service response does not prove human receipt.
- **Expected outcome and acceptance:** restart/partial-failure tests preserve failed alert and budget messages and avoid repeating recorded successes. Evidence: tests/test_delivery_recovery.py and tests/test_notifications.py.
- **Actual outcome:** restart, partial-failure, retry and acknowledgement regressions pass in the integrated suite. Real notification-endpoint acceptance remains pending.

## D011 Treat GCP billing scans as provisional

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** retain source incompleteness, use a separate scan watermark and refresh one day's overlap in incremental billing scans. Keep invoice-month and cost-type distinctions.
- **Rationale and importance:** export arrival is not settled billing. Bounded scans permit progress, but corrections older than the overlap can be missed without invoice-period reconciliation.
- **Expected outcome and acceptance:** fixtures retain late rows/adjustments without duplicates; a settled invoice replay recovers older corrections. Evidence: tests/test_gcp_connector.py and tests/test_delivery_recovery.py.
- **Actual outcome:** bounded provisional scans are present. Automated invoice-period reconciliation and live completeness evidence are pending.

## D012 Remove secret bearing errors and require protected delivery

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** provider HTTP errors expose only status/path, excluding request headers and response bodies. Require HTTPS for Slack and TLS for authenticated SMTP; exclude credentials/customer data from build inputs and keep runtime code protected.
- **Rationale and importance:** providers can echo secrets in error bodies; operational tooling must not leak the credentials it monitors. Certificate failures must fail delivery rather than downgrade.
- **Expected outcome and acceptance:** adversarial errors and insecure delivery settings are rejected without leaking secrets. Evidence: tests/test_security.py, tests/test_notifications.py and tests/test_container_config.py.
- **Actual outcome:** targeted error-redaction, notification-security and container-config regressions pass. Live TLS/channel checks and container runtime remain unverified. This is a targeted review, not a security certification.

## D013 Preserve the exact verified pricing registry bytes

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** continue vendoring the pricing data with pinned provenance/checksum; use .gitattributes to prevent line-ending conversion of the JSON. Gateway dependency adoption is a separate reviewed decision.
- **Rationale and importance:** checkout byte conversion can break verification, while skipping verification would accept untrusted prices. A checksum is integrity evidence, not proof every model rate is current.
- **Expected outcome and acceptance:** clean checkout loads the verified registry; missing/mismatched checksums fail. Evidence: tests/test_security.py and src/prahari/pricing/vendor/PROVENANCE.md.
- **Actual outcome:** registry verification tests pass and local SHA-256 equals the pinned `e7c0872654c7af4adc8a2b52b4a10a5e70e88e8e9c119f78c52d18ec8e1bd616`. Exact JSON bytes are unchanged; .gitattributes prevents checkout conversion. Cross-platform clean checkout is not tested separately. Existing suffix-based alias fallback and price freshness need provider-specific conformance before financial controls.

## D014 Retain activity older than the spend replay window

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** seed the detector with persisted last activity before its 30-day replay; count requests/tokens as activity even when cost is free or unknown. Baselines remain per credential, not per model/region.
- **Rationale and importance:** dropping older activity hides dormancy after restart; switching models must not create a fresh credential baseline. Missing earlier history still limits certainty.
- **Expected outcome and acceptance:** old known activity enables dormancy findings, while gap-filled silence never refreshes it. Evidence: tests/test_detection_coverage.py and tests/test_delivery_recovery.py.
- **Actual outcome:** old-history and free/unpriced-activity regressions pass. Real baseline calibration remains pending.

## D015 Network metadata supplements cost and audit evidence

**Date:** 2026-10-12. **Status:** accepted; integration deferred.
- **Decision and evidence:** use source/destination/time/bytes/direction/vantage/coverage metadata with DNS, audit and gateway correlation. No packet-content interception or TLS decryption. See [NETWORK_TELEMETRY.md](NETWORK_TELEMETRY.md).
- **Rationale and importance:** sampled flows cannot count every token, prove content/inference geography, or see an external attacker bypassing the customer's VPC.
- **Expected outcome and acceptance:** one-workload sanitized fixtures show known routes, sampling gaps, NAT/private routing and external bypass explicitly.
- **Actual outcome:** the sourced integration plan exists; no logging has been enabled and no network connector is implemented.

## D016 Limit each shared admin credential to one organization

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** reject multiple enabled collectors for the same OpenAI/Anthropic provider in one process while that provider shares an environment credential.
- **Rationale and importance:** relabeling the same credential across account IDs can misattribute spend or duplicate collection. Separate credential-bound collectors are required before supporting multiple organizations.
- **Expected outcome and acceptance:** config rejects duplicate enabled organizations but allows disabled entries and different providers. Evidence: tests/test_money_coverage.py.
- **Actual outcome:** the configuration guard is present; true multi-organization credential management is deferred.

## D017 Separate reported incident facts from simulations

**Date:** 2026-10-12. **Status:** accepted and documented.
- **Decision and evidence:** describe only the founder-reported weekend exposure of roughly ₹6–7 crore as the origin. Mark all replay/detection/control scenarios synthetic; publish measured outcomes only with authorized source and timing evidence.
- **Rationale and importance:** invented leak mechanisms, dormancy/duration details or “money saved” claims would turn a useful fixture into misleading traction.
- **Expected outcome and acceptance:** overview/case study label facts, hypotheses and simulation outcomes; research distinguishes vendor claims from a competitive test.
- **Actual outcome:** the case study/project summaries and backtest output separate reported facts from simulation. Backtest JSON uses explicit bucket timestamps, later-bucket spend and false response/avoided-loss flags; 20 backtest tests pass within the integrated suite. Actual invoice amount, employer-data permission, measured detection and avoided loss remain unverified.

## D018 Freeze delivery targets and prevent queue starvation

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** freeze the original message and channel set per queued event; filter inactive channels before queue limits and seed only alerts not already queued, with critical priority.
- **Rationale and importance:** configuration changes must not silently erase a failed delivery or add new obligations to historical messages. Old failed/inactive rows must not prevent a new critical incident from entering delivery.
- **Expected outcome and acceptance:** restart/config-change and queue-pressure fixtures preserve original obligations and deliver eligible new work. Evidence: tests/test_delivery_recovery.py.
- **Actual outcome:** these cases are covered locally. Removing a channel leaves its old obligation unresolved; an explicit cancellation/retarget workflow is deferred. The current design remains at-least-once.

## D019 Migrate existing data and preserve complete billing grain

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** schema version 2 migrates populated v1 stores transactionally and rekeys records with currency, charge category, invoice/type and service/project grain. Re-fetched GCP groups replace matching legacy aggregates rather than double-counting them. Recreate indexes after commit because the tested DuckDB version rejected recreation inside the data migration transaction.
- **Rationale and importance:** new code must not lose old usage or overwrite distinct services. A failed conversion must preserve the earlier schema/data and expose the original error.
- **Expected outcome and acceptance:** a populated v1 fixture survives migration, rollback, restart and repeated ingestion; separate accounts/services remain distinct. Evidence: tests/fixtures/schema_v1.sql and tests/test_delivery_recovery.py.
- **Actual outcome:** local upgrade/rollback/idempotency regressions pass. No large customer database or production migration has been tested. Back up the store before upgrade; old code cannot read schema v2, and a downgrade migration is not supplied.

## D020 Bound collection and cloud query waits

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** cap each async fetch at 60 seconds; GCP submission/result waits are bounded at 15/40 seconds with automatic retries disabled and a requested server job timeout.
- **Rationale and importance:** a stalled source must not indefinitely postpone persisted incident delivery. Explicit provider bounds also limit orphaned background waits.
- **Expected outcome and acceptance:** a stalled fake collector fails within its deadline while queued alerts remain deliverable; query fixtures assert SDK timeouts. Evidence: tests/test_delivery_recovery.py and tests/test_gcp_connector.py.
- **Actual outcome:** deadline fixtures pass. Collectors still share a bounded cycle wait. Cancelling an async task does not guarantee worker-thread or server-job cancellation; actual cloud timing remains unverified.

## D021 Isolate incomplete FX and label native currency correctly

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** missing conversion marks only affected records/budgets incomplete; native-currency scopes remain evaluable. Budget explanations, notifications and CLI output use their actual currency. Budget amounts must be finite and positive.
- **Rationale and importance:** unrelated USD usage must not disable a fully priced INR project budget, and dollars must not be presented as rupees. AI anomaly replay excludes GCP non-AI charges and non-usage charge categories.
- **Expected outcome and acceptance:** scoped missing-FX isolation, USD wording and invalid-budget fixtures pass; no monetary enforcement on incomplete totals. Evidence: tests/test_money_coverage.py and tests/test_delivery_recovery.py.
- **Actual outcome:** local regression coverage exists. Customer FX and legitimate/abusive baseline calibration still require live acceptance.

## D022 Accept keyless GCP Application Default Credentials

**Date:** 2026-10-12. **Status:** implemented locally.
- **Decision and evidence:** startup configuration no longer requires a GOOGLE_APPLICATION_CREDENTIALS file path; prefer customer workload identity/ADC. Provider credential verification remains the actual authentication check.
- **Rationale and importance:** forcing a downloaded service-account key would contradict the deployment guidance and increase credential exposure. Environment presence alone does not prove authentication.
- **Expected outcome and acceptance:** unset/empty key-path configurations are allowed; OpenAI/Anthropic admin keys remain required. Evidence: tests/test_gcp_adc_config.py.
- **Actual outcome:** local configuration checks pass. No live ADC permissions or deployment have been verified.

## D023 Publish one current plan with explicit evidence gates

**Date:** 2026-10-12. **Status:** accepted and documented.
- **Decision and evidence:** [PILOT_PLAN.md](PILOT_PLAN.md) records the repository assessment, source/accounting/control/network phases, commercial gates and failure paths. Older plans are marked historical, and unsupported competitor/localization/traction claims are corrected.
- **Rationale and importance:** a founder needs a coherent next milestone rather than conflicting catalogs of planned and shipped features. A rough 12–20-week planning range is conditional, not a delivery promise.
- **Expected outcome and acceptance:** source feasibility and paid demand determine expansion; failed differentiation narrows the wedge instead of multiplying connectors.
- **Actual outcome:** the plan and sourced market/network records are committed artifacts of this change. Customer discovery, live comparisons and renewals remain pending.

## D024 Compare and reuse provider-native controls where adequate

**Date:** 2026-10-12. **Status:** accepted; live evaluation pending.
- **Decision and evidence:** include Google native AI anomaly signals and Preview spend caps in the competitive/pilot baseline, and evaluate reuse before building a custom cloud shutdown mechanism. See [Google release notes](https://docs.cloud.google.com/billing/docs/release-notes) and [cap limitations](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps).
- **Rationale and importance:** existing cloud protections overlap substantially with the founding use case. A custom control must justify its integration cost and blast radius; cross-provider identity/evidence remains a hypothesis to test.
- **Expected outcome and acceptance:** compare scoped native caps/alerts with the pilot incident workflow; measure delays, in-flight exposure and eligible paths. Provider-native enforcement is not guaranteed instant.
- **Actual outcome:** native scope/limitations are documented in the market research. No cap or native action has been configured or tested against a live account.

## D025 Make residency policy depend on applicable rules and evidence

**Date:** 2026-10-12. **Status:** accepted and documented.
- **Decision and evidence:** maintain separate configured, provider-guaranteed, observed and unknown location evidence; review data category, customer roles, current/future duties and sector rules rather than impose one universal DPDP localization rule. [INDIA_REGULATION.md](INDIA_REGULATION.md) records official sources and unresolved questions.
- **Rationale and importance:** India-hosted metadata, model processing, backups, encryption keys, alert destinations and support access are distinct dataflows. Incorrect legal certainty can misroute data or mislead procurement.
- **Expected outcome and acceptance:** each partner reviews the applicable matrix and full dataflow, with retention/escalation owners and model-specific processing commitments. A residency finding identifies its policy and evidence rather than claim certification.
- **Actual outcome:** the sourced review distinguishes DPDP phased commencement, CERT-In, payment-specific RBI scope and SEBI cloud/CSCRF abeyance nuances. No customer's legal applicability or live residency has been certified.

## D026 Publish the foundation on a separate branch and draft PR

**Date:** 2026-10-12. **Status:** completed.
- **Decision and evidence:** commit and push the authorized changes on codex/prahari-pilot-foundation, with a draft pull request collecting implementation and research.
- **Rationale and importance:** preserve a concrete review checkpoint for a broad foundation repair, including migration and live-validation limits, before merging or deploying it.
- **Expected outcome and acceptance:** the remote branch contains the tested code and durable decision record, and the PR is accessible for review.
- **Actual outcome:** implementation/research commit `7665f432971e5b068c23d012e6c3b7487312699e` is pushed; [draft PR #1](https://github.com/mahikshith/prahari/pull/1) is open and attached to this chat. The 334-test suite covers that implementation; this publication entry is a documentation-only follow-up. No merge or deployment occurred.

## D027 Keep network security narrowly scoped to incident evidence

**Date:** 2026-10-12. **Status:** recommended; D015's accepted metadata plan remains in force.
- **Decision and evidence:** use optional existing flow/DNS/NAT and native-policy evidence; postpone a general network-security product. [FEATURE_PRIORITIES.md](FEATURE_PRIORITIES.md) records the challenged assumptions and adoption gate.
- **Rationale and importance:** the external direct-key attack can bypass the customer's VPC entirely. Broad packet/security tooling increases support and deployment burden without resolving missing provider identity or usage.
- **Expected outcome and acceptance:** one-workload trial demonstrates additional decision-useful evidence; two design partners establish a recurring need before making the integration a standard feature. Sampling, cost and bypass remain visible.
- **Actual outcome:** primary-source and specialist review is recorded. No network trial or new logging/control has been enabled; incremental value remains unproven.

## D028 Prioritize protection drift, ownership and confirmed incident response

**Date:** 2026-10-12. **Status:** recommended.
- **Decision and evidence:** strengthen one operational workflow with fresh coverage/control-state evidence, trusted owners and a reconciled incident packet containing acknowledgement and confirmed response. Reuse existing gateway/on-call/native controls.
- **Rationale and importance:** generic dashboards and budget thresholds already overlap with existing products. Changed protection state and an unresolved owner can matter even between rare incidents.
- **Expected outcome and acceptance:** controlled protection changes and source outages surface actionable findings; operator drills demonstrate reduced investigation effort and verified effects versus the customer's baseline.
- **Actual outcome:** priorities are proposed in FEATURE_PRIORITIES.md. No new feature or paid-buyer evidence establishes differentiation yet.

## D029 Gate agent controls and optimization on trusted run/outcome telemetry

**Date:** 2026-10-12. **Status:** recommended.
- **Decision and evidence:** consider per-run call/retry/runtime/spend limits after routed telemetry is proved; add cost per successful task only with trusted customer success/quality evidence.
- **Rationale and importance:** accidental loops can waste money, but agentless billing cannot establish run identity or task success. Token reduction and cheaper model routing alone do not establish a better business outcome.
- **Expected outcome and acceptance:** bounded loop/retry/concurrency drills and quality-preserving task-cost comparisons justify expansion; unsupported identities and unknown outcomes remain explicit.
- **Actual outcome:** candidate features and prerequisites are documented, without implementation or measured savings. Broad automatic optimization remains deferred.

## D030 Validate one paid workflow before broadening the product

**Date:** 2026-10-12. **Status:** recommended; D002's two-segment discovery remains accepted.
- **Decision and evidence:** retain both customer groups in discovery but prioritize one buyer role and one incident workflow for first delivery. Compare against the existing customer stack and require paid commitment/renewal evidence.
- **Rationale and importance:** provider access gaps, adequate incumbent tools, rare-incident economics and customer-specific installation work can invalidate the startup despite a large reported loss.
- **Expected outcome and acceptance:** a paid comparison establishes incremental operational value; weak results narrow the wedge or favor integration/services before additional modules.
- **Actual outcome:** the candid scope/failure assessment is recorded. No buyer demand, pilot payment or renewal has been established by this recommendation.

## D031 Keep hourly user/account FinOps visibility central alongside incidents

**Date:** 2026-10-12. **Status:** accepted product direction; source acceptance pending.
- **Decision and evidence:** the founder clarified ordinary per-user/per-account cross-platform token consumption and cost as a core requirement, without limiting identity to service accounts. [USER_COST_VISIBILITY.md](USER_COST_VISIBILITY.md) records the implementation contract and provider sources.
- **Rationale and importance:** budgeting/allocation has routine value between incidents. The earlier security-focused feature recommendation must not crowd out the original FinOps objective; usefulness still does not establish uniqueness or paid demand.
- **Expected outcome and acceptance:** a two-user GCP + OpenAI pilot shows attributed hourly estimates, model/token details, freshness, budgets and unattributed/unpriced amounts, then reconciles supported billing without double-counting.
- **Actual outcome:** the requirement and pilot sequence are clarified in current planning. Existing raw user/key rollups do not establish cross-platform employee attribution or live hourly billing.

## D032 Separate employee identity, usage estimates and reconciled billing

**Date:** 2026-10-12. **Status:** recommended implementation contract.
- **Decision and evidence:** namespace provider/account user IDs and map them to trusted customer identity; label dedicated-key ownership separately from authenticated application identity. Keep live/hourly estimates and provider/invoice charges as separate reconciled layers.
- **Rationale and importance:** shared credentials obscure the employee, equal raw IDs can collide, and daily reports cannot prove exact hourly charges. Subscription fees and source delay cannot be repaired by inventing per-token prices or user mappings.
- **Expected outcome and acceptance:** fixtures exercise shared keys, cross-account identity collisions, absent user data, unknown prices, source freshness and timezone boundaries; known user totals plus unattributed cost explain the known subtotal.
- **Actual outcome:** the source/identity design is documented. No identity resolver, new employee-tool connector or live claim has been implemented or validated by this entry.

## Updating actual outcomes

Append dated evidence under the relevant ID after final tests, live-source checks, invoice reconciliation or customer trials. Include the tested revision/window, command or artifact, result and material limits. Keep historical outcomes; add a new decision when the choice changes. Do not replace a pending live outcome with a passing mocked test.
