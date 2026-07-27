# GHL Chatbot — Integration Plan (v1)

*Plain-language build plan. Written 2026-07-22. Read `START_HERE.md` first for the compliance
boundary and the marketing facts behind these decisions.*

**What we're building first:** one chatbot that welcomes a new person, figures out if we can help
their back, and books them — running in two places at once: the **chat bubble on our websites** and
the **first text to a brand-new lead**. Everything else (no-shows, and the big win-back pool) comes
later. This doc only covers v1.

---

## 1. The big idea in one breath

The website chat and a fresh lead texting in are the **same conversation**. Someone shows up, the
bot says hi, asks what's going on, checks if we're a fit, and grabs them a time. It doesn't matter if
they typed in a bubble on the site or came in as an ad lead — it's one script, one brain, one place
to store it. Build it once, point it at both doors.

---

## 2. The three pieces (the "engine")

Only three parts do all the work. Every version of this bot, now and later, uses these same three.

**1. The brain — Amazon's safe AI (Bedrock).**
This is the smart part that reads what a person says and decides what to say back. We're only allowed
to send health talk to an AI we signed a safety contract with (a "BAA"). We have that with Amazon,
and we already use it every day in the morning briefing, so it's proven. Model:
`us.anthropic.claude-sonnet-4-6`, region `us-east-1`. (Google's AI, Vertex, is our backup — also
safe-contracted — but we start with Amazon because it already works here.)

**2. The middleman — a little program on our office computer.**
This is the piece we build. It sits in the middle: it catches an incoming message, asks the brain
"what should I say?", and sends the answer back out. It runs on the Worker machine, on our own
network. The regular Claude helper (the one Harry types to) only helps *write* this program — it
never sees real patient chats. That split is the whole reason we stay compliant.

**3. The notebook — GoHighLevel (GHL).**
This is where every contact and every chat gets saved. GHL is also safe-contracted, so health chats
are allowed to live there. The moment someone starts chatting, we make a contact for them in GHL —
so we catch the lead and keep the whole history even if they wander off.
> ⚠ **The GHL safety contract is a paid add-on.** If that bill ever lapses or the plan gets
> downgraded, the protection quietly shuts off while patient chats are still sitting inside. Treat
> that line item as a safety switch, not a cost. Check it on any plan review.

---

## 3. How a chat actually flows

Same seven steps whether it starts on the website or as a new lead:

```
   Website bubble  ─┐
                    ├─►  Middleman program  ──►  Amazon's safe AI (Bedrock)
   New lead text   ─┘        (our computer)            │
                                   │                    │  "here's what to say"
                                   │  ◄─────────────────┘
                                   ▼
                              GoHighLevel
                    (save contact, save chat, book the time)
                                   │
                                   ▼
                    Reply goes back to the person
             (a staff member can read along or jump in anytime)
```

1. A message comes in (bubble on the site, or a fresh lead we need to answer fast).
2. The middleman program picks it up.
3. It makes or finds the person's contact in GHL, so the lead and the chat are saved right away.
4. It asks Amazon's safe AI what to say back.
5. It sends the reply.
6. If the person wants to book, the bot looks up open times in GHL and sets the appointment.
7. A staff person can watch the chat and take over whenever they want. The bot is happy to hand off.

---

## 4. The one core conversation

The bot's job is simple: **say hi → find out what's wrong → ask a few quick fit questions → offer a
time → book it → hand off to a human when it should.** One question at a time, short messages, sounds
like a real person from the clinic, never like an ad.

Rough shape:

> **Bot:** Hi! This is the team over at the Disc Center. What's been going on with your back or neck?
> **Person:** Sharp pain shooting down my leg for a few weeks.
> **Bot:** Ugh, that sciatica-type pain is rough. How long has it been going — and has it kept you
> from work or sleep?
> *(a couple of gentle fit questions: how long, where, any imaging, tried anything yet)*
> **Bot:** Sounds like exactly the kind of thing we help with. I've got Thursday at 2:15 or Friday at
> 10:30 — want me to lock one in? Takes about 20 minutes.

**Special case — leads that came in through Meta (Facebook/Instagram):** the very first message
includes a plain opt-out line, e.g. *"Reply STOP any time to stop texts."* This ships on day one.

