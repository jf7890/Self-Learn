"""
rate_limit.py — simple in-memory rate limiting for auth endpoints
(login, Jellyfin login, forgot-password, first-run setup).

In-memory rather than DB-backed: state resets on restart, which is an
acceptable tradeoff here — a restart is rare enough that briefly
reopening the window isn't a meaningful risk, and it avoids adding
write load to SQLite on every single request attempt.

Keyed by (IP, identifier) rather than IP alone or identifier alone:
  - IP alone would let one attacker's failed attempts against many
    different usernames lock out none of them individually but still
    hammer the server.
  - Identifier alone (e.g. just username) would let an attacker lock a
    *specific victim* out of their own account by deliberately failing
    their login repeatedly from anywhere — a denial-of-service on that
    person. Combining both means each IP gets its own budget per
    identifier, closing that griefing vector.
"""

import ipaddress
import os
import time
from collections import defaultdict
from fastapi import Request, HTTPException

WINDOW_SECONDS = 15 * 60  # 15 minutes
MAX_ATTEMPTS = 5
MAX_IP_ATTEMPTS = 25

_attempts = defaultdict(list)  # key -> [timestamps of failures]


def _trusted_proxies() -> set[str]:
    configured = os.environ.get("TRUSTED_PROXIES", "127.0.0.1,::1")
    return {value.strip() for value in configured.split(",") if value.strip()}


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """Trust forwarded client addresses only from configured reverse proxies."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and peer in _trusted_proxies():
        candidate = forwarded.split(",")[0].strip()
        if _valid_ip(candidate):
            return candidate
    return peer


def _prune(key: str) -> list:
    now = time.time()
    attempts = [t for t in _attempts[key] if now - t < WINDOW_SECONDS]
    _attempts[key] = attempts
    return attempts


def check_rate_limit(key: str, max_attempts: int = MAX_ATTEMPTS):
    attempts = _prune(key)
    if len(attempts) >= max_attempts:
        retry_after = int(WINDOW_SECONDS - (time.time() - attempts[0]))
        minutes = max(1, (retry_after + 59) // 60)
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        )


def record_failure(key: str):
    _prune(key)
    _attempts[key].append(time.time())


def record_success(key: str):
    _attempts.pop(key, None)
