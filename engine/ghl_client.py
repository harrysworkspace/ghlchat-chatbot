"""
ghl_client.py - thin wrapper over the GoHighLevel (LeadConnector v2) REST API.

Mirrors the conventions already proven in ..\\..\\FCC-Daily\\ghl_pull.ps1: base
services.leadconnectorhq.com, Bearer token, Version: 2021-07-28, with retry/backoff and 429
rate-limit handling. Endpoints and shapes come from GHL_WIRING_PLAN.md section 4.

IMPORTANT
- This module makes NO call on import and NO call on its own. It only calls GHL when one of its
  methods is invoked with a real token/base. In tests we inject a fake transport, so the suite
  never touches the live account.
- A dedicated bot token is used (config.ghl_api_token), never the marketing pull's token.
- Sending is gated by the orchestrator's safety layer, not here - this client is a plain transport.
"""

import json
import time

DEFAULT_TIMEOUT = 30


class GhlError(Exception):
    pass


class GhlClient:
    def __init__(self, cfg, session=None):
        """
        cfg: dict from config.load()
        session: an object with .request(method, url, headers=, params=, json=, timeout=) ->
                 response having .status_code, .headers, .json(), .text. Defaults to requests.Session().
                 Injectable so tests (and a dry-run mode) never hit the network.
        """
        self.base = cfg["ghl_base"].rstrip("/")
        self.version = cfg["ghl_version"]
        self.token = cfg.get("ghl_api_token", "")
        self.location_id = cfg["location_id"]
        self._session = session
        self.max_retries = 4

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Version": self.version,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method, path, params=None, body=None):
        if not self.token:
            raise GhlError("no GHL token configured - refusing to call the API")
        url = f"{self.base}{path}"
        last_err = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.request(
                    method, url, headers=self._headers(),
                    params=params, json=body, timeout=DEFAULT_TIMEOUT,
                )
            except Exception as e:
                last_err = f"transport error: {e}"
                time.sleep(min(2 ** attempt, 8))
                continue

            code = resp.status_code
            if code == 429:  # rate limited - honor backoff and retry
                wait = _retry_after(resp.headers) or min(2 ** attempt, 8)
                time.sleep(wait)
                last_err = "429 rate limited"
                continue
            if 500 <= code < 600:
                last_err = f"{code} server error"
                time.sleep(min(2 ** attempt, 8))
                continue
            if code >= 400:
                raise GhlError(f"{method} {path} -> {code}: {_short(resp)}")
            return _json(resp)
        raise GhlError(f"{method} {path} failed after retries: {last_err}")

    # ---- Contacts ---------------------------------------------------------------------------
    def upsert_contact(self, phone=None, email=None, first_name=None, attribution=None, source=None):
        body = {"locationId": self.location_id}
        if phone: body["phone"] = phone
        if email: body["email"] = email
        if first_name: body["firstName"] = first_name
        if source: body["source"] = source
        if attribution: body["attributionSource"] = attribution
        return self._request("POST", "/contacts/upsert", body=body)

    def get_contact(self, contact_id):
        return self._request("GET", f"/contacts/{contact_id}")

    def set_dnd(self, contact_id, dnd=True):
        """Set do-not-contact on a contact (opt-out compliance)."""
        return self._request("PUT", f"/contacts/{contact_id}", body={"dnd": bool(dnd)})

    # ---- Conversations ----------------------------------------------------------------------
    def get_thread(self, conversation_id, limit=25):
        """Recent messages in a conversation (newest-first per GHL); used as the brain's context."""
        return self._request("GET", f"/conversations/{conversation_id}/messages",
                             params={"limit": limit})

    def send_message(self, contact_id, message, channel="SMS", conversation_id=None):
        """
        POST /conversations/messages. channel maps to GHL `type` (SMS or Live_Chat).
        Returns the API response (conversationId, messageId). The orchestrator gates this call;
        the client itself does not decide whether a send is allowed.
        """
        body = {"type": channel, "contactId": contact_id, "message": message}
        if conversation_id:
            body["conversationId"] = conversation_id
        return self._request("POST", "/conversations/messages", body=body)

    # ---- Calendars / appointments -----------------------------------------------------------
    def get_free_slots(self, calendar_id, start_ms, end_ms, timezone):
        return self._request("GET", f"/calendars/{calendar_id}/free-slots",
                             params={"startDate": start_ms, "endDate": end_ms, "timezone": timezone})

    def book_appointment(self, calendar_id, contact_id, start_iso, end_iso=None,
                         title=None, status="confirmed"):
        body = {"calendarId": calendar_id, "locationId": self.location_id,
                "contactId": contact_id, "startTime": start_iso, "appointmentStatus": status}
        if end_iso: body["endTime"] = end_iso
        if title: body["title"] = title
        return self._request("POST", "/calendars/events/appointments", body=body)

    # ---- Opportunities (pipeline) -----------------------------------------------------------
    def move_stage(self, opportunity_id, pipeline_stage_id):
        return self._request("PUT", f"/opportunities/{opportunity_id}",
                             body={"pipelineStageId": pipeline_stage_id})

    def get_pipelines(self):
        return self._request("GET", "/opportunities/pipelines",
                             params={"locationId": self.location_id})

    # ---- Escalation helpers -----------------------------------------------------------------
    def add_tag(self, contact_id, tags):
        if isinstance(tags, str): tags = [tags]
        return self._request("POST", f"/contacts/{contact_id}/tags", body={"tags": tags})


def _retry_after(headers):
    try:
        h = {k.lower(): v for k, v in dict(headers).items()}
        if "retry-after" in h:
            return float(h["retry-after"])
        # GHL burst window header, in ms
        if "x-ratelimit-interval-milliseconds" in h:
            return float(h["x-ratelimit-interval-milliseconds"]) / 1000.0
    except Exception:
        pass
    return None


def _json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": getattr(resp, "text", "")}


def _short(resp):
    t = getattr(resp, "text", "") or ""
    return t[:300]
