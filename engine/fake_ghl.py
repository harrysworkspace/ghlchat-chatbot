"""
fake_ghl.py - an in-process stand-in for GoHighLevel, for offline tests.

It implements just the methods the orchestrator calls (get_thread, send_message, add_tag) and
records what happened, so the whole bot loop can run end-to-end with ZERO network and zero risk
to the live account. Never used in production - tests and the offline demo only.
"""


class FakeGhl:
    def __init__(self):
        self.sent = []          # list of dicts: contact_id, message, channel
        self.tags = []          # list of (contact_id, tags)
        self.threads = {}       # conversation_id -> thread dict (GHL newest-first shape)
        self._n = 0

    def seed_thread(self, conversation_id, messages=None, assigned_to=None):
        """messages: list of {direction, body, id} NEWEST-FIRST (GHL order)."""
        self.threads[conversation_id] = {
            "assignedTo": assigned_to,
            "messages": {"messages": messages or []},
        }

    # --- methods the orchestrator uses ---
    def get_thread(self, conversation_id, limit=25):
        return self.threads.get(conversation_id, {})

    def send_message(self, contact_id, message, channel="SMS", conversation_id=None):
        self._n += 1
        mid = f"bot-{self._n}"
        self.sent.append({"contact_id": contact_id, "message": message,
                          "channel": channel, "message_id": mid})
        return {"messageId": mid, "conversationId": conversation_id or f"conv-{contact_id}"}

    def add_tag(self, contact_id, tags):
        self.tags.append((contact_id, tags))
        return {"ok": True}

    def set_dnd(self, contact_id, dnd=True):
        self.dnd = getattr(self, "dnd", [])
        self.dnd.append((contact_id, dnd))
        return {"ok": True}
