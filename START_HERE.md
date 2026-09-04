# GHLchat-Chatbot — project brief

> **RULES.md LOADER (added 2026-09-03):** Before any action, load `Z:\Administration\cowork\RULES.md` and this project's `STATE.md`. RULES.md overrides your defaults and your caution. You do not ask Harry to confirm anything in it. You do not restate it back to him. Where anything below conflicts with RULES.md, RULES.md wins.


*A conversational agent operating inside GoHighLevel for Frye Chiropractic / Disc Center of the
Antelope Valley (DCOA). This is the starting document: read it, then the documents in §3, before
designing anything.*

Created 2026-07-21. Status: **design, nothing built.**

---

## 1. ⚠ Compliance boundary — decide this before writing any code

**A bot that talks to leads about back pain, sciatica, symptoms, injuries and appointments is
handling health information.** It sits *inside* the PHI boundary, not outside it. That makes it
different from every other marketing tool in this folder, all of which deal only in aggregates.

Consequences:

- **Inference must run on AWS Bedrock** (BAA held) or Google Vertex (BAA held). **Not** a
  third-party chatbot SaaS, not the Anthropic API directly, not OpenAI, not the Cowork app.
- **GHL is BAA-covered** (confirmed 2026-07-21). It is a **paid add-on**, so message threads
  containing health complaints may be stored there. ⚑ **Operational risk to record: the BAA is tied
  to a paid tier.** A plan downgrade, a lapsed payment or an account change silently turns a
  compliant system into a non-compliant one, with patient conversations already sitting in it.
  Treat that subscription line item as a compliance control, not a billing detail — and check it
  during any plan review.
- **Conversation logs are PHI.** They cannot be pasted into an AI assistant for debugging, cannot go
  into a git repo, and cannot be emailed. Debug from synthetic or de-identified transcripts.
- **Never let the bot give clinical advice.** Screening and scheduling only. Any symptom that could
  indicate an emergency — loss of bladder or bowel control, progressive weakness, saddle-area
  numbness, significant trauma — must escalate to a human immediately and say so plainly.

See `..\GOVERNANCE_AND_PROCESS.md` and `..\OPERATIONS_MANUAL.md` §1 for the full posture.

## 2. What the bot is for

Not "engagement." The practice measures one thing: **a patient who STARTED CARE.** Every design
decision should trace to that. The bot exists to move people from first contact to a kept
appointment to a started care plan — and to stop losing the ones already in the pipeline.

## 3. Read these first

