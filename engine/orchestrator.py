"""
orchestrator.py - one inbound message in, the right (safe) action out.

Pipeline per message (GHL_WIRING_PLAN.md section 3):
  normalize -> dedupe -> kill switch -> debounce -> human-standdown -> load history ->
  bot_brain.get_reply -> (escalate? tag+assign+ER message, NO booking) : gated send.

Every outbound side effect passes SendGate. With the shipped config nothing reaches a real
person: sends are simulated (logged) until allow_real_sends is on AND the contact is allowlisted.

The brain and GHL client are injected, so the whole loop runs in tests against a fake GHL and a
mock brain with zero network. bot_brain.py itself is unchanged.
"""

import time

import config as config_mod
import consent
import inbound_adapter
import safety as safety_mod


BOT_TAG = "BOT-EMERGENCY-ESCALATION"


class Result(dict):
    """Structured outcome for logging/testing. Not an exception; the loop always returns one."""
    pass


class Orchestrator:
    def __init__(self, cfg, ghl, get_reply, gate=None, dedupe=None, debounce=None,
                 kill_switch=None, logger=None, clock=time.time):
        self.cfg = cfg
        self.ghl = ghl
        self.get_reply = get_reply
        self.clock = clock
        self.log = logger or (lambda *a, **k: None)

        here = safety_mod.Path(__file__).resolve().parent
        self.kill = kill_switch or safety_mod.KillSwitch(here / cfg.get("kill_switch_file", "KILL_SWITCH"))
        qh = cfg.get("quiet_hours", {})
        quiet = safety_mod.QuietHours(qh.get("start", 21), qh.get("end", 8), cfg.get("timezone"))
        rl = cfg.get("rate_limit", {})
        rate = safety_mod.RateLimiter(rl.get("max_per_10s", 20), rl.get("daily_max", 5000), clock=clock)
        self.gate = gate or safety_mod.SendGate(cfg, self.kill, quiet, rate, clock=clock)
        self.dedupe = dedupe or safety_mod.Dedupe(cfg.get("dedupe_ttl_seconds", 3600), clock=clock)
        self.debounce = debounce or safety_mod.Debounce(cfg.get("debounce_seconds", 2), clock=clock)

        self._our_sent_ids = set()   # message ids the bot sent - anything else outbound = a human
        self._opted_out = set()      # contacts who texted STOP - never message again (until opt-in)

    # ---- main entry -------------------------------------------------------------------------
    def handle(self, payload, lead_source=None, now=None):
        msg = inbound_adapter.normalize(payload)
        if msg is None:
            return Result(action="ignored", reason="not an actionable inbound message")

        if self.dedupe.seen(msg["message_id"]):
            return Result(action="ignored", reason="duplicate message", message_id=msg["message_id"])
        self.dedupe.mark(msg["message_id"])

        if self.kill.engaged():
            return Result(action="halted", reason="kill switch engaged")

        # Consent comes before anything the bot might say.
        intent = consent.classify(msg["text"])
        if intent == "opt_out":
            self._opted_out.add(msg["contact_id"])
            if self.cfg.get("allow_real_sends"):
                try:
                    self.ghl.set_dnd(msg["contact_id"], True)
                except Exception as e:
                    self.log("set_dnd failed:", e)
            send = self._send(msg["contact_id"], consent.OPT_OUT_REPLY, msg["channel"],
                              msg["conversation_id"], now)
            return Result(action="opted_out", contact_id=msg["contact_id"], **send)
        if intent == "help":
            send = self._send(msg["contact_id"], consent.HELP_REPLY, msg["channel"],
                              msg["conversation_id"], now)
            return Result(action="help_sent", contact_id=msg["contact_id"], **send)
        if intent == "opt_in":
            self._opted_out.discard(msg["contact_id"])
            if self.cfg.get("allow_real_sends"):
                try:
                    self.ghl.set_dnd(msg["contact_id"], False)
                except Exception as e:
                    self.log("set_dnd clear failed:", e)
            send = self._send(msg["contact_id"], consent.OPT_IN_REPLY, msg["channel"],
                              msg["conversation_id"], now)
            return Result(action="opted_in", contact_id=msg["contact_id"], **send)

        # Someone who opted out is never messaged again (until they opt back in).
        if msg["contact_id"] in self._opted_out:
            return Result(action="suppressed_opted_out", contact_id=msg["contact_id"])

        if self.debounce.should_wait(msg["contact_id"]):
            # A burst from the same contact: let the later message carry the full context.
            return Result(action="debounced", reason="rapid follow-up; will answer on settle",
                          contact_id=msg["contact_id"])

        # Human-standdown: never compete with a live agent.
        thread = self._safe_get_thread(msg["conversation_id"])
        if self._human_engaged(thread):
            return Result(action="stood_down", reason="a human agent is on this conversation",
                          contact_id=msg["contact_id"])

        history = self._history(thread, msg["text"])
        source = lead_source or self._infer_source(msg)

        try:
            brain = self.get_reply(history, lead_source=source)
        except Exception as e:
            return Result(action="error", reason=f"brain failed: {e}", contact_id=msg["contact_id"])
        if not brain.get("ok"):
            return Result(action="error", reason=brain.get("error"), contact_id=msg["contact_id"])

        if brain.get("escalate"):
            return self._escalate(msg, brain["reply"], now)

        send = self._send(msg["contact_id"], brain["reply"], msg["channel"], msg["conversation_id"], now)
        return Result(action="replied", **send, reply=brain["reply"], channel=msg["channel"],
                      contact_id=msg["contact_id"])

    # ---- escalation -------------------------------------------------------------------------
    def _escalate(self, msg, reply, now):
        # Tag for humans (assignment endpoint confirmed against the live account later).
        tagged = False
        if self.cfg.get("allow_real_sends"):
            try:
                self.ghl.add_tag(msg["contact_id"], BOT_TAG)
                tagged = True
            except Exception as e:
                self.log("escalation tag failed:", e)
        send = self._send(msg["contact_id"], reply, msg["channel"], msg["conversation_id"], now)
        # NOTE: deliberately NO booking on an emergency.
        return Result(action="escalated", tagged=tagged, booked=False,
                      reply=reply, channel=msg["channel"], contact_id=msg["contact_id"], **send)

    # ---- gated send -------------------------------------------------------------------------
    def _send(self, contact_id, message, channel, conversation_id, now):
        allowed, reason, simulated = self.gate.check(contact_id, now=now)
        if not allowed:
            self.log(f"SEND BLOCKED ({reason}) to {contact_id}: {message[:60]}")
            return {"send": "blocked", "send_reason": reason}
        if simulated:
            self.log(f"SEND SIMULATED ({reason}) to {contact_id} [{channel}]: {message[:80]}")
            return {"send": "simulated", "send_reason": reason}
        try:
            resp = self.ghl.send_message(contact_id, message, channel=channel,
                                         conversation_id=conversation_id)
            self.gate.commit()
            mid = resp.get("messageId") or resp.get("id")
            if mid:
                self._our_sent_ids.add(mid)
            self.log(f"SENT to {contact_id} [{channel}] messageId={mid}")
            return {"send": "sent", "send_reason": "ok", "message_id": mid}
        except Exception as e:
            self.log("send failed:", e)
            return {"send": "error", "send_reason": str(e)}

    # ---- helpers ----------------------------------------------------------------------------
    def _safe_get_thread(self, conversation_id):
        if not conversation_id or not self.cfg.get("ghl_api_token"):
            return {}
        try:
            return self.ghl.get_thread(conversation_id)
        except Exception as e:
            self.log("get_thread failed (treating as empty):", e)
            return {}

    @staticmethod
    def _extract_messages(thread):
        """Tolerant of a few GHL response shapes; returns a list of message dicts oldest-first."""
        if not thread:
            return []
        m = thread.get("messages", thread)
        if isinstance(m, dict):
            m = m.get("messages", [])
        if not isinstance(m, list):
            return []
        # GHL returns newest-first; we want oldest-first for the LLM.
        return list(reversed(m))

    def _human_engaged(self, thread):
        if not thread:
            return False
        if thread.get("assignedTo") or thread.get("assignedUserId"):
            return True
        for msg in self._extract_messages(thread):
            direction = (msg.get("direction") or "").lower()
            if direction == "outbound":
                mid = msg.get("id") or msg.get("messageId")
                if mid not in self._our_sent_ids:
                    return True   # an outbound we didn't send == a human replied
        return False

    def _history(self, thread, latest_text):
        history = []
        for msg in self._extract_messages(thread):
            body = (msg.get("body") or "").strip()
            if not body:
                continue
            role = "assistant" if (msg.get("direction", "").lower() == "outbound") else "user"
            history.append({"role": role, "content": body})
        # Ensure the just-arrived message is present as the final user turn.
        if not history or history[-1]["role"] != "user" or history[-1]["content"] != latest_text:
            history.append({"role": "user", "content": latest_text})
        return history

    @staticmethod
    def _infer_source(msg):
        raw = msg.get("raw", {})
        src = (raw.get("source") or raw.get("utmSource") or "").lower()
        if "fb" in src or "face" in src or "insta" in src or "ig" in src or "meta" in src:
            return "meta"
        return "website" if msg["channel"] == "Live_Chat" else "sms"


def build(cfg=None, ghl=None, get_reply=None, logger=print):
    """Convenience wiring for real use on the Worker (after Augustine's approval)."""
    cfg = cfg or config_mod.load()
    if ghl is None:
        from ghl_client import GhlClient
        ghl = GhlClient(cfg)
    if get_reply is None:
        from bot_brain import get_reply as _gr
        get_reply = _gr
    return Orchestrator(cfg, ghl, get_reply, logger=logger)
