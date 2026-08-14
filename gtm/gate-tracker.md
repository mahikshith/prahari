# Gate Tracker

Running score across the 30 discovery calls. Fill in **the same day as the call** —
retrospective scoring drifts toward whatever we want to be true.

Gates and pass bars: `docs/DECISION_GATES.md`. Question set: `discovery-script.md`.

---

## Running totals

**Calls completed: 0 / 30**

| Gate | What it tests | Bar | PASS | FAIL | UNCLEAR | Rate | Status |
|---|---|---|---|---|---|---|---|
| **1** Blindness | Can't state per-team AI cost without manual work | >70% | 0 | 0 | 0 | — | ⬜ |
| **2** Abuse felt | Real event or top-3 risk ranking | >30% | 0 | 0 | 0 | — | ⬜ |
| **3** Residency | Raised **unprompted** | >40% | 0 | 0 | 0 | — | ⬜ |
| **4** Local budget | ₹20L+ approvable in India | ≥5 total | 0 | — | — | — | ⬜ |
| **5** Enforcement | Pays >30% more than for visibility | >50% | 0 | 0 | 0 | — | ⬜ |

**Segment coverage:** GCC 0/10 · BFSI 0/6 · CISO 0/5 · Scale-up 0/8

---

## Call log

Copy this block per call.

<details>
<summary><b>Template</b></summary>

```
### Call NN — <Company or code> · <Segment> · <Role> · <Date>

G1 Blindness      [ PASS / FAIL / UNCLEAR ]
    How they'd answer the CFO:
    Providers they'd have to check:
    % attributable today:

G2 Abuse          [ PASS / FAIL / UNCLEAR ]
    Real event?
    Time to notice:
    Risk register position:

G3 Residency      [ UNPROMPTED / PROMPTED / NOT RAISED ]
    Their exact words:

G4 Budget         [ PASS / FAIL / UNCLEAR ]
    Owner (local / HQ):
    Largest local approval:
    Which budget line:

G5 Enforcement    [ PASS / FAIL / UNCLEAR ]
    Visibility worth:      Rs
    Enforcement worth:     Rs
    Gap:                   %
    Would they allow auto-revoke? What's required first:

Best quote:
Referrals:
Surprise (something I didn't expect):
```

</details>

---

## Signals to watch beyond the gates

Things that would change the plan even if every gate passes. Log them as they appear —
the second column is the one that matters.

| Signal | Heard from | Implication |
|---|---|---|
| They already run Torii / Flexera / Vantage / Finout / Zluri | | Displacement sale, not greenfield. Much harder |
| They have no admin API access, or can't get it | | Onboarding blocker — how big? |
| Their pain is cloud cost, not AI cost | | North Star pulls forward; wedge may be wrong |
| Their pain is seats, not API tokens | | Torii's turf. Reconsider the wedge |
| CISO is the buyer, not FinOps | | Reprice to the security line, lead with the incident |
| "We'd build this internally" | | Especially from IT services — points to OEM, not direct |
| Agentic/runaway-loop cost is the live worry, not credential abuse | | Same detection engine, different story. Cheap pivot |

---

## Weekly review

Run every 5 calls. Answer in writing, not in your head.

1. Which gate is furthest from its bar?
2. Is any gate already unrecoverable at this sample size?
3. What has surprised me most, and does it change the thesis?
4. Am I unconsciously leading on Gate 3? *(Re-read three call notes and check.)*

**If a gate is clearly failing by call 15, stop.** Re-read the decision branches in
`docs/DECISION_GATES.md` — including the two that say walk away — and spend the
remaining calls testing the alternative rather than confirming the failure.

---

## Decision

*Fill in at call 30, or earlier if a gate fails decisively.*

| | |
|---|---|
| Date | |
| Gates passed | |
| Branch taken | |
| Rationale | |

Then record the outcome in `CHANGELOG.md` under Decisions, and update `CONTEXT.md`.
