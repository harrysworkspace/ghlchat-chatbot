# Build status — chatbot engine

Updated 2026-07-22. Tracks what's built while we wait on Augustine's approval
(`..\Chatbot_Integration_Approval.docx`). **Nothing here has touched the live GHL account.**

## Done and tested (offline, no network, no live account)

| Piece | File | State |
|---|---|---|
| The brain | `bot_brain.py` | ✅ Built + **live Bedrock smoke test passed** (see `smoke_log.txt`) |
| Config loader | `config.py` | ✅ Fail-closed defaults |
| GHL API wrapper | `ghl_client.py` | ✅ Built; injectable transport so tests never hit the network |
| Inbound normalizer | `inbound_adapter.py` | ✅ Handles both Workflow-webhook and native InboundMessage shapes |
| Safety guardrails | `safety.py` | ✅ Kill switch, quiet hours, rate limit, allowlist, dedupe, debounce |
| Turn orchestrator | `orchestrator.py` | ✅ Full loop with every send gated |
| Consent / STOP-HELP | `consent.py` | ✅ Opt-out sets DND + suppresses; HELP + START handled |
| Fake GHL + tests | `fake_ghl.py`, `selftest.py` | ✅ **35/35 checks pass** end-to-end |

Run the offline suite (safe anywhere, no creds):

```
python selftest.py
```

## The safety guarantee (why this can't hurt the live operation)

The whole loop runs, but **it cannot message a real person** in its shipped state. A send only
becomes real when BOTH are true: `allow_real_sends: true` AND the contact is on
`messaging_allowlist`. Otherwise the send is *simulated* (logged, not sent). On top of that: a kill
switch file halts everything, quiet hours and a rate limiter bound it, and the bot **stands down the
instant a human agent is on the thread**. All of this is proven in `selftest.py`.

## Gated on Augustine (can't finish until the approval doc comes back)

- **Dedicated bot token** (A1) → into `ghl_bot_config.json` (copy from the `.example`).
- **Inbound path** (A2): Workflow webhook vs Marketplace app — `inbound_adapter.py` already handles
  both; this only decides which we switch on.
- **Front door / hosting** (A3): AWS Lambda endpoint vs on-prem — the receiver + `requirements.txt`
  web-framework line are deliberately deferred until this is chosen.
- **Calendar id, pipeline stage ids, allow-duplicate setting** (B1/B3/B5) → into config; unblocks the
  booking sub-flow.
- **Dummy test contact id** → into `messaging_allowlist` for the first supervised live test.

## Not built yet (next, after approval)

1. **Inbound receiver** (the front door) — small, once A3 is decided.
2. **Booking sub-flow** — free-slots → appointment → move stage, behind the "no silent retry" guard.
   (`ghl_client` already has the calls; the orchestrator has the hook.)
3. **Live end-to-end on the dummy contact**, then the supervised pilot.

## Notes for the next session

- Deps: the offline suite needs nothing extra. The Worker run needs `requests` + `tzdata` added to
  the venv (`requirements.txt`); `boto3` is already there.
- `ghl_client` uses a **separate** config/token from the marketing pull on purpose (isolation, §0 of
  the wiring plan). Never point it at `helper_config.json`.
- Human-standdown and thread-history parsing are written against GHL's *documented* message shape;
  re-verify against one real payload before the pilot (open item in the wiring plan).
