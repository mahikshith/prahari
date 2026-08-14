# Cross-Platform AI Cost Visibility — Market Research & Go/No-Go Decision

**Scope:** deep market research + a decision framework. No build plan — that comes only if the gates in Part 8 pass.
**Chosen direction (Mahikshith's call):** lead with **both** cross-provider cost visibility **and** credential-abuse detection/enforcement; **sell India-domestic first**.

---

## Context

**The trigger.** AI spend at the company is scattered across Claude Code (developers), Copilot Studio + M365 Copilot (management), Gemini (some teams), and GCP/Vertex service accounts (robotics/AI APIs). A GCP service account key leaked into an LLM chat, was used from outside the organisation, and the company is now carrying roughly **₹6 crore (~$700K)** of unbudgeted cost from a single credential.

**The hypothesis.** One platform giving real-time, cross-provider visibility into AI token and cost consumption by team — regardless of whether the team uses Azure, AWS, GCP, Anthropic, OpenAI or a seat-based tool — is a large, underserved market, especially in India.

**What this document answers.** Is the market real? Who already owns it? What have they missed? Would investors fund it? And what specifically has to be true before committing to build.

---

## Part 1 — Verdict up front

**Three findings, in order of importance:**

**1. The problem is real, urgent, and validated at the top of the FinOps profession.** 98% of FinOps practitioners now manage AI spend (31% in 2024). Granular AI spend monitoring is the **#1 most-requested capability** in the entire 2026 State of FinOps survey. 73% of AI projects blow their budget. This is not a hypothesis — it's the stated top unmet need of an entire profession.

**2. The generic product is already shipped by at least six funded companies, and every independent pure-play in the adjacent category was acquired in the last eight months.** Torii, Flexera, Finout, Vantage, Amnic and Mavvrik all ship cross-provider AI cost visibility today. Langfuse → ClickHouse, Helicone → Mintlify, Humanloop → Anthropic, Portkey → Palo Alto Networks ($140M). Visibility alone is a feature, not a company.

**3. The thing that actually burned ₹6 crore is unowned by anyone.** No product closes the loop from *leaked credential → anomalous inference spend → automated containment → quantified rupee impact*. FinOps tools see the bill but not the identity; security tools see the credential but never the money. That seam is the only defensible position — and it is the one lived through first-hand.

**Consequence for the chosen direction:** visibility and enforcement are not two options to pick between. **Visibility is the entry product; enforcement is the moat; and you cannot build the second without first building the first.** Ship visibility to land, ship enforcement to retain and to unlock the CISO budget. The pitch carries both from day one.

**Consequence for India-domestic-first:** it is a defensible choice, but it rests on **one** load-bearing assumption — that DPDP/data-residency gives an Indian vendor a structural reason to be preferred over Torii/Flexera/Vantage. Gate #3 in Part 8 tests exactly that. If residency doesn't come up unprompted in customer calls, India-domestic-first collapses into "a cheaper version of a crowded market," and the plan must change.

---

## Part 2 — Market validation (the case FOR)

### The pain is the #1 stated need of the FinOps profession

From the **State of FinOps 2026 Report** (1,192 practitioners managing $83B+ annual cloud spend):

| Metric | Value |
|---|---|
| FinOps practitioners managing AI spend | **98%** (63% in 2025, 31% in 2024) |
| #1 most-requested capability in the entire survey | **Granular AI spend monitoring** (tokens, LLM requests, GPU) |
| #1 desired skillset across all org sizes | AI cost management (58% prioritising training) |
| AI projects that exceeded budget | **73%** (some by 2.4×, ~$2.3M unanticipated) |
| Avg enterprise AI budget | ~$85K/month, up 36% in 2025 |
| FinOps teams also managing SaaS beyond cloud | 90% |

31% → 63% → 98% in 24 months is one of the fastest capability-adoption curves in enterprise software. **The tooling arrived after the problem — that is the startup window.**

### The cost curve is structurally worsening

- **Agentic multiplier:** Gartner (Mar 2026) — agentic AI consumes **5–30× more tokens per task** than chatbots. Microsoft/Stanford Digital Economy Lab put some agentic tasks at ~1000× chat, because full accumulated context is re-sent at every step (by step 20 you've paid for the same context 20 times).
- **Uber:** Claude Code adoption went 32% → 84% of a 5,000-engineer org between Dec 2025 and Mar 2026. **The entire annual AI budget was gone by April.** Per-engineer API cost ran $500–$2,000/month.
- Per-token prices fell **67% YoY** ($18.40 → $6.07 per M tokens) — and total spend still grew **483%** from 2024 to 2026. Jevons paradox: cheaper tokens make the visibility problem worse, not better.
- Token consumption projected to grow **24× by 2030**.

### Shadow AI exceeds the official budget

- Shadow AI = **4–9% of total enterprise software spend** (6% median) — **2–3× the formal AI budget line**; audited cases reach 10×.
- Concentration: ChatGPT personal/team 22–28%, AI coding tools 14–20%, Claude 10–16%, Perplexity/AI search 6–10%; a 50+ tool long tail is only 12–18%.
- Corporate-card category data is currently the *only* reliable discovery source — finance, not IT, holds ground truth. Nobody has productised that well.
- Orgs with high shadow AI average **$4.74M** breach cost vs $4.07M — a **$670K premium per incident**.

### The credential-abuse vector is a named, industrialised threat

The ₹6 crore incident has a name: **LLMjacking**.

- Coined by Sysdig (May 2024). Attacker scripts validate stolen credentials against **AI21, Anthropic, AWS Bedrock, Azure, ElevenLabs, MakerSuite, Mistral, OpenAI, OpenRouter and GCP Vertex AI**, then resell inference via reverse proxies.
- Sysdig's figures: **$46,080/day** on one Claude 2.x victim account; **>$100,000/day** on Claude 3 Opus. A documented Gemini key leak produced **$82,000 in ~48 hours** against a baseline of a couple hundred dollars a month.
- **Sysdig: 376% rise in credential theft specifically targeting AI services, Q4 2025 → Q1 2026.**
- Cloud Security Alliance (Mar & Jun 2026) now tracks it as a black market with suppliers, brokers and marketplaces. Pillar Security documented **"Operation Bizarre Bazaar"** (Dec 2025–Jan 2026), the first attributed large-scale campaign with a full commercial monetisation pipeline.

**₹6 crore from one service account is entirely consistent with published data. This is a category, not an outlier.**

### Capital and regulation are moving in

- Gartner: **$2.59 trillion** global AI spend in 2026; AI platforms/models market $64B, **+63% YoY**.
- Gartner: AI governance platform spend **$492M (2026) → $1B+ (2030)**, 45.3% CAGR; orgs with dedicated governance platforms are **3.4× more likely** to rate governance effective.
- Enterprise AI gateway market: **$0.88B (2025) → $11.32B (2035)**, 29.1% CAGR.
- India: DPDP Rules notified 13 Nov 2025, **hard compliance deadline May 2027**; IT Amendment Rules 2026 live since 20 Feb 2026.

---

## Part 3 — Competitive landscape (the case AGAINST the generic idea)

Four layers already claim pieces. **The pure-play layer has already consolidated.**

### Layer 1 — AI gateways / proxies (real-time tokens, only what routes through them)

| Player | Status |
|---|---|
| **Portkey** | **Acquired by Palo Alto Networks, $140M, agreed 30 Apr 2026.** Becomes the AI Gateway for Prisma AIRS. 1,600+ providers. |
| **Helicone** | **Acquired by Mintlify, Mar 2026. Maintenance mode.** |
| **LiteLLM** | OSS leader — 40K stars, ~3.4M downloads/day, 240M Docker pulls. Suffered a confirmed **supply-chain attack Mar 2026** (backdoored PyPI builds with credential-stealing payload). |
| Martian / TrueFoundry / Kong / Cloudflare | Routing-cost optimisation and infra plays. |

**Structural weakness:** a gateway only sees traffic developers deliberately route through it. Blind to ChatGPT Team seats, Claude.ai signups, Copilot licences — and, critically, **blind to a stolen credential calling the provider directly.** Adds latency; needs an org-wide rollout mandate.

### Layer 2 — LLM observability / tracing (deep per-app, needs instrumentation)

| Player | Status |
|---|---|
| **Langfuse** | **Acquired by ClickHouse, Jan 2026.** Still OSS, most-adopted open option. |
| **Humanloop** | **Sunset after joining Anthropic.** |
| LangSmith / Braintrust / Arize / W&B Weave | Eval-and-trace-first, not finance-first. |
| **Datadog LLM Observability** | $8 per 10,000 monitored LLM requests/month. Auto-instruments OpenAI, Anthropic, Bedrock, LangChain. |

**Structural weakness:** built for debugging, not cost attribution — they tell you a request was slow, not that it cost $0.12 because of a 4,000-token completion. SDK instrumentation means coverage is per-application and never organisation-complete.

### Layer 3 — Cloud FinOps platforms (billing-centric, bolting on AI)

| Player | Funding / scale | AI coverage |
|---|---|---|
| **PointFive** | **$60M Series B led by Accel (2026)**, w/ Index, Salesforce Ventures | Cloud + AI cost under consumption pricing |
| **CloudZero** | $56M Series C (May 2025); **~$42M ARR (Mar 2026)**, $14B spend under management | Cost-per-feature/customer — but **no dedicated third-party AI provider tracking** |
| **Finout** | $26.3M Series B | Ingests OpenAI, Anthropic, **Cursor** natively alongside AWS/GCP, **at no extra charge** |
| **Vantage** | — | Native **OpenAI Admin + Anthropic Admin** connectors, Vertex, Bedrock. **Daily granularity only** on Anthropic/OpenAI; built for finance more than engineering |
| **Mavvrik** (ex-DigitalEx) | $6.2M seed (S3 Ventures, Flyover) | Claims the only "full-stack AI FinOps": GenAI + agentic + infra + SaaS, OTel session-level agent tracking |
| **Amnic** | **$20M**, registered Bangalore / HQ SF | **Agentless, read-only**; OpenAI, Anthropic, Bedrock, Gemini + multi-cloud + K8s |
| nOps, OpsLyft, Economize, CloudKeeper | Smaller / India-linked | Cloud-first, AI bolt-on |

### Layer 4 — SaaS management & shadow AI — **the closest direct competitor**

| Player | Status |
|---|---|
| **Torii** | **Launched "AI Management Platform" 12 May 2026.** Meters **seats + tokens + shadow AI** together. Per-employee and per-model breakdown, forecasts overages before invoices arrive, flags **overlapping tools** (teams paying for Claude Code + Copilot + Cursor at once). Discovers personal-card signups via SSO logs, browser signals, finance feeds. **Leader, 2026 Gartner MQ for SaaS Management Platforms.** |
| **Flexera** | **Launched AI Cost Management 10 June 2026**, keynoted at FinOps X. Tokens + credits across **ChatGPT, Claude, Copilot** plus Bedrock/Foundry models. Fortune 500 early access. |
| **Zluri** | **Bangalore-founded.** AuthKnox discovery engine, 300+ integrations, explicit shadow-AI visibility. The most likely India-domestic competitor. |
| CloudEagle, Zylo, BetterCloud, Trelica (1Password) | Spend/licence optimisation with AI discovery layered on. |

### The honest read

> The product as originally described is being shipped right now by **Torii, Flexera, Finout, Vantage, Amnic and Mavvrik**. Torii already covers seats-*and*-tokens with Gartner MQ Leader distribution.
>
> Every independent pure-play in the adjacent category exited within eight months: **Langfuse → ClickHouse, Helicone → Mintlify, Humanloop → Anthropic, Portkey → Palo Alto Networks.**
>
> **Market message: "AI cost dashboard" is a feature unless it also owns enforcement or a data surface nobody else has.**

---

## Part 4 — What everyone has missed (the real openings)

**1. Cost and security are still two separate products — and this is the ₹6 crore seam.**
FinOps tools see a bill but have no concept of *which identity* spent it, or whether that identity was legitimate. Security tools (Wiz, Sysdig, GitGuardian, Prisma AIRS) see the leaked credential but never quantify the money. Nobody ships *leaked service account → anomalous inference spend → auto-revoke → rupee impact* as one timeline. Palo Alto buying Portkey proves convergence has started — but from the security side, sold to CISOs as security, not to CFOs as cost control.

**2. Detection latency is structurally too slow to matter.**
Vantage: **daily granularity** on Anthropic/OpenAI. AWS CUR and GCP billing exports: 4–24h+. LLMjacking burns **$46K–$100K/day**. A daily-granularity tool cannot in principle catch this before six figures are gone. Meanwhile Anthropic's Usage & Cost Admin API surfaces data **within ~5 minutes** and supports **one poll per minute** — the raw material for sub-hour detection exists and **nobody is using it for abuse detection.**

**3. No one covers all four spend surfaces in one allocation model.**
Seats (Copilot / ChatGPT Team / Cursor) + direct API tokens + cloud-native AI (Bedrock / Vertex / Azure OpenAI / GPU) + shadow AI. Torii has seats+tokens, thin on cloud-native AI and GPU. FinOps platforms have cloud but not seats. Nobody rolls all four into per-employee, per-team, per-cost-centre chargeback.

**4. Attribution still demands instrumentation nobody can mandate.**
Gateways need routing; SDKs need code changes. In a real enterprise — 40 teams, dozens of accounts, contractors, a GCC/HQ split — mandatory instrumentation is a 12-month rollout that never completes. **Agentless-first (admin APIs, billing exports, SSO logs, card feeds) is the only architecture that reaches full coverage in week one.** Amnic proves it works for cloud; nobody has done it end-to-end for AI.

**5. Agentic cost attribution is unowned.** With a 5–30× multiplier, the unit that matters is cost-per-agent-run, per-workflow, per-customer. Trace tools do it per-app; FinOps platforms don't do it at all.

**6. India-native requirements are served by exactly zero global vendors.**
INR/GST-aware invoice reconciliation, **DPDP-compliant India data residency**, **GCC↔HQ dual cost-centre allocation**, and transfer-pricing-friendly chargeback reports. A GCC that must show HQ what it consumed, in INR, for TP documentation, has no tool today. **This is the whole basis of the India-domestic-first bet.**

---

## Part 5 — India-domestic market (the chosen GTM, examined honestly)

### The four domestic buyer segments, ranked

| # | Segment | Why they buy | Realistic ACV | Cycle |
|---|---|---|---|---|
| **1** | **India GCCs** (2,100+ centres, 2.3M people, ~$100B revenue) | Spending **global-scale AI budgets from India**; increasingly separate contracting entities with own budgets; need GCC↔HQ chargeback and TP documentation | **₹25–80L ($30–95K)** | 3–6 mo |
| **2** | **BFSI + regulated** (banks, insurers, NBFCs) | RBI localisation + DPDP force India-resident governance data; highest compliance willingness-to-pay | **₹50L–2Cr ($60–240K)** | 6–12 mo |
| **3** | **Indian IT services** (TCS, Infosys, Wipro, HCL, LTIMindtree, Tech Mahindra + mid-tier) | Massive internal AI seat sprawl; must bill AI cost back to clients per project — a chargeback problem nobody solves | **₹50L–2Cr**, or OEM deal | 9–18 mo, high build-vs-buy risk |
| **4** | **Indian AI-native scale-ups / unicorns** (Razorpay, Meesho, Swiggy, Zepto, Cred, Postman, Sarvam, Krutrim…) | High AI intensity, fast decisions, real pain | **₹8–25L ($10–30K)** | 4–8 wks |

**Sequencing implication:** land segment 4 for logo velocity and product feedback, but **build the business on segment 1.** GCCs are the segment where the "India ACVs are low" rule breaks — their budgets are global budgets denominated locally.

### Why India-domestic-first is defensible here (steelmanning the choice)

1. **India adopts AI faster and therefore hits cost chaos first.** Deloitte: **40% of Indian orgs report significant or full AI usage vs ~28% globally.** Buyer readiness is genuinely ahead.
2. **GCCs are becoming independent buying centres** — they now contract as distinct legal entities outside global frameworks, and new AI/engineering workstreams carry their own budgets and stakeholders. This buyer did not exist three years ago.
3. **Regulation is a moat, not a tax.** DPDP Rules (deadline **May 2027**) plus RBI localisation give a *legal* reason to prefer an India-resident vendor over Torii/Flexera/Vantage — who will be slow to stand up India data residency for a mid-size market. **This is the single strongest structural advantage available.**
4. **INR/GST reconciliation and TP-friendly chargeback** are real unmet needs no global vendor will build.
5. **Market is growing fast:** India IT spend +6–8% in 2026 (vs 4–6% global), ~40% of budgets to change initiatives with **40–45% of that to AI/data**; India public cloud **$17.5B in 2026, +28.1%**; India AI/GenAI spend → **$6B by 2027** (33.7% CAGR).
6. **Founder is in-market with a lived ₹6 crore incident.** Credibility and warm network — in Indian enterprise sales, that is worth more than product differentiation.

### What must be designed around

| Constraint | Reality | Response |
|---|---|---|
| **ACV ceiling** | Domestic pricing is a fraction of US; India's $20B SaaS ARR is overwhelmingly *exported* | Anchor on GCC/BFSI, not SMB. **~25–40 customers to reach $1M ARR** — enterprise motion, not PLG |
| **IT services build-not-buy** | TCS/Infosys/Wipro already run FinOps + cloud-cost practices and monetise AI governance advisory | Sell them the **engine** (OEM/white-label), not the seat. Convert the biggest competitor into channel |
| **Zluri is already here** | Bangalore-founded, shadow-AI discovery, 300+ integrations | They own SaaS/identity; they do **not** own cloud-native AI, tokens, or abuse detection. Compete on the API/cloud/security half |
| **Long procurement** | 3–12 month cycles, services-bundled preference | Price a paid pilot; lead with a security incident story, which shortens cycles more than a cost story |
| **Price anchoring for later global expansion** | INR list price is hard to raise later | Publish a **USD list**, offer an India regional price at 40–50% of it. Identical product, explicit regional pricing — standard and reversible |

### Pricing model

**Platform fee tiered on AI spend under management.** Explicitly **not** % of savings (FinOps buyers now resist savings-share) and **not** % of spend (Indian CFOs read it as a tax on their own growth). Add a separate security/enforcement module priced to the CISO line item — in Indian enterprises that budget is frequently larger and less price-sensitive than the FinOps line.

---

## Part 6 — Investor appetite

**Capital is available, but only for the right shape.**

**In favour:**
- **PointFive: $60M Series B led by Accel (2026)** with Index and Salesforce Ventures — for precisely this thesis.
- CloudZero: $56M Series C, ~$42M ARR, growing ~33% in a single quarter (Dec 2025 → Mar 2026).
- Portkey exited at **$140M** to Palo Alto Networks in roughly three years.
- **Amnic raised $20M as an India-registered team** — direct proof that Indian founders get funded in this exact category.
- Gartner-sized adjacent category ($492M → $1B+) with a regulatory tailwind.

**To respect:**
- Every large round went to a **broad platform**; every **narrow point tool** was absorbed. A seed pitch for "cross-provider AI cost dashboard" in late 2026 draws the *"isn't this a feature of Torii/Flexera/Datadog?"* objection in minute three — and it is a fair objection. The answer must be enforcement + identity-level data, not more charts.
- **India-domestic-first specifically:** US funds will discount India-only TAM. Indian B2B funds (Accel India, Peak XV, Lightspeed India, Elevation, Together Fund, Stellaris, Blume) *do* back India-domestic B2B when the wedge is **compliance-driven** — which is exactly the DPDP/residency argument. **Pitch the India wedge as regulatory inevitability, not as patriotism.** Frame it as "India is the beachhead because DPDP makes residency mandatory by May 2027; the product is global."

**The strongest asset in any pitch is the ₹6 crore incident.** It is a specific, quantified, first-person failure of every tool on the market. Write it up as an anonymised case study — it is the cold open for every sales call and every investor meeting.

---

## Part 7 — Product shape implied by the research (for the decision, not for building)

**Positioning:** *The only platform that sees every rupee of AI spend across every provider — and can stop it within the hour when it goes wrong.*

**Sequence, not a choice:**
- **Entry (lands the deal):** agentless cross-provider visibility — tokens, seats, cloud AI and shadow AI normalised into one schema, allocated to teams and cost centres, reconciled to the invoice in INR with GST.
- **Moat (retains and expands):** per-identity, per-key, sub-hour anomaly baselines → LLMjacking detection → budget hard-stops and automated key revocation via provider admin APIs. Nearly free to build *once the read-only connections exist*, impossible to build without them, and it unlocks a second budget-holder.

**Why agentless is non-negotiable:** admin/usage APIs, billing exports, SSO logs and card feeds give full-organisation coverage in week one with no code changes. Gateways and SDKs cannot — and a stolen credential calling a provider directly is invisible to both.

**Deliberately out of scope:** gateway/proxy (PANW and LiteLLM own it), SDK tracing (Langfuse/Datadog own it), model routing (Martian), GPU cluster optimisation (nOps/Cast AI).

**Key technical fact that makes the moat real:** Anthropic's Usage & Cost Admin API delivers data in **~5 minutes** and permits **1 poll/minute**, against competitors' **daily** granularity and cloud billing exports' 4–24h lag. The detection-latency gap is a measurable, demonstrable product claim.

**Known integration trap to verify early:** GitHub Copilot cost attribution requires connecting **both** the org-level usage metrics API **and** the enterprise-level billing connection — org metrics alone will not surface cost. Usage is also attributed by org membership rather than seat assignment, so the same developer appears in multiple org dashboards and team totals cannot be summed. Any accurate seat-cost claim has to solve this.

---

## Part 8 — Go / No-Go decision framework

**Decide on evidence, not enthusiasm.** Run ~25–30 structured conversations before committing engineering time: **10 India GCC** FinOps/CloudOps/platform leads, **6 BFSI** (IT + risk), **5 CISOs**, **8 Indian AI-native scale-ups**. No product needed — the ₹6 crore story is the entire opening.

### The five gates

| # | Gate | Pass bar | Why it matters |
|---|---|---|---|
| **1** | **Blindness is real.** They cannot state per-team AI cost without a manual spreadsheet exercise | **>70%** | If they can already answer it, the entry product has no wedge |
| **2** | **The abuse vector is felt.** Have experienced a credential-abuse or runaway-agent cost event, or rank it top-3 fear | **>30%** | This is the differentiator. Below this, you're selling a commodity dashboard |
| **3** | **Residency is load-bearing.** DPDP / India data residency raised **unprompted** as a reason to prefer an Indian vendor | **>40%** | **The make-or-break gate for India-domestic-first.** This is the only structural advantage over Torii/Flexera |
| **4** | **Budget exists and is local.** ≥5 buyers confirm **₹20L+** annual budget authority for this line item, approvable in India | **≥5 of 30** | Tests whether GCC budget independence is real or theatre |
| **5** | **Enforcement is worth more than visibility.** Would pay materially more for auto-revoke + hard-stops than for dashboards alone | **>50%** | Determines whether this is a control plane (company) or a dashboard (feature) |

### Reading the result

- **Gates 1, 2, 3 and 5 pass →** GO. Build the agentless control plane, India-domestic-first, GCC-led. Raise on the compliance-inevitability narrative.
- **1, 2, 5 pass but 3 fails →** GO, but **not India-domestic-first.** Without the residency advantage you're competing on price against better-funded incumbents in your lowest-ACV market. Switch to India-built/global-sold, USD pricing.
- **1 and 3 pass, 2 and 5 fail →** This is a **feature**, not a company. Best outcome is building the normalisation + INR/GST/TP reporting engine and OEM'ing it to a FinOps or SaaS-management platform, or to an Indian IT services FinOps practice.
- **4 fails while others pass →** The product is right, the buyer is wrong. Re-target BFSI and Indian IT services, where budget authority is unambiguously local.
- **1 or 2 fails →** The ₹6 crore incident was an outlier for this company, not a market signal. Walk away cleanly and cheaply.

### One technical feasibility check worth doing during discovery

Using the company's own existing accounts (read-only admin keys, no new infrastructure): pull one month from the Anthropic Usage & Cost API, OpenAI org costs, and the GCP billing export, and **reconcile the computed total against the actual invoices.** Target **≤2% variance**. A finance tool that disagrees with the invoice is dead on arrival — and this is cheap to test now, before any commitment. It also produces the second-best artefact after the ₹6 crore story: proof the numbers tie out.

---

## Appendix — Sources

State of FinOps 2026 (finops.org/data — 1,192 practitioners, $83B+ spend) · Gartner AI governance and AI platforms forecasts (Feb & Jul 2026) · Sysdig LLMjacking research · Cloud Security Alliance LLMjacking research notes (Mar, Jun 2026) · Pillar Security "Operation Bizarre Bazaar" · Nasscom–Zinnov GCC Report 2026 · Deloitte India AI adoption · Bain India enterprise tech spend 2026 · IDC India AI spend · Torii AI Management Platform launch (12 May 2026) · Flexera AI Cost Management launch (10 Jun 2026) · Palo Alto Networks–Portkey acquisition (30 Apr 2026) · ClickHouse–Langfuse (Jan 2026) · Mintlify–Helicone (Mar 2026) · PointFive Series B (Accel) · CloudZero Series C and Sacra ARR data · Vantage / Finout / Mavvrik / Amnic / Zluri product documentation · Anthropic Usage & Cost Admin API docs · GitHub Copilot usage metrics API docs · Redress Compliance Shadow AI Spend Report 2026 · India DPDP Rules (notified 13 Nov 2025).
