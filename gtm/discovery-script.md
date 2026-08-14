# Discovery Call Script

**Purpose:** score the five gates in `docs/DECISION_GATES.md` across ~30 calls. This
is not a sales call. The goal is a decision, and a clean "no" is worth as much as a
yes — it's worth more than a soft yes you act on for six months.

**Target mix:** 10 India GCC FinOps/CloudOps/platform leads · 6 BFSI (IT + risk) ·
5 CISOs · 8 Indian AI-native scale-ups.

**Length:** 30 minutes. Never run over — you want the second call more than the extra
ten minutes.

**Record in `gate-tracker.md` the same day.** Retrospective scoring drifts toward
whatever you want to be true.

---

## The one rule

**Do not say "DPDP", "data residency", "India-hosted", or "compliance" until the
prospect does.**

Gate 3 carries the entire India-domestic-first decision. If you plant the word, the
answer is worthless and you will have destroyed your own evidence. Bite your tongue.
If they never raise it in 30 calls, that is the finding — and it means the geography
changes, not the product.

---

## Open (2 min)

> "I'm not selling anything today — I'm trying to find out whether a problem I hit is
> a real market or just my bad luck. Twenty-five minutes, and I'll tell you what I've
> found from everyone else I've spoken to. Fair trade?"

Then the story, told straight and short:

> "A stale GCP service account key at my company got pasted into an LLM chat. Someone
> outside the org used it. We found out from the invoice. It was about six crore."

Then stop talking. **The silence after that number does more work than anything you
could say next.** Let them react. Their unprompted first response is the most honest
data in the whole call.

---

## Gate 1 — Blindness (5 min)

*Pass bar: >70% cannot answer without a manual exercise.*

1. "If your CFO asked right now what your AI spend was last month, broken down by
   team — how would you get that?"
2. "How long would it take?" *(Listen for "I'd have to pull it together" — that's a
   pass. "It's on a dashboard" is a fail, and worth digging into: whose dashboard?)*
3. "Which providers would you have to check?" *(Count them. The number is itself the
   pitch.)*
4. "Does that include seats — Copilot, Cursor, ChatGPT Team — or only API usage?"
5. "What proportion of your AI spend can you attribute to a specific team today?"

**Scoring:** PASS if reconstructing it requires manual work across ≥2 sources.

---

## Gate 2 — The abuse vector (6 min)

*Pass bar: >30% have had an event or rank it top-3.*

Do not lead with LLMjacking. Ask about surprises first.

6. "Have you ever been surprised by an AI bill? What happened?"
7. "Has a credential of yours ever been used by someone who shouldn't have had it —
   AI or otherwise?"
8. "Has an agent or a runaway loop ever burned through budget unexpectedly?"
9. "If a key leaked today, how would you find out? What's the path?"
10. "How long between something going wrong and someone noticing?"

Only *after* they've answered, share the rates: $46K–$100K/day, 376% rise in
AI-targeted credential theft. Then:

11. "Where does that sit on your risk register?"

**Scoring:** PASS only on a real event, near-miss, or an explicit top-3 ranking.
"That sounds scary" is a FAIL. Enthusiasm is not evidence.

---

## Gate 3 — Residency *(listen only, never prompt)* (silent)

*Pass bar: >40% raise it unprompted.*

There are no questions here. You are listening across the whole call for any of:

- "where would this data sit?"
- "is it hosted in India?"
- "we can't send that outside our environment"
- "our DPO / audit / RBI / DPDP would need to see this"
- "we'd need it on-prem / in our VPC"

**Scoring:** PASS only if it comes from them, unprompted, anywhere in the 30 minutes.
Write down their exact words — the phrasing tells you whether it's a real constraint
or a reflex.

If they haven't raised it by minute 25, you may ask the neutral version — **and mark
it as prompted, which does not count toward the gate**:

> "Anything about where this data lives that would matter to you?"

---

## Gate 4 — Budget authority (5 min)

*Pass bar: ≥5 of 30 confirm ₹20L+ approvable locally.*

12. "Who owns the AI budget — here, or headquarters?"
13. "If you wanted a tool like this, could you sign for it? Or does it route through
    HQ procurement?"
14. "What's the largest software purchase you've approved locally in the last year?"
15. "Which budget would this come out of — FinOps, platform, or security?" *(This one
    also tells you whether the CISO or the CFO is your real buyer.)*

**Scoring:** PASS on confirmed local authority at ₹20L+. "I'd have to check" is a
FAIL — GCC budget independence is exactly what this gate exists to test, and a maybe
is a no.

---

## Gate 5 — Enforcement vs visibility (6 min)

*Pass bar: >50%, with a price gap over ~30%.*

Present them as two separate products. Never bundle them in the question.

16. "Product A shows you every rupee of AI spend across every provider, allocated by
    team, reconciled to your invoice. What's that worth annually?"

*Get a number. Write it down. Do not move on without one.*

17. "Product B does all of that, and can also hard-stop a budget and revoke a
    compromised key automatically — within the hour, before you've seen a bill.
    What's *that* worth?"

*Get the second number.*

18. "Would you actually let a tool revoke a key automatically? What would have to be
    true first?" *(The answer here is the product spec for dry-run mode.)*

**Scoring:** PASS if B exceeds A by >30%. Two similar numbers means we're selling a
dashboard — and dashboards are a feature owned by six better-funded companies.

---

## Close (3 min)

19. "What did I not ask that I should have?"
20. "Who else should I be talking to?" *(Always. Referral is the cheapest channel you
    have.)*
21. "If I build this, would you look at it against your own data?"

Then deliver what you promised at the open — two or three genuine findings from
earlier calls. This is what makes the next 29 people take your meeting.

---

## Immediately after (5 min, non-negotiable)

Fill in `gate-tracker.md`:

- Five gate verdicts: PASS / FAIL / UNCLEAR
- Their exact words on Gate 3, if any
- Both numbers from Gate 5
- One quote worth reusing
- Who they referred you to

**Do this before the next call.** Memory reconstructs conversations to fit what you
already believe, and this whole exercise is worthless if the data is contaminated by
hope.

---

## Weekly review

Every 5 calls, check the running rates against the pass bars.

If a gate is clearly failing by call 15, **stop and re-read `docs/DECISION_GATES.md`,
including the branches that say walk away.** Do not burn the remaining 15 calls
confirming what you already know — spend them testing the alternative instead.
