"""
safety.py - the guardrails that keep the live GHL operation safe (GHL_WIRING_PLAN.md section 0).

Every outbound side effect must pass SendGate.check() first. The default posture is FAIL CLOSED:
with the shipped config, allow_real_sends is False and only a dummy contact is on the allowlist,
so nothing can reach a real person until those are deliberately changed.

Pieces:
  - KillSwitch    : a file whose mere presence stops all sends.
  - QuietHours    : no sends outside allowed local hours.
  - RateLimiter   : sliding-window burst + daily cap, well under GHL's limits.
  - Dedupe        : ignore a messageId we've already processed (webhooks fire more than once).
  - Debounce      : coalesce rapid-fire messages from the same contact.
  - SendGate      : combines allowlist + master switch + kill switch + quiet hours + rate limit.

No network here. Pure, testable logic. Time and "now" are injectable for tests.
"""

import time
from collections import deque
from datetime import datetime
from pathlib import Path


class KillSwitch:
    def __init__(self, path):
        self.path = Path(path)

    def engaged(self):
        return self.path.exists()


class QuietHours:
    """Blocks sends during quiet hours. Window may wrap midnight (e.g. start=21, end=8)."""
    def __init__(self, start_hour, end_hour, tz_name="America/Los_Angeles"):
        self.start = start_hour
        self.end = end_hour
        self.tz_name = tz_name

    def _now_hour(self, now=None):
        if now is not None:
            return now.hour
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(self.tz_name)).hour
        except Exception:
            return datetime.now().hour

    def is_quiet(self, now=None):
        h = self._now_hour(now)
        if self.start == self.end:
            return False
        if self.start < self.end:          # same-day window
            return self.start <= h < self.end
        return h >= self.start or h < self.end   # wraps midnight


class RateLimiter:
    def __init__(self, max_per_10s=20, daily_max=5000, clock=time.time):
        self.max_per_10s = max_per_10s
        self.daily_max = daily_max
        self.clock = clock
        self._recent = deque()      # timestamps in the last 10s
        self._day = None
        self._day_count = 0

    def allow(self):
        now = self.clock()
        # burst window
        while self._recent and now - self._recent[0] > 10:
            self._recent.popleft()
        # daily window
        day = int(now // 86400)
        if day != self._day:
            self._day, self._day_count = day, 0
        if len(self._recent) >= self.max_per_10s:
            return False, "burst rate limit"
        if self._day_count >= self.daily_max:
            return False, "daily rate limit"
        return True, None

    def record(self):
        now = self.clock()
        self._recent.append(now)
        day = int(now // 86400)
        if day != self._day:
            self._day, self._day_count = day, 0
        self._day_count += 1


class Dedupe:
    def __init__(self, ttl_seconds=3600, clock=time.time):
        self.ttl = ttl_seconds
        self.clock = clock
        self._seen = {}      # id -> ts

    def seen(self, key):
        if key is None:
            return False
        self._evict()
        return key in self._seen

    def mark(self, key):
        if key is not None:
            self._seen[key] = self.clock()

    def _evict(self):
        now = self.clock()
        for k in [k for k, ts in self._seen.items() if now - ts > self.ttl]:
            del self._seen[k]


class Debounce:
    """True from should_wait() if this contact messaged within the debounce window."""
    def __init__(self, window_seconds=2, clock=time.time):
        self.window = window_seconds
        self.clock = clock
        self._last = {}

    def should_wait(self, contact_id):
        now = self.clock()
        prev = self._last.get(contact_id)
        self._last[contact_id] = now
        return prev is not None and (now - prev) < self.window


class SendGate:
    """
    The single chokepoint for outbound. check(contact_id) returns (allowed: bool, reason, simulated).
    - simulated=True means "allowed to proceed but do NOT actually hit GHL" (master switch off or
      contact not on the allowlist) - the orchestrator logs it instead of sending. This is how the
      bot runs full end-to-end without ever messaging a real person.
    """
    def __init__(self, cfg, kill_switch, quiet_hours, rate_limiter, clock=time.time):
        self.allowlist = set(cfg.get("messaging_allowlist", []))
        self.allow_real = bool(cfg.get("allow_real_sends", False))
        self.kill = kill_switch
        self.quiet = quiet_hours
        self.rate = rate_limiter
        self.clock = clock

    def check(self, contact_id, now=None):
        if self.kill.engaged():
            return False, "kill switch engaged", False
        if self.quiet.is_quiet(now):
            return False, "quiet hours", False
        ok, why = self.rate.allow()
        if not ok:
            return False, why, False
        # Fail-closed gates: a REAL send needs both the master switch on AND the contact allowlisted.
        if not self.allow_real:
            return True, "master switch off - simulate", True
        if contact_id not in self.allowlist:
            return True, "contact not on allowlist - simulate", True
        return True, "ok", False

    def commit(self):
        """Call after an actual (non-simulated) send so the rate limiter counts it."""
        self.rate.record()
