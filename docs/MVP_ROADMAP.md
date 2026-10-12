# MVP Roadmap

**Historical work breakdown:** status counts, session estimates and phase checklists below preserve earlier planning; they are not the current implementation/test record. Follow DECISIONS.md and PROGRESS.md. Persistence/config/daemon are now implemented locally; accepted work prioritizes GCP + OpenAI and the hybrid pilot.

**Consistency review: 2026-10-12.** This design catalog includes deferred targets, not a shipped-feature inventory. Current scope and outcomes are in [DECISIONS.md](DECISIONS.md) and [PROGRESS.md](../PROGRESS.md): GCP + OpenAI, hybrid collection, customer-owned India cloud first, and live-source/response acceptance still required.

**What "MVP" means here, precisely:**

> A design partner installs the collector in their own VPC, points it at their own
> accounts, and targets: cost allocated where trusted evidence exists and reconciled to their
> invoice within 2%, abuse alerts delivered somewhere they actually read, and budget
> tracking with dry-run enforcement.

Not a demo. Not a dashboard. Something a stranger runs against production data
without us in the room.

Everything below is measured against that bar. Anything that doesn't move us toward
it is out of scope, however tempting.

---

## Historical implementation snapshot

*Updated after the Phase B build. 205 tests, ruff clean.*

| Built and tested | Built but **never run for real** | Not built |
|---|---|---|
| Detection engine, 5 rules | Anthropic connector | Enforcement actions (E) |
| Baselines, aggregation | OpenAI connector | GCP audit-log connector (C1) |
| Budget engine + scoping | GCP billing connector | Streamlit view (D1) |
| Insights, rankings, FX | Price registry | Multi-tenant / auth / UI |
| **DuckDB store** (A3) | | |
| **Collector daemon** (B1) | | |
| **Alert delivery** (B2) | | |
| **YAML config + CLI** (B3) | | |
| **Docker collector** (B4) | | |
| Backtest, report CLI | | |

**The honest summary: the collector is now a running program rather than a set of
scripts — but nothing has still ever touched a live provider API.** Phase A remains
the critical path and remains blocked on credentials.

Try it without any credentials at all:

```powershell
uv run prahari validate -c prahari.example.yaml   # exits 2: config good, creds missing
uv run prahari status   -c prahari.example.yaml
```

---

## The one thing that matters most

**No connector has ever met a real API.** Every response shape, pagination cursor,
rate limit and edge case is written from documentation (`ASSUMPTIONS.md` A8). Real
billing APIs routinely differ from their docs.

Live acceptance needs authorized credentials. Employer-data permission gates employer records; independent founder/customer sandbox verification need not wait on that permission.

**That is the critical path. It is also the cheapest item on this list.**

---

## Dependency order

```
  IP position (A2)  ──►  credentials  ──►  A1 live-fire  ──►  A2 reconcile ≤2%
                                                │                    │
                                                │                    └──►  real backtest,
                                                │                          retain evidence labels
                                                ▼
                                          A3 persistence
                                                │
                        ┌───────────────────────┼───────────────────────┐
                        ▼                       ▼                       ▼
                   B1 daemon              B2 alert delivery        B3 config file
                        └───────────────────────┼───────────────────────┘
                                                ▼
                                         B4 Docker collector
                                                │
                                                ▼
                                    ►  DESIGN PARTNER RUNS IT  ◄
                                                │
                                ┌───────────────┴───────────────┐
                                ▼                               ▼
                    C  GCP audit-log identity          E  enforcement actions
                       (fixes A11)                        (only if Gate 5 passes)

  Discovery calls run in parallel throughout and gate everything past B.
```

---

## Phase A — Make it real

*Do this regardless of the gates. It de-risks everything and produces the
reconciliation number, which is itself a sales artifact.*

