"""
main.py — uLearn API

Endpoints:
  POST /auth/login              -> { token, user }
  GET  /courses                 -> list with per-user completion %
  GET  /courses/{id}            -> course detail: sections, lessons, attachments
  GET  /media/{lesson_id}       -> range-request video/audio/doc stream
  GET  /attachments/{id}        -> file download
  POST /progress                -> upsert watch position / completion
  POST /admin/rescan            -> re-walk COURSES_ROOT (admin only)
"""

import os
import sqlite3
import zipfile
import tempfile
import io
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from db import init_db, get_conn, row_to_dict, get_setting, set_setting, any_users_exist
from auth import (
    hash_password,
    authenticate_local,
    authenticate_with_jellyfin,
    get_or_create_jellyfin_linked_user,
    jellyfin_settings,
    issue_token,
    get_current_user,
    require_admin,
)
from scanner import scan_all, COURSES_ROOT
import mailer
import auth
import rate_limit
from access.policies import (
    can_access_course,
    course_id_for_lesson,
    require_course_access,
    require_lesson_access,
    safe_course_path,
)
from routers.comments import router as comments_router
from routers.progress import router as progress_router
from routers.notes import router as notes_router
from routers.media import router as media_router
from services.ranges import RANGE_WINDOW_BYTES, parse_single_range
from schemas import (
    BrandingUpdate,
    SetupRequest,
    LoginRequest,
    ForgotPasswordRequest,
    SetPasswordRequest,
    DurationUpdate,
    CreateMemberRequest,
    ResetPasswordRequest,
    CourseAccessUpdate,
    SettingsUpdate,
    TestJellyfinRequest,
    NotificationSettingsUpdate,
    EmailSettingsUpdate,
    EmailTestRequest,
    CourseUpdate
)

app = FastAPI(title="uLearn API")
app.include_router(progress_router)
app.include_router(comments_router)
app.include_router(notes_router)
app.include_router(media_router)

# Compatibility alias retained for existing helper tests and callers.
_parse_single_range = parse_single_range

BRANDING_DIR = os.path.join(os.path.dirname(os.environ.get("ULEARN_DB", "/data/ulearn.db")), "branding")
ALLOWED_LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/webp": "webp"}
ALLOWED_FAVICON_TYPES = {
    "image/png": "png", "image/svg+xml": "svg", "image/webp": "webp",
    "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico",
}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2MB


def _asset_path(kind: str, ext: str) -> str:
    return os.path.join(BRANDING_DIR, f"{kind}.{ext}")


async def _save_branding_asset(kind: str, file: UploadFile, allowed_types: dict, setting_key: str):
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"{kind.capitalize()} must be one of: {', '.join(sorted(set(allowed_types.values())))}")

    contents = await file.read()
    if len(contents) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail=f"{kind.capitalize()} must be under 2MB")

    os.makedirs(BRANDING_DIR, exist_ok=True)
    with get_conn() as conn:
        old_ext = get_setting(conn, setting_key) or ""

    if old_ext:
        old_path = _asset_path(kind, old_ext)
        if os.path.isfile(old_path):
            os.remove(old_path)

    ext = allowed_types[file.content_type]
    with open(_asset_path(kind, ext), "wb") as f:
        f.write(contents)

    with get_conn() as conn:
        set_setting(conn, setting_key, ext)


def _delete_branding_asset(kind: str, setting_key: str):
    with get_conn() as conn:
        old_ext = get_setting(conn, setting_key) or ""
        if old_ext:
            old_path = _asset_path(kind, old_ext)
            if os.path.isfile(old_path):
                os.remove(old_path)
        set_setting(conn, setting_key, "")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:4173,http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    secret = os.environ.get("SECRET_KEY", "")
    if not secret or secret == "change-me":
        raise RuntimeError(
            "SECRET_KEY is not set (or still the default placeholder). Set a real random "
            "32+ character value via the SECRET_KEY environment variable before starting uLearn."
        )
    init_db()


