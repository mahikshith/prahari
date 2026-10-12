# Hourly cross-platform cost per user and account

**Reviewed:** 2026-10-12. **Status:** core product requirement clarified by the founder; live feasibility and implementation remain pending. Daily cost visibility is a central use case alongside incident response, not limited to service accounts.

## Product value and proposed view

Answer: what did this person/team spend this hour, across which approved platforms, accounts, models and tasks; how does that compare with their budget; and how much remains unpriced or unattributed? This supports regular budgeting and allocation even when there is no security incident. High spend alone does not establish waste or low productivity.

Display person/team, provider and account, model, time window, input/output/cache quantities, estimated cost, provider-reported cost where available, budget position, source freshness and attribution evidence. Keep native currency plus explicitly dated INR conversion. Hourly totals retain missing-cost and missing-identity coverage rather than pretending to be a complete bill.

## Three distinct numbers

| View | Source and meaning | Limit |
|---|---|---|
| Live consumption estimate | Completed request usage from an approved gateway/application, with trusted user identity and applicable model rates | Collection latency must be measured. Streams, tool fees, missing usage, discounts and unknown prices can prevent a complete estimate. In-flight exposure is separate. |
| Hourly usage/estimate | Request events or provider usage buckets, grouped by supported identity and priced with provenance | An hourly bucket does not prove immediate availability. Partial windows and source delays remain visible. |
| Reconciled cost | Provider cost reports and settled invoices, retaining credits/adjustments and unallocated differences | Coarser provider totals cannot be presented as exact per-user hourly charges; overlapping usage and billing layers must not be added together. |

## Verified source examples

- OpenAI's completions usage endpoint supports minute/hour/day buckets and grouping by user, API key, project and model. Its cost endpoint currently provides daily buckets and supports additional identity dimensions, with some user/project combinations dependent on organization and period. These are provider identities; they do not automatically identify an employee behind a shared backend. [Usage reference](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions), [cost reference](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs).
- Anthropic's general API usage provides minute/hour/day buckets and key/workspace/model dimensions; its general cost report is daily. [Usage and cost documentation](https://platform.claude.com/docs/en/manage-claude/usage-cost-api).
- Claude Code has a separate per-user analytics source with daily estimated token/cost metrics; its documentation directs real-time monitoring toward OTel integration. This is a later-source example, not an expansion of the GCP + OpenAI pilot. [Claude Code analytics](https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api).
- Gemini responses provide post-execution usage metadata; a pre-request token count may differ from consumed usage. Connect response usage to trusted application identity for attributed estimates. GCP billing alone does not supply that employee mapping. [Google token/usage guidance](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/get-token-count).

## Identity is the load-bearing integration

There are three supported paths to validate: provider user IDs mapped to the customer's identity directory; dedicated keys with explicit, time-bounded ownership; and authenticated application/gateway identity for users behind shared credentials. Key ownership is a declared mapping, not proof that only its owner used it. A service account, IP or project name is not an employee identity.

Namespace source IDs by provider and organization/account before mapping them to a customer-controlled person ID. Preserve the mapping source, validity period, team and confidence. Do not merge equal raw user IDs across accounts/providers, infer identity from a display name, or silently split shared usage equally. Unknown mappings remain unattributed. Collect the minimum identifier metadata; prompts and personal-account surveillance are unnecessary for this view.

Subscription/SaaS tools need separate authorized admin/report integrations. Keep their native seat fees, credits or metered quantities; do not manufacture token-level invoice costs from a subscription fee. Unmanaged personal accounts cannot be promised universal coverage.

Hourly boundaries need an explicit timezone. A coarse UTC hour cannot be divided accurately into IST calendar hours without finer events; preserve the source bucket or obtain minute/request-level data. State source event time and availability time separately.

## Repository state and minimum pilot

The OpenAI connector already requests hourly usage grouped by user/key/project/model. `UsageRecord` carries user and account fields; `per_user_consumption` rolls up raw user IDs and falls back to a key identifier. This is not a validated cross-platform employee identity system. Raw-ID namespacing/mapping, evidence labels, hourly presentation and live source acceptance remain work to do.

Use two test employees, two providers and one approved company application. Capture one provider-identity path and one shared-key application path, plus an unattributed direct call. Establish whether the same person is resolved correctly across accounts without cross-account collisions. Measure freshness, preserve unknown prices and missing stream usage, avoid replay duplicates, and reconcile the supported provider total. Prove that the displayed per-user sum plus unattributed amount explains the known subtotal.

The first pilot remains GCP + OpenAI. Broader employee tools follow demonstrated demand and usable admin data. This feature deserves priority over general network-security expansion; its value must still be compared with existing FinOps/gateway products and validated with paying users.
