"""Public authentication, setup, and password-reset routes."""

import os

from fastapi import APIRouter, HTTPException, Request, Response

import auth
import mailer
import rate_limit
from auth import (authenticate_local, authenticate_with_jellyfin,
                  get_or_create_jellyfin_linked_user, hash_password,
                  issue_token, jellyfin_settings)
from db import any_users_exist, get_conn, get_setting, row_to_dict
from schemas import ForgotPasswordRequest, LoginRequest, SetPasswordRequest, SetupRequest

router = APIRouter()
SESSION_COOKIE = "session_token"

def auth_response(response: Response, user: dict):
    token = issue_token(user)
    secure = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}
    response.set_cookie(SESSION_COOKIE, token, max_age=auth.JWT_TTL_SECONDS, httponly=True,
                        secure=secure, samesite="lax", path="/")
    return {"user": {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}}


def normalized_identifier(value: str) -> str:
    return value.strip().casefold()[:150]


def validate_credentials(username: str, password: str):
    username = username.strip()
    if not username or len(username) > 150 or len(password) > 1024:
        raise HTTPException(status_code=400, detail="Invalid username or password")
    return username


def log_login_attempt(user_id, username: str, ip: str, success: bool, method: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO login_history(user_id,username,ip_address,success,method) VALUES(?,?,?,?,?)",
                     (user_id, username[:150], ip, int(success), method))
        if success and user_id:
            conn.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP,last_login_ip=? WHERE id=?", (ip, user_id))
        conn.execute("DELETE FROM login_history WHERE created_at < datetime('now','-90 days')")


def check_login_limits(ip: str, username: str, prefix="login"):
    account_key = f"{prefix}:{ip}:{normalized_identifier(username)}"
    ip_key = f"{prefix}-ip:{ip}"
    rate_limit.check_rate_limit(account_key)
    rate_limit.check_rate_limit(ip_key, max_attempts=rate_limit.MAX_IP_ATTEMPTS)
    return account_key, ip_key


def record_login_failure(keys):
    for key in keys:
        rate_limit.record_failure(key)


def record_login_success(keys):
    for key in keys:
        rate_limit.record_success(key)


@router.get("/auth/config")
def auth_config():
    with get_conn() as conn:
        needs_setup = not any_users_exist(conn)
    return {"needs_setup": needs_setup, "jellyfin_enabled": jellyfin_settings()["enabled"]}


@router.post("/auth/setup")
def setup(body: SetupRequest, request: Request, response: Response):
    ip = rate_limit.get_client_ip(request)
    key = f"setup:{ip}"
    rate_limit.check_rate_limit(key)
    username = body.username.strip()
    if not username or len(username) > 150:
        rate_limit.record_failure(key)
        raise HTTPException(status_code=400, detail="Username is required and must be 150 characters or fewer")
    if len(body.password) < 8 or len(body.password) > 1024:
        rate_limit.record_failure(key)
        raise HTTPException(status_code=400, detail="Password must be between 8 and 1024 characters")
    with get_conn() as conn:
        if any_users_exist(conn):
            raise HTTPException(status_code=409, detail="Setup already completed")
        cursor = conn.execute("INSERT INTO users(username,password_hash,is_admin) VALUES(?,?,1)", (username, hash_password(body.password)))
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone())
    rate_limit.record_success(key)
    return auth_response(response, user)


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    ip = rate_limit.get_client_ip(request)
    username = validate_credentials(body.username, body.password)
    keys = check_login_limits(ip, username)
    try:
        user = authenticate_local(username, body.password)
    except ValueError as error:
        record_login_failure(keys)
        log_login_attempt(None, username, ip, False, "local")
        raise HTTPException(status_code=401, detail=str(error))
    record_login_success(keys)
    log_login_attempt(user["id"], user["username"], ip, True, "local")
    return auth_response(response, user)


@router.post("/auth/jellyfin/login")
def jellyfin_login(body: LoginRequest, request: Request, response: Response):
    ip = rate_limit.get_client_ip(request)
    username = validate_credentials(body.username, body.password)
    keys = check_login_limits(ip, username, "jellyfin-login")
    try:
        jellyfin_user = authenticate_with_jellyfin(username, body.password)
    except ValueError:
        record_login_failure(keys)
        log_login_attempt(None, username, ip, False, "jellyfin")
        raise HTTPException(status_code=401, detail="Invalid Jellyfin credentials")
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))
    user = get_or_create_jellyfin_linked_user(jellyfin_user)
    record_login_success(keys)
    log_login_attempt(user["id"], user["username"], ip, True, "jellyfin")
    return auth_response(response, user)


@router.post("/auth/logout", status_code=204)
def logout(response: Response):
    secure = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=secure, samesite="lax")

@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request):
    email = body.email.strip()[:320]
    ip = rate_limit.get_client_ip(request)
    ip_key = f"forgot-password-ip:{ip}"
    key = f"forgot-password:{ip}:{email.casefold()}"
    rate_limit.check_rate_limit(key)
    rate_limit.check_rate_limit(ip_key, max_attempts=rate_limit.MAX_IP_ATTEMPTS)
    rate_limit.record_failure(key)
    rate_limit.record_failure(ip_key)
    if email:
        with get_conn() as conn:
            user = conn.execute("SELECT id,username FROM users WHERE email=?", (email,)).fetchone()
            if user and get_setting(conn, "smtp_enabled") == "1":
                token = auth.create_auth_token(conn, user["id"], "reset", ttl_hours=1)
                site_name = get_setting(conn, "site_name") or "uLearn"
                site_url = (get_setting(conn, "site_url") or "").rstrip("/")
                template = get_setting(conn, "template_password_reset") or ""
                link = f"{site_url}/set-password/{token}" if site_url else f"/set-password/{token}"
                text = mailer.render_template(template, {"username": user["username"], "site_name": site_name, "link": link})
                mailer.send_email(email, f"Reset your {site_name} password", text)
    return {"ok": True, "message": "If that email is registered, a reset link has been sent."}


@router.get("/auth/token/{token}")
def check_auth_token(token: str):
    with get_conn() as conn:
        resolved = auth.resolve_auth_token(conn, token)
    if not resolved:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")
    return {"valid": True, "kind": resolved["kind"], "username": resolved["username"]}


@router.post("/auth/token/{token}")
def set_password_via_token(token: str, body: SetPasswordRequest, response: Response):
    if len(body.password) < 8 or len(body.password) > 1024:
        raise HTTPException(status_code=400, detail="Password must be between 8 and 1024 characters")
    with get_conn() as conn:
        resolved = auth.resolve_auth_token(conn, token)
        if not resolved:
            raise HTTPException(status_code=400, detail="This link is invalid or has expired")
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.password), resolved["user_id"]))
        auth.consume_auth_token(conn, token)
        user = conn.execute("SELECT id,username,is_admin FROM users WHERE id=?", (resolved["user_id"],)).fetchone()
    return auth_response(response, dict(user))