# ---------------------------------------------------------------------------
# Public: auth config + first-run setup
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """No auth — for uptime monitoring (Uptime Kuma, Docker HEALTHCHECK,
    etc). Actually queries the database rather than just confirming the
    process is alive, since a stuck/corrupted DB is the more likely real
    failure mode for a small self-hosted app like this."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database check failed: {e}")


@app.get("/auth/config")
def auth_config():
    """Tells the login page whether to show setup, and whether to show
    the 'Sign in with Jellyfin' button. No auth required — read-only."""
    with get_conn() as conn:
        needs_setup = not any_users_exist(conn)
    jf = jellyfin_settings()
    return {"needs_setup": needs_setup, "jellyfin_enabled": jf["enabled"]}


# ---------------------------------------------------------------------------
# Public: branding (site name, accent color, logo)
# ---------------------------------------------------------------------------

@app.get("/branding")
def get_branding():
    """No auth — the login and setup screens need this before anyone's
    signed in."""
    with get_conn() as conn:
        site_name = get_setting(conn, "site_name") or "uLearn"
        accent_color = get_setting(conn, "accent_color") or "#e8a33d"
        logo_ext = get_setting(conn, "logo_ext") or ""
        favicon_ext = get_setting(conn, "favicon_ext") or ""
    return {
        "site_name": site_name,
        "accent_color": accent_color,
        "logo_url": "/branding/logo" if logo_ext else None,
        "favicon_url": "/branding/favicon" if favicon_ext else None,
    }


@app.get("/branding/logo")
def get_branding_logo():
    with get_conn() as conn:
        logo_ext = get_setting(conn, "logo_ext") or ""
    if not logo_ext:
        raise HTTPException(status_code=404, detail="No logo uploaded")
    logo_path = _asset_path("logo", logo_ext)
    if not os.path.isfile(logo_path):
        raise HTTPException(status_code=404, detail="Logo file missing on disk")
    media_type = {v: k for k, v in ALLOWED_LOGO_TYPES.items()}.get(logo_ext, "application/octet-stream")
    return FileResponse(logo_path, media_type=media_type)


@app.get("/branding/favicon")
def get_branding_favicon():
    with get_conn() as conn:
        favicon_ext = get_setting(conn, "favicon_ext") or ""
    if not favicon_ext:
        raise HTTPException(status_code=404, detail="No favicon uploaded")
    favicon_path = _asset_path("favicon", favicon_ext)
    if not os.path.isfile(favicon_path):
        raise HTTPException(status_code=404, detail="Favicon file missing on disk")
    media_type = {v: k for k, v in ALLOWED_FAVICON_TYPES.items() if k != "image/vnd.microsoft.icon"}.get(favicon_ext, "application/octet-stream")
    return FileResponse(favicon_path, media_type=media_type)

@app.put("/admin/branding")
def update_branding(body: BrandingUpdate, current=Depends(require_admin)):
    name = body.site_name.strip() or "uLearn"
    color = body.accent_color.strip()
    if not color.startswith("#") or len(color) != 7:
        raise HTTPException(status_code=400, detail="Accent color must be a hex value like #e8a33d")
    with get_conn() as conn:
        set_setting(conn, "site_name", name)
        set_setting(conn, "accent_color", color)
    return {"ok": True}


@app.post("/admin/branding/logo")
async def upload_branding_logo(file: UploadFile = File(...), current=Depends(require_admin)):
    await _save_branding_asset("logo", file, ALLOWED_LOGO_TYPES, "logo_ext")
    return {"ok": True}


@app.delete("/admin/branding/logo")
def delete_branding_logo(current=Depends(require_admin)):
    _delete_branding_asset("logo", "logo_ext")
    return {"ok": True}


@app.post("/admin/branding/favicon")
async def upload_branding_favicon(file: UploadFile = File(...), current=Depends(require_admin)):
    await _save_branding_asset("favicon", file, ALLOWED_FAVICON_TYPES, "favicon_ext")
    return {"ok": True}


@app.delete("/admin/branding/favicon")
def delete_branding_favicon(current=Depends(require_admin)):
    _delete_branding_asset("favicon", "favicon_ext")
    return {"ok": True}

@app.post("/auth/setup")
def setup(body: SetupRequest, request: Request):
    """Creates the first admin account. Locked out once any user exists."""
    key = f"setup:{rate_limit.get_client_ip(request)}"
    rate_limit.check_rate_limit(key)
    with get_conn() as conn:
        if any_users_exist(conn):
            raise HTTPException(status_code=409, detail="Setup already completed")
        if len(body.password) < 8:
            rate_limit.record_failure(key)
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (body.username, hash_password(body.password)),
        )
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())

    rate_limit.record_success(key)
    token = issue_token(user)
    return {"token": token, "user": {"id": user["id"], "username": user["username"], "is_admin": True}}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def _log_login_attempt(user_id, username: str, ip: str, success: bool, method: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO login_history (user_id, username, ip_address, success, method) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, ip, int(success), method),
        )
        if success and user_id:
            conn.execute(
                "UPDATE users SET last_login_at = CURRENT_TIMESTAMP, last_login_ip = ? WHERE id = ?",
                (ip, user_id),
            )
        # opportunistic cleanup — keeps the table from growing unbounded
        # on a long-running instance without needing a scheduled job
        conn.execute("DELETE FROM login_history WHERE created_at < datetime('now', '-90 days')")

@app.post("/auth/login")
def login(body: LoginRequest, request: Request):
    ip = rate_limit.get_client_ip(request)
    key = f"login:{ip}:{body.username.lower()}"
    rate_limit.check_rate_limit(key)

    try:
        user = authenticate_local(body.username, body.password)
    except ValueError as e:
        rate_limit.record_failure(key)
        _log_login_attempt(None, body.username, ip, success=False, method="local")
        raise HTTPException(status_code=401, detail=str(e))

    rate_limit.record_success(key)
    _log_login_attempt(user["id"], user["username"], ip, success=True, method="local")
    token = issue_token(user)
    return {
        "token": token,
        "user": {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])},
    }


@app.post("/auth/jellyfin/login")
def jellyfin_login(body: LoginRequest, request: Request):
    ip = rate_limit.get_client_ip(request)
    key = f"jellyfin-login:{ip}:{body.username.lower()}"
    rate_limit.check_rate_limit(key)

    try:
        jf_user = authenticate_with_jellyfin(body.username, body.password)
    except ValueError:
        rate_limit.record_failure(key)
        _log_login_attempt(None, body.username, ip, success=False, method="jellyfin")
        raise HTTPException(status_code=401, detail="Invalid Jellyfin credentials")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = get_or_create_jellyfin_linked_user(jf_user)
    rate_limit.record_success(key)
    _log_login_attempt(user["id"], user["username"], ip, success=True, method="jellyfin")
    token = issue_token(user)
    return {
        "token": token,
        "user": {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])},
    }


# ---------------------------------------------------------------------------
# Invite / password reset (token-based, no auth required)
# ---------------------------------------------------------------------------

@app.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Always returns the same generic response whether or not the email
    matches an account — an attacker probing for valid emails shouldn't
    be able to tell the difference."""
    email = body.email.strip()
    key = f"forgot-password:{rate_limit.get_client_ip(request)}:{email.lower()}"
    rate_limit.check_rate_limit(key)
    rate_limit.record_failure(key)  # always counts as an "attempt", success or not — see docstring above

    if email:
        with get_conn() as conn:
            user = conn.execute("SELECT id, username FROM users WHERE email = ?", (email,)).fetchone()
            if user and get_setting(conn, "smtp_enabled") == "1":
                token = auth.create_auth_token(conn, user["id"], "reset", ttl_hours=1)
                site_name = get_setting(conn, "site_name") or "uLearn"
                site_url = (get_setting(conn, "site_url") or "").rstrip("/")
                template = get_setting(conn, "template_password_reset") or ""
                link = f"{site_url}/set-password/{token}" if site_url else f"/set-password/{token}"
                body_text = mailer.render_template(template, {"username": user["username"], "site_name": site_name, "link": link})
                mailer.send_email(email, f"Reset your {site_name} password", body_text)
    return {"ok": True, "message": "If that email is registered, a reset link has been sent."}


