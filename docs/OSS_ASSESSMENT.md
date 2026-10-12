# Critical assessment of upstream open source

Reviewed: 2026-10-12. Scope: primary repository licenses, official documentation and selected upstream issue reports relevant to the GCP + OpenAI pilot. This is a reuse assessment, not an exhaustive source audit. No upstream defect below was independently reproduced during this review. Issue status describes what GitHub reported on the review date; an open report is not proof that every release is affected.

Current product decisions are in [DECISIONS.md](DECISIONS.md), implementation status in [PROGRESS.md](../PROGRESS.md), and network coverage limits in [NETWORK_TELEMETRY.md](NETWORK_TELEMETRY.md). None of the gateways or observability servers below has been deployed by this work.

## What can be reused

Licenses below describe the named repository and directory edition as inspected, not every hosted product, dependency or enterprise feature. Before distribution or deployment, record the selected release, commit, container digest, dependency notices and applicable commercial terms. References to `main` or `develop` are moving sources, not approved installation pins.

| Project and verified source | License / edition | Useful overlap with Prahari | Reuse position |
|---|---|---|---|
| [LiteLLM](https://github.com/BerriAI/litellm), [license](https://github.com/BerriAI/litellm/blob/main/LICENSE) | MIT outside `enterprise/`; that directory has separate terms | Provider adapters, virtual keys, per-entity budgets, routing and spend estimates | First optional gateway trial candidate; no production selection yet |
| [Portkey gateway](https://github.com/Portkey-AI/gateway), [license](https://github.com/Portkey-AI/gateway/blob/main/LICENSE) | MIT gateway repository; hosted/enterprise capabilities require separate verification | Multi-provider routing, retries, caching and streaming normalization | Alternative if the first candidate fails required trials; avoid adopting both |
| [Langfuse](https://github.com/langfuse/langfuse), [license](https://github.com/langfuse/langfuse/blob/main/LICENSE) | MIT Expat outside `ee/`, `web/src/ee/`, `worker/src/ee/`; third-party terms remain applicable | Application traces, usage/cost tracking, evaluation and prompt workflows | Accept customer exports; do not operate a second full tracing platform for the pilot |
| [Helicone](https://github.com/Helicone/helicone), [license](https://github.com/Helicone/helicone/blob/main/LICENSE) | Apache-2.0 repository; hosted service terms are separate | Proxy/async telemetry, request analytics, custom properties and cost limits | Integration source or comparison fixture, not another required server |
| [OTel GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai), [license](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/LICENSE); [OpenLLMetry](https://github.com/traceloop/openllmetry), [license](https://github.com/traceloop/openllmetry/blob/main/LICENSE) | Apache-2.0 repositories; conventions and instrumentation are different components | Common telemetry vocabulary and optional application instrumentation | Reuse the vocabulary and existing customer collector; add instrumentation only for agreed coverage |
| [OpenCost](https://github.com/opencost/opencost), [license](https://github.com/opencost/opencost/blob/develop/LICENSE) | Apache-2.0; inspected default branch `develop` | Kubernetes/cloud allocation and now vLLM inference infrastructure cost | Defer integration until a customer has self-hosted inference or Kubernetes allocation needs |
| [Microsoft FinOps toolkit](https://github.com/microsoft/finops-toolkit), [license](https://github.com/microsoft/finops-toolkit/blob/main/LICENSE) | MIT repository | Cost export ingestion, FOCUS-oriented analytics and allocation/reporting patterns | Reuse concepts and datasets where applicable; defer its Azure analytics infrastructure |

## LiteLLM: strong overlap, financial controls still need a trial

Official [budget documentation](https://docs.litellm.ai/docs/proxy/users) describes pre-request cost reservations and reconciliation with actual spend. It also documents limits: database-backed budgets are required, global `max_budget` without a database fails open, and reservation coverage depends on available pricing. Unpriced image/audio requests cannot be treated as proven monetary reservations. Team membership also changes which personal/team budget applies. A configured dollar limit alone does not establish a bounded worst-case loss.

[Production guidance](https://docs.litellm.ai/docs/proxy/prod) requires shared Redis state for multiple instances and discusses database contention at high spend-update volumes. That adds operational work for a solo founder. [Issue #39150](https://github.com/BerriAI/litellm/issues/39150), open, reports buffered spend crossing a budget reset being charged to the wrong window; the reporter names version 1.106.0 and a specific main commit. Use it as a delayed-writer/reset-boundary regression scenario, not as our own confirmed finding.

The maintainer's [March 2026 security update](https://docs.litellm.ai/blog/security-update-march-2026) identifies compromised PyPI releases 1.82.7 and 1.82.8 and says official Proxy Docker images and GitHub source were not affected. Adoption must use a reviewed, pinned artifact and supplier/security checks. This incident does not establish that all distribution paths or later releases are compromised.

## Portkey: gateway reuse is different from enterprise deployment

The [gateway README](https://github.com/Portkey-AI/gateway) describes a 2.0 transition and distinguishes enterprise functionality. Verify the exact selected release and feature edition rather than transferring hosted-product claims to the MIT gateway. Official [hybrid architecture](https://portkey.ai/docs/self-hosting/hybrid-deployments/architecture) separates a customer-hosted data plane from a hosted control plane containing configuration and metrics. A gateway in an India VPC therefore does not, by itself, establish that every relevant datum stays in India.

[Issue #1797](https://github.com/Portkey-AI/gateway/issues/1797), open, reports a mid-answer upstream stream closure presented as a clean HTTP 200 without completion/error markers; it names an image digest pulled in September 2026. Reproduce against the proposed pinned release. The financial question is whether incomplete requests retain known usage, distinguish unknown final cost, and account for all retry/fallback attempts. Retrying a partially delivered answer also has application correctness consequences.

## Langfuse: useful tracing, estimates need financial provenance

[Token/cost documentation](https://langfuse.com/docs/observability/features/token-and-cost-tracking) distinguishes ingested usage/cost from inferred quantities, requires non-overlapping usage buckets, and documents missing model/pricing cases. Inclusive provider totals plus cached/reasoning subcounts need normalization before multiplication. It documents USD cost details and limitations on inferred reasoning-model usage. Prahari still needs native billing currency, dated FX, invoice adjustments and explicit unknown values.

[Issue #5358](https://github.com/langfuse/langfuse/issues/5358) is closed/completed: users reported inconsistent chart totals, a maintainer acknowledged a bug and said a fix was pushed on 2025-02-10. This is a historical regression example, not an allegation of a current defect.

[Self-hosted telemetry documentation](https://langfuse.com/self-hosting/security/telemetry) says aggregated deployment telemetry reaches `eu.posthog.com`. OSS can disable it on all application containers; enterprise license-compliance telemetry cannot be disabled through that setting. Raw prompts/traces are excluded from that deployment telemetry according to the documentation, but configured tracing storage and other integrations still need a separate data-flow review. Check enterprise terms for required governance features.

## Helicone: privacy and limit semantics are deployment-specific

[Custom limit documentation](https://docs.helicone.ai/features/advanced-usage/custom-rate-limits) describes request/cost limits, client-provided policy/user/property headers and Cloudflare KV. Token-based limits and simultaneous multiple policies are listed as forthcoming on that page. Do not equate this documented feature set with atomic concurrent cost reservation. A trusted service must assign identity and policy; arbitrary client labels cannot establish employee attribution.

[Omit Logs documentation](https://docs.helicone.ai/features/advanced-usage/omit-logs) explicitly distinguishes suppressing storage from suppressing transfer: proxy omission headers still send content to the backend, whereas async content disabling can prevent that transfer. Test the chosen mode and version with sensitive markers.

[Issue #5788](https://github.com/Helicone/helicone/issues/5788), open, reports vendor-specific inclusive/exclusive long-context price boundary errors. [Issue #5757](https://github.com/Helicone/helicone/issues/5757), open, reports missing returns on validation/rate-limit error paths. Both are reporter claims, not reproduced defects here. They justify exact-threshold pricing fixtures and adversarial rejection tests for the selected release; they do not justify declaring the entire project insecure.

## OTel and OpenLLMetry: interoperability, not a spend ledger

The [OTel GenAI span conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md) currently have Development status and describe caller-observed logical operations, potentially spanning retries. Provider attribution can differ from the true upstream behind a proxy. Usage attributes can include cached tokens, so copying them into exclusive cost buckets without mapping is unsafe. Pin a semantic-convention version and preserve provider-native evidence alongside normalized fields.

The [OpenLLMetry README](https://github.com/traceloop/openllmetry) describes instrumented application/provider calls exporting to OTel-compatible destinations. It states SDK/instrumentation deployment telemetry was removed starting with v0.49.2; this does not disable configured trace exports. Its [privacy documentation](https://www.traceloop.com/docs/openllmetry/privacy/traces) provides a content-capture disable setting. Verify tool arguments, exceptions, streaming and nested calls for the chosen packages rather than assuming one setting removes all sensitive content.

Architectural inference: sampling, exporter loss, retries and logical-operation spans make traces unsuitable as the sole financial ledger. Trace identity labels also need trusted authentication mapping. SDK instrumentation does not observe an external attacker calling the provider directly with a stolen credential.

## OpenCost and FinOps toolkit: broader cost coverage, different evidence

OpenCost's current [README](https://github.com/opencost/opencost/blob/develop/README.md) includes multi-cloud costs and AI inference, so calling it Kubernetes-only or claiming it has no AI support would be wrong. Its [inference documentation](https://github.com/opencost/opencost/blob/develop/docs/inference-cost-tracking.md) describes vLLM metrics, infrastructure allocation and a default two-minute collection interval. Allocation and usage cost bases differ; usage excludes idle/shared infrastructure and does not reconcile to the bill. Missing timing metrics use a fixed cost-split fallback. This is useful self-hosted inference economics, not evidence of every OpenAI/Gemini API request or external credential use. The README also warns that querying one sharded Prometheus pod can produce incomplete results.

The [FinOps toolkit overview](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/finops-toolkit-overview) and [hubs architecture](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/hubs/finops-hubs-overview) describe export-driven cost analytics, reports and infrastructure such as Data Factory, Azure Data Explorer/Fabric and storage. Cloud export support should be checked per release; do not assume Azure-only coverage. Billing export analytics cannot establish immediate per-request blocking, token content, caller location or authenticated employee attribution without additional sources. Reuse normalization/allocation ideas; do not add that infrastructure solely to label the pilot FinOps.

## Conformance trials before adopting a gateway or telemetry adapter

All following outcomes are pending. Run synthetic fixtures first, then a customer-approved, bounded pilot with provider usage/billing reconciliation. Publish the exact release, configuration, coverage and failures with results.

| Trial | Acceptance evidence |
|---|---|
| Identity and bypass | Forged employee/policy labels rejected or marked untrusted. A direct provider call appears only through available provider/audit sources and is explicitly outside gateway control. Document detection delay and uncovered paths. |
| Token and currency accuracy | Exact fixtures for cached input, reasoning output, long-context boundaries and supported modalities; no overlapping counts. Preserve native quantity/unit/currency and pricing provenance. Missing usage/prices/FX remain unknown. Explain invoice credits, taxes and negotiated-price differences. |
| Streaming and retries | Full completion, cancellation, missing final usage, upstream cut and fallback attempts remain distinguishable. Retried requests are separately accountable; unknown final cost cannot become zero or disappear. |
| Concurrent budgets | Simultaneous requests at the cap, bounded output, reset boundaries and delayed spend writers produce measured maximum exposure. Reservation release/reconciliation is idempotent. Define rejection behavior on database/Redis failure; no hard-cap claim from an untested fail-open path. |
| Durability and scale | Replay/restart/export outage preserves financial event IDs without double charging. Report loss/duplicate counts, queue age, accounting lag and p95 latency at the customer's expected and burst load; sampled traces are not counted as complete spend. |
| Privacy and residency | Sensitive markers absent from permitted telemetry, diagnostics and tool attributes. Record all outbound hosts/control-plane transfers. Test regional fallback policy against approved model/endpoint configurations; endpoint IP geography alone is not processing-location proof. |
| Supply chain and editions | Review release/digest, notices, enterprise feature requirements, vulnerability advisories and upgrade ownership. Demonstrate the deployed edition actually supports required controls. |

## Recommended minimum reuse path

Retain Prahari's small GCP + OpenAI collection/reconciliation core. Trial **one** pinned LiteLLM gateway in the customer environment for consenting application traffic only, with database-backed budgets and explicit failure behavior. Keep it optional until these trials establish its coverage and financial bounds. Portkey is an alternative candidate if required trials or edition constraints fail; neither is a production dependency today.

Accept existing OTel/Langfuse/Helicone metadata through adapters where customers already operate them. Avoid deploying all their servers. Build the differentiated layer around credential/workload ownership, source freshness and coverage, estimated-versus-billed reconciliation, incident evidence and customer-approved containment. Add OpenCost or a larger FinOps pipeline only when a validated workload demands it. No combination removes the need for provider-side evidence or makes a blanket compliance/certification promise.
