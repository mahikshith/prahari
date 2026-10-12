# ASSUMPTIONS

**Reviewed: 2026-10-12.** Earlier assumptions are retained for traceability, not treated as incident facts. [docs/DECISIONS.md](docs/DECISIONS.md) governs current choices; [PROGRESS.md](PROGRESS.md) governs verification. A6 and A10 are resolved below. Live-provider and employer-data acceptance remain open.

Every assumption made in Mahikshith's absence, so none of them silently harden into fact.

**Rules:** each entry states what was assumed, why, the blast radius if wrong, and how to verify. Accepted choices now live in docs/DECISIONS.md; CONTEXT.md and CHANGELOG.md summarize them. When one is confirmed or corrected, move it out and note it in `PROGRESS.md`.

**Status key:** 🔴 blocks real data · 🟡 shapes work, cheap to change · 🟢 low risk

---

## A1 🔴 Incident data is unavailable, so the backtest runs on synthetic data

**Assumed:** the GCP BigQuery billing export for the incident window cannot be accessed yet, so the Stage 0 backtest is built against a **synthetic dataset calibrated to published LLMjacking rates** rather than real billing records.

**Calibration** (all from `docs/MARKET_RESEARCH.md` sources):
- Sysdig's $46,080/day is a modeled worst-case quota/price calculation, not sustained measured victim loss.
- Ten-day duration, roughly $70K/day and ₹84/USD are synthetic scenario inputs; they do not reconcile an actual invoice or prove the founder's reported ₹6–7 crore exposure.

**Why:** the backtest is the artifact that opens all 30 discovery calls. Waiting for data access would idle the only unblocked path to a demo. Real GCP sources expose different identity/usage fields and arrival delays; replacing the source table alone does not establish the same detection evidence.

**Blast radius if wrong:** low for the code, moderate for the claim. Every number in the artifact must be labelled synthetic until real data replaces it. **Never show a synthetic figure to a prospect as if it were measured** — one such slip destroys the credibility the artifact exists to build.

**Verify:** build a separately authorized real-source replay after proving field coverage and source delay. Do not assume a BigQuery-source CLI switch exists or that results should match the synthetic scenario.

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

**Blast radius:** absent dormancy or caller-origin evidence can disable those rules. Whether remaining rules detect the real event depends on source coverage, freshness and calibration; it is not guaranteed.

**Verify:** the real audit log will show first-use timing and caller origin.

---

## A5 🟡 GCP Cloud Audit Logs expose caller origin (IP/geo) for Vertex calls

**Assumed:** `NEW_GEO` is implementable on GCP because Cloud Audit Logs record `callerIp` and `callerSuppliedUserAgent` for Vertex AI API calls.

**Why:** the audit schema supports origin fields, but specific methods/settings must be checked. callerIp can be internal/redacted; callerSuppliedUserAgent is caller-controlled. Relative signal/noise is not yet measured.

**Blast radius:** moderate. If unavailable, `NEW_GEO` must abstain on GCP (the rule already does this correctly rather than guessing) and detection leans on spend and dormancy signals.

**Verify:** check whether Data Access audit logs are enabled for `aiplatform.googleapis.com` in the target project — they are **off by default**, which is itself a finding worth telling customers about.

---

## A6 🟢 Resolved 2026-10-12 runtime FX placeholders removed

**Prior assumption:** ₹84/USD was a synthetic presentation input, not a verified customer rate.

**Current outcome:** runtime FxTable defaults are empty and the daemon uses explicitly configured finite positive dated rates with provenance. Missing conversion remains a coverage/configuration gap; it does not invent money. Synthetic scenario rates remain labeled inputs only.

**Remaining acceptance:** verify the customer's chosen FX source/date and invoice treatment. See decision D008 and current PROGRESS.md for regression outcomes.

---

## A7 🟢 Detection thresholds are starting points, not calibrated values