@app.get("/auth/token/{token}")
def check_auth_token(token: str):
    with get_conn() as conn:
        resolved = auth.resolve_auth_token(conn, token)
    if not resolved:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")
    return {"valid": True, "kind": resolved["kind"], "username": resolved["username"]}

@app.post("/auth/token/{token}")
def set_password_via_token(token: str, body: SetPasswordRequest):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    with get_conn() as conn:
        resolved = auth.resolve_auth_token(conn, token)
        if not resolved:
            raise HTTPException(status_code=400, detail="This link is invalid or has expired")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.password), resolved["user_id"]))
        auth.consume_auth_token(conn, token)
        user = conn.execute("SELECT id, username, is_admin FROM users WHERE id = ?", (resolved["user_id"],)).fetchone()

    jwt_token = issue_token(dict(user))
    return {
        "token": jwt_token,
        "user": {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])},
    }


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

# Compatibility aliases keep endpoint code stable while policy logic lives in
# one independently testable module.
_can_access_course = can_access_course
_require_course_access = require_course_access
_course_id_for_lesson = course_id_for_lesson
_require_lesson_access = require_lesson_access

def _safe_course_path(relative_path: str) -> str:
    return safe_course_path(COURSES_ROOT, relative_path)

def _course_with_stats(conn, course, user_id: int) -> dict:
    total = conn.execute(
        "SELECT COUNT(*) c FROM lessons l JOIN sections s ON l.section_id = s.id "
        "WHERE s.course_id = ?",
        (course["id"],),
    ).fetchone()["c"]
    done = conn.execute(
        "SELECT COUNT(*) c FROM progress p "
        "JOIN lessons l ON p.lesson_id = l.id "
        "JOIN sections s ON l.section_id = s.id "
        "WHERE s.course_id = ? AND p.user_id = ? AND p.completed = 1",
        (course["id"], user_id),
    ).fetchone()["c"]
    item = row_to_dict(course)
    item["lesson_count"] = total
    item["completed_count"] = done
    item["percent_complete"] = round((done / total) * 100) if total else 0
    return item