### A1 · Verify the selected GCP and OpenAI sources
**Size:** 1–2 sessions, plus however long the surprises take.
**Needs:** authorized OpenAI admin access and GCP billing/audit access with least-privilege grants. Existing Anthropic support is not an additional pilot prerequisite.

Run `verify_credentials()`, then a real `fetch()` over a settled window. Expect
breakage in pagination, field names, and empty-window handling. Fix, and convert
each surprise into a test.

**Done when:** selected sources return real records and field/completeness evidence for an agreed window, and every
mocked test still passes alongside a new real-shape fixture.

### A2 · Reconciliation script — **the credibility gate**
**Size:** 1 session. **Depends on:** A1.

`scripts/reconcile.py`: computed total vs the actual invoice, per provider, per
billing period. Report variance and where it comes from.

**Done when:** variance ≤2% (F4.2) on a real invoice, or we understand exactly why
not. A finance tool that disagrees with the invoice is dead on arrival — better to
learn that in week two than month six.

### A3 · Persistence
**Size:** 2 sessions. **Blocks:** everything in Phase B.

The earlier empty-store state is superseded: DuckDB persistence, watermarks and per-channel notification state are implemented locally. The remaining acceptance below tests restart, replay and source correctness.

- DuckDB store with a `usage_records` table keyed on the natural grain
- Idempotent upsert — re-fetching a window must not double-count
- Per-connector watermarks so the daemon knows where it left off
- Alert state, so a fired threshold doesn't re-fire every cycle
- Same query layer used by the backtest and the report

**Done when:** collect twice over the same window and totals are unchanged; kill the
process mid-backfill and it resumes correctly.

---

## Phase B — Make it run

*This is what turns a set of scripts into something a stranger can install. Do not
start before the discovery gates pass — see `DECISION_GATES.md`.*

### B1 · Collector daemon
**Size:** 2 sessions. **Depends on:** A3.

Async loop, measured provider-specific source freshness and permitted poll intervals, incremental fetch with provisional GCP scan/overlap semantics, exponential backoff,
graceful shutdown, structured logs with no credentials in them.

**Done when:** it runs unattended for 48 hours, survives a provider 500 and a
network drop, and its totals still reconcile.

### B2 · Alert delivery
**Size:** 1 session. **Depends on:** A3.

An alert nobody receives is not detection. Slack webhook + SMTP, routed per budget
owner, with dedup and a daily digest for low-severity findings. The alert body is
already written — `Alert.explain()` and `BudgetState.explain()` produce it.

**Done when:** a synthetic test alert reaches configured remote channels within an
agreed delivery target; restarts preserve failed messages and do not retry recorded
successful channels. At-least-once delivery can still duplicate after remote acceptance
but before durable local acknowledgement; this is not a detection SLA or exactly-once claim.

### B3 · Config file
**Size:** 1 session.

Budgets, connectors, allocation rules and alert routing are currently hardcoded in
`scripts/report.py`. Needs a validated YAML config (Pydantic — already a dependency)
with a `--dry-run` validate mode.

**Done when:** a design partner configures their own budgets without touching Python.

### B4 · Docker collector
**Size:** 1 session. **Depends on:** B1, B3.

Customer-owned India deployment reduces central credential exposure. Review provider/log/backup/notification/support destinations independently; a container/VPC does not establish compliance or complete security.

Non-root image, no secrets baked in, env or mounted-file credentials, healthcheck,
`docker compose up` quickstart in the README.

**Done when:** someone who has never seen the repo gets it collecting in under 15
minutes from the README alone.

---

## Phase C — Close the GCP detection gap

### C1 · Cloud Audit Logs connector
**Size:** 2 sessions. **Why it matters:** `ASSUMPTIONS.md` A11.

The GCP billing export carries **no caller identity**. GCP detection is currently
project-level, and `DORMANT_KEY_WAKE` and `NEW_GEO` — the two rules that fired
hardest in the backtest — cannot work from it at all.

