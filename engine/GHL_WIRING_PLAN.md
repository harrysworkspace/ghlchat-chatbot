# Wiring the bot to GoHighLevel — integration proposal

*Step 2 of `..\INTEGRATION_PLAN.md`. The brain (`bot_brain.py`) is proven; this is how it plugs
into GHL so it can hear a real lead, save the contact, reply, and book. Researched against the
current (2026) LeadConnector v2 API and cross-checked with our own `..\..\FCC-Daily\ghl_pull.ps1`.*

Written 2026-07-22. Status: **proposal — nothing built.** Decisions marked ⟐ need your call.

---

## TL;DR in plain words

A lead texts (or types in the website chat). GHL pokes a small program of ours. That program
finds-or-makes the contact, reads the recent chat from GHL, asks our brain what to say, and sends
the reply back through GHL. If it's an emergency, it doesn't book — it flags a human. Same loop
handles SMS and website chat; only the "channel" tag differs.

The one real decision is **how GHL reaches us**, because a text can arrive at any moment and our
runner sits behind the clinic firewall. Two honest options below (§2). Everything else is
well-trodden API calls we already know how to make.

---

## 0. Ground rule: the live GHL operation is not to be disturbed

GHL is in daily production use by live staff working real leads. **No step in this build may risk
their data, their conversations, or their rate-limit budget.** Everything below is designed to be
isolated, fail-closed, and instantly reversible. These are hard requirements, not preferences.

- **Separate, revocable bot token.** Mint a *dedicated* Private Integration Token for the bot with
  least-privilege scopes — never share `ghl_pull.ps1`'s token. Killing the bot then means revoking
  one token, with zero effect on the marketing pull or anything else. The bot's blast radius is its
  own. *(GHL allows up to 5 PITs per location.)*
- **Fail-closed messaging allowlist.** The bot may send to a contact **only if that contact is on an
  explicit allowlist.** The list starts as a single quarantined **dummy contact** (same idea as the
  `aaaab` test code in Platinum). Any contact not on the list gets **no send, ever.** Real patients
  are messaged only after you deliberately widen that scope.
- **Human-collision standdown.** The bot engages **only brand-new, unassigned, un-human-touched
  leads.** The moment a staff member is assigned to a thread, or has replied in it, the bot **stands
  down and sends nothing.** It never competes with a live agent for a conversation.
- **No writes to real records during build/test.** No stage moves, no opportunity creates, no tags or
  assignments on real contacts until a deliberate pilot — and even then, tightly scoped.
- **Inbound trigger built disabled + narrow.** The Workflow (or webhook subscription) that hears
  inbound messages is created **disabled** and scoped to a test tag / single contact first. Pointing
  it at live inbound is a separate, deliberate, reversible switch — never a side effect of building.
- **Rate-limit citizenship.** Hard-cap the bot's request rate far below GHL's shared ceiling
  (100 req / 10s per location) and avoid broad polling, so staff working in GHL are never throttled
  by us.
- **Reversibility.** Every piece has an off switch. Kill switch + revoke token = GHL returns to
  exactly its current state, with no residue.

*(Open item: is there a separate GHL **test sub-account** we can build against, or do we test inside
the live location using a single quarantined dummy contact? See §7.)*

---

## 1. What we reuse (no new auth to invent)

Our `ghl_pull.ps1` already talks to GHL exactly the way the API wants, so we copy it:

| Thing | Value | Source |
|---|---|---|
| Base URL | `https://services.leadconnectorhq.com` | `ghl_pull.ps1` |
| Auth mechanism | `Authorization: Bearer <PIT>` — same style as `ghl_pull.ps1`, but a **separate, dedicated bot token** (§0), not the shared `ghl_api_key` | `ghl_pull.ps1` |
| Version header | `2021-07-28` (pin it everywhere) | `ghl_pull.ps1` |
| Location | `uEanpHM7WXjNsXmCuRS5` | `START_HERE.md` |

