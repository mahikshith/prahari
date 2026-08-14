# Decision Gates

**These outrank the build plan.** If the gates fail, we stop or change direction regardless of how much code exists. Written down now, before we're emotionally invested, precisely so that a later self can't quietly move the goalposts.

Evidence comes from **~30 structured conversations**: 10 India GCC FinOps/CloudOps/platform leads, 6 BFSI (IT + risk), 5 CISOs, 8 Indian AI-native scale-ups.

No product needed to run these. The ₹6 crore backtest is the entire opening.

## The five gates

| # | Gate | Pass bar | Why it matters |
|---|---|---|---|
| **1** | **Blindness is real** — they cannot state per-team AI cost without a manual spreadsheet exercise | **>70%** | If they can already answer it, the entry product has no wedge |
| **2** | **The abuse vector is felt** — they've had a credential-abuse or runaway-agent cost event, or rank it a top-3 fear | **>30%** | This is the differentiator. Below this, we're selling a commodity dashboard against six funded incumbents |
| **3** | **Residency is load-bearing** — DPDP / India data residency raised **unprompted** as a reason to prefer an Indian vendor | **>40%** | **Make-or-break for India-domestic-first.** The only structural advantage over Torii and Flexera |
| **4** | **Budget exists and is local** — confirmed **₹20L+** annual authority for this line item, approvable in India | **≥5 of 30** | Tests whether GCC budget independence is real or theatre |
| **5** | **Enforcement beats visibility** — would pay materially more for auto-revoke + hard-stops than for dashboards alone | **>50%** | Decides whether this is a control plane (a company) or a dashboard (a feature) |

## How to read the result

| Outcome | Decision |
|---|---|
| **1, 2, 3, 5 pass** | **GO.** Agentless control plane, India-domestic-first, GCC-led. Raise on the compliance-inevitability narrative |
| **1, 2, 5 pass · 3 fails** | **GO, but not India-domestic-first.** Without the residency advantage we'd be competing on price against better-funded incumbents in our lowest-ACV market. Switch to India-built / global-sold, USD pricing |
| **1, 3 pass · 2, 5 fail** | **It's a feature, not a company.** Best outcome: build the normalisation + INR/GST/transfer-pricing engine and OEM it to a FinOps or SaaS-management platform, or to an Indian IT services FinOps practice |
| **4 fails, others pass** | **Right product, wrong buyer.** Re-target BFSI and Indian IT services, where budget authority is unambiguously local |
| **1 or 2 fails** | **Walk away.** The ₹6 crore incident was an outlier for one company, not a market signal. Stop cleanly and cheaply |

## Rules for running this honestly

1. **Don't lead the witness on Gate 3.** The word "DPDP" must come from them. If we mention residency first, the answer is worthless — and Gate 3 is the one carrying the whole geography decision.
2. **Gate 2 counts real events, not enthusiasm.** "That sounds scary" is not a yes. "We had an incident / near-miss / it's on our risk register" is.
3. **Gate 5 needs a number, not a nod.** Ask what they'd pay for visibility alone, then for enforcement. A gap under ~30% counts as a fail.
4. **Record every call in `gtm/gate-tracker.md` the same day.** Retrospective scoring drifts toward whatever we want to be true.
5. **Review weekly.** If a gate is clearly failing by call 15, stop and re-decide — don't burn the remaining 15 calls confirming it.

## Technical feasibility check (runs alongside)

Using existing accounts, read-only, no new infrastructure: pull one month from the Anthropic Usage & Cost API, OpenAI org costs, and the GCP billing export, and reconcile computed totals against the actual invoices.

**Target: ≤2% variance.** A finance tool that disagrees with the invoice is dead on arrival — and this is cheap to test now, before commitment. It also yields the second-best artifact after the ₹6 crore story: proof the numbers tie out.
