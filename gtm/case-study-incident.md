# Founder reported weekend exposure and synthetic detection scenarios

**Status:** draft. The founding account is founder-reported; the replay and legitimate-control workloads are synthetic. No measured avoided-loss claim is made.

## The founder report

The founder describes a service account exposed to the internet and then used without authorization from a different location to consume Gemini tokens during a weekend. People were unaware while the activity continued. He estimates roughly **₹6–7 crore of cost/exposure**.

The paid amount after credits/recovery, detailed timeline, leak mechanism, permissions and supporting records are not yet verified. Do not infer that the key was pasted into an LLM, used for robotics, dormant for 41 days or abused for ten days. Those details are not established by this account. Employer-data and incident-publication permission must be resolved before using any identifiable records commercially.

The problem to investigate is actionable: can operators connect an identity's unusual AI activity to spend quickly enough to respond, including when an underlying key bypasses the organization's applications?

## What the synthetic scenarios show

The repository includes a deliberate attack fixture and a legitimate-control fixture. They model changes such as credential dormancy, spend growth, unfamiliar caller origin, expensive-model usage and a legitimate burst.

A replay can show which rules fire and the modeled spend at alert time for those generated inputs. Its attack duration, geography, baseline, FX and spend are simulation assumptions. The legitimate-control result is a fixture result, not a production false-positive measurement. Generated exposure and detection figures are not actual customer savings.

A real replay needs authorized audit/usage data, provider source-availability times, identity coverage and invoice reconciliation. A prevention claim also needs response timing, action effectiveness, in-flight spend and remaining bypass access.

## What the first pilot should establish

Use GCP + OpenAI in an authorized sandbox/customer environment, with read-only collection first and the customer holding credentials. The same core supports both startup/midmarket and regulated enterprise buyers.

1. Establish what identity, usage, cost and origin evidence the actual sources expose, and how late it arrives.
2. Demonstrate an alert reaching the configured remote channels despite a partial channel failure or collector restart.
3. Compare a controlled direct-key abuse scenario and legitimate burst against the customer's existing tooling.
4. Reconcile a settled invoice; identify estimates, unknown prices, credits, FX and unallocated differences.
5. Validate opt-in scoped containment and routed budget blocking in a sandbox before enabling live action.

A gateway controls routed calls; an external attacker using a stolen provider credential can bypass it and the customer's VPC. [Network telemetry](../docs/NETWORK_TELEMETRY.md) can add route/endpoint evidence but cannot decrypt prompts, count tokens or prove physical inference geography.

Customer-owned India deployment is a product choice, not a blanket DPDP compliance claim. Review provider processing commitments, logs, backups, notifications, support access and applicable law/contracts separately.

## Presentation rule

Lead with the founder's reported operational problem, label simulation outputs clearly, and ask for the buyer's concrete evidence and existing alternatives. Do not claim no competitors, typical crore-scale losses, a guaranteed detection time, money saved or compliance from a private collector.

See [the decision log](../docs/DECISIONS.md), [market evidence](../docs/MARKET_RESEARCH.md) and [pilot gates](../docs/DECISION_GATES.md) before using this draft.