Verify principal/key/delegation, method and callerIp availability per target API. Prefer request-level correlation where supplied. Project/time matches are candidate evidence, not exact per-key billing; preserve unknown/unallocated cost and redacted origin.

**Note for the first sales conversation:** Data Access audit logs are **off by
default** for many GCP services. Check actual configuration and method coverage during onboarding; do not assume every prospect is missing them.

**Done when:** an authorized fixture establishes real identity/usage coverage, source delay and reconciliation limits. Do not claim exact credential spend without matching evidence.

---

## Phase D — Make it demoable

### D1 · Streamlit view
**Size:** 1 session. Deliberately throwaway — the real UI is Next.js, later, only
with paying design partners. This exists to make the backtest and budget views
presentable on a call.

### D2 · Real backtest
**Depends on:** authorized A1/C1 evidence. Publish real findings separately from synthetic scenarios, with source-availability and response limits. Never drop the synthetic label from figures still generated by fixtures or imply avoided losses from replay alone.

---

## Phase E — Enforcement

The hybrid control path is accepted design scope; implementation remains gated by source/accounting/response acceptance and customer authorization. Paid-pilot evidence determines expansion.

`decide_enforcement()` currently returns a decision and nothing acts on it. To close
the loop:

- Provider adapters: Anthropic admin key disable, OpenAI key revoke, GCP service
  account key disable / quota override
- Approval flow — nobody grants write scope to something that acts unilaterally
- Immutable audit log: actor, reason, before/after
- Circuit breaker and rate limit, so a bug cannot revoke an entire estate
- Reversal path where the provider allows it

**Done when:** a design partner authorises one real revoke in a sandbox and it works,
audited end to end.

---

## Not in the MVP — actively defended

Multi-tenant control plane · authn/authz · SOC 2 · Next.js UI · AWS Bedrock and Azure
OpenAI connectors · seat/shadow-AI discovery · agentic per-run attribution · anything
resembling general multi-cloud FinOps.

Each is real work we will likely do. None of it gets a design partner to value
faster, and the research is unambiguous that the way to lose here is to drift into
CloudZero/Vantage/Finout's territory before we own our own.

---

## Non-code work, which is still the critical path

| | Owner | Status |
|---|---|---|
| **Settle the IP/data-use position** (A2) | Mahikshith | Blocks employer-data use; independent authorized sandboxes remain available |
| **Run the 30 discovery calls** | Mahikshith | Unblocked. Gates everything past Phase A |
| GitHub publication | Mahikshith | Remote exists; current publishing follows explicit authorization and secret review |
| Obtain admin credentials for A1 | Mahikshith | Authorized founder/customer accounts; employer permission only for employer records |

The gates in `DECISION_GATES.md` outrank this entire document. If Gate 2 or Gate 5
fails, most of Phase B onward should not be built at all — the honest outcome is an
OEM engine, or walking away. That is written down deliberately, while we are not yet
invested enough to argue with it.

---

## Suggested order, if everything unblocks

1. **A1 → A2** — live-fire and reconcile. Two sessions to find out whether the whole
   premise holds. Produces the "our numbers match your invoice" artifact.
2. **Discovery calls in parallel** — they need no code, and they decide the rest.
3. **A3 → B1 → B2 → B3 → B4** — the collector a design partner can actually run.
4. **C1** — GCP identity, without which our own incident story is only half true.
5. **D2** — authorized real replay, with synthetic/observed/counterfactual findings kept distinct.
6. **E** — after scoped sandbox/source/accounting gates; no live actions in the foundation.

Rough total to a design partner running it unattended: **10–14 working sessions**,
assuming credentials arrive and live-fire holds no nasty surprises. The surprises are
the part I cannot size, which is exactly why A1 comes first.

The selected gateway provides routed budget admission; direct-key bypass remains a separate provider/audit path. See NETWORK_TELEMETRY.md before adding metadata ingestion or changing cloud logging.
