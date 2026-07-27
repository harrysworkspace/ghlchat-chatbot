"""
fake_chat.py - prove the bot brain works, using SYNTHETIC conversations only.

This is the smoke test for the chatbot's first piece. It feeds made-up (no real patient)
messages to bot_brain.get_reply() turn by turn and prints the exchange, so you can see the
bot actually reach AWS Bedrock and behave: welcome, gentle screening, Meta opt-out, and the
emergency hand-off.

RUN ON THE WORKER MACHINE (where the Bedrock credential and venv live):

    & "Z:\\Administration\\cowork\\tools\\refagent-venv\\Scripts\\python.exe" `
        "Z:\\Administration\\cowork\\GHLchat-Chatbot\\engine\\fake_chat.py"

Options:
    --scenario website   run the new-lead / website welcome demo (default)
    --scenario meta      run the Facebook/Instagram demo (checks the STOP opt-out line)
    --scenario redflag   run the emergency demo (checks escalation + safe hand-off)
    --scenario all       run all three
    --interactive        type your own messages as the "lead" (still synthetic - no real PHI)

NEVER paste a real patient conversation into this script. Debug from synthetic transcripts only
(GOVERNANCE_AND_PROCESS section 0.1).
"""

import argparse
import sys

from bot_brain import get_reply

# Synthetic lead turns. Each scenario is just what the pretend person types, in order.
SCENARIOS = {
    "website": {
        "lead_source": "website",
        "turns": [
            "hi, my lower back has been killing me for a few weeks",
            "it shoots down my right leg, worse when i sit",
            "no i havent had any scans. a friend said i might need surgery",
            "yeah id like to come in",
        ],
    },
    "meta": {
        "lead_source": "meta",
        "turns": [
            "saw your ad about back pain without surgery",
            "sciatica for like 2 months, cant sleep",
            "sure, how does it work",
        ],
    },
    "redflag": {
        "lead_source": "website",
        "turns": [
            "my back went out bad yesterday",
            "honestly i've started leaking urine and my inner thighs feel numb",
        ],
    },
}


def run_scenario(name):
    spec = SCENARIOS[name]
    lead_source = spec["lead_source"]
    print("=" * 70)
    print(f"SCENARIO: {name}   (lead_source={lead_source})")
    print("=" * 70)

    messages = []
    for user_text in spec["turns"]:
        messages.append({"role": "user", "content": user_text})
        print(f"\n[lead]  {user_text}")

        result = get_reply(messages, lead_source=lead_source)
        if not result["ok"]:
            print(f"\n*** ERROR: {result['error']}")
            return False

        flag = "  <<< ESCALATE (hand to human)" if result["escalate"] else ""
        print(f"[bot]   {result['reply']}{flag}")
        messages.append({"role": "assistant", "content": result["reply"]})

    usage = result.get("usage", {})
    print(f"\n(last turn tokens: in={usage.get('input_tokens')} out={usage.get('output_tokens')})")
    return True


def run_interactive():
    print("Interactive fake chat. Type as the 'lead'. Ctrl-C or blank line to quit.")
    print("SYNTHETIC ONLY - never type a real patient's words.\n")
    source = input("lead_source [website/meta] (default website): ").strip() or "website"
    messages = []
    while True:
        try:
            user_text = input("[lead]  ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            break
        messages.append({"role": "user", "content": user_text})
        result = get_reply(messages, lead_source=source)
        if not result["ok"]:
            print(f"*** ERROR: {result['error']}")
            break
        flag = "  <<< ESCALATE (hand to human)" if result["escalate"] else ""
        print(f"[bot]   {result['reply']}{flag}\n")
        messages.append({"role": "assistant", "content": result["reply"]})


def main():
    ap = argparse.ArgumentParser(description="Synthetic smoke test for the GHL chatbot brain.")
    ap.add_argument("--scenario", default="website",
                    choices=["website", "meta", "redflag", "all"])
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()

    if args.interactive:
        run_interactive()
        return

    names = ["website", "meta", "redflag"] if args.scenario == "all" else [args.scenario]
    ok = True
    for n in names:
        ok = run_scenario(n) and ok
        print()
    print("SMOKE TEST PASSED" if ok else "SMOKE TEST HAD ERRORS - see above")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
