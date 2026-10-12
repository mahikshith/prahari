# Project Plan

**Historical staging snapshot:** stage/status claims, schedules and checklists below preserve an earlier plan, not current completion evidence. DECISIONS.md/PROGRESS.md govern GCP + OpenAI, hybrid scope and actual outcomes; the founding event is reported and the existing replay synthetic.

**Consistency review: 2026-10-12.** This design catalog includes deferred targets, not a shipped-feature inventory. Current scope and outcomes are in [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](../PROGRESS.md): GCP + OpenAI, hybrid collection, customer-owned India cloud first, and live-source/response acceptance still required.

> **For the concrete work breakdown from here to a working MVP, see
> [MVP_ROADMAP.md](MVP_ROADMAP.md).** This document holds the staging philosophy and
> the standing risks; the roadmap holds the ordered task list, dependencies and
> done-criteria. Stage 0 below is complete (on synthetic data) and Stage 1 is partly
> complete.

Each stage should produce demonstrable technical and buyer evidence. Distribution,
trust and implementation correctness all matter; keep buyer conversations alongside
engineering instead of treating either as proof of product-market fit.

## Stage 0 — The ₹6 crore backtest (now, ~1 week)

**Deliverable:** one sentence, backed by real data.
> *"Prahari would have fired at ₹X spent, N hours before the invoice revealed it."*

**Why first.** A synthetic replay can exercise detection rules while source access is unresolved. It does not prove real latency, ownership of employer records or prevented loss; an authorized real replay requires source-availability evidence.

- [ ] Export historical GCP billing data covering the incident window (BigQuery billing export)
- [ ] Real replay adapter — separate project billing from supported audit/request identity evidence; billing alone cannot reconstruct per-service-account spend
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

Residency is one buyer/deployment signal, not a blanket legal preference for an Indian vendor or the sole India-first criterion. Current gates require paid-pilot, technical and renewal evidence.

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
- [ ] Planned routed budget admission/blocking with verified concurrency and bypass limits
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
| Incumbent meets the same pilot need | Compare the actual workflow/deployment cost; narrow the wedge or consider integration/OEM instead of asserting an unserved buyer |
| Design partner won't grant admin keys | Self-hosted collector + dry-run mode exist precisely for this. If it still fails, that's a Gate-3 signal |
| GCP incident data unavailable / IP-encumbered | Use explicitly synthetic fixtures; published worst-case threat estimates are scenario inputs, not measured typical loss |
| Solo founder + AI-written code handling credentials | Customer-held deployment, least privilege, secret-safe operational configuration and regression/live checks; hosting does not eliminate runtime risk |
