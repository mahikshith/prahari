# One leaked credential. ₹6 crore. Ten days of silence.

> **Status: DRAFT — the detection figures below are modelled, not measured.**
> The backtest currently runs on synthetic data calibrated to published LLMjacking
> rates because the real billing export is not yet accessible (`ASSUMPTIONS.md` A1).
> **Do not present the modelled numbers to a prospect as measured.** The incident
> itself is real; the "would have detected at" figures are a simulation until re-run
> on the actual export. Re-run, then delete this banner.

---

## What happened

A GCP service account key belonging to an Indian engineering organisation was pasted
into an LLM chat. It was a stale credential — provisioned for a batch job that had
since been retired, never revoked, still carrying broad Vertex AI permissions.

Some weeks later it was used from outside the organisation.

By the time the invoice surfaced it, the company was carrying roughly **₹6 crore
(~$700,000)** in unbudgeted inference spend.

Nobody was asleep at the wheel. The organisation ran Claude Code for developers,
Copilot Studio and M365 Copilot for management, Gemini in some teams, and Vertex
service accounts for robotics workloads. Every one of those surfaces had a dashboard.
None of them were looking at the same thing, and none of them were looking at *this*.

## This is a category, not an accident

The attack has a name: **LLMjacking**. Sysdig's threat research team documented it in
May 2024, and by 2026 it is an industry with suppliers, brokers and marketplaces.

| | |
|---|---|
| Sustained daily burn on one hijacked account | **$46,080** (Claude 2.x), **>$100,000** (Claude 3 Opus) |
| A documented Gemini key leak | **$82,000 in ~48 hours**, against a ~$200/month baseline |
| Rise in credential theft targeting AI services, Q4 2025 → Q1 2026 | **376%** |

Attackers validate stolen credentials against ten or more providers — Anthropic,
Bedrock, Azure, Vertex, OpenAI, Mistral, OpenRouter and others — then resell inference
access through reverse proxies. The economics are excellent for them: they are selling
something they did not pay for, on your account, priced to move.

₹6 crore in ten days is not an outlier. It is the going rate.

## Why every tool in the stack missed it

The organisation was not short of tooling. The tooling was structurally incapable.

**Cloud FinOps platforms** report from billing exports. AWS CUR and GCP billing
exports lag 4–24 hours; the leading platforms offer **daily granularity** on Anthropic
and OpenAI feeds. An attack that burns six figures per day cannot, even in principle,
be caught by a system that reports once a day.

**AI gateways and proxies** only see traffic developers deliberately route through
them. A stolen credential calls the provider directly. It is not in the proxy's field
of view at all.

**LLM tracing tools** require SDK instrumentation inside your applications. The
attacker is not using your application.

**Security tools** did eventually flag an exposed credential — but a secrets scanner
reports a finding, not a bill. Nobody could connect "this key is exposed" to "this key
is currently spending ₹40 lakh a day."

That last gap is the whole problem. **Cost tools see the money but not the identity.
Security tools see the identity but not the money.** No product on the market joins
them.

## What detection would have looked like

Prahari maintains rolling baselines per *credential* — not per credential-and-model,
which would hand an attacker a fresh baseline the moment they switched models.

In the first hour of the attack, four independent signals fired at once:

| Rule | What it saw |
|---|---|
| `DORMANT_KEY_WAKE` | A credential idle for 41 days suddenly transacting |
| `SPEND_SPIKE` | Hourly spend far beyond anything in the key's history |
| `NEW_GEO` | First-ever request from an unfamiliar country and network |
| `MODEL_ESCALATION` | Abrupt switch to the most expensive model available |

Within two hours a fifth fired — `RESALE_PATTERN`: sustained near-maximum context,
around the clock, with none of the diurnal shape of human work. Machine demand, not
team demand.

### The number *(modelled — see banner)*

| | |
|---|---|
| Detected at | **₹72,359 spent** |
| Time to detection | **under 1 hour** from attack onset |
| Invoice surfaced it | **10 days later**, at **₹5.85 crore** |
| Exposure between the two | **₹5.84 crore** |

Same data. Same credential. The only difference is how often somebody looked.

### And it stayed quiet on the real workload

The organisation's legitimate production service account ran throughout — including a
deploy-day evaluation burst that spiked to roughly 5× normal.

That burst raised **warnings, never criticals**. The distinction matters more than the
detection does: a system that escalates every busy Tuesday gets muted within a
fortnight, and a muted detector is indistinguishable from no detector.

## What this costs to find out

Read-only. No SDK, no proxy, no code changes. Connect the admin and billing APIs you
already have and we reconstruct the last quarter — including whether anything is
happening right now that your invoice will tell you about in three weeks.

The collector runs inside your own VPC. Your credentials never cross our boundary;
only aggregated cost records do. For a regulated Indian entity with DPDP obligations
landing in May 2027, that is not a feature — it is the only shape the answer can take.

---

### Notes for whoever presents this

- **Lead with the ₹6 crore, not the product.** The number opens the conversation; the
  product is the second half.
- **Do not oversell the detection figures until the real export has been run.** "This
  is what our simulation shows; we're re-running it on the actual data" is a stronger
  position than a number you cannot defend under questioning.
- **The false-positive paragraph is not a weakness — it is the credibility.** Everyone
  in the room has been burned by an alerting system that cried wolf. Say it before
  they ask.
- **Anonymise properly** before this leaves the building: employer name, project ids,
  service account names, dates. Resolve the IP position first (`ASSUMPTIONS.md` A2).
