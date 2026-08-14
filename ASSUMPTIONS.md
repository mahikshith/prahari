# ASSUMPTIONS

Every assumption made in Mahikshith's absence, so none of them silently harden into fact.

**Rules:** each entry states what was assumed, why, the blast radius if wrong, and how to verify. Nothing here is a decision — decisions live in `CONTEXT.md` and `CHANGELOG.md`. When one is confirmed or corrected, move it out and note it in `PROGRESS.md`.

**Status key:** 🔴 blocks real data · 🟡 shapes work, cheap to change · 🟢 low risk

---

## A1 🔴 Incident data is unavailable, so the backtest runs on synthetic data

**Assumed:** the GCP BigQuery billing export for the incident window cannot be accessed yet, so the Stage 0 backtest is built against a **synthetic dataset calibrated to published LLMjacking rates** rather than real billing records.

**Calibration** (all from `docs/MARKET_RESEARCH.md` sources):
- Sysdig: $46,080/day sustained on a hijacked Claude 2.x account; >$100,000/day on Claude 3 Opus
- Documented Gemini key leak: $82,000 in ~48 hours against a ~$200/month baseline
- Attack duration modelled at ~10 days × ~$70K/day ≈ $700K ≈ **₹5.9 crore at ₹84/USD** — which reconciles with the reported ₹6 crore

**Why:** the backtest is the artifact that opens all 30 discovery calls. Waiting for data access would idle the only unblocked path to a demo. The pipeline is identical either way; only the source table changes.

**Blast radius if wrong:** low for the code, moderate for the claim. Every number in the artifact must be labelled synthetic until real data replaces it. **Never show a synthetic figure to a prospect as if it were measured** — one such slip destroys the credibility the artifact exists to build.

**Verify:** run `scripts/backtest_incident.py --source bigquery` once access exists. The detection output should be directionally similar; if it is wildly different, the rule thresholds are miscalibrated and that is a genuine finding.

---

## A2 🔴 Employer IP/data-use position is unresolved

**Assumed:** no employer data is touched. Everything to date uses synthetic or public data only.

**Why:** the incident occurred at Mahikshith's employer. Whether the billing data, the incident narrative, and any early customer relationships are usable commercially is a real question with a cheap answer now and an expensive one later.

**Blast radius if wrong:** severe and retroactive — it could taint the founding artifact and the first customer relationships.

**Verify:** Mahikshith to confirm the position before any employer billing data enters this repo. Until then `data/` stays synthetic. **This is the single most important open item.**

---

## A3 🟡 The ₹6 crore figure is gross unbudgeted cost, unrecovered

**Assumed:** ₹6 crore is the total unbudgeted spend, without provider goodwill credits, insurance recovery, or negotiated write-down.

**Why:** it was stated as "the cost the company has to bear."

**Blast radius:** affects only the case-study headline. If a large portion was recovered, the honest number is smaller and the story shifts from "cost" to "exposure and recovery effort" — still a strong story, differently framed.

**Verify:** ask what was actually paid after any credits.

---

## A4 🟡 Attack shape: dormancy, then sustained abuse from new geography

**Assumed:** the key leaked, sat unused for a period, then was monetised — sustained high-volume inference from an unfamiliar origin, outside business hours, on premium models.

**Why:** this is the documented LLMjacking pattern (harvest → validate → resell via reverse proxy), and it is what CSA's "Operation Bizarre Bazaar" describes. It is also the shape that makes `DORMANT_KEY_WAKE` and `NEW_GEO` fire.

**Blast radius:** if the real attack began immediately on leak, `DORMANT_KEY_WAKE` contributes nothing and `SPEND_SPIKE` carries the detection alone. Detection still works; the artifact is just less multi-signal.

**Verify:** the real audit log will show first-use timing and caller origin.

---

## A5 🟡 GCP Cloud Audit Logs expose caller origin (IP/geo) for Vertex calls

**Assumed:** `NEW_GEO` is implementable on GCP because Cloud Audit Logs record `callerIp` and `callerSuppliedUserAgent` for Vertex AI API calls.

**Why:** standard for GCP admin/data-access audit logs. Without it, the highest-signal, lowest-noise rule is unavailable on our primary surface.

**Blast radius:** moderate. If unavailable, `NEW_GEO` must abstain on GCP (the rule already does this correctly rather than guessing) and detection leans on spend and dormancy signals.

**Verify:** check whether Data Access audit logs are enabled for `aiplatform.googleapis.com` in the target project — they are **off by default**, which is itself a finding worth telling customers about.

---

## A6 🟡 FX rate ₹84 = $1 for INR presentation

**Assumed:** a flat ₹84/USD for converting published USD figures to INR in artifacts.

**Why:** approximate mid-2026 rate; sufficient for an order-of-magnitude artifact.

**Blast radius:** cosmetic in the artifact, **not** in the product. `UsageRecord` already stores `currency` and `fx_rate_date` separately for exactly this reason — production must use RBI reference rates dated to the transaction, not a constant.

**Verify:** wire the RBI reference rate feed before any customer-facing number.

---

## A7 🟢 Detection thresholds are starting points, not calibrated values

**Assumed:** `SPEND_SPIKE_MULTIPLE = 3.2×`, `SPEND_SPIKE_MIN_ABSOLUTE = $50`, `DORMANCY_DAYS = 30`.

**Why:** 3.2× is the widely-cited industry starting threshold; the $50 floor and 30-day dormancy are judgement calls to suppress noise.

**Blast radius:** low now, high at a customer. Every one is a false-positive/miss tradeoff we must own explicitly. A detector that cries wolf weekly gets muted, which is operationally identical to not existing.

**Verify:** calibrate against real design-partner data. Until then, treat any precision claim as unearned.

---

## A8 🟡 Anthropic and OpenAI connectors written against documented API shapes, unexercised

**Assumed:** the Usage & Cost Admin API and OpenAI org usage/costs endpoints behave as documented — response shape, pagination, and rate limits.

**Why:** no admin keys available. Connectors are written to the documented contract and covered by mocked tests.

**Blast radius:** moderate. Real APIs routinely differ from their docs in pagination and edge cases. Expect a round of fixes on first live call, and treat the mocked tests as design validation, not proof of correctness.

**Verify:** run `verify_credentials()` against a real admin key, then reconcile a full month against an actual invoice (≤2% variance, `docs/REQUIREMENTS.md` F4.2).

---

## A9 🟢 Unified platform is the North Star; AI-first is the wedge

**Assumed:** Mahikshith's instruction that the platform must eventually cover all cloud cost (BigQuery, Cloud Run, GKE, storage) — not only AI — is a **roadmap** statement, not a re-scope of the current wedge. AI/LLM cross-provider stays the entry product.

**Why:** stated explicitly — *"but first let's focus on llm or ai costs with cross platform for now."* Recorded in `CONTEXT.md` as the North Star with the architectural implications carried now (FOCUS 1.3 already covers all cloud services, so nothing needs re-modelling later).

**Blast radius:** low. The data model is already general enough. The risk is scope creep, not rework.

**Verify:** confirm on next contact that AI-first sequencing still holds.

---

## A10 🟢 No GitHub remote created

**Assumed:** the repo stays local until Mahikshith authorises a remote.

**Why:** pushing publishes the incident narrative, the strategy, and the competitive analysis. That is an outward-facing action and his call, not mine.

**Verify:** ask. A private remote is a minute's work once authorised.
