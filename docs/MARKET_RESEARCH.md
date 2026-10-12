# Prahari: market evidence and pilot decisions

**Reviewed:** 12 October 2026. **Status:** research and product hypotheses, not customer validation.

**Current decision:** a solo founder builds one shared core for GCP + OpenAI, deployed first in a customer's India cloud. Agentless collection provides discovery and billing reconciliation; an optional gateway provides request telemetry and budget blocking for routed traffic. India-hosted SaaS comes later. This explicitly supersedes the earlier agentless-only/no-gateway product preference; it does not establish complete coverage or compliance.

## 1. What the evidence supports

The founder reports a service-account exposure followed by unauthorized Gemini use and roughly ₹6–7 crore of cost/exposure. The paid amount, credits, timeline, leak mechanism and permission to use employer information remain unverified. Do not add details from the synthetic scenario to this account.

The repository's backtest is synthetic. Spend-at-alert, ten-day exposure and the legitimate-control result demonstrate behavior on that fixture; they are not measured incident detection, avoided losses or production false-positive rates. A real replay must include source availability and response delays before making a counterfactual prevention claim.

The [State of FinOps 2026 report](https://data.finops.org/) covers 1,192 respondents representing more than $83 billion of annual cloud spend. It reports that 98% manage AI spend, up from 63% in 2025 and 31% in 2024; granular AI spend monitoring leads its requested tooling capabilities. This establishes practitioner interest, not Indian customer willingness to pay or Prahari product-market fit. The previously attributed 73% AI budget-overrun figure was not verified in this source and has been removed.

[Sysdig's LLMjacking research](https://www.sysdig.com/blog/llmjacking-stolen-cloud-credentials-used-in-new-ai-attack) documents stolen credentials being tested across AI providers and potential resale through reverse proxies. Its $46,080/day figure is a worst-case quota-and-price calculation across four regions, not measured daily loss on one victim. Use it as a threat scenario, not a typical incident rate or evidence that the founder's loss is representative.

Precise forecasts, adoption multipliers, shadow-AI percentages, ACVs, funding totals and vendor prices from the earlier memo have been omitted where direct support was not established. Acquisition examples below are evidence of competition and consolidation, not proof that every new point product must fail.

## 2. Competitors already overlap substantially

These are documented or vendor-advertised capabilities. No live product bakeoff has been performed. Missing public documentation is not proof of a missing capability.

| Platform | Verified overlap | Pilot question for Prahari |
|---|---|---|
| [Datadog](https://docs.datadoghq.com/llm_observability/investigate/cost/) | Request cost estimates from usage and model prices, custom team/customer tags, application correlation; automatic pricing is limited to text models. | Can the customer's Datadog/cloud-security setup already provide the same identity, spend and response timeline? |
| [Sentry](https://sentry.io/solutions/ai-observability/) | Model/tool/agent traces with token usage, cost, errors and timing. | What coverage exists when a caller bypasses the instrumented application? |
| [CloudZero](https://docs.cloudzero.com/docs/ai-platforms) | Third-party AI provider connectors, allocation dimensions, budgets and unit economics alongside cloud spend. | Compare connector freshness, credential attribution and response actions; the earlier claim that third-party AI tracking was absent was incorrect. |
| [Finout](https://www.finout.io/artificial-intelligence) | Advertises cross-provider AI/cloud costs, business allocation, anomaly alerts and budgets. | Measure real source delay and allocation evidence; distinguish alerts from access enforcement. |
| [Portkey](https://portkey.ai/docs/product/ai-gateway) | Multi-provider gateway, budgets, rate limits, routing, caching and guardrails. | Test direct-key bypass and concurrent budget exposure. Its [hybrid architecture](https://portkey.ai/docs/self-hosting/hybrid-deployments/architecture) includes customer-VPC components and a hosted control plane; inspect each data surface. |
| [TrueFoundry](https://www.truefoundry.com/blog/ai-gateway-budgets-quotas) | Tenant/team and per-entity budget policies with alert/enforce modes. It also describes [runtime residency enforcement](https://www.truefoundry.com/blog/data-residency-in-truefoundry-ai-gateway). | Test underlying cloud-key abuse, distributed budget correctness and independent residency evidence. Residency policy and per-user budgets are not unique features. |
| [Langfuse](https://langfuse.com/docs/observability/features/token-and-cost-tracking) / [Helicone](https://docs.helicone.ai/features/advanced-usage/custom-rate-limits) / [LiteLLM](https://docs.litellm.ai/docs/proxy/users) | Existing tracing, cost attribution and/or budget controls, including self-hosted options. | Compare the actual chosen version and deployment, not the feature name. Reuse one gateway instead of recreating provider adapters. |
| [SigNoz](https://signoz.io/docs/ai-observability/) | OTel-based token/cost/latency/tool-call observability, self-hosted and cloud options. | Demonstrate incident and coverage advantages beyond dashboards. |
| [Google Cloud native controls](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps) | Eligible-service spend caps and AI early anomaly signals already overlap with the founding use case. | Compare the existing native workflow before building a custom shutdown path. Test scope, delay and maximum exposure. |
| [Amnic](https://amnic.com/blogs/genai-cost-management-platform) | Describes token spend across OpenAI, Anthropic, Gemini and Bedrock, attributed to business dimensions. | Validate collection method, identity evidence and containment in a trial. |
| [Torii](https://support.toriihq.com/hc/en-us/articles/51567364875547-What-is-the-Torii-AI-Module) / [Flexera](https://www.flexera.com/products/ai-cost-management) / [Zluri](https://www.zluri.com/product-tours/shadow-it) | Adjacent AI spend/seat governance and shadow-AI discovery. Torii documents vendor admin APIs for billed costs; Flexera advertises models, apps and infrastructure; Zluri documents AI app discovery. | Include these when buyers want employee tooling governance; do not assume cloud FinOps and SaaS governance never overlap. |

Palo Alto Networks [agreed to acquire Portkey for $140 million](https://www.sec.gov/Archives/edgar/data/1327567/000132756726000015/panw-20260430.htm) on 30 April 2026 and [announced completion](https://investors.paloaltonetworks.com/news-releases/news-release-details/palo-alto-networks-completes-acquisition-portkey-secure-ai) on 29 May. Helicone [announced joining Mintlify](https://www.helicone.ai/blog/joining-mintlify) on 3 March and continued service in maintenance mode, including security, model, bug and performance updates. Neither fact establishes that their OSS licenses or all capabilities disappear.

Google's [release notes](https://docs.cloud.google.com/billing/docs/release-notes) announced AI early anomalies on 24 July 2026 and Preview spend caps on 27 July. Early signals are daily service-level insights from near-real-time estimates. Current [cap limitations](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps) include one project, one eligible service, a monthly period and gross estimated costs. Enforcement is delayed and overages remain payable. These are meaningful existing protections; they do not supply a cross-provider per-employee incident view or prove instant loss prevention. Native controls are a baseline and potential integration, not an absent competitor.

## 3. The differentiated hypothesis to test

**Hypothesis:** customers will pay for a clear incident view joining trusted identity, anomalous estimated AI spend, coverage gaps, scoped containment and eventual billing reconciliation. The advantage must hold against existing tooling, not merely against provider console screenshots.

- **Coverage:** agentless APIs expose what providers supply; gateways expose routed traffic. A stolen underlying key can bypass a gateway. Audit records and policy restrictions are needed for that path. No architecture establishes organization-wide coverage in a week by default.
- **Identity:** a shared key cannot identify the employee who used it without trusted application identity or ownership mapping. A service-account principal is not necessarily an individual key. Audit and billing joins on project/time do not establish exact per-caller spend.
- **Timing:** publish source-event time, ingestion time and completeness. Google gives [no Cloud Billing export delivery/latency guarantee](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables); a fixed 4–24-hour range is not an SLA. Poll frequency and hourly buckets do not establish fresh data. Verify every source before promising sub-hour detection.
- **Accounting:** keep estimated, provider-reported and billing-reconciled amounts separate. OpenAI explicitly distinguishes [Usage from Costs](https://platform.openai.com/docs/api-reference/usage). Explain credits, discounts, taxes, FX and unallocated differences rather than hiding them inside one percentage.
- **Optimization:** measure cost per successful task with acceptable quality, including retries, tools, retrieval and evaluation. Token reduction alone is not proof of savings. Model routing and broad optimization are later work.
- **Network evidence:** IP/DNS/flow metadata can strengthen coverage and destination-risk findings, but cannot determine encrypted content, token counts or physical inference geography. See [NETWORK_TELEMETRY.md](NETWORK_TELEMETRY.md).

## 4. India deployment is a requirement to validate, not a legal moat

The DPDP Act does not create a blanket requirement that all personal data stay in India. [Section 16](https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf) provides for notified restrictions on overseas transfer and preserves stricter applicable laws. Sector rules, contracts, data categories and phased commencement require separate applicability checks. Do not pitch a universal May 2027 localization deadline or claim Indian incorporation confers compliance. [INDIA_REGULATION.md](INDIA_REGULATION.md) records the dated applicability and evidence matrix.

Customer-owned India hosting is the current product decision. Logs, raw records, credentials, backups, encryption keys and support paths need their own review. Hosted alerts and identity services can create other transfers. Endpoint configuration, provider processing commitments and observed traffic are different evidence. Prompts are excluded by default. The initial product supplies evidence; it does not promise certifications or legal compliance.

## 5. Buyers, pricing and investment

Serve two groups with one core: startup/midmarket platform teams needing understandable spend controls, and regulated enterprise platform/security teams needing the same controls plus deployment and audit evidence. Interview and score them separately; do not average their procurement constraints. Start with the buyers who can authorize a small pilot, not an assumed enterprise ACV.

The likely operational champion is a platform/security lead, with FinOps or finance involved in reconciliation. Identify the actual budget owner, existing alternative, procurement steps and acceptable installation permissions. Local support, implementation speed and buyer access can justify India-first independently of residency.

Offer a fixed paid pilot with agreed success criteria. Production pricing remains a hypothesis until renewals and measured value exist. Do not infer ₹20L+ budget authority, security willingness-to-pay or investor appetite from market size or acquisition prices. A fundraise should use verified partner outcomes, coverage and deployment economics; synthetic avoided-loss numbers are not traction.

## 6. Evidence gates before expanding

The following are pilot targets, not measured achievements. Use customer-authorized accounts or a separate founder sandbox; employer-data approval blocks employer data use, not independent testing.

| Gate | Evidence required |
|---|---|
| Source feasibility | Live GCP + OpenAI fixtures establish field availability, source freshness, pagination and permissions; document unsupported methods and missing identity/usage. |
| Differentiation | Compare controlled direct-key abuse, a legitimate burst, retry-loop spend and regional fallback against the buyer's current stack or a direct competitor. Record misses and false alerts. |
| Commercial | Obtain three paid design partners with named owners and written success criteria. Interviews establish concrete prior pain and alternatives; survey percentages and enthusiasm are not purchase evidence. |
| Accounting | Reconcile a settled period per provider; target ≤2% aggregate variance with explicit explanations and visible unallocated amounts. A missing identity field is not fixed by a matching total. |
| Containment | In an authorized sandbox, demonstrate scoped audited action and confirmed outcome; gateway blocking is tested under concurrency, interrupted streams and unavailable accounting state. Disclose bypass and in-flight exposure. |
| Retention | At least two partners renew or expand based on demonstrated value. If they do not, revise the buyer/wedge before adding more providers or spend categories. |

Keep discovery non-leading and record evidence promptly. A weak residency signal changes deployment priorities; it does not automatically invalidate India-first. If an incumbent passes the same incident drill at lower integration cost, narrow the wedge or pursue integration/OEM work instead of asserting an absent market.

## 7. Current limits

No live competitor bakeoff, customer interviews, paid pilots or measured incident replay support this memo. Earlier claims about complete coverage, unique capabilities, typical incident losses, guaranteed latency, regulatory inevitability and specific customer ACVs have been withdrawn. Maintain dated source links and separate verified facts, vendor claims and Prahari hypotheses as evidence arrives.
