# Chatbot engine — first piece (the "brain")

This folder is step 1 of the integration plan: the bot's brain, plus a way to prove it works.
Nothing here talks to real patients or GHL yet — it only turns "conversation so far" into "the
next thing to say," using AWS Bedrock (the BAA-covered, PHI-safe path).

## Files

- **`bot_brain.py`** — the brain. `get_reply(messages, lead_source)` sends the conversation to
  Bedrock (`us.anthropic.claude-sonnet-4-6`, `us-east-1`) and returns the next reply. It carries
  the welcome/qualify/book system prompt, adds the Meta STOP opt-out when `lead_source="meta"`,
  forces plain-ASCII output, and runs an independent emergency word-net that flags red-flag
  messages so a human is pulled in. Reuses the exact credential pattern from
  `..\..\FCC-Daily\enrich_briefing.py`.
- **`fake_chat.py`** — the smoke test. Runs synthetic (no-PHI) conversations through the brain and
  prints the exchange. Three demos: `website`, `meta`, `redflag`, plus `--interactive`.

## Run the live smoke test (on the Worker machine)

Worker is where the Bedrock credential and the shared venv live. From a normal (non-elevated)
session as `user`:

```powershell
& "Z:\Administration\cowork\tools\refagent-venv\Scripts\python.exe" `
    "Z:\Administration\cowork\GHLchat-Chatbot\engine\fake_chat.py" --scenario all
```

Try your own words:

```powershell
& "Z:\Administration\cowork\tools\refagent-venv\Scripts\python.exe" `
    "Z:\Administration\cowork\GHLchat-Chatbot\engine\fake_chat.py" --interactive
```

The venv already has `boto3`. If the import fails, see `MACHINE_STATE_2026-07-20.md` §2.

## What "passing" looks like

- **website** — warm hi, one gentle question at a time, moves toward booking without inventing a
  specific time.
- **meta** — the first bot message ends with a natural "Reply STOP any time" line.
- **redflag** — when the pretend lead mentions leaking urine + saddle/inner-thigh numbness, the
  bot stops screening, says to seek emergency care now, and the line is tagged
  `<<< ESCALATE (hand to human)`.

## What was already checked (in a sandbox, no creds/network)

The ASCII sanitizer, the emergency net (including the exact demo wording and cauda-equina phrases
like "leaking urine", "can't hold my bladder", inner-thigh numbness), the Meta opt-out assembly,
the temperature, and the "must start with a user turn" guard all pass. The only thing the live run
adds is confirming Bedrock itself answers on this machine.

## Safety reminders for this folder

- Synthetic transcripts only. Never paste a real patient conversation into these scripts, into the
  Cowork/Claude assistant, into email, or into git (GOVERNANCE_AND_PROCESS §0.1).
- This is the brain only. Booking, GHL reads/writes, rate limits, quiet hours and the kill switch
  arrive in the next steps of `..\INTEGRATION_PLAN.md`.