The Private Integration Token (PIT) is enough for **every runtime call the bot makes** — find/create
contacts, read a thread, send a message, get calendar slots, book, move a pipeline stage. We just
need to make sure these **scopes** are ticked on the PIT: `contacts.write/readonly`,
`conversations.write/readonly`, `conversations/message.write/readonly`, `calendars.readonly`,
`calendars/events.write`, `opportunities.write/readonly`.

The one thing a PIT **cannot** do is *subscribe to GHL's native webhooks* — that needs a Marketplace
app. That limitation is the whole reason §2 exists.

---

## 2. ⟐ The one big decision: how does GHL reach us?

A reply-bot has to be told the instant a message arrives. There are two axes here.

### 2a. What tells us a message came in

**Option A — GHL Workflow → Webhook action (no Marketplace app).**
Build a Workflow in the GHL UI: trigger "Customer replied / inbound message" → action "Webhook
(POST)" to our endpoint, with a payload we shape (`contactId`, `message body`, `conversationId`,
channel). Works with just the PIT and the account UI. Fastest to stand up, fully reversible.
*Downside:* we hand-maintain the workflow and its field mapping, and it's a touch slower than a
native webhook.

**Option B — Private Marketplace OAuth app → `InboundMessage` webhook.**
Register a private/unlisted Marketplace app on the location and subscribe to `InboundMessage`. GHL
then sends a clean, **signed** payload (Ed25519 `X-GHL-Signature`) with `contactId`, `conversationId`,
`messageType` (SMS vs "Live Chat"), `body`, `chatWidgetId`, etc., plus an `OutboundMessage` feed for
delivery status. Richer and lower-maintenance at runtime. *Downside:* someone has to create the
Marketplace app.

> **Recommendation:** ship v1 on **Option A** (Workflow webhook) — it needs no new app and gets us
> live fastest — but write our code behind a thin "inbound adapter" so moving to **Option B** later
> is a config swap, not a rewrite. Both hand our code the same three facts: which contact, what they
> said, which channel.

### 2b. ⟐ Where our receiver lives (this is the compliance-load-bearing choice)

The webhook payload contains the message text, which is **PHI**. So whatever public endpoint GHL
posts to must sit inside a BAA. Our runner is behind the clinic firewall and isn't reachable from
the internet, so we need a front door. Two BAA-clean ways:

**Option 1 — AWS front door (recommended).** A tiny AWS endpoint (API Gateway → Lambda, or a small
always-on box) receives the webhook, and the bot logic runs there, calling Bedrock (already in AWS)
and calling back to GHL. Everything stays inside the **AWS BAA + GHL BAA** the whole way. Our own
governance explicitly lists AWS as an allowed PHI home, so this is compliant, always-on, and reuses
the Bedrock credential. Trade-off: the bot's runtime moves from the clinic box into AWS (a change
from the "middleman on the office computer" sketch, but a permitted and sturdier one).

**Option 2 — On-prem receiver + clinic port-forward.** Keep the bot on the Worker machine and have
clinic IT open one HTTPS port (with a TLS cert) so GHL can reach it directly — no third party in the
middle. Most "PHI never leaves the building," but it needs a firewall change, a cert, and the box to
be always up and always reachable. Avoid consumer tunnels (ngrok/Cloudflare) unless that vendor
signs a BAA, since the tunnel would see the PHI payload.

> **Recommendation:** **Option 1 (AWS front door).** It's BAA-covered end to end, always reachable,
> and reuses what we already trust for PHI. Option 2 is the fallback if you'd rather keep the runtime
> physically in the clinic.

