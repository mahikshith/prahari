# PROGRESS

*Session handoff. A cold session — or one resuming after a rate limit — should read
`CLAUDE.md` → this file → `ASSUMPTIONS.md` and be able to continue without
re-deriving anything.*

**Last updated:** 2026-08-15 (autonomous session)
**Stage:** 0 — the incident backtest ✅ done · Stage 1 partially done · Stage 2 ready to run
**Tests:** 47 passing · ruff clean
**Repo:** local only, 4 commits, no remote (see `ASSUMPTIONS.md` A10)

---

## Where things actually stand

**The Stage 0 artifact exists and works.** `uv run python scripts/backtest_incident.py`
produces the headline:

> Detected at **₹72,359** spent — **10 days** and **₹5.84 crore** before the invoice
> revealed it.

All four signals corroborate inside the attack's first hour, and the legitimate
control credential raises warnings but never criticals. **This runs on synthetic data**
calibrated to published LLMjacking rates because the real GCP export isn't accessible
(`ASSUMPTIONS.md` A1) — the detection path is identical when real data lands.

**Stage 2 (discovery) is fully unblocked and is now the critical path.** The case
study, call script and gate tracker are written. Nothing about the 30 calls depends on
more code.

---

## Done

### Research and scaffold
- [x] Market research — market size, four competitor layers, gaps, investor appetite, India reality → `docs/MARKET_RESEARCH.md`
- [x] OSS inventory with licence audit → `docs/OSS_INVENTORY.md`
- [x] Requirements, architecture, tech stack, staged plan, decision gates → `docs/`
- [x] Repo, git, `CLAUDE.md`, `CONTEXT.md`, `ASSUMPTIONS.md`, `CHANGELOG.md`

### Detection engine (the moat)
- [x] FOCUS 1.3-aligned `UsageRecord` — Decimal money, UTC-only, components kept separate
- [x] Five named rules, seasonally-adjusted per-credential baselines, 24h exposure projection
- [x] `UsageRecord` → `Observation` aggregation with gap filling
- [x] **Bug found & fixed:** `detection_key` included model+region, so an attacker switching models got a fresh empty baseline. Now per-credential.
- [x] **Bug found & fixed:** gap-filled zero hours refreshed `last_seen`, so `DORMANT_KEY_WAKE` could never fire. `last_seen` now tracks activity, not observations.

### Backtest
- [x] Synthetic incident generator — two credentials (legit control + stale leaked key), calibrated to Sysdig's $46K–$100K/day
- [x] Backtest script with structured JSON output
- [x] Indian digit grouping (lakh/crore), because western grouping reads as carelessness to our buyer

### Connectors
- [x] Anthropic — Usage & Cost Admin API, hourly buckets, split cache-creation shapes
- [x] OpenAI — org usage/costs, epoch timestamps, cached-token subtraction
- [x] Price registry vendored from LiteLLM at pinned SHA `4ea5749` (2,427 models), sha256-verified
- [x] Mocked tests for both (**not** exercised against live APIs — `ASSUMPTIONS.md` A8)

### GTM
- [x] `gtm/case-study-incident.md` — the cold open, with an honest synthetic-data banner
- [x] `gtm/discovery-script.md` — 30-call question set, engineered not to lead on Gate 3
- [x] `gtm/gate-tracker.md` — same-day scoring template

---

## Next up

**Ranked. The first two need Mahikshith; the rest don't.**

1. **[BLOCKED — needs Mahikshith] Settle the IP/data-use position.** Everything touching employer data waits on this. `ASSUMPTIONS.md` A2. Cheapest item on the list, largest blast radius.
2. **[BLOCKED — needs Mahikshith] GCP billing export access** for the incident window. Re-run the backtest on real data, delete the synthetic banner from the case study.
3. **[READY] Start the 30 discovery calls.** This is the critical path — the gates decide whether any more code is worth writing. Nothing blocks it.
4. **[READY] Reconciliation script** (`scripts/reconcile.py`) — computed total vs actual invoice, per provider. Needs an admin key to run, but can be written now.
5. **[READY] GCP Vertex connector** — BigQuery billing export + Cloud Monitoring. The ₹6cr surface, and the one connector we most need.
6. **[READY] Streamlit view over the backtest** — turns the terminal output into something demoable on a call.
7. **[LATER] Enforcement dry-run engine.** Gate 5 decides whether this is the product or a nice-to-have.

---

## Blocked

| Item | Blocked on | Assumption made meanwhile |
|---|---|---|
| Real backtest | GCP billing export access | A1 — synthetic data, clearly labelled |
| Any employer data | IP / data-use position | A2 — nothing touched, synthetic only |
| Live connector verification | Admin API keys | A8 — written to documented shapes, mocked tests |
| GitHub remote | Mahikshith's authorisation | A10 — local only |

---

## How to run things

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"   # uv
cd C:\Users\mahik\Prahari

uv run python -m pytest tests/ -q                     # 47 tests
uv run --with ruff ruff check src tests scripts       # lint
uv run python scripts/backtest_incident.py            # THE ARTIFACT
uv run python scripts/backtest_incident.py --json out/backtest.json
uv run python scripts/fetch_pricing_registry.py       # refresh pinned registry
```

**Gotchas that cost time once already:**
- Never round-trip source files through PowerShell `Get-Content`/`Set-Content` — it mangles UTF-8. Use the Edit tool.
- `Scenario` uses `slots=True`, so defaults aren't readable off the class (`Scenario().seed`, not `Scenario.seed`).
- `premium_models()` requires a provider. Unfiltered, re-hosted variants (wandb/, watsonx/) dwarf the frontier models.

---

## Decision log

| Date | Decision |
|---|---|
| 2026-08-15 | Both visibility **and** enforcement, sequenced — visibility lands, enforcement is the moat |
| 2026-08-15 | India-domestic first, contingent on Gate 3 (DPDP/residency raised unprompted) |
| 2026-08-15 | Agentless only — no gateway, no SDK instrumentation |
| 2026-08-15 | Self-hosted collector; we never store customer credentials |
| 2026-08-15 | Python data plane; Streamlit for the throwaway v0, Next.js for the real product UI |
| 2026-08-15 | Vendor LiteLLM pricing JSON, never install the package (Mar 2026 supply-chain attack) |
| 2026-08-15 | Backtest before product — the artifact opens 30 doors, the product opens none yet |
| 2026-08-15 | **Unified platform is the North Star; AI cross-provider is the wedge.** Entering from AI and expanding to cloud is the opposite of every incumbent's path, and better: the security moat only exists on the AI side |
| 2026-08-15 | Detection baselines are per-**credential**, not per-(credential, model) — anything finer is an evasion hole |
