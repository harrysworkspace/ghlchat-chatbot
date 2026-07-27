"""
selftest.py - full offline test of the GHL wiring, with NO network and NO live account.

Runs the whole orchestrator loop against fake_ghl and a mock brain, proving the safety behaviour
that protects the live operation:
  fail-closed sends, allowlist, human-standdown, dedupe, debounce, quiet hours, kill switch,
  escalation (no booking), direction filtering, and correct history/lead-source to the brain.

Run:  python selftest.py      (exit 0 = all pass)
"""

import sys
import types
from datetime import datetime

import config as config_mod
import consent
import inbound_adapter
from orchestrator import Orchestrator
from fake_ghl import FakeGhl

FAILS = 0
def check(name, cond):
    global FAILS
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS += 1


def base_cfg(**over):
    cfg = dict(config_mod.DEFAULTS)
    cfg["ghl_api_token"] = "TESTTOKEN"          # lets the loop call get_thread on the fake
    cfg["messaging_allowlist"] = ["DUMMY"]
    cfg["allow_real_sends"] = False             # default fail-closed
    cfg["quiet_hours"] = {"start": 0, "end": 0} # disabled by default; the quiet-hours test sets its own
    cfg.update(over)
    return cfg


class MutClock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t


def mock_brain(reply="Hey, tell me more about your back?", escalate=False, capture=None):
    def _gr(messages, lead_source=None):
        if capture is not None:
            capture["messages"] = messages
            capture["lead_source"] = lead_source
        esc = escalate or any("urine" in m["content"].lower() for m in messages if m["role"] == "user")
        return {"ok": True, "reply": reply, "escalate": esc, "usage": {}, "error": None}
    return _gr


def inbound(contact="DUMMY", text="my back hurts", channel="SMS", mid="m1", conv="conv-DUMMY",
            direction="inbound", source=None):
    p = {"type": "InboundMessage", "contactId": contact, "conversationId": conv,
         "messageId": mid, "body": text, "messageType": channel, "direction": direction}
    if source:
        p["source"] = source
    return p


# ---------------------------------------------------------------------------------------------
print("=== adapter ===")
n = inbound_adapter.normalize(inbound())
check("adapter normalizes InboundMessage", n and n["contact_id"] == "DUMMY" and n["channel"] == "SMS")
wf = {"contact_id": "C2", "message": "hello", "channel": "sms", "message_id": "w1", "direction": "inbound"}
check("adapter normalizes Workflow payload", inbound_adapter.normalize(wf)["text"] == "hello")
check("adapter drops outbound (reply-loop guard)",
      inbound_adapter.normalize(inbound(direction="outbound")) is None)
check("adapter drops empty-text", inbound_adapter.normalize(inbound(text="")) is None)

print("\n=== fail-closed default (the core safety guarantee) ===")
ghl = FakeGhl()
orch = Orchestrator(base_cfg(), ghl, mock_brain(), clock=MutClock())
r = orch.handle(inbound(text="hi my lower back is killing me"))
check("default config => reply SIMULATED, not sent", r["action"] == "replied" and r["send"] == "simulated")
check("no real send happened", len(ghl.sent) == 0)

print("\n=== real send only when master switch ON and contact allowlisted ===")
ghl = FakeGhl()
orch = Orchestrator(base_cfg(allow_real_sends=True), ghl, mock_brain(), clock=MutClock())
r = orch.handle(inbound(contact="DUMMY"))
check("allowlisted + enabled => actually sent", r["send"] == "sent" and len(ghl.sent) == 1)
# a non-allowlisted contact stays simulated even with the master switch on
ghl2 = FakeGhl()
orch2 = Orchestrator(base_cfg(allow_real_sends=True), ghl2, mock_brain(), clock=MutClock())
r2 = orch2.handle(inbound(contact="REALPERSON", conv="conv-REAL"))
check("non-allowlisted contact => simulated (still no send)", r2["send"] == "simulated" and len(ghl2.sent) == 0)

print("\n=== human-standdown ===")
ghl = FakeGhl()
ghl.seed_thread("conv-DUMMY", messages=[
    {"direction": "outbound", "body": "Hi, this is Sarah from the clinic!", "id": "human-1"},
    {"direction": "inbound", "body": "my back hurts", "id": "m1"},
])
orch = Orchestrator(base_cfg(allow_real_sends=True), ghl, mock_brain(), clock=MutClock())
r = orch.handle(inbound(mid="m2", text="still hurts"))
check("human on thread => bot stands down", r["action"] == "stood_down" and len(ghl.sent) == 0)
# assignment alone also triggers standdown
ghl = FakeGhl(); ghl.seed_thread("conv-DUMMY", messages=[], assigned_to="user-9")
orch = Orchestrator(base_cfg(allow_real_sends=True), ghl, mock_brain(), clock=MutClock())
check("assigned conversation => stands down",
      orch.handle(inbound(mid="m3"))["action"] == "stood_down")

