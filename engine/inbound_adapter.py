"""
inbound_adapter.py - turn whatever GHL sends us into ONE clean shape.

We support two inbound paths (GHL_WIRING_PLAN.md section 2a) without the rest of the code caring
which one is live:
  - Option A: a GHL Workflow -> Webhook (POST) action, payload shaped by us via custom values.
  - Option B: a private Marketplace app's native `InboundMessage` webhook.

Both normalize to:
  { contact_id, conversation_id, message_id, text, channel, direction, raw }

channel is "SMS" or "Live_Chat" (the two we reply on). direction lets the orchestrator drop
anything that isn't a real inbound message (never react to our own outbound - reply-loop guard).

Swapping Option A <-> B touches ONLY this file.
"""

# GHL messageType strings we care about -> our channel tag
_CHANNEL_MAP = {
    "sms": "SMS",
    "type_sms": "SMS",
    "live chat": "Live_Chat",
    "live_chat": "Live_Chat",
    "type_live_chat": "Live_Chat",
    "webchat": "Live_Chat",
}


def _channel(raw_value, default="SMS"):
    if raw_value is None:
        return default
    return _CHANNEL_MAP.get(str(raw_value).strip().lower(), default)


def normalize(payload):
    """
    payload: dict from either inbound path. Returns the normalized dict, or None if this isn't an
    actionable inbound message (e.g. it's an outbound echo, or missing a contact).
    """
    if not isinstance(payload, dict):
        return None

    # Native InboundMessage (Option B) has type == "InboundMessage" and rich fields.
    if payload.get("type") == "InboundMessage" or "messageType" in payload:
        direction = (payload.get("direction") or "inbound").lower()
        norm = {
            "contact_id": payload.get("contactId"),
            "conversation_id": payload.get("conversationId"),
            "message_id": payload.get("messageId") or payload.get("id"),
            "text": (payload.get("body") or "").strip(),
            "channel": _channel(payload.get("messageType") or payload.get("messageTypeString")),
            "direction": direction,
            "raw": payload,
        }
    else:
        # Workflow -> Webhook (Option A): we control these keys via custom-value mapping.
        direction = (payload.get("direction") or "inbound").lower()
        norm = {
            "contact_id": payload.get("contact_id") or payload.get("contactId"),
            "conversation_id": payload.get("conversation_id") or payload.get("conversationId"),
            "message_id": payload.get("message_id") or payload.get("messageId"),
            "text": (payload.get("message") or payload.get("body") or "").strip(),
            "channel": _channel(payload.get("channel") or payload.get("messageType")),
            "direction": direction,
            "raw": payload,
        }

    # Drop anything not actionable.
    if norm["direction"] != "inbound":
        return None
    if not norm["contact_id"] or not norm["text"]:
        return None
    return norm
