"""Short-lived, session-bound playback tickets.

Tickets are opaque random values. Active playback renews the idle timeout on every
Range request, while abandoned/copied URLs expire quickly and never work without
the exact HttpOnly session cookie that created them.
"""

import hashlib
import secrets
import threading
import time

# Fifteen idle minutes tolerates pausing to take notes without interrupting
# playback. Tickets still require the exact session cookie and have a hard cap.
IDLE_TTL_SECONDS = 15 * 60
MAX_TTL_SECONDS = 6 * 60 * 60
_lock = threading.Lock()
_tickets: dict[str, dict] = {}


def session_fingerprint(session_token: str) -> str:
    return hashlib.sha256(session_token.encode("utf-8")).hexdigest()


def issue_playback_ticket(user_id: str, lesson_id: int, session_token: str) -> str:
    now = time.monotonic()
    ticket = secrets.token_urlsafe(32)
    record = {
        "user_id": str(user_id),
        "lesson_id": int(lesson_id),
        "session": session_fingerprint(session_token),
        "created": now,
        "last_seen": now,
    }
    with _lock:
        _cleanup(now)
        _tickets[ticket] = record
    return ticket


def validate_playback_ticket(ticket: str, user_id: str, session_token: str):
    now = time.monotonic()
    fingerprint = session_fingerprint(session_token)
    with _lock:
        _cleanup(now)
        record = _tickets.get(ticket)
        if not record:
            return None
        if record["user_id"] != str(user_id) or record["session"] != fingerprint:
            return None
        if now - record["last_seen"] > IDLE_TTL_SECONDS or now - record["created"] > MAX_TTL_SECONDS:
            _tickets.pop(ticket, None)
            return None
        record["last_seen"] = now
        return dict(record)


def revoke_playback_ticket(ticket: str):
    with _lock:
        _tickets.pop(ticket, None)


def _cleanup(now: float):
    expired = [ticket for ticket, record in _tickets.items()
               if now - record["last_seen"] > IDLE_TTL_SECONDS or now - record["created"] > MAX_TTL_SECONDS]
    for ticket in expired:
        _tickets.pop(ticket, None)