print("\n=== dedupe & debounce ===")
clk = MutClock()
orch = Orchestrator(base_cfg(), FakeGhl(), mock_brain(), clock=clk)
orch.handle(inbound(mid="dup"))
check("same messageId twice => 2nd ignored", orch.handle(inbound(mid="dup"))["action"] == "ignored")
clk = MutClock()
orch = Orchestrator(base_cfg(), FakeGhl(), mock_brain(), clock=clk)
orch.handle(inbound(contact="X", conv="cx", mid="a"))
r = orch.handle(inbound(contact="X", conv="cx", mid="b"))   # same instant, same contact
check("rapid follow-up from same contact => debounced", r["action"] == "debounced")

print("\n=== quiet hours & kill switch ===")
orch = Orchestrator(base_cfg(quiet_hours={"start": 21, "end": 8}), FakeGhl(), mock_brain(), clock=MutClock())
r = orch.handle(inbound(mid="q1"), now=datetime(2026, 7, 22, 23, 0))
check("quiet hours => send blocked", r.get("send") == "blocked" and r.get("send_reason") == "quiet hours")
r2 = orch.handle(inbound(contact="X2", conv="cx2", mid="q2"), now=datetime(2026, 7, 22, 12, 0))
check("midday => not blocked by quiet hours", r2.get("send") in ("simulated", "sent"))

kill = types.SimpleNamespace(engaged=lambda: True)
orch = Orchestrator(base_cfg(), FakeGhl(), mock_brain(), kill_switch=kill, clock=MutClock())
check("kill switch => halted", orch.handle(inbound(mid="k1"))["action"] == "halted")

print("\n=== escalation (emergency) ===")
ghl = FakeGhl()
orch = Orchestrator(base_cfg(allow_real_sends=True), ghl,
                    mock_brain(reply="Please call 911 now; a team member is coming."), clock=MutClock())
r = orch.handle(inbound(text="i started leaking urine and my thighs are numb"))
check("emergency => escalated", r["action"] == "escalated")
check("emergency => NOT booked", r["booked"] is False)
check("emergency => human tag added", any(t[1] == "BOT-EMERGENCY-ESCALATION" for t in ghl.tags))
check("emergency => ER message still delivered", r["send"] == "sent")

print("\n=== brain receives correct context ===")
cap = {}
ghl = FakeGhl()
orch = Orchestrator(base_cfg(), ghl, mock_brain(capture=cap), clock=MutClock())
orch.handle(inbound(text="sciatica down my leg"))
check("brain got the user turn", cap["messages"][-1] == {"role": "user", "content": "sciatica down my leg"})
# meta inference from source
cap2 = {}
orch = Orchestrator(base_cfg(), FakeGhl(), mock_brain(capture=cap2), clock=MutClock())
orch.handle(inbound(text="saw your fb ad", source="facebook"))
check("lead_source inferred as meta from source", cap2["lead_source"] == "meta")
# website inference from Live_Chat
cap3 = {}
orch = Orchestrator(base_cfg(), FakeGhl(), mock_brain(capture=cap3), clock=MutClock())
orch.handle(inbound(text="hi", channel="Live Chat", conv="cw"))
check("lead_source inferred as website for web chat", cap3["lead_source"] == "website")

print("\n=== consent / STOP-HELP ===")
check("classify STOP => opt_out", consent.classify("STOP") == "opt_out")
check("classify natural 'stop texting me' => opt_out", consent.classify("please stop texting me") == "opt_out")
check("classify HELP => help", consent.classify("help") == "help")
check("classify START => opt_in", consent.classify("START") == "opt_in")
check("classify normal msg => None", consent.classify("my back hurts") is None)

# STOP stops the bot and suppresses future messages; no brain call, DND set when live.
ghl = FakeGhl()
orch = Orchestrator(base_cfg(allow_real_sends=True), ghl, mock_brain(), clock=MutClock())
r = orch.handle(inbound(mid="s1", text="STOP"))
check("STOP => opted_out action", r["action"] == "opted_out")
check("STOP => DND set on GHL", getattr(ghl, "dnd", []) == [("DUMMY", True)])
check("after STOP, normal message is suppressed",
      orch.handle(inbound(mid="s2", text="actually my back still hurts"))["action"] == "suppressed_opted_out")

# HELP replies with the standard line and does not run the bot.
ghl = FakeGhl()
orch = Orchestrator(base_cfg(allow_real_sends=True), ghl, mock_brain(), clock=MutClock())
r = orch.handle(inbound(mid="h1", text="HELP"))
check("HELP => help_sent", r["action"] == "help_sent")
check("HELP => standard help text sent", ghl.sent and ghl.sent[-1]["message"] == consent.HELP_REPLY)

# START after STOP re-opts-in and clears DND, and the bot works again.
ghl = FakeGhl()
orch = Orchestrator(base_cfg(allow_real_sends=True), ghl, mock_brain(), clock=MutClock())
orch.handle(inbound(mid="o1", text="STOP"))
r = orch.handle(inbound(mid="o2", text="START"))
check("START => opted_in", r["action"] == "opted_in")
check("START => DND cleared", ("DUMMY", False) in getattr(ghl, "dnd", []))
check("after opt-in, bot replies again",
      orch.handle(inbound(mid="o3", text="my back hurts"))["action"] == "replied")

print("\nRESULT:", "ALL PASS" if FAILS == 0 else f"{FAILS} FAILED")
sys.exit(1 if FAILS else 0)
