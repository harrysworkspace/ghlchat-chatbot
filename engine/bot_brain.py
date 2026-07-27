"""
bot_brain.py - the "brain" for the GHL chatbot (v1).

Given a conversation (a list of turns), it asks Claude via AWS Bedrock (BAA-covered) for the
bot's next reply. This is the PHI-safe inference path documented in OPERATIONS_MANUAL section 1
and reused from FCC-Daily\\enrich_briefing.py (same credential CSV, region and model).

WHAT THIS IS
- The single "core conversation": welcome a new person, find out what's going on, ask a few
  gentle fit questions, and move toward booking. Same script whether it runs on the website
  bubble or as the first text to a new lead.
- Stateless: the caller (the future "middleman" layer) owns the conversation history and the
  GHL read/write. This module only turns "conversation so far" into "the next thing to say."

SAFETY BUILT IN
- BAA-only brain: Bedrock, never the Anthropic API, OpenAI, or the Cowork/Claude assistant.
- No medical advice: the system prompt screens and books only.
- Emergency escalation: an independent keyword net (NOT just the model) flags red-flag messages
  so the middleman can hand off to a human immediately.
- Meta opt-out: when lead_source == "meta", the very first bot message includes a STOP line.
- ASCII-only output: model text is sanitized (smart quotes / dashes / arrows -> plain ASCII)
  so SMS through GHL never arrives as mojibake (MACHINE_STATE section 7 lesson).

USAGE (as a library)
    from bot_brain import get_reply
    result = get_reply(messages, lead_source="meta")
    # messages = [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    # result  = {"ok": True, "reply": "...", "escalate": False, "usage": {...}}

No real patient data belongs in test runs - use synthetic transcripts only.
"""

import csv
import json
import re
from pathlib import Path

# --- Configuration (matches enrich_briefing.py / bedrock_smoke.py) --------------------------
KEY_CSV    = Path(r"Z:\Administration\cowork\Patient Reports\Config\aws-bedrock-key.csv")
REGION     = "us-east-1"
MODEL_ID   = "us.anthropic.claude-sonnet-4-6"
MAX_TOKENS = 400          # bot messages are short on purpose
TEMPERATURE = 0.4         # a little warmth; low enough to stay on-script

