# Feature scope: candid product assessment

**Reviewed:** 2026-10-12. **Status:** recommendations for founder review; no feature implementation or change to the accepted pilot scope. Two specialist agents challenged the security and product assumptions. Actual buyer demand and incremental value remain unproven.

**Founder clarification, 2026-10-12:** ordinary hourly cost/consumption per user and account across platforms is central alongside abuse detection. [USER_COST_VISIBILITY.md](USER_COST_VISIBILITY.md) records the source/identity limits and first pilot. The earlier incident-focused recommendation below must not exclude day-to-day FinOps value.

## Product judgment

The current vision combines observability, FinOps, credential security, agent controls, optimization and compliance. That is too broad for a solo founder's first product. More modules increase integration and support obligations before the core promise has been proved.

The strongest current hypothesis is a focused operational workflow: understand ordinary AI consumption and budgets by trusted person/team/account, investigate suspicious changes, reach an accountable operator, verify scoped containment, and reconcile the final cost. Customers must find that workflow materially better than their existing stack.

Request-cost dashboards and budget thresholds already overlap with [Datadog](https://docs.datadoghq.com/llm_observability/investigate/cost/), [Portkey](https://portkey.ai/docs/product/ai-gateway), [LiteLLM](https://docs.litellm.ai/docs/proxy/users) and [Google native caps](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps). Another dashboard is not, by itself, evidence of a defensible business. A reported large incident establishes one organization's pain, not a repeatable buyer or willingness to pay.

## Network security: recommendation

Keep network telemetry as an optional evidence source. Do not make general network security a new product pillar for the pilot. Full packet inspection, intrusion detection, firewall management and a broad security operations platform introduce a different deployment burden and buying conversation.

The founding external-credential attack is the decisive counterexample. An attacker can call the provider from their own infrastructure. **Architectural inference:** that call does not cross the customer's VPC, so logs of that VPC cannot show it. An outgoing-traffic graph can look ordinary while unauthorized provider charges accumulate.

[Google flow logs](https://docs.cloud.google.com/vpc/docs/flow-logs) observe configured resources and sampled connections. The [record schema](https://docs.cloud.google.com/vpc/docs/about-flow-logs-records) supplies connection/resource metadata. It is not a prompt-content or token ledger. Country/IP information must not be presented as an identified attacker or proof of inference location.

Useful narrow questions include: did a covered workload contact an unexpected AI endpoint; did its route bypass the configured gateway; and do network records corroborate the workload/time evidence in an incident? Preserve unmatched and missing data instead of inventing joins. Network-policy posture can also be relevant: [VPC Service Controls](https://docs.cloud.google.com/vpc-service-controls/docs/overview) addresses unauthorized network access using stolen credentials for supported services. Inspect exact method coverage before proposing an integration; it is not a universal third-party AI firewall.

**Adoption gate:** first run one authorized workload trial using existing logs. Keep the integration optional until two design partners show the same unresolved operational need. Require additional evidence that changes an investigation or response decision, disclosed sampling/bypass coverage, acceptable false alerts and measured collection cost. Compare both an external direct-key call and an in-VPC compromise. More collected logs alone do not pass.

## What deserves priority

These capabilities share the same usage, identity, coverage and policy core. Several elaborate the existing plan rather than increase provider scope.

| Priority | Capability | Why it earns its place | Acceptance evidence |
|---|---|---|---|
| First | Hourly cross-platform user/account cost | Give users and finance teams routine visibility into attributed usage, estimated spend and budgets, with freshness and unknown totals explicit. | Trusted identity joins two providers; missing identity remains unattributed, hourly estimates are distinguished from reconciled bills. See USER_COST_VISIBILITY.md. |
| First | Protection coverage and drift | Show whether each known workload has fresh evidence, an owner and configured controls. Detect missing/lifted caps and changes that invalidate protection. This provides recurring operational value between incidents. | A controlled cap/config change or source outage becomes a specific coverage finding; unknown inventory remains unknown. |
| First | Trusted ownership and credential posture | Route an incident to the accountable team/service. Use existing IAM inventory to surface long-lived keys, unsupported ownership and broad permissions; integrate existing exposure signals rather than invent a secret scanner. | Owner can be reached in a drill; evidence distinguishes principal, key, workload and employee. Shared credentials do not imply employee identity. |
| First | One incident packet and confirmed response | Assemble identity, behavior, source delay, known/estimated cost, operator acknowledgement, proposed action and verified effect. Later append settled billing. An HTTP success from an action API is insufficient. | Operator can explain why the finding fired and what stopped; records show residual access/exposure and fewer manual investigation steps than the baseline. |
| After routed telemetry is proved | Runaway-agent controls | Group calls by trusted run/task identity; bound spend, calls, retries and runtime. A legitimate loop can waste money without a stolen credential. | A bounded loop is interrupted without breaking a legitimate long run; retries, delegation, cancellation and concurrent reservations are accounted for. Requires application/gateway integration. |
| After outcome evidence is available | Cost per successful task | Measure whether a workflow delivers acceptable results at lower total cost. Include failures, retries, tools and relevant infrastructure rather than reward token reduction alone. | Customer supplies trustworthy success/quality metadata; a controlled change lowers comparable task cost without exceeding agreed quality/reliability limits. |

Protection drift has a concrete native example. Google documents that moving a capped project between billing accounts deletes its old caps; an enforced cap can be lifted and usage resume. Monitoring the state and ownership of controls may therefore add value beyond configuring them once. This is a product hypothesis, not a reproduced Prahari capability. [Google cap behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)

Credential posture should follow provider guidance on reducing key circulation, identifying unused keys and using safer authentication alternatives. Detected exposure does not establish that every leak has been found. [Google service-account key guidance](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)

## Ideas to leave out of the first product

- A general SIEM, firewall, packet capture or TLS-interception platform.
- Broad DLP, prompt-injection scanning and employee browser surveillance.
- Autonomous model switching or prompt rewriting without a customer-specific quality evaluation.
- All-provider coverage, SaaS-seat discovery and GPU economics simultaneously.
- Exact employee attribution from shared keys, or an “India compliant” score derived from IP geolocation.
- A second custom gateway, alerting platform or secret scanner where a reviewed existing component fits.

These exclusions are pilot scope recommendations, not claims that the categories lack value. Expand when repeatable paid demand and feasible evidence support the additional work.

## Reasons the startup could fail

1. **The needed evidence does not exist or arrives too late.** A project-level bill cannot become exact per-service-account usage through a prettier interface, IP correlation or an LLM explanation. The next source experiment must establish supported identity joins and delay.
2. **Customers will not grant the required access or route traffic.** Rapid direct-key protection cannot be promised from delayed billing if provider activity, gateway coverage and effective native restrictions are unavailable.
3. **The buyer already solves the workflow adequately.** Native caps, isolated credentials, a gateway, cloud security tools and existing on-call automation may be cheaper and easier. Incumbents have installed integrations and procurement trust.
4. **Alerts and deployment become the founder's service burden.** Frequent false findings, many customer-specific mappings or difficult customer-owned upgrades can turn the business into low-margin integration work.
5. **Rare incidents fail to produce recurring willingness to pay.** Protection drift and routine runaway-agent prevention could help, but must be demonstrated. A catastrophic story does not prove subscription retention.

Keep both agreed customer groups in discovery. Focus the first delivery on one buyer role and one incident workflow; do not create two products. Compare controlled drills against the customer's real baseline and require paid commitments and renewal. If the incremental value is weak, narrow the problem or pursue an integration/services model before adding more features.

No new network/security controls or cloud actions were enabled by this assessment. The practical next step remains the GCP + OpenAI source-feasibility pilot in [PILOT_PLAN.md](PILOT_PLAN.md).