**Assumed:** `SPEND_SPIKE_MULTIPLE = 3.2×`, `SPEND_SPIKE_MIN_ABSOLUTE = $50`, `DORMANCY_DAYS = 30`.

**Why:** all three are prototype judgment calls, not verified industry calibration. Validate false positives/misses on authorized partner workloads.

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

**Why:** stated explicitly — *"but first let's focus on llm or ai costs with cross platform for now."* Recorded in `CONTEXT.md` as the North Star with the architectural implications carried now (FOCUS terminology supports broader categories, but new sources, pricing and mappings may require model changes).

**Blast radius:** low. The data model is already general enough. The risk is scope creep, not rework.

**Verify:** confirm on next contact that AI-first sequencing still holds.

---

## A11 🔴 GCP billing export carries no caller identity — detection there is project-level only

**Discovered, not assumed** — but it changes the plan, so it belongs here.

The BigQuery Cloud Billing export contains project, service, SKU, location and resource. It does **not** contain who made the call. There is no service account, no API key, no caller IP.

**Consequence:** on GCP, the finest detection grain the billing export supports is the **project**. `DORMANT_KEY_WAKE` and `NEW_GEO` — the two rules that fired first and hardest in the backtest — cannot work from this source at all. Export delivery has no latency guarantee, so billing alone cannot establish sub-hour detection.

**What this means for the incident story:** the ₹6 crore detection narrative depends on credential-level signals. Those come from **Cloud Audit Logs** (`protoPayload.authenticationInfo.principalEmail`, `protoPayload.requestMetadata.callerIp`), not from billing. A GCP deployment therefore needs **two** connectors joined:

| Source | Gives | Latency | Job |
|---|---|---|---|
| BigQuery billing export | project, service, SKU, cost | no delivery/latency guarantee | provisional allocation and later reconciliation |
| Cloud Audit Logs | available principal/key/origin/method fields | verify observed delay and method coverage | identity/detection evidence where available |

**Verify:** confirm Data Access audit logs are enabled for `aiplatform.googleapis.com` — they are **off by default**, which is itself worth telling every prospect. Then implement supported audit/request correlation. Project/time matches alone do not prove exact per-key spend; retain uncertainty and unallocated amounts.

**Blast radius: high.** Without the audit-log connector, GCP detection is materially weaker than the case study implies. The billing connector shipped here is real and useful, but it is the allocation half, not the detection half.

---

## A12 🟡 Cloud services pulled forward into the AI wedge

**Assumed:** Mahikshith's request to "try integrating GCP BigQuery, Cloud Run billing as well" is a request to broaden **coverage**, not to re-order the roadmap away from AI-first.

**Why it cost almost nothing:** the billing export contains every GCP service in one table. One connector, one query, and BigQuery/Cloud Run/Compute/Storage arrive alongside Vertex. There was no version of this that covered only Vertex without deliberately discarding rows.

Services are tagged `ai` / `data` / `compute` / `other` (`connectors/gcp.py: classify`) so reporting can lead with AI and expand to total cloud spend without re-deriving the split.

**Blast radius:** low technically, real strategically. The risk is that the pitch drifts to "multi-cloud FinOps", which is CloudZero/Vantage/Finout's home ground and a fight we lose. **Coverage is broad; the story stays AI-first.**

**Verify:** confirm AI remains the lead in customer conversations, and watch the Gate tracker signal "their pain is cloud cost, not AI cost."

---

## A10 🟢 Resolved 2026-10-12 GitHub remote exists

**Prior assumption:** the project would remain local until manual publication.

**Current outcome:** origin points to https://github.com/mahikshith/prahari.git and the working branch is codex/prahari-pilot-foundation. Historical setup-script/private-repo/browser-login notes are not current access facts. Publishing follows explicit human authorization and secret review.

**Verify:** git remote -v and the current branch; use PROGRESS.md for actual publish/PR outcome. No account authentication or repository visibility is inferred from this entry.
