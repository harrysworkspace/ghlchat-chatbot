"""
config.py - load the chatbot's settings.

Reads ghl_bot_config.json (gitignored; see ghl_bot_config.example.json). This is DELIBERATELY a
separate config from the marketing pull's helper_config.json so the bot has its own dedicated,
revocable token and its own isolated settings (GHL_WIRING_PLAN.md section 0).

Nothing here touches the network. Loading config has no side effects.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "ghl_bot_config.json"

# Safe defaults. Every one of these is designed to fail CLOSED - the out-of-the-box state cannot
# message a real person: allow_real_sends is False and the allowlist holds only a dummy id.
DEFAULTS = {
    "ghl_base": "https://services.leadconnectorhq.com",
    "ghl_version": "2021-07-28",
    "ghl_api_token": "",                       # dedicated bot PIT - added only after Augustine approves
    "location_id": "uEanpHM7WXjNsXmCuRS5",
    "calendar_id": "",                         # TBD from account (open item B1)
    "pipeline_id": "iqPVQQEk3uCMGZxUmVTy",     # Marketing Pipeline 1
    "stage_ids": {},                           # e.g. {"engaged": "...", "scheduled": "..."}
    "timezone": "America/Los_Angeles",
    "quiet_hours": {"start": 21, "end": 8},    # no sends 9pm-8am local
    "rate_limit": {"max_per_10s": 20, "daily_max": 5000},   # far under GHL's 100/10s & 200k/day
    "messaging_allowlist": ["DUMMY_CONTACT_ID"],            # ONLY these contacts may be messaged
    "allow_real_sends": False,                 # master switch. False = simulate every send (log only)
    "kill_switch_file": "KILL_SWITCH",         # if this file exists in the engine dir, all sends stop
    "debounce_seconds": 2,
    "dedupe_ttl_seconds": 3600,
}


def load(path=None):
    """Return the merged config dict (defaults <- file). Missing file is fine (uses defaults)."""
    cfg = dict(DEFAULTS)
    p = Path(path) if path else CONFIG_PATH
    if p.exists():
        try:
            user = json.loads(p.read_text(encoding="utf-8"))
            for k, v in user.items():
                cfg[k] = v
        except Exception as e:
            raise RuntimeError(f"could not parse {p.name}: {e}")
    return cfg


if __name__ == "__main__":
    c = load()
    # Never print the token.
    safe = {k: ("<set>" if k == "ghl_api_token" and v else v) for k, v in c.items()}
    print(json.dumps(safe, indent=2))