**Root level** (`Z:\Administration\cowork\`):

1. `MACHINE_STATE_2026-07-20.md` — machine state, tools, and the failure lessons. Start here.
2. `OPERATIONS_MANUAL.md` — shared operating context; §1 compliance posture, §10 lessons log.
3. `GOVERNANCE_AND_PROCESS.md` — data classification and PHI rules.
4. `HARDENING_AND_RESILIENCE.md` — how things are built to fail safely here.
5. `_STRUCTURE.md`, `README.md` — directory map and conventions.

**Where the marketing knowledge actually lives:**

6. `..\Campaign Dashboard\START_HERE_2026-07-20.md` — attribution findings, including the fact that
   per-campaign attribution *is* present in the data.
7. `..\FCC-Daily\RULES.md` — the operating thresholds the practice is measured against.
8. `..\FCC-Daily\CONTEXT.md` — standing operator notes; dated, pruned when stale.
9. `..\FCC-Daily\README.md` — see "Open items", which holds the single most useful marketing finding
   in this folder (§5 below).
10. `..\FCC-Daily\PROJECT_SYNOPSIS.md` — architecture and product-readiness write-up.

## 4. Where the practice is actually losing people

A diagnosis from live data (7-day window 14–20 July 2026), not a guess. **Design against these five
numbers.**

| Signal | Value | What it means |
|---|---|---|
| **Open opportunities parked in "Called"** | **682 of 721 open — 95%** | The largest pool in the business. Contacted once, then nothing. A graveyard — and the bot's biggest opportunity by an order of magnitude. |
| **No-shows** | **5 vs a 1.5 baseline (+233%)** | Booked appointments not kept. Third consecutive elevated week. Directly suppresses care starts. |
| **Lead → appointment** | **32% vs a 40% target** | One in three leads books. Top of funnel is fine; conversion to booking is not. |
| **Awaiting ROF / Thinking About It** | **4 and 3** | Came in, heard the report of findings, now deciding. Small numbers, high value, time-sensitive. |
| **Cost per care start** | **$244.63 vs a $60 target** | Every recovered no-show or reactivated dormant lead improves this without spending another advertising dollar. |

**That last row is the argument for this whole project.** With ad spend at $978.51 a week producing
4 care starts, the cheapest possible new patient is one already sitting in the CRM. A bot that
reactivates even a small fraction of 682 dormant records outperforms any ad optimisation available.

## 5. Strategic context that must not be re-litigated

From the practice's own documents. These are settled decisions.

- **Disc patients, not general chiropractic.** The brand is Disc Center of the Antelope Valley. A
  previous marketing manager pivoted toward general chiro — roughly 88% of spend — and muddled the
  proposition. All messaging is disc / spinal decompression / surgery-alternative.
- **Calls beat bookings beat form fills.** Harry's stated priority, and the reasoning is blunt:
  *callers show up*. A bot that produces a phone conversation is worth more than one that produces
  a form submission.
- **The landing-page self-schedule path converts roughly 9× better than standard ad leads.** The
  most valuable single line in the FCC-Daily README. Whatever the bot does, moving people onto the
  self-schedule path is the highest-leverage action available to it.
- **Primary competitor to study: Spinatomy** (spinatomy.com). They win with eligibility-quiz
  funnels, Meta + YouTube demand generation, video proof stacks, and surgery-alternative
  positioning. The eligibility quiz matters most here — it is a conversational qualification flow,
  which is precisely what a bot does natively.
- **Closed channels:** Google Ads, Medicare and Spanish. Warmed leads may still convert so they
  still need nurture, but no new acquisition spend goes there.

## 6. Conversion practice mapped to those leaks

Principles in rough order of expected value. Where these are industry convention rather than
measurements from this practice, they are marked — verify before betting real money on a number.

**Speed to lead is the highest-leverage variable in inbound conversion.** *(Industry convention,
well evidenced in sales literature.)* Response measured in minutes rather than hours changes
outcomes disproportionately, because the lead is still on the page and still in the problem. The
bot's structural advantage is that it never sleeps and never has a full waiting room — it answers at
9pm on a Sunday, which is when disc pain is worst and when people search.

**Conversational booking beats sending a link.** Every hop — read message, click link, load page,
choose slot — sheds people. If the bot offers two concrete times in the message and confirms one, it
removes the hops. Given the 9× self-schedule finding, this is where to concentrate effort.

**Ask one question at a time, and qualify gently.** Eligibility-style screening — how long, where,
prior imaging, previous treatment, whether surgery has been raised — does two things: it lifts show
rate by increasing commitment, and it hands the front desk a warm record. This is the Spinatomy quiz
pattern in conversational form.

**Confirmation is a sequence, not an event.** A booking made five days out with no contact in
between is a coin flip. A cadence at 48 hours, 24 hours and the morning of — two-way, so they can
reply "reschedule" instead of silently not appearing — is the standard answer to a no-show problem.
The practice currently confirms manually from a printed sheet; the bot should carry that load and
leave the sheet as the exception list.

**No-show recovery must be immediate and specific.** Same day, not next week. Offer a named slot
rather than "call us to rebook" — the ask has to be smaller than the effort of ignoring it.

**Dormant reactivation is a campaign, not a message.** 682 records will not respond to one text. It
needs segmentation (how old, which stage they reached, did they ever book), a handful of touches
over a couple of weeks, and a hard stop. Start with the most recent cohort, measure, then widen.

**Write like a person from the clinic, not like a clinic.** Named sender, plain language, short
messages, no marketing voice. In healthcare the trust bar is higher and tolerance for salesiness is
lower.

**Hand off cleanly and early.** The bot should be eager to pass to a human — on any clinical
question, any frustration, any emergency indicator, any request to speak to someone. A bot that
tries to hold the conversation is worse than no bot at all.

## 7. What already exists that the bot can use

**GHL is the CRM of record.** `services.leadconnectorhq.com`, API version header `2021-07-28`,
location `uEanpHM7WXjNsXmCuRS5`. Private Integration Token lives in
`..\FCC-Daily\helper_config.json` — gitignored; never commit it, never paste it into a chat.

**Pipelines and stages are known:**
- Marketing Pipeline 1 — `iqPVQQEk3uCMGZxUmVTy` (all paid disc leads land here)
- Spanish Pipeline — `6tPiCjiU9VgSOXJBA17v` (closed channel, residual movement only)
- Stages: New Lead → Engaged Lead → Scheduled or Needs Call → Scheduled and Confirmed →
  Awaiting ROF → TAI (Thinking About It) → No Show, plus Won (started care)
- Full stage IDs are in the Campaign Dashboard handoff document.

**Attribution data is richer than the daily briefing implies.** Opportunities carry `utmCampaign`,
`utmCampaignId`, `utmContent`, `utmSource`, `utmMedium`, `adSource`, `fbp`/`fbc` and `utmAdId`
(16 distinct ads), plus `isFirst`/`isLast` for first- versus last-touch. Whatever the bot books
should preserve these so conversions can finally be tied back to spend.

**`lastStageChangeAt` is populated on every opportunity** — use it, not `dateUpdated`, for anything
time-based. `dateUpdated` moves whenever any field is edited and will mislead you.

**Known broken — do not build on:** GCLID capture into GHL, and the `[SJ] Book Appt` workflow
(draft state, probably not firing). Meta CAPI firing is unconfirmed.

**Call tracking numbers:** (661) 466-2632 PPC call extension; (661) 735-4177 GMB Frye;
(661) 998-1754 GMB Antelope Valley.

## 8. Tools and runtimes available

| Tool | Where | Notes |
|---|---|---|
| **AWS Bedrock** | `us-east-1`, `us.anthropic.claude-sonnet-4-6` | **The PHI-safe inference path.** Credential at `..\Patient Reports\Config\aws-bedrock-key.csv`. Working examples: `..\FCC-Daily\enrich_briefing.py`, `..\Patient Reports\agent\bedrock_smoke.py` |
| **Python 3.13.14** | `C:\Program Files\Python313` | Not on PATH — call by absolute path |
| **Shared venv** | `..\tools\refagent-venv` | Currently **boto3 only** — reinstall what you need |
| **PowerShell 5.1** | built in | The house scripting language |
| **Dedicated runner** | host `Worker`, account `user` | Headless, auto-logon, Splashtop, Windows Task Scheduler |

## 9. Build principles for this environment

Earned the hard way — see `MACHINE_STATE_2026-07-20.md` §5.

- **Verify effects, not invocations.** "Message sent" is not "message delivered" is not "message
  read." For a bot this matters more than anywhere else in the system.
- **A failure must never delete its own evidence.** Keep conversation state until success is
  confirmed.
- **Never auto-retry anything with an external side effect** without an idempotency check. Sending
  a patient the same message twice is a credibility problem; five times is a complaint.
- **Nothing launched hidden may be able to ask a question** — three separate outages here came from
  invisible dialogs blocking automated processes.
- **Rate limit, quiet hours and a kill switch are day-one requirements**, not polish. A messaging
  bot with a bug reaches real patients within seconds.
- **Keep generated text ASCII** unless every layer is verified UTF-8 end to end. A smart quote from
  a model arrives as mojibake.

## 10. Open questions to answer before building

1. ~~Does GHL's agreement cover PHI?~~ **Answered 2026-07-21: yes, BAA in place as a paid add-on.**
   Not a blocker. The remaining action is to make sure that subscription is never quietly dropped
   (see §1).
2. **Which channel first — SMS, web chat, or Facebook/Instagram DM?** Volume, consent posture and
   after-hours behaviour differ sharply. SMS carries the strongest opt-in requirements.
3. **Consent and opt-out.** What does existing intake capture, and is it sufficient for automated
   outbound messaging?
4. **What may the bot write to GHL?** Booking an appointment and moving a stage are irreversible
   side effects. The house rule from the resilience review is that irreversible writes never
   auto-retry. Decide the safe boundary before wiring anything up.
5. **Which use case ships first?** The data argues for **no-show confirmation and recovery** —
   smallest surface, clearest measurement against a 1.5 baseline, least risk, and it relieves work
   the front desk does by hand today. Dormant reactivation is the bigger prize but a far larger
   blast radius.
6. **How is success measured?** Use the metrics the daily briefing already tracks, so the bot's
   effect appears in numbers that are already trusted — not in a separate dashboard.