*(Outbound-only pieces — e.g. proactive follow-ups — don't need a front door at all; they can run
from the Worker box on a schedule. It's only the real-time inbound reply that needs to be reachable.)*

---

## 3. The turn lifecycle (what happens on each message)

```
Lead texts / types in web chat
        │
        ▼
GHL  ──(webhook: contactId, body, channel)──►  our receiver
        │
        1. verify it's really GHL (signature or shared secret)
        2. ignore if direction != inbound        (never reply to our own messages)
        3. dedupe on messageId                    (webhooks can fire twice)
        4. debounce ~2s per contact               (catch rapid-fire texts as one turn)
        5. GET /conversations/{id}/messages        (load recent thread = context)
        6. bot_brain.get_reply(history, channel)   (Bedrock -> the next line)
        │
        ├─ if escalate:  tag EMERGENCY, assign to a human, send the ER message, STOP (no booking)
        ├─ else:         POST /conversations/messages  (type = SMS or Live_Chat)
        │
        └─ if the person wants to book:
               GET  /calendars/{id}/free-slots   -> offer real times
               POST /calendars/events/appointments
               POST/PUT /opportunities           (create / move pipeline stage)
```

One handler serves both channels; we just branch the reply `type` on the inbound channel
(`SMS` vs `Live_Chat`). GHL stays the source of truth for the conversation, so PHI lives where the
BAA already covers it.

---

## 4. Endpoint reference (all `Version: 2021-07-28`, `Bearer <PIT>`)

| Purpose | Call |
|---|---|
| Find-or-create contact (+ UTM) | `POST /contacts/upsert` — body `locationId`, `phone`/`email`, `attributionSource{utm…}` |
| Read recent thread (context) | `GET /conversations/{conversationId}/messages` |
| **Send reply** | `POST /conversations/messages` — `{ type: "SMS" \| "Live_Chat", contactId, message }` (no conversationId needed; GHL routes to the contact's thread) |
| Log an out-of-band turn | `POST /conversations/messages/inbound` |
| Free appointment slots | `GET /calendars/{calendarId}/free-slots?startDate={epochMs}&endDate={epochMs}&timezone=…` |
| Book appointment | `POST /calendars/events/appointments` — `calendarId, locationId, contactId, startTime(ISO±offset)` |
| Pipelines/stages lookup | `GET /opportunities/pipelines?locationId=…` |
| Create / move opportunity | `POST /opportunities/` · `PUT /opportunities/{id}/status` — `pipelineId`, `pipelineStageId` |
| Tag / assign (escalation) | contact tag + conversation assignment via Contacts/Conversations endpoints |

Known IDs: Marketing Pipeline 1 = `iqPVQQEk3uCMGZxUmVTy` (stages New Lead → Engaged → Scheduled/Needs
Call → Scheduled & Confirmed → Awaiting ROF → TAI → No Show → Won). Full stage IDs live in the
Campaign Dashboard handoff. **Calendar ID for booking is not yet known — see §7.**

---

## 5. New code to build (brain stays untouched)

- **`ghl_client.py`** — thin wrapper over the calls in §4 (mirrors `ghl_pull.ps1`'s `Invoke-Ghl`
  retry/backoff, reads the same `helper_config.json`). Functions: `upsert_contact`, `get_thread`,
  `send_message`, `get_free_slots`, `book_appointment`, `move_stage`, `tag_and_assign`.
- **`inbound_adapter.py`** — normalizes whichever inbound path (Option A or B) into one
  `{contact_id, conversation_id, text, channel, message_id}` shape. Swapping A→B touches only this.
- **`webhook_receiver`** — the front door (AWS handler or on-prem service). Does steps 1–4 above
  (verify, direction filter, dedupe, debounce), then calls the orchestrator.
- **`orchestrator.py`** — steps 5–7: load history, call `bot_brain.get_reply`, act on `escalate`,
  send, and run the booking sub-flow. This is where the kill switch, quiet hours, rate limit and
  DND/consent checks live.
- **`state`** — a small processed-`messageId` cache (idempotency) and per-contact debounce timers.

`bot_brain.py` does not change. It already returns `{reply, escalate}`; the orchestrator decides what
to do with that.

---

## 6. Safety & compliance controls (mapped to our house rules)

- **BAA end to end.** GHL (BAA) ↔ our receiver (AWS BAA, §2b Opt.1) ↔ Bedrock (BAA). No PHI touches
  the Cowork/Claude assistant, a non-BAA host, email, or git. *(GOVERNANCE §0.)*
- **No reply loops.** Act only on `direction: inbound`; tag our own sends and ignore outbound events.
- **Idempotency.** Dedupe on `messageId`; never auto-retry a send without a check *(HARDENING;
  START_HERE §9 — "sending the same message twice is a credibility problem").*
- **Emergency net wins.** If `bot_brain` returns `escalate`, we tag + assign to a human and send the
  ER message; we do **not** book. Already proven in the smoke test.
- **Consent & opt-out.** Honor per-channel DND; STOP handling for Meta leads (already in the brain);
  confirm intake consent before first-touch SMS *(open item, §7).*
- **Kill switch, quiet hours, rate limit** — day-one, in the orchestrator. Burst ceiling is 100 req /
  10s per location; a single clinic is nowhere near it, but any blast/poll loop can trip it, so we
  throttle and back off on HTTP 429.
- **Verify effects, not sends.** "202 from the API" ≠ "delivered." Watch delivery status (native via
  Option B `OutboundMessage`, or a light reconciliation poll) and surface `failed`/`undelivered`.
- **Debug from synthetic transcripts only.** Live conversation logs are PHI — never pasted anywhere
  outside the BAA boundary *(GOVERNANCE §0.1).*

---

## 7. ⟐ Open questions to confirm on the live account

1. **Can we create a private Marketplace app on this location?** Decides Option A vs B (§2a).
2. **Front door: AWS or on-prem port-forward?** (§2b) — the one architectural call to make first.
3. **SMS transport today — LC Phone or external Twilio?** Confirms API sends flow out without a
   custom provider, and confirms A2P 10DLC registration/throughput for a healthcare sender.
4. **"Allow Duplicate Contact" setting** on the location (match by phone, email, or both) — governs
   how `upsert` dedupes.
5. **Which calendar** should the bot book into? Need the `calendarId` (+ confirm slot duration and
   timezone).
6. **Consent capture point** for first-touch SMS — what does intake record today, and is it enough?
7. **Chat Widget** installed on the clinic sites and mapped to this location? Grab its `chatWidgetId`
   so we can tell web chat from SMS deterministically.

---

## 8. Suggested build order

1. **`ghl_client.py` + read-only proof** — upsert a *dummy* contact and read its thread. No sends yet.
2. **Send path** — post an SMS reply to the dummy contact; confirm it lands and we don't loop.
3. **Inbound (Option A)** — wire the Workflow→Webhook to a receiver; echo round-trip on the dummy.
4. **Orchestrator + brain** — full loop end to end on synthetic/dummy contacts, with kill switch,
   quiet hours, rate limit, dedupe, debounce.
5. **Booking sub-flow** — free-slots → appointment → move stage, with the "no silent retry" guard.
6. **Escalation wiring** — tag + assign + ER message on red flags; verify a human is actually pinged.
7. **Quiet pilot** — website widget + a trickle of real new leads, staff watching every thread.

---

## Sources

LeadConnector v2 API (marketplace.gohighlevel.com/docs): Private Integrations & scopes; Conversations
send-message & add-inbound-message; InboundMessage / OutboundMessage / ProviderOutboundMessage
webhooks; Conversation Providers; Contacts upsert; Calendars get-slots & create-appointment; Chat
Widget API; OAuth FAQs (rate limits). Workflow Webhook action (help.gohighlevel.com). Local:
`..\..\FCC-Daily\ghl_pull.ps1`, `START_HERE.md`, `..\..\GOVERNANCE_AND_PROCESS.md`.
