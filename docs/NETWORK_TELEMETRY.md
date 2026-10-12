# Network telemetry: useful evidence with explicit coverage

**Reviewed:** 12 October 2026. **Status:** integration plan only; no collector or cloud logging changes are implemented here.

Inbound/outbound IP traffic helps answer **which observed workload contacted which network endpoint, when, and with what traffic volume**. It can identify unfamiliar destinations, gateway bypass from a covered workload and changes in network behavior. It cannot establish which personal data was sent, how many tokens were billed, or where a provider physically ran inference. Network evidence supplements audit, gateway and billing records.

## GCP sources and their limits

| Source | Useful evidence | Coverage limit |
|---|---|---|
| [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs) | Sampled, aggregated IP flows for supported resources, including VM/GKE and Direct VPC egress workloads. | Primary sampling is dynamic; setting secondary sampling to 100% does not capture every packet. Missing flows are not proof of no traffic. |
| [Flow record fields](https://docs.cloud.google.com/vpc/docs/about-flow-logs-records) | IPs/ports/protocol, start/end, reporter, estimated bytes/packets and optional resource/PSC metadata. | Metadata can be missing or inaccurate. Packet direction does not generally establish who initiated the connection; preserve reporter and any connection-direction evidence separately. |
| [Cloud NAT logs](https://docs.cloud.google.com/nat/docs/monitoring) | TCP/UDP translation events and some egress errors; useful for mapping private workloads to public source addresses. | Records can be omitted and only cover traffic using that NAT path. These are not packet-content or total-volume logs. |
| [Cloud DNS query logs](https://docs.cloud.google.com/dns/docs/monitoring) | Queried name, answer, originating IP and timing when the query is in the enabled logging scope. | A DNS lookup is not proof of a connection. Cached resolution, other resolvers and encrypted DNS can leave gaps; several hostnames can share an IP. |
| [Cloud Audit Logs](https://docs.cloud.google.com/logging/docs/audit) | Authenticated principal and API operation; callerIp in request metadata may identify an external origin. | IPs can be internal or redacted to private/gce-internal-ip. Verify logging and field availability for each target API method. |

**Stolen-key blind spot:** an attacker outside the customer VPC calling the provider directly does not traverse the customer's VPC. Flow/NAT/DNS logs there cannot observe that request. Provider-side audit/usage evidence is the required complementary path; its availability and delay must be tested. An external caller IP identifies observed network origin, not the attacker, employee or physical location with certainty.

**HTTPS:** flow records contain connection metadata, not decrypted prompts, responses, request paths or authorization headers. Do not introduce packet interception or TLS decryption. Persistent connections, streaming, compression and multimodal payloads make byte counts unsuitable for token/cost conversion. Keep cost in the usage/billing ledger.

## Private connectivity and residency

[Private Google Access](https://docs.cloud.google.com/vpc/docs/private-access-options) lets eligible internal-address workloads reach Google APIs. [Global PSC endpoints](https://docs.cloud.google.com/vpc/docs/about-accessing-google-apis-endpoints) provide internal VPC addresses for Google APIs. Public Google API IPs can also carry traffic within Google's network: a public address alone does not prove public-internet transit.

[Regional/multi-regional PSC endpoints](https://docs.cloud.google.com/docs/security/compliance/about-accessing-regional-google-apis-endpoints) target supported regional services and have separate reachability rules. Global reachability of a private endpoint is not the inference-processing region. Google's [model endpoint guidance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations) explicitly says endpoint selection alone does not guarantee data residency or in-region ML processing. Check the model/feature's processing commitment and contract separately; IP geolocation is only destination metadata.

Inventory the actual route: direct public access, NAT, Private Google Access, PSC or an application gateway. For [Cloud Run Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc), private-ranges-only and all-traffic have different coverage; public API calls can avoid the VPC under the former. Flow logs do not provide the Cloud Run revision name. Workload attribution must preserve uncertainty instead of assigning an ephemeral IP permanently to a service.

## Minimum integration phase after live-source validation

1. Use one customer-authorized GCP project and one known workload. Read existing flow/NAT/DNS logs and routing configuration first. If logging is absent, show a coverage gap; have the customer review scope, cost, retention and India log-bucket placement before enabling it. Do not enable an organization-wide sink by default.
2. Add one read-only Cloud Logging ingestion path to the existing collector; keep network observations separate from monetary usage records. Reuse existing scheduling, persistence, deduplication and alert delivery. Preserve UTC event and receipt time, provider log identity, source/destination IP and optional ports/protocol, estimated bytes/packets when available, direction, reporter/vantage, project/resource, and the sampling/filter/route coverage configuration. Unknown fields stay unknown.
3. Correlate DNS answers, time-bounded workload inventory and NAT translations with flow endpoints. Link gateway/audit events by request identifier when supplied; otherwise retain candidate time/resource matches with their uncertainty. Do not turn a project/time-window match into exact per-key cost or an employee identity. Preserve separately observed principal/key/delegation evidence where available in the [audit schema](https://docs.cloud.google.com/logging/docs/reference/audit/auditlog/rest/Shared.Types/AuditLog).
4. Show observed routes, unmatched traffic, missing telemetry and destination-policy findings beside spend/incidents. Label findings as observed, inferred or unknown. Unknown processing region requires investigation or a configured policy decision; a mapped IP country does not justify a fraud verdict or a compliance certificate.
5. Keep metadata within the customer environment with least-privilege access and agreed retention. IPs, principal IDs and DNS labels can identify people or expose internal names; allowlist fields, mask sensitive labels and exclude payloads, raw headers and tokens before exports or alerts.

**Acceptance:** replay sanitized fixtures for a known provider call, NAT translation, inbound response, missing/redacted caller IP, absent DNS, sampled-out flow and Cloud Run route bypass. Re-ingestion must not duplicate evidence or money. A controlled external direct-key call must remain invisible in VPC evidence while appearing in the verified provider/audit path; record any unsupported path instead of claiming full coverage. Measure ingestion delay and log cost before broadening scope.

## Later clouds

AWS can use [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-basics.html), with [explicit omissions](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-limitations.html) and publication delay, plus provider/audit and DNS sources. Azure should target Virtual Network Flow Logs; [NSG flow logs no longer accept new creation and retire on 30 September 2027](https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-migrate). Both are later connectors, subject to the same metadata, vantage and bypass limits.
