"""
auth.py — uLearn authentication.

Two sign-in paths:
  1. Local accounts (username + password) — the default, always available.
     Admin accounts are created via first-run setup; member accounts are
     created by an admin from the dashboard.
  2. Jellyfin sign-in — off by default. An admin turns it on and sets the
     Jellyfin server URL from Settings. When enabled, the login page shows
     a "Sign in with Jellyfin" button in addition to the normal fields
     (same pattern as NodecastTV). Verifying a Jellyfin login still uses
     the direct AuthenticateByName call, then links/creates a local user
     row keyed on jellyfin_user_id.
"""

import os
import time
import secrets
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
import requests
from fastapi import Cookie, Header, HTTPException, Depends, Query
from db import get_conn, row_to_dict, get_setting

JWT_SECRET = os.environ.get("SECRET_KEY", "change-me")
JWT_ALGO = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days

CLIENT_NAME = "uLearn"
DEVICE_NAME = "uLearn-Server"
DEVICE_ID = "ulearn-server-001"
APP_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Local password auth
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def authenticate_local(username: str, password: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        # Run a dummy bcrypt comparison anyway, so a nonexistent username
        # doesn't respond measurably faster than a real one with a wrong
        # password — otherwise response timing leaks which usernames exist.
        bcrypt.checkpw(password.encode(), bcrypt.gensalt())
        raise ValueError("Invalid username or password")
    if not verify_password(password, row["password_hash"]):
        raise ValueError("Invalid username or password")
    return row_to_dict(row)


# ---------------------------------------------------------------------------
# Jellyfin auth (optional, admin-toggled)
# ---------------------------------------------------------------------------

def jellyfin_settings() -> dict:
    with get_conn() as conn:
        return {
            "enabled": get_setting(conn, "jellyfin_auth_enabled") == "1",
            "url": get_setting(conn, "jellyfin_url") or "",
        }


def authenticate_with_jellyfin(username: str, password: str) -> dict:
    settings = jellyfin_settings()
    if not settings["enabled"]:
        raise RuntimeError("Jellyfin sign-in is not enabled")
    if not settings["url"]:
        raise RuntimeError("Jellyfin URL is not configured")

    auth_header = (
        f'MediaBrowser Client="{CLIENT_NAME}", Device="{DEVICE_NAME}", '
        f'DeviceId="{DEVICE_ID}", Version="{APP_VERSION}"'
    )

    resp = requests.post(
        f"{settings['url'].rstrip('/')}/Users/AuthenticateByName",
        headers={"Content-Type": "application/json", "X-Emby-Authorization": auth_header},
        json={"Username": username, "Pw": password},
        timeout=10,
    )

    if not resp.ok:
        raise ValueError("Invalid Jellyfin credentials")

    user = resp.json()["User"]
    return {
        "jellyfin_user_id": user["Id"],
        "username": user["Name"],
        "is_admin": bool(user.get("Policy", {}).get("IsAdministrator", False)),
    }


def get_or_create_jellyfin_linked_user(jf_user: dict) -> dict:
    """
    Finds a local user already linked to this Jellyfin account, or a local
    account with a matching username to auto-link, or creates a new local
    account tied to this Jellyfin identity.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE jellyfin_user_id = ?", (jf_user["jellyfin_user_id"],)
        ).fetchone()
        if row:
            return row_to_dict(row)

        existing = conn.execute(
            "SELECT * FROM users WHERE username = ? AND jellyfin_user_id IS NULL",
            (jf_user["username"],),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET jellyfin_user_id = ? WHERE id = ?",
                (jf_user["jellyfin_user_id"], existing["id"]),
            )
            return row_to_dict(
                conn.execute("SELECT * FROM users WHERE id = ?", (existing["id"],)).fetchone()
            )

        cur = conn.execute(
            "INSERT INTO users (username, jellyfin_user_id, is_admin) VALUES (?, ?, ?)",
            (jf_user["username"], jf_user["jellyfin_user_id"], int(jf_user["is_admin"])),
        )
        return row_to_dict(
            conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        )


# ---------------------------------------------------------------------------
# JWT issuing / verification
# ---------------------------------------------------------------------------

def issue_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "is_admin": bool(user["is_admin"]),
        "exp": int(time.time()) + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(
    authorization: str = Header(default=None),
    session_token: str = Cookie(default=None),
    t: str = Query(default=None),
) -> dict:
    """
    Prefer the HttpOnly session cookie. Bearer and query-token support remain
    temporarily for API compatibility, but the web client never places a JWT
    in a media URL.

    Re-verifies against the database on every call rather than trusting
    the token's embedded claims — otherwise deleting a user, or demoting
    an admin, wouldn't take effect until their existing token naturally
    expired (up to 14 days later).
    """
    token = None
    if session_token:
        token = session_token
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif t:
        token = t

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    payload = decode_token(token)

    with get_conn() as conn:
        user = conn.execute(
            "SELECT id, username, is_admin FROM users WHERE id = ?", (payload.get("sub"),)
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists")

    return {"sub": str(user["id"]), "username": user["username"], "is_admin": bool(user["is_admin"])}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Invite / password-reset tokens
# ---------------------------------------------------------------------------

def create_auth_token(conn, user_id: int, kind: str, ttl_hours: int) -> str:
    """kind: 'invite' | 'reset'. Any unused, unexpired tokens of the same
    kind for this user are invalidated first, so requesting a new reset
    link makes an older one stop working."""
    conn.execute(
        "UPDATE auth_tokens SET used = 1 WHERE user_id = ? AND kind = ? AND used = 0",
        (user_id, kind),
    )
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO auth_tokens (token, user_id, kind, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, kind, expires_at),
    )
    return token


def resolve_auth_token(conn, token: str):
    """Returns the auth_tokens row (with user info joined) if the token is
    valid, unused, and unexpired — otherwise None."""
    row = conn.execute(
        "SELECT t.token, t.kind, t.expires_at, t.used, u.id as user_id, u.username "
        "FROM auth_tokens t JOIN users u ON u.id = t.user_id "
        "WHERE t.token = ?",
        (token,),
    ).fetchone()
    if not row:
        return None
    if row["used"]:
        return None
    expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return None
    return row


def consume_auth_token(conn, token: str):
    conn.execute("UPDATE auth_tokens SET used = 1 WHERE token = ?", (token,))