**Hard stops built into the script:** the bot never gives medical advice — it only screens and books.
Anything that sounds like an emergency (loss of bladder or bowel control, saddle-area numbness,
sudden bad weakness, a serious injury) gets handed to a human **right now**, and the bot says so
plainly.

---

## 5. Safety rails that ship with v1 (they come almost free)

Most of the safety comes from *how* we build, not from extra work:

- **Health talk only ever goes to the safe brain (Amazon) and the safe notebook (GHL).** Built in by
  choosing those two tools. Never OpenAI, never the plain Anthropic API, never the Claude helper.
- **Opt-out / STOP** — especially on Meta leads. Lives in the same code.
- **"No medical advice, hand off emergencies"** — lives in the bot's instructions.
- **An off switch (kill switch)** — one setting that stops all outbound instantly.
- **Quiet hours + a rate limit** — no 3 a.m. texts, and it can't fire hundreds of messages in a burst.
- **Never paste a real patient chat** into the Claude helper, into email, or into code storage. If
  we're fixing a bug, we use fake pretend chats.

**What we're deferring on purpose (the slow, paperwork-y stuff):** a formal review of what consent
our intake forms already capture, detailed log-keeping rules, and the compliance officer's written
sign-off. None of that blocks getting v1 working — but it's on the list before we scale up.

---

## 6. Things to nail down before we wire it up

Short list of decisions and facts we need. Most we already have.

1. **Website widget = GHL's own chat widget**, embedded on the clinic sites, so the chat lives inside
   GHL's safe space from message one. (If we ever build a custom bubble, it may only talk to our own
   middleman — never to an outside chatbot company.)
2. **How a new lead triggers the bot** — GHL can either ping our program when a lead arrives (a
   "webhook") or our program can check GHL every few seconds (a "poll"). Pick one; webhook is faster,
   poll is simpler and matches how other jobs here already work.
3. **What the bot may write to GHL** — booking an appointment and moving a stage are permanent. House
   rule: a permanent write never auto-retries without a check. Draw that safe line before wiring it.
4. **GHL details we already have** (from `START_HERE.md` §7): location `uEanpHM7WXjNsXmCuRS5`, API
   version header `2021-07-28`, Marketing Pipeline 1 `iqPVQQEk3uCMGZxUmVTy`, and the private token in
   `..\FCC-Daily\helper_config.json` (never commit it, never paste it).
5. **Don't build on the known-broken pieces** — the `[SJ] Book Appt` workflow (draft, maybe not
   firing) and GCLID capture. We book through the GHL API ourselves instead.

---

## 7. Build order

1. **Stand up the middleman program** on the Worker machine and confirm it can talk to Amazon's safe
   AI (reuse the working example in `..\FCC-Daily\enrich_briefing.py`). Prove it with a fake chat.
2. **Connect it to GHL** — read an incoming message, make/find a contact, write a reply back. Test on
   a dummy contact, not a real person.
3. **Teach it the core conversation** — the welcome → fit questions → offer time script, plus the
   Meta opt-out line and the emergency hand-off.
4. **Let it book** — look up open times and set an appointment in GHL, with the "no silent retry"
   guard.
5. **Turn on the off switch, quiet hours, and rate limit.** Not optional.
6. **Quiet pilot** — run it on the website bubble and a small trickle of new leads with a staff member
   watching every chat. Fix what's awkward.
7. **Open the gate** — let it handle new leads on its own, staff still able to jump in.

---

## 8. How we'll know it's working

Use the numbers the daily briefing already tracks, so the bot's effect shows up where the practice
already looks:

- **Lead → appointment rate** — today about **32%**, target **40%**. This is the number v1 should
  move.
- **Speed to first reply** — should drop to minutes (the bot never sleeps).
- **Cost per care start** — today about **$244**, target **$60**. More booked leads from the same ad
  spend pushes this down.

---

## 9. What's next (later, not now)

Same engine, new scripts, opened one at a time:

- **No-shows** — confirm appointments and win back the ones who don't show (SMS in GHL).
- **The big win-back pool** — the ~682 dormant "Called" records, with a warm "hey, how's the back?"
  reopener, dripped out slowly, newest first.

Both reuse the exact three pieces above. Build v1 solid and the rest is mostly new wording.
