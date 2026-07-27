"""
consent.py - opt-out / opt-in / HELP handling for SMS (compliance must-have).

US texting rules require honoring standard keywords. This classifies an inbound message and
provides the standard reply text. The orchestrator uses it BEFORE the brain, so:
  - opt-out  -> set do-not-contact, stop messaging this person, (carrier/we) confirm once.
  - help     -> reply with the standard help line; do not run the bot.
  - opt-in   -> clear do-not-contact, resume.

Pure logic, ASCII only. No network.
"""

import re

# Standard carrier opt-out / help / opt-in keywords (matched as a whole message, case-insensitive).
_OPT_OUT = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "stop all", "optout", "opt out"}
_HELP    = {"help", "info"}
_OPT_IN  = {"start", "unstop", "yes", "resume"}

# Looser natural-language opt-out phrases (people don't always send the exact keyword).
_OPT_OUT_PHRASES = re.compile(
    r"\b(stop texting|stop messaging|remove me|take me off|do not (text|contact|message)|"
    r"don'?t text me|leave me alone|no more texts?)\b", re.IGNORECASE)

HELP_REPLY = ("Disc Center of the Antelope Valley. We help with back and neck pain. "
              "Call (661) 466-2632 or reply STOP to opt out. Msg & data rates may apply.")
OPT_OUT_REPLY = ("You're unsubscribed and won't get more texts from us. "
                 "Reply START if you ever want to hear from us again.")
OPT_IN_REPLY = "You're opted back in. How can we help with your back or neck?"


def classify(text):
    """Return 'opt_out' | 'help' | 'opt_in' | None."""
    if not text:
        return None
    t = text.strip().lower()
    # exact single-keyword message (the standard, carrier-recognized form)
    word = re.sub(r"[^a-z ]", "", t).strip()
    if word in _OPT_OUT:
        return "opt_out"
    if word in _HELP:
        return "help"
    if word in _OPT_IN:
        return "opt_in"
    # natural-language opt-out anywhere in the message
    if _OPT_OUT_PHRASES.search(t):
        return "opt_out"
    return None