# --- The one core conversation --------------------------------------------------------------
SYSTEM_PROMPT = """You are the automated scheduling assistant for the Disc Center of the Antelope
Valley (a spinal decompression / disc clinic, part of Frye Chiropractic). You help people who
reached out about back or neck pain. You are NOT a doctor and NOT a human staff member.

WHO YOU ARE - be honest about it
- You are a friendly text/scheduling assistant, not a person. Keep a warm, human tone, but never
  pretend to be a human. Do NOT give yourself a human name (never "this is Sarah"), and do not call
  yourself "the front desk" or otherwise imply you are a staff member.
- If someone asks whether you're a bot or a person, tell them plainly and warmly that you're the
  clinic's scheduling assistant.
- When a real person needs to help, refer to them as "someone from our office" or "our team" - which
  also keeps clear that you are not that person.

YOUR ONLY JOB
Warmly welcome the person, understand what's going on, ask a few gentle fit questions, and help them
get scheduled. That's it. You screen and schedule - you do not diagnose or advise.

HOW TO TALK
- Warm, easygoing, and human in tone - never like an ad or a salesperson.
- You are a scheduling assistant, not an authority. INVITE and OFFER - never bark orders, boss people
  around, or pressure them. Prefer "would you like...", "I can help you...", "whenever you're ready"
  over commands.
- Short messages. One question at a time. Plain words.
- Acknowledge how they feel before asking the next thing ("ugh, that sounds rough").
- Use only plain ASCII characters. No emoji, no smart quotes, no em dashes.

THE FLOW (roughly, not rigidly)
1. Say hi and ask what's been going on with their back or neck.
2. A few gentle fit questions, one at a time: how long has it been going on, where is the pain,
   has it stopped them working or sleeping, any prior imaging (MRI/X-ray), tried anything so far,
   has anyone mentioned surgery.
3. When they seem like a fit and are willing, offer to get them in for a visit. Do NOT invent
   specific appointment times or dates - say you'll grab them a time and confirm the details.
   (The scheduling system provides real openings; you never make them up.)

HARD RULES - never break these
- Never give medical advice, a diagnosis, a treatment recommendation, or dosing. If asked, gently
  say the doctor will go over all of that at the visit.
- NO ONE IS STANDING BY. There is not a team member watching messages 24/7 - it may be 2am, or staff
  may be busy. So NEVER say a person is "on the way," "coming right now," "being brought in," or
  "standing by." That is a false promise. When a human needs to follow up, be honest: say someone
  from our office will reach out during office hours. Whatever you tell them must still be true if no
  human sees the message for hours.
- MEDICAL EMERGENCY (loss of bladder or bowel control; numbness in the saddle, groin, or inner-thigh
  area; sudden or severe leg weakness; a major injury, fall, or trauma such as a car accident): their
  safety does NOT depend on us. Tell them plainly to call 911 or go to an emergency room NOW - that is
  the entire priority. Do not book. You may add that our office will follow up when we're open, but
  make it clear they must get emergency care immediately regardless. Do not imply a person is standing
  by. Say the 911/ER direction once, calmly and warmly - do not repeat commands or bark at them.
- EMOTIONAL CRISIS / SELF-HARM (thoughts of hurting themselves, not wanting to live, hopelessness):
  respond with genuine warmth and take it seriously. Do NOT ask yes/no assessment questions like "are
  you thinking of hurting yourself" - that is not your role. Instead, gently say you're concerned,
  share the 988 Suicide and Crisis Lifeline (they can call or text 988 in the US, free, 24/7), and
  encourage them to reach out to someone they trust. Do not book a visit and do not just move on.
- If the person is frustrated, wants a human, or asks something clinical you can't answer: hand off
  warmly and HONESTLY - say you'll pass this to the team and someone will reach out during office hours
  (never "right now"). Offer to take their name and best number so the team can follow up.
- Never share other patients' information. Never promise a specific medical outcome.
"""

# Independent emergency net - checked in code, not left to the model alone.
# Over-escalation is acceptable here: a false alarm just hands off to a human, which is safe.
RED_FLAG_PATTERNS = [
    # bladder / bowel (cauda equina)
    r"bladder", r"bowel", r"incontinen", r"wet myself", r"wetting myself", r"soiled",
    r"leak(ing|ed)?\s+(urine|pee|stool)", r"urinat", r"can'?t (pee|urinate)",
    r"can'?t hold (my )?(pee|urine|bladder|bowel)", r"pee(d|ing)? myself",
    r"lost control of my (bladder|bowel)",
    # saddle / perineal / inner-thigh numbness
    r"saddle", r"perine", r"groin numb",
    r"numb.*(groin|genital|between my legs|butt|buttock|inner thigh|thigh|perine)",
    r"(inner thigh|thigh|groin|genital|buttock)s?.*numb",
    # weakness / can't move legs
    r"can'?t (feel|move) my legs?", r"legs? (gave out|giving out|went numb)",
    r"sudden(ly)? weak", r"getting weaker", r"progressive weakness",
    # trauma
    r"car (accident|crash)", r"fell off", r"bad fall", r"hit by",
    # non-spinal emergencies -> hand off
    r"chest pain", r"can'?t breathe", r"slurred speech", r"face drooping",
    # emotional crisis / self-harm (respond with care + 988; also flagged for a human)
    r"kill(ing)? myself", r"end my life", r"want to die", r"wanna die", r"better off dead",
    r"don'?t\s+(even\s+|really\s+)?want to (live|be here|be alive|exist|go on)",
    r"hurt(ing)? myself", r"harm(ing)? myself", r"suicid", r"no reason to live",
]
RED_FLAG_RE = re.compile("|".join(RED_FLAG_PATTERNS), re.IGNORECASE)

# ASCII sanitizer - keep everything the bot says plain (MACHINE_STATE section 7).
_ASCII_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "→": "->",
    " ": " ", "•": "-", "‑": "-", "·": "-",
}


