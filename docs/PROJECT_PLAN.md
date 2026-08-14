# Project Plan

Sequenced so that **each stage produces a sales artifact**, not just code. The research is unambiguous that distribution and trust — not engineering — decide this market, so nothing here builds for more than ~2 weeks without something to show a buyer.

## Stage 0 — The ₹6 crore backtest (now, ~1 week)

**Deliverable:** one sentence, backed by real data.
> *"Prahari would have fired at ₹X spent, N hours before the invoice revealed it."*

**Why first.** It costs a week, uses data we already own, and simultaneously: proves the detection-latency claim, becomes the cold open for all 30 discovery calls, and becomes slide 2 of any pitch. Building product before this is building blind.

- [ ] Export historical GCP billing data covering the incident window (BigQuery billing export)
- [ ] `scripts/backtest_incident.py` — load into DuckDB, reconstruct hourly spend per service account
- [ ] Implement `SPEND_SPIKE` + `DORMANT_KEY_WAKE` + `NEW_GEO` against that series
- [ ] Produce the timeline chart: actual spend curve, detection point, invoice-discovery point, rupees between them
- [ ] Write it up as an anonymised case study → `gtm/case-study-incident.md`

**Blocked on:** access to the GCP billing export for the incident period, and a decision on the IP/data-use position if this is employer data.

## Stage 1 — Reconciliation proof (~1 week)

**Deliverable:** "our numbers match your invoice to within 2%."

- [ ] Anthropic connector (Usage & Cost Admin API)
- [ ] OpenAI connector (org usage + costs)
- [ ] FOCUS-aligned `UsageRecord` + normalisation
- [ ] Vendored LiteLLM price registry with pinned SHA + checksum
- [ ] `scripts/reconcile.py` — computed total vs actual invoice, per provider, per period
- [ ] Hit ≤2% variance on real invoices, or find out why not

This is the credibility gate. A finance tool that disagrees with the invoice is dead on arrival, and we should discover that in week two rather than month six.

## Stage 2 — Discovery (parallel with Stage 1, ~4 weeks)

**Not blocked on code.** The backtest is the only artifact needed to open these conversations.

30 structured calls — 10 India GCC FinOps/platform leads, 6 BFSI, 5 CISOs, 8 Indian AI-native scale-ups. Score against the five gates in `DECISION_GATES.md`.

- [ ] `gtm/discovery-script.md` — the question set, phrased to avoid leading the witness
- [ ] `gtm/gate-tracker.md` — running score per gate
- [ ] Weekly review: are we still passing?

**Gate 3 (DPDP/residency raised unprompted) is make-or-break for India-domestic-first.** If it fails, the geography changes, not the product.

## Stage 3 — Working collector (~3 weeks, only if gates pass)

- [ ] GCP Vertex connector (BigQuery billing export + Cloud Monitoring) — the ₹6cr surface
- [ ] Detection engine proper: EWMA + STL deseasonalisation, all five rules
- [ ] Allocation engine with `UNALLOCATED` surfaced
- [ ] DuckDB store + Streamlit internal dashboard
- [ ] Docker image for the self-hosted collector
- [ ] Design partner runs it against their own data

## Stage 4 — Enforcement (~2 weeks)

The line between a dashboard and a control plane.

- [ ] Dry-run engine: what *would* be revoked, with no write access required
- [ ] Budget hard-stops (org/team/key)
- [ ] Key revocation via provider admin APIs
- [ ] Audit log with actor + reason
- [ ] Get one design partner to authorise a real revoke in a sandbox

## Stage 5 — Product (only with paying design partners)

Next.js + shadcn/ui + Tremor UI · multi-tenant control plane · WorkOS SSO · India-resident deployment option · SOC 2 readiness.

## Sequencing rules

1. **Never build more than two weeks without a buyer conversation.** The research says distribution decides this, not features.
2. **Every stage ends in something demonstrable**, not something merely working.
3. **Stage 2 gates outrank the build plan.** If they fail, stop and re-read `DECISION_GATES.md` — including the branches that say walk away.
4. **Reconciliation before features.** Wrong numbers cost more credibility than missing features.

## Named risks

| Risk | Response |
|---|---|
| Torii/Flexera ship enforcement first | Move on the security buyer they don't sell to; our detection latency is a harder engineering problem than their dashboards |
| Design partner won't grant admin keys | Self-hosted collector + dry-run mode exist precisely for this. If it still fails, that's a Gate-3 signal |
| GCP incident data unavailable / IP-encumbered | Reconstruct the scenario synthetically from published LLMjacking rates ($46K–100K/day). Weaker artifact, still usable |
| Solo founder + AI-written code handling credentials | Never hold customer credentials. Self-hosted collector is a security decision before it is a sales one |