@app.get("/courses")
def list_courses(current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        courses = conn.execute("SELECT * FROM courses WHERE is_hidden = 0 ORDER BY title").fetchall()
        result = []
        for course in courses:
            item = _course_with_stats(conn, course, user_id)
            item["has_access"] = bool(current.get("is_admin")) or _can_access_course(conn, current, course["id"])
            # Do not expose learner-specific progress for a locked course.
            if not item["has_access"]:
                item["completed_count"] = 0
                item["percent_complete"] = 0
            result.append(item)
        return result


@app.get("/featured")
def featured_courses(current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        courses = conn.execute("SELECT * FROM courses WHERE is_featured = 1 AND is_hidden = 0 ORDER BY added_at DESC").fetchall()
        result = []
        for course in courses:
            item = _course_with_stats(conn, course, user_id)
            item["has_access"] = bool(current.get("is_admin")) or _can_access_course(conn, current, course["id"])
            if not item["has_access"]:
                item["completed_count"] = 0
                item["percent_complete"] = 0
            result.append(item)
        return result


@app.get("/courses/{course_id}")
def get_course(course_id: int, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course or not _can_access_course(conn, current, course_id):
            raise HTTPException(status_code=404, detail="Course not found")

        sections = conn.execute(
            "SELECT * FROM sections WHERE course_id = ? ORDER BY order_index", (course_id,)
        ).fetchall()

        section_list = []
        for section in sections:
            lessons = conn.execute(
                "SELECT l.*, p.completed, p.position_seconds "
                "FROM lessons l "
                "LEFT JOIN progress p ON p.lesson_id = l.id AND p.user_id = ? "
                "WHERE l.section_id = ? ORDER BY l.order_index",
                (user_id, section["id"]),
            ).fetchall()

            attachments = conn.execute(
                "SELECT * FROM attachments WHERE section_id = ?", (section["id"],)
            ).fetchall()

            section_dict = row_to_dict(section)
            section_dict["lessons"] = []
            for lesson in lessons:
                lesson_dict = row_to_dict(lesson)
                subs = conn.execute(
                    "SELECT id, language, label FROM subtitles WHERE lesson_id = ? ORDER BY language",
                    (lesson["id"],),
                ).fetchall()
                lesson_dict["subtitles"] = [row_to_dict(s) for s in subs]
                section_dict["lessons"].append(lesson_dict)
            section_dict["attachments"] = [row_to_dict(a) for a in attachments]
            section_list.append(section_dict)

        course_attachments = conn.execute(
            "SELECT * FROM attachments WHERE course_id = ? AND section_id IS NULL",
            (course_id,),
        ).fetchall()

        result = row_to_dict(course)
        result["sections"] = section_list
        result["attachments"] = [row_to_dict(a) for a in course_attachments]
        return result


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

@app.post("/lessons/{lesson_id}/duration")
def set_lesson_duration(lesson_id: int, body: DurationUpdate, current=Depends(get_current_user)):
    """
    Scanning doesn't probe media files for runtime (no ffprobe dependency),
    so we learn a lesson's real duration the first time someone plays it,
    from the browser's own <video> metadata. Harmless for any authenticated
    user to report — it's just caching a fact about the file, not a
    per-user value.
    """
    if body.duration_seconds <= 0:
        return {"ok": False}
    with get_conn() as conn:
        _require_lesson_access(conn, current, lesson_id)
        conn.execute("UPDATE lessons SET duration_seconds = ? WHERE id = ?", (body.duration_seconds, lesson_id))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin — members
# ---------------------------------------------------------------------------

@app.get("/admin/users")
def list_users(current=Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, email, is_admin, jellyfin_user_id, password_hash, "
            "last_login_at, last_login_ip, created_at FROM users ORDER BY created_at"
        ).fetchall()
        result = []
        for r in rows:
            item = row_to_dict(r)
            item["pending_invite"] = item["password_hash"] is None and item["jellyfin_user_id"] is None
            del item["password_hash"]
            result.append(item)
        return result


@app.post("/admin/users")
def create_user(body: CreateMemberRequest, current=Depends(require_admin)):
    email = body.email.strip()

    if body.send_invite:
        if not email:
            raise HTTPException(status_code=400, detail="Email is required to send an invite")
        with get_conn() as conn:
            if get_setting(conn, "smtp_enabled") != "1":
                raise HTTPException(status_code=400, detail="SMTP isn't configured — set it up under Admin \u2192 Email first")
    elif len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (body.username,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")
        if email:
            existing_email = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing_email:
                raise HTTPException(status_code=409, detail="Email already in use")

        password_hash = None if body.send_invite else hash_password(body.password)
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, email, is_admin) VALUES (?, ?, ?, ?)",
            (body.username, password_hash, email or None, int(body.is_admin)),
        )
        user_id = cur.lastrowid

        if body.send_invite:
            token = auth.create_auth_token(conn, user_id, "invite", ttl_hours=48)
            site_name = get_setting(conn, "site_name") or "uLearn"
            site_url = (get_setting(conn, "site_url") or "").rstrip("/")
            template = get_setting(conn, "template_invite") or ""

        result = row_to_dict(conn.execute("SELECT id, username, email, is_admin, created_at FROM users WHERE id = ?", (user_id,)).fetchone())

    if body.send_invite:
        link = f"{site_url}/set-password/{token}" if site_url else f"/set-password/{token}"
        body_text = mailer.render_template(template, {"username": body.username, "site_name": site_name, "link": link})
        mailer.send_email(email, f"You're invited to {site_name}", body_text)

    return result


@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current=Depends(require_admin)):
    if user_id == int(current["sub"]):
        raise HTTPException(status_code=400, detail="Can't delete your own account")
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"ok": True}

