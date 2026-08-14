# CONTEXT

*Why this project exists and what we've decided. Update when a decision changes, not when work progresses — that's `PROGRESS.md`.*

## The origin

A GCP service account key leaked into an LLM chat at Mahikshith's company. It was used from outside the organisation. The unbudgeted cost is roughly **₹6 crore (~$700K)** from that single credential.

The wider problem it exposed: AI spend is scattered across Claude Code (developers), Copilot Studio + M365 Copilot (management), Gemini (some teams), and GCP/Vertex service accounts (robotics/AI APIs). Nobody could say who was spending what, on which provider, until an invoice arrived.

## What the research established

Full memo: [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md). The three findings that shape everything:

1. **The problem is validated at the top of the FinOps profession.** 98% of practitioners now manage AI spend (31% in 2024); granular AI spend monitoring is the #1 most-requested capability in the 2026 State of FinOps survey; 73% of AI projects blow budget.
2. **The generic product is already shipped six times over.** Torii (May 2026), Flexera (June 2026), Finout, Vantage, Amnic, Mavvrik. And every independent pure-play in the adjacent category was acquired within eight months: Langfuse→ClickHouse, Helicone→Mintlify, Humanloop→Anthropic, Portkey→Palo Alto ($140M). **A cross-provider AI cost dashboard is a feature, not a company.**
3. **Nobody owns what actually cost ₹6 crore.** FinOps tools see the bill but not the identity. Security tools see the credential but never the money. The loop from *leaked credential → anomalous spend → containment → rupee impact* is unclaimed.

The incident is not bad luck — it's a named category, **LLMjacking**. Sysdig documented $46K/day on a hijacked Claude 2.x account and >$100K/day on Opus, and a **376% rise** in AI-targeted credential theft between Q4 2025 and Q1 2026.

## Decisions made

| Decision | Rationale |
|---|---|
| **Both visibility and enforcement** — visibility is the entry product, enforcement is the moat | Not a choice between them: you can't build the second without the first. Ship in that order, pitch both |
| **India-domestic first** | GCCs are now independent buying centres (2,100+ centres, 2.3M people); India adopts AI faster (40% vs 28% at significant/full usage); DPDP deadline May 2027 gives an Indian vendor a *legal* preference over Torii/Flexera |
| **Agentless, never a gateway or SDK** | A stolen credential calling a provider directly is invisible to both. That blindness is our differentiator — adopting their architecture would inherit it |
| **Self-hosted collector; we never hold customer credentials** | We'd otherwise be the highest-value target in the category. Also the DPDP story, also the enterprise objection-killer |
| **Backtest before product** | Research says distribution and trust decide this market, not features |
| **Codename Prahari** (प्रहरी, sentinel) | Provisional. Renaming is cheap now, expensive after the first customer |

## The load-bearing assumption

India-domestic-first rests entirely on **DPDP/data-residency giving us a structural reason to be preferred over Torii and Flexera.** That is Gate 3 in [docs/DECISION_GATES.md](docs/DECISION_GATES.md).

If residency does not come up **unprompted** in discovery calls, India-domestic-first collapses into "a cheaper version of a crowded market" — and the geography must change, not the product. Watch this one.

## Open questions

- **IP / data-use position** if the incident data and early customers come from the current employer. Needs sorting before we touch employer billing data. Not a blocker, cheaper now than later.
- **Name.** Prahari is a working codename, not a decision.
- **Whether GCC budget independence is real or theatre** — Gate 4 tests it.
