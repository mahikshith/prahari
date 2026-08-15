# MVP Roadmap

**What "MVP" means here, precisely:**

> A design partner installs the collector in their own VPC, points it at their own
> accounts, and within two weeks gets: cost allocated by team and reconciled to their
> invoice within 2%, abuse alerts delivered somewhere they actually read, and budget
> tracking with dry-run enforcement.

Not a demo. Not a dashboard. Something a stranger runs against production data
without us in the room.

Everything below is measured against that bar. Anything that doesn't move us toward
it is out of scope, however tempting.

---

## Where we actually are

| Built and tested | Built but **never run for real** | Not built |
|---|---|---|
| Detection engine, 5 rules | Anthropic connector | Persistence (`store/` is empty) |
| Baselines, aggregation | OpenAI connector | Collector daemon / scheduler |
| Budget engine + scoping | GCP billing connector | Alert delivery |
| Insights, rankings, FX | Price registry (live-fetched once) | Config file |
| Backtest (synthetic) | | Docker packaging |
| Report CLI | | Enforcement actions |
| 154 tests, security review | | GCP audit-log connector |

**The honest summary: the analysis layer is real, and the plumbing that would make it
a product does not exist yet.** Nothing has ever touched a live provider API.

---

## The one thing that matters most

**No connector has ever met a real API.** Every response shape, pagination cursor,
rate limit and edge case is written from documentation (`ASSUMPTIONS.md` A8). Real
billing APIs routinely differ from their docs.

Until that changes, every downstream estimate is built on sand — and the fix needs
credentials, which needs the IP/data-use position settled (`ASSUMPTIONS.md` A2).

**That is the critical path. It is also the cheapest item on this list.**

---

## Dependency order

```
  IP position (A2)  ──►  credentials  ──►  A1 live-fire  ──►  A2 reconcile ≤2%
                                                │                    │
                                                │                    └──►  real backtest,
                                                │                          drop synthetic banner
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

### A1 · Live-fire the three connectors
**Size:** 1–2 sessions, plus however long the surprises take.
**Needs:** admin keys — Anthropic (`sk-ant-admin…`), OpenAI org admin, GCP service
account with BigQuery dataViewer on the billing export.

Run `verify_credentials()`, then a real `fetch()` over a settled window. Expect
breakage in pagination, field names, and empty-window handling. Fix, and convert
each surprise into a test.

**Done when:** all three return real `UsageRecord`s for a 24-hour window, and every
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

`store/` is an empty package. Today every run recomputes from scratch in memory,
which makes incremental collection, backfill, period comparison and alert dedup all
impossible.

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

Async loop, per-connector poll intervals (Anthropic at 1/min — it's the only
sub-hour surface we have), watermark-driven incremental fetch, exponential backoff,
graceful shutdown, structured logs with no credentials in them.

**Done when:** it runs unattended for 48 hours, survives a provider 500 and a
network drop, and its totals still reconcile.

### B2 · Alert delivery
**Size:** 1 session. **Depends on:** A3.

An alert nobody receives is not detection. Slack webhook + SMTP, routed per budget
owner, with dedup and a daily digest for low-severity findings. The alert body is
already written — `Alert.explain()` and `BudgetState.explain()` produce it.

**Done when:** a simulated attack in a test environment lands in Slack within a
minute, and a second identical hour does *not* produce a second message.

### B3 · Config file
**Size:** 1 session.

Budgets, connectors, allocation rules and alert routing are currently hardcoded in
`scripts/report.py`. Needs a validated YAML config (Pydantic — already a dependency)
with a `--dry-run` validate mode.

**Done when:** a design partner configures their own budgets without touching Python.

### B4 · Docker collector
**Size:** 1 session. **Depends on:** B1, B3.

This *is* the security architecture, not packaging convenience: the customer runs it
in their VPC, credentials never cross our boundary, only aggregates leave. It also
collapses the "will your Python app run in our environment" conversation.

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

Pull `protoPayload.authenticationInfo.principalEmail` and
`requestMetadata.callerIp` for `aiplatform.googleapis.com`, join to billing on
project + time window.

**Note for the first sales conversation:** Data Access audit logs are **off by
default** in GCP. Most prospects will not have them enabled — which is a finding
worth telling them, and a prerequisite we need to flag during onboarding.

**Done when:** the incident backtest runs on real GCP data with credential-level
attribution, not project-level.

---

## Phase D — Make it demoable

### D1 · Streamlit view
**Size:** 1 session. Deliberately throwaway — the real UI is Next.js, later, only
with paying design partners. This exists to make the backtest and budget views
presentable on a call.

### D2 · Real backtest
**Depends on:** A1, C1. Re-run on the actual incident export, delete the synthetic
banner from `gtm/case-study-incident.md`, and replace every modelled figure with a
measured one.

---

## Phase E — Enforcement

**Gate 5 decides whether this is the product or a nice-to-have.** Do not build it
before the discovery calls answer that.

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
| **Settle the IP/data-use position** (A2) | Mahikshith | **Blocks all of Phase A** |
| **Run the 30 discovery calls** | Mahikshith | Unblocked. Gates everything past Phase A |
| Push the private repo (`scripts/setup_remote.ps1`) | Mahikshith | Needs a browser login |
| Obtain admin credentials for A1 | Mahikshith | Follows the IP position |

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
5. **D2** — real backtest, honest numbers, banner deleted.
6. **E** — only if Gate 5 says so.

Rough total to a design partner running it unattended: **10–14 working sessions**,
assuming credentials arrive and live-fire holds no nasty surprises. The surprises are
the part I cannot size, which is exactly why A1 comes first.