@app.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, body: ResetPasswordRequest, current=Depends(require_admin)):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.password), user_id))
    return {"ok": True}


@app.get("/admin/users/{user_id}/course-access")
def get_user_course_access(user_id: int, current=Depends(require_admin)):
    with get_conn() as conn:
        user = conn.execute("SELECT id, username, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        courses = conn.execute(
            "SELECT c.id, c.title, CASE WHEN a.user_id IS NULL THEN 0 ELSE 1 END AS granted "
            "FROM courses c LEFT JOIN course_access a ON a.course_id=c.id AND a.user_id=? ORDER BY c.title",
            (user_id,),
        ).fetchall()
    return {"user": row_to_dict(user), "courses": [row_to_dict(row) for row in courses]}

@app.put("/admin/users/{user_id}/course-access")
def set_user_course_access(user_id: int, body: CourseAccessUpdate, current=Depends(require_admin)):
    requested = set(body.course_ids)
    with get_conn() as conn:
        user = conn.execute("SELECT id, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["is_admin"]:
            raise HTTPException(status_code=400, detail="Admins already have access to every course")
        valid = {row["id"] for row in conn.execute("SELECT id FROM courses").fetchall()}
        if not requested.issubset(valid):
            raise HTTPException(status_code=400, detail="One or more course IDs are invalid")
        conn.execute("DELETE FROM course_access WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO course_access(user_id, course_id, granted_by) VALUES (?, ?, ?)",
            [(user_id, course_id, int(current["sub"])) for course_id in sorted(requested)],
        )
    return {"ok": True, "course_ids": sorted(requested)}


# ---------------------------------------------------------------------------
# Admin — settings (Jellyfin sign-in toggle + URL)
# ---------------------------------------------------------------------------

@app.get("/admin/settings")
def get_settings(current=Depends(require_admin)):
    with get_conn() as conn:
        return {
            "jellyfin_auth_enabled": get_setting(conn, "jellyfin_auth_enabled") == "1",
            "jellyfin_url": get_setting(conn, "jellyfin_url") or "",
        }

@app.put("/admin/settings")
def update_settings(body: SettingsUpdate, current=Depends(require_admin)):
    if body.jellyfin_auth_enabled and not body.jellyfin_url.strip():
        raise HTTPException(status_code=400, detail="Jellyfin URL is required to enable Jellyfin sign-in")
    with get_conn() as conn:
        set_setting(conn, "jellyfin_auth_enabled", "1" if body.jellyfin_auth_enabled else "0")
        set_setting(conn, "jellyfin_url", body.jellyfin_url.strip())
    return {"ok": True}

@app.post("/admin/settings/test-jellyfin")
def test_jellyfin_connection(body: TestJellyfinRequest, current=Depends(require_admin)):
    import requests
    url = body.jellyfin_url.strip()
    if not url:
        with get_conn() as conn:
            url = get_setting(conn, "jellyfin_url") or ""
    if not url:
        raise HTTPException(status_code=400, detail="Enter a Jellyfin URL first")
    try:
        resp = requests.get(f"{url.rstrip('/')}/System/Info/Public", timeout=5)
        resp.raise_for_status()
        info = resp.json()
        return {"ok": True, "server_name": info.get("ServerName"), "version": info.get("Version")}
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Couldn't reach Jellyfin: {e}")


# ---------------------------------------------------------------------------
# Admin — notifications (Discord/Telegram webhooks + templates)
# ---------------------------------------------------------------------------

@app.get("/admin/notifications")
def get_notification_settings(current=Depends(require_admin)):
    with get_conn() as conn:
        return {
            "discord_enabled": get_setting(conn, "discord_enabled") == "1",
            "discord_webhook_url": get_setting(conn, "discord_webhook_url") or "",
            "telegram_enabled": get_setting(conn, "telegram_enabled") == "1",
            "telegram_bot_token": get_setting(conn, "telegram_bot_token") or "",
            "telegram_chat_id": get_setting(conn, "telegram_chat_id") or "",
            "template_course_completed": get_setting(conn, "template_course_completed") or "",
            "template_course_added": get_setting(conn, "template_course_added") or "",
        }

@app.put("/admin/notifications")
def update_notification_settings(body: NotificationSettingsUpdate, current=Depends(require_admin)):
    if body.discord_enabled and not body.discord_webhook_url.strip():
        raise HTTPException(status_code=400, detail="Discord webhook URL is required to enable Discord notifications")
    if body.telegram_enabled and not (body.telegram_bot_token.strip() and body.telegram_chat_id.strip()):
        raise HTTPException(status_code=400, detail="Bot token and chat ID are required to enable Telegram notifications")
    if not body.template_course_completed.strip():
        raise HTTPException(status_code=400, detail="Course-completed template can't be empty")
    if not body.template_course_added.strip():
        raise HTTPException(status_code=400, detail="Course-added template can't be empty")

    with get_conn() as conn:
        set_setting(conn, "discord_enabled", "1" if body.discord_enabled else "0")
        set_setting(conn, "discord_webhook_url", body.discord_webhook_url.strip())
        set_setting(conn, "telegram_enabled", "1" if body.telegram_enabled else "0")
        set_setting(conn, "telegram_bot_token", body.telegram_bot_token.strip())
        set_setting(conn, "telegram_chat_id", body.telegram_chat_id.strip())
        set_setting(conn, "template_course_completed", body.template_course_completed.strip())
        set_setting(conn, "template_course_added", body.template_course_added.strip())
    return {"ok": True}


@app.post("/admin/notifications/test")
def test_notification(current=Depends(require_admin)):
    with get_conn() as conn:
        discord_enabled = get_setting(conn, "discord_enabled") == "1"
        discord_url = get_setting(conn, "discord_webhook_url") or ""
        telegram_enabled = get_setting(conn, "telegram_enabled") == "1"
        telegram_token = get_setting(conn, "telegram_bot_token") or ""
        telegram_chat_id = get_setting(conn, "telegram_chat_id") or ""
        template = get_setting(conn, "template_course_completed") or ""

    if not discord_enabled and not telegram_enabled:
        raise HTTPException(status_code=400, detail="Enable and save at least one channel first")

    message = notifications.render_template(template, {
        "username": current.get("username", "test-user"),
        "course_title": "Sample Course (test notification)",
        "lesson_count": 12,
    })

    results = {}
    if discord_enabled:
        try:
            notifications._send_discord(discord_url, message)
            results["discord"] = "ok"
        except Exception as e:
            results["discord"] = f"failed: {e}"
    if telegram_enabled:
        try:
            notifications._send_telegram(telegram_token, telegram_chat_id, message)
            results["telegram"] = "ok"
        except Exception as e:
            results["telegram"] = f"failed: {e}"

    if any(v != "ok" for v in results.values()):
        raise HTTPException(status_code=400, detail="; ".join(f"{k}: {v}" for k, v in results.items()))
    return {"ok": True, "results": results}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Admin — email (SMTP settings + invite/reset templates)
# ---------------------------------------------------------------------------

@app.get("/admin/email-settings")
def get_email_settings(current=Depends(require_admin)):
    with get_conn() as conn:
        return {
            "smtp_enabled": get_setting(conn, "smtp_enabled") == "1",
            "smtp_host": get_setting(conn, "smtp_host") or "",
            "smtp_port": get_setting(conn, "smtp_port") or "587",
            "smtp_username": get_setting(conn, "smtp_username") or "",
            "smtp_password": get_setting(conn, "smtp_password") or "",
            "smtp_from_address": get_setting(conn, "smtp_from_address") or "",
            "smtp_from_name": get_setting(conn, "smtp_from_name") or "uLearn",
            "smtp_use_tls": get_setting(conn, "smtp_use_tls") == "1",
            "site_url": get_setting(conn, "site_url") or "",
            "template_invite": get_setting(conn, "template_invite") or "",
            "template_password_reset": get_setting(conn, "template_password_reset") or "",
        }

@app.put("/admin/email-settings")
def update_email_settings(body: EmailSettingsUpdate, current=Depends(require_admin)):
    if body.smtp_enabled and not (body.smtp_host.strip() and body.smtp_from_address.strip()):
        raise HTTPException(status_code=400, detail="SMTP host and from-address are required to enable email")
    if not body.template_invite.strip() or not body.template_password_reset.strip():
        raise HTTPException(status_code=400, detail="Email templates can't be empty")
    try:
        port = int(body.smtp_port)
        if not (1 <= port <= 65535):
            raise ValueError()
    except ValueError:
        raise HTTPException(status_code=400, detail="SMTP port must be a number between 1 and 65535")

    with get_conn() as conn:
        set_setting(conn, "smtp_enabled", "1" if body.smtp_enabled else "0")
        set_setting(conn, "smtp_host", body.smtp_host.strip())
        set_setting(conn, "smtp_port", str(port))
        set_setting(conn, "smtp_username", body.smtp_username.strip())
        set_setting(conn, "smtp_password", body.smtp_password)
        set_setting(conn, "smtp_from_address", body.smtp_from_address.strip())
        set_setting(conn, "smtp_from_name", body.smtp_from_name.strip() or "uLearn")
        set_setting(conn, "smtp_use_tls", "1" if body.smtp_use_tls else "0")
        set_setting(conn, "site_url", body.site_url.strip())
        set_setting(conn, "template_invite", body.template_invite.strip())
        set_setting(conn, "template_password_reset", body.template_password_reset.strip())
    return {"ok": True}

@app.post("/admin/email-settings/test")
def test_email_settings(body: EmailTestRequest, current=Depends(require_admin)):
    if not body.to_address.strip():
        raise HTTPException(status_code=400, detail="Enter an address to send the test to")
    with get_conn() as conn:
        site_name = get_setting(conn, "site_name") or "uLearn"
    try:
        mailer.send_email_raising(
            body.to_address.strip(),
            f"Test email from {site_name}",
            f"If you're reading this, {site_name}'s email settings are working correctly.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}

# ---------------------------------------------------------------------------
# Admin — login history
# ---------------------------------------------------------------------------

@app.get("/admin/login-history")
def get_login_history(current=Depends(require_admin), limit: int = 200):
    limit = max(1, min(limit, 500))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, user_id, username, ip_address, success, method, created_at "
            "FROM login_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


# Admin — courses (featured / hidden / tags)
# ---------------------------------------------------------------------------

@app.get("/admin/courses")
def admin_list_courses(current=Depends(require_admin)):
    """All courses regardless of hidden status, with lesson counts but no
    per-user progress — this is a management index, not a learner view."""
    with get_conn() as conn:
        courses = conn.execute("SELECT * FROM courses ORDER BY title").fetchall()
        result = []
        for course in courses:
            total = conn.execute(
                "SELECT COUNT(*) c FROM lessons l JOIN sections s ON l.section_id = s.id "
                "WHERE s.course_id = ?",
                (course["id"],),
            ).fetchone()["c"]
            item = row_to_dict(course)
            item["lesson_count"] = total
            result.append(item)
        return result

@app.put("/admin/courses/{course_id}")
def admin_update_course(course_id: int, body: CourseUpdate, current=Depends(require_admin)):
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Course not found")
        conn.execute(
            "UPDATE courses SET tags = ?, is_featured = ?, is_hidden = ? WHERE id = ?",
            (body.tags.strip(), int(body.is_featured), int(body.is_hidden), course_id),
        )
    return {"ok": True}


# Admin — backup
# ---------------------------------------------------------------------------

@app.get("/admin/backup")
def download_backup(current=Depends(require_admin)):
    """Zips a consistent snapshot of the database plus branding assets for
    download. Deliberately excludes course files — those live outside
    uLearn's own data (a NAS mount, local disk, wherever) and re-backing
    them up here would duplicate whatever's already backing up that
    storage. This is for the things only uLearn itself holds: accounts,
    progress, settings, comments, branding.
    """
    source_db_path = os.environ.get("ULEARN_DB", "/data/ulearn.db")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Use SQLite's own backup API rather than copying the file directly
        # — safe even if a write happens elsewhere at the same moment,
        # unlike a raw file copy which could grab a half-written state.
        snapshot_path = os.path.join(tmp_dir, "ulearn.db")
        src = sqlite3.connect(source_db_path)
        dst = sqlite3.connect(snapshot_path)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        # Build the zip fully in memory before the temp directory (and the
        # snapshot file inside it) gets cleaned up — a FileResponse pointing
        # at a path inside this `with` block would otherwise try to read a
        # file that's already been deleted by the time it actually streams.
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot_path, arcname="ulearn.db")
            if os.path.isdir(BRANDING_DIR):
                for fname in sorted(os.listdir(BRANDING_DIR)):
                    fpath = os.path.join(BRANDING_DIR, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, arcname=f"branding/{fname}")
        buffer.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"ulearn-backup-{timestamp}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Admin — library
# ---------------------------------------------------------------------------

@app.post("/admin/rescan")
def rescan(current=Depends(require_admin)):
    summary = scan_all()
    for course in summary.get("new_courses", []):
        notifications.notify("course_added", {
            "course_title": course["title"],
            "lesson_count": course["lesson_count"],
            "username": current.get("username", ""),
        })
    return summary