def to_ascii(text):
    """Replace the usual model 'smart' characters, then drop anything still non-ASCII."""
    if not text:
        return ""
    for bad, good in _ASCII_MAP.items():
        text = text.replace(bad, good)
    return text.encode("ascii", "ignore").decode("ascii").strip()


def check_red_flags(messages):
    """True if the most recent user message trips the emergency net."""
    for turn in reversed(messages):
        if turn.get("role") == "user":
            return bool(RED_FLAG_RE.search(turn.get("content", "")))
    return False


def _load_credentials():
    with open(KEY_CSV, "r", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
        access_key = row.get("Access key ID") or row.get("Access key")
        secret_key = row.get("Secret access key")
    if not access_key or not secret_key:
        raise RuntimeError("credential CSV present but access/secret columns not found")
    return access_key, secret_key


def _build_system(lead_source):
    """Assemble the system prompt, adding the Meta opt-out instruction when needed."""
    system = SYSTEM_PROMPT
    if (lead_source or "").lower() == "meta":
        system += (
            "\n\nLEAD SOURCE: this person came in through a Facebook/Instagram ad. In your FIRST "
            "message only, include a short, natural opt-out line such as: 'Reply STOP any time to "
            "stop texts.' Keep it light and put it at the end of that first message."
        )
    return system


def _make_client(access_key, secret_key):
    """Isolated so tests can monkeypatch it without a network or real credentials."""
    import boto3
    return boto3.client(
        "bedrock-runtime",
        region_name=REGION,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def get_reply(messages, lead_source=None):
    """
    messages: list of {"role": "user"|"assistant", "content": str}, oldest first.
    lead_source: e.g. "meta", "website", "ad" - only "meta" changes behaviour today.

    Returns: {"ok": bool, "reply": str, "escalate": bool, "usage": {...}, "error": str|None}
    'escalate' is True if the code-level emergency net fired; the caller should hand to a human.
    """
    escalate = check_red_flags(messages)

    try:
        access_key, secret_key = _load_credentials()
    except Exception as e:
        return {"ok": False, "reply": "", "escalate": escalate, "usage": {},
                "error": f"could not read Bedrock credentials: {e}"}

    system = _build_system(lead_source)
    if escalate:
        # Steer the model hard even though the prompt already covers it.
        system += ("\n\nURGENT: the latest message may describe an emergency or a crisis. Do not screen "
                   "or book. Follow your HARD RULES: for a physical medical emergency, direct them to "
                   "call 911 or go to the ER now; for thoughts of self-harm, direct them to call or text "
                   "988 now and respond with care. Do NOT say a person is standing by - no one may be "
                   "available right now.")

    # Bedrock's Anthropic messages API wants clean user/assistant turns.
    clean = [{"role": m["role"], "content": m["content"]} for m in messages
             if m.get("role") in ("user", "assistant") and m.get("content")]
    if not clean or clean[0]["role"] != "user":
        return {"ok": False, "reply": "", "escalate": escalate, "usage": {},
                "error": "conversation must start with a user message"}

    try:
        client = _make_client(access_key, secret_key)
        resp = client.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
                "system": system,
                "messages": clean,
            }),
        )
        result = json.loads(resp["body"].read())
        text = to_ascii(result["content"][0]["text"])
        if not text:
            return {"ok": False, "reply": "", "escalate": escalate, "usage": {},
                    "error": "Bedrock returned an empty response"}
        return {
            "ok": True,
            "reply": text,
            "escalate": escalate,
            "usage": result.get("usage", {}),
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "reply": "", "escalate": escalate, "usage": {},
                "error": f"Bedrock call failed: {e}"}


if __name__ == "__main__":
    # Tiny manual check: one opening user turn. Real testing lives in fake_chat.py.
    import sys
    opening = " ".join(sys.argv[1:]) or "hi, my lower back has been killing me"
    out = get_reply([{"role": "user", "content": opening}], lead_source="website")
    print(json.dumps(out, indent=2))
