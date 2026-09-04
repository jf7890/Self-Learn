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
import mimetypes
import re
import sqlite3
import zipfile
import tempfile
import io
import uuid
import imghdr
from html.parser import HTMLParser
from html import escape
from datetime import date, timedelta, datetime
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
import notifications
import mailer
import auth
import rate_limit

app = FastAPI(title="uLearn API")

BRANDING_DIR = os.path.join(os.path.dirname(os.environ.get("ULEARN_DB", "/data/ulearn.db")), "branding")
ALLOWED_LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/webp": "webp"}
ALLOWED_FAVICON_TYPES = {
    "image/png": "png", "image/svg+xml": "svg", "image/webp": "webp",
    "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico",
}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2MB
DATA_DIR = os.path.dirname(os.environ.get("ULEARN_DB", "/data/ulearn.db"))
NOTE_IMAGES_DIR = os.path.join(DATA_DIR, "note-images")
MAX_NOTE_IMAGE_BYTES = 8 * 1024 * 1024

class _NoteSanitizer(HTMLParser):
    """Small allow-list sanitizer for contenteditable notes."""
    allowed = {"p", "div", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "blockquote", "pre", "code", "h1", "h2", "h3", "a", "img", "span", "table", "thead", "tbody", "tr", "th", "td"}
    void = {"br", "img"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed: return
        clean = []
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href", "").startswith(("http://", "https://")):
            clean = [("href", attrs["href"]), ("target", "_blank"), ("rel", "noopener noreferrer")]
        elif tag == "img":
            src = attrs.get("src", "")
            if re.fullmatch(r"/api/notes/images/[a-f0-9-]+\.(?:png|jpe?g|webp|gif)", src):
                width = attrs.get("data-width", "100")
                align = attrs.get("data-align", "left")
                caption = attrs.get("data-caption", "").strip()[:500]
                if width not in {"25", "50", "75", "100"}: width = "100"
                if align not in {"left", "center", "right"}: align = "left"
                clean = [("src", src), ("data-width", width), ("data-align", align)]
                if caption: clean.append(("data-caption", caption))
            else: return
        elif tag in {"p", "h1", "h2", "h3"}:
            align = attrs.get("style", "")
            align_match = re.search(r"text-align:\s*(left|center|right|justify)", align)
            indent = attrs.get("data-indent", "0")
            if indent not in {"1", "2", "3", "4", "5", "6"}: indent = "0"
            if align_match: clean.append(("style", f"text-align:{align_match.group(1)}"))
            if indent != "0": clean.append(("data-indent", indent))
        elif tag == "span":
            match = re.search(r"font-size:\s*(12|15|18|24)px", attrs.get("style", ""))
            if match: clean = [("style", f"font-size:{match.group(1)}px")]
        self.out.append("<" + tag + "".join(f' {k}="{escape(v, quote=True)}"' for k,v in clean) + ">")
    def handle_endtag(self, tag):
        if tag in self.allowed and tag not in self.void: self.out.append(f"</{tag}>")
    def handle_data(self, data): self.out.append(escape(data))

def sanitize_note_html(value: str) -> str:
    if len(value.encode("utf-8")) > 250_000:
        raise HTTPException(status_code=400, detail="Note is too large")
    parser = _NoteSanitizer(); parser.feed(value); parser.close()
    return "".join(parser.out)


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


class BrandingUpdate(BaseModel):
    site_name: str = "uLearn"
    accent_color: str = "#e8a33d"


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


class SetupRequest(BaseModel):
    username: str
    password: str


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


class LoginRequest(BaseModel):
    username: str
    password: str


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

class ForgotPasswordRequest(BaseModel):
    email: str


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


class SetPasswordRequest(BaseModel):
    password: str


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

def _can_access_course(conn, current: dict, course_id: int) -> bool:
    if bool(current.get("is_admin")):
        return conn.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone() is not None
    return conn.execute(
        "SELECT 1 FROM course_access WHERE user_id = ? AND course_id = ?",
        (int(current["sub"]), course_id),
    ).fetchone() is not None

def _require_course_access(conn, current: dict, course_id: int):
    # Deliberately return 404 so an unauthorized user cannot enumerate IDs.
    if not _can_access_course(conn, current, course_id):
        raise HTTPException(status_code=404, detail="Course not found")

def _course_id_for_lesson(conn, lesson_id: int):
    row = conn.execute(
        "SELECT s.course_id FROM lessons l JOIN sections s ON s.id = l.section_id WHERE l.id = ?",
        (lesson_id,),
    ).fetchone()
    return row["course_id"] if row else None

def _require_lesson_access(conn, current: dict, lesson_id: int):
    course_id = _course_id_for_lesson(conn, lesson_id)
    if course_id is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    _require_course_access(conn, current, course_id)
    return course_id

def _safe_course_path(relative_path: str) -> str:
    root = os.path.realpath(COURSES_ROOT)
    candidate = os.path.realpath(os.path.join(root, relative_path))
    if os.path.commonpath((root, candidate)) != root:
        raise HTTPException(status_code=404, detail="File not found")
    return candidate

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
# Private study notes
# ---------------------------------------------------------------------------

class NoteUpdate(BaseModel):
    content_html: str = ""

@app.get("/lessons/{lesson_id}/note")
def get_lesson_note(lesson_id: int, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        _require_lesson_access(conn, current, lesson_id)
        row = conn.execute("SELECT content_html, updated_at FROM lesson_notes WHERE user_id = ? AND lesson_id = ?", (user_id, lesson_id)).fetchone()
    return row_to_dict(row) if row else {"content_html": "", "updated_at": None}

@app.put("/lessons/{lesson_id}/note")
def save_lesson_note(lesson_id: int, body: NoteUpdate, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    clean = sanitize_note_html(body.content_html)
    with get_conn() as conn:
        _require_lesson_access(conn, current, lesson_id)
        conn.execute("INSERT INTO lesson_notes(user_id, lesson_id, content_html, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(user_id, lesson_id) DO UPDATE SET content_html=excluded.content_html, updated_at=CURRENT_TIMESTAMP", (user_id, lesson_id, clean))
        row = conn.execute("SELECT content_html, updated_at FROM lesson_notes WHERE user_id = ? AND lesson_id = ?", (user_id, lesson_id)).fetchone()
    return row_to_dict(row)

@app.post("/lessons/{lesson_id}/note-images")
async def upload_note_image(lesson_id: int, file: UploadFile = File(...), current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        _require_lesson_access(conn, current, lesson_id)
    data = await file.read(MAX_NOTE_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_NOTE_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be between 1 byte and 8 MB")
    detected = imghdr.what(None, data)
    ext = {"jpeg": "jpg", "png": "png", "webp": "webp", "gif": "gif"}.get(detected)
    if not ext:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, WebP and GIF images are allowed")
    user_dir = os.path.join(NOTE_IMAGES_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    name = f"{uuid.uuid4()}.{ext}"
    with open(os.path.join(user_dir, name), "wb") as out:
        out.write(data)
    with get_conn() as conn:
        conn.execute("INSERT INTO note_images(name, user_id, lesson_id) VALUES (?, ?, ?)", (name, user_id, lesson_id))
    return {"url": f"/api/notes/images/{name}"}

@app.get("/notes/images/{name}")
def serve_note_image(name: str, current=Depends(get_current_user)):
    if not re.fullmatch(r"[a-f0-9-]+\.(?:png|jpe?g|webp|gif)", name):
        raise HTTPException(status_code=404, detail="Image not found")
    user_id = int(current["sub"])
    path = os.path.join(NOTE_IMAGES_DIR, str(user_id), name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Image not found")
    with get_conn() as conn:
        reference = f"/api/notes/images/{name}"
        row = conn.execute(
            "SELECT s.course_id FROM note_images i JOIN lessons l ON l.id=i.lesson_id "
            "JOIN sections s ON s.id=l.section_id WHERE i.user_id=? AND i.name=? "
            "UNION SELECT s.course_id FROM lesson_notes n JOIN lessons l ON l.id=n.lesson_id "
            "JOIN sections s ON s.id=l.section_id WHERE n.user_id=? AND instr(n.content_html, ?) > 0 LIMIT 1",
            (user_id, name, user_id, reference),
        ).fetchone()
        if not row or not _can_access_course(conn, current, row["course_id"]):
            raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})

# ---------------------------------------------------------------------------
# Media streaming (range-request aware — required for video seek to work)
# ---------------------------------------------------------------------------

CHUNK_SIZE = 1024 * 1024  # 1MB read chunks
RANGE_WINDOW_BYTES = 8 * 1024 * 1024  # balance ahead-buffering with reliable Vite/Cloudflare responses

def _range_not_satisfiable(file_size: int):
    return Response(status_code=416, headers={
        "Content-Range": f"bytes */{file_size}",
        "Accept-Ranges": "bytes",
    })

def _parse_single_range(value: str, file_size: int):
    # RFC 7233 single byte range only. Browsers do not need multipart ranges.
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or file_size <= 0:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if len(first) > 20 or len(last) > 20:
        return None
    if not first:  # suffix range: bytes=-500
        suffix = int(last)
        if suffix <= 0:
            return None
        start = max(0, file_size - suffix)
        return start, file_size - 1
    start = int(first)
    if start >= file_size:
        return None
    end = int(last) if last else min(start + RANGE_WINDOW_BYTES - 1, file_size - 1)
    if end < start:
        return None
    return start, min(end, file_size - 1)

@app.api_route("/media/{lesson_id}", methods=["GET", "HEAD"])
def stream_media(lesson_id: int, request: Request, current=Depends(get_current_user)):
    with get_conn() as conn:
        lesson = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        _require_lesson_access(conn, current, lesson_id)

    file_path = _safe_course_path(lesson["relative_path"])
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File missing on disk")

    file_size = os.path.getsize(file_path)
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    common = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    range_header = request.headers.get("range")
    if not range_header:
        if request.method == "HEAD":
            return Response(status_code=200, media_type=content_type, headers={**common, "Content-Length": str(file_size)})
        return FileResponse(file_path, media_type=content_type, headers=common)

    byte_range = _parse_single_range(range_header, file_size)
    if byte_range is None:
        return _range_not_satisfiable(file_size)
    start, end = byte_range
    length = end - start + 1
    headers = {**common, "Content-Range": f"bytes {start}-{end}/{file_size}", "Content-Length": str(length)}
    if request.method == "HEAD":
        return Response(status_code=206, media_type=content_type, headers=headers)

    def iter_chunk():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    return StreamingResponse(iter_chunk(), status_code=206, media_type=content_type, headers=headers)

@app.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, current=Depends(get_current_user)):
    with get_conn() as conn:
        att = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if att:
            _require_course_access(conn, current, att["course_id"])
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = _safe_course_path(att["relative_path"])
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(file_path, filename=att["file_name"])


SRT_TIMESTAMP_RE = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


def _srt_to_vtt(srt_text: str) -> str:
    """Converts SRT subtitle text to WebVTT — the format browsers actually
    support natively via <track>, unlike raw SRT. For standard SRT the
    only real differences are the timestamp decimal separator (comma vs
    period) and the required WEBVTT header line."""
    body = SRT_TIMESTAMP_RE.sub(r"\1.\2", srt_text)
    return "WEBVTT\n\n" + body.strip() + "\n"


@app.get("/subtitles/{subtitle_id}")
def get_subtitle(subtitle_id: int, current=Depends(get_current_user)):
    """Always returns WebVTT regardless of the source format on disk (SRT
    is converted on the fly), since that's the only subtitle format
    browsers support in a <track> element."""
    with get_conn() as conn:
        sub = conn.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
        if sub:
            _require_lesson_access(conn, current, sub["lesson_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    file_path = _safe_course_path(sub["relative_path"])
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Subtitle file missing on disk")

    # utf-8-sig transparently strips a BOM if present — common in
    # subtitle files exported from Windows-based tools.
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        raw_text = f.read()

    if file_path.lower().endswith(".vtt"):
        vtt_text = raw_text if raw_text.strip().upper().startswith("WEBVTT") else "WEBVTT\n\n" + raw_text
    else:
        vtt_text = _srt_to_vtt(raw_text)

    return Response(content=vtt_text, media_type="text/vtt")


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

class DurationUpdate(BaseModel):
    duration_seconds: float


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
# Continue watching
# ---------------------------------------------------------------------------

@app.get("/continue-watching")
def continue_watching(current=Depends(get_current_user)):
    """Most recently touched, not-yet-completed lesson per course — powers
    a Netflix-style resume row. Deliberately one card per course, not one
    per in-progress lesson, so starting several lessons in the same course
    doesn't crowd the row with duplicates of that course."""
    user_id = int(current["sub"])
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT p.position_seconds, p.updated_at, "
            "l.id as lesson_id, l.title as lesson_title, l.duration_seconds, "
            "s.title as section_title, c.id as course_id, c.title as course_title "
            "FROM progress p "
            "JOIN lessons l ON l.id = p.lesson_id "
            "JOIN sections s ON s.id = l.section_id "
            "JOIN courses c ON c.id = s.course_id "
            "WHERE p.user_id = ? AND p.completed = 0 AND p.position_seconds > 5 "
            "AND (? = 1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id = ? AND a.course_id = c.id)) "
            "ORDER BY p.updated_at DESC",
            (user_id, int(bool(current.get("is_admin"))), user_id),
        ).fetchall()

        seen_courses = set()
        deduped = []
        for row in rows:
            if row["course_id"] in seen_courses:
                continue
            seen_courses.add(row["course_id"])
            deduped.append(row_to_dict(row))
            if len(deduped) >= 8:
                break

        return deduped


def _compute_streak(date_strings: list) -> int:
    """Consecutive days of activity, counting backward from today. Today
    without activity yet doesn't break a streak that was active yesterday
    — otherwise everyone's streak would show 0 first thing each morning."""
    if not date_strings:
        return 0
    dates = set(date_strings)
    today = date.today()
    cursor = today
    if today.isoformat() not in dates:
        cursor = today - timedelta(days=1)
        if cursor.isoformat() not in dates:
            return 0
    streak = 0
    while cursor.isoformat() in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@app.get("/me/stats")
def my_stats(current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        lessons_completed = conn.execute(
            "SELECT COUNT(*) c FROM progress p JOIN lessons l ON l.id=p.lesson_id JOIN sections s ON s.id=l.section_id "
            "WHERE p.user_id = ? AND p.completed = 1 AND (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id))",
            (user_id, int(bool(current.get("is_admin"))), user_id)
        ).fetchone()["c"]

        courses_completed = conn.execute(
            "SELECT COUNT(*) c FROM ("
            "  SELECT s.course_id, COUNT(l.id) total, "
            "         SUM(CASE WHEN p.completed = 1 THEN 1 ELSE 0 END) done "
            "  FROM lessons l "
            "  JOIN sections s ON l.section_id = s.id "
            "  LEFT JOIN progress p ON p.lesson_id = l.id AND p.user_id = ? "
            "  WHERE (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id)) "
            "  GROUP BY s.course_id "
            "  HAVING total > 0 AND total = done"
            ")",
            (user_id, int(bool(current.get("is_admin"))), user_id),
        ).fetchone()["c"]

        watch_seconds = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(l.duration_seconds, p.position_seconds)), 0) s "
            "FROM progress p JOIN lessons l ON l.id = p.lesson_id JOIN sections s ON s.id=l.section_id "
            "WHERE p.user_id = ? AND p.completed = 1 "
            "AND (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id))",
            (user_id, int(bool(current.get("is_admin"))), user_id),
        ).fetchone()["s"]

        user_row = conn.execute("SELECT created_at FROM users WHERE id = ?", (user_id,)).fetchone()

        date_rows = conn.execute(
            "SELECT DISTINCT DATE(p.updated_at) d FROM progress p JOIN lessons l ON l.id=p.lesson_id "
            "JOIN sections s ON s.id=l.section_id WHERE p.user_id = ? "
            "AND (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id)) ORDER BY d DESC",
            (user_id, int(bool(current.get("is_admin"))), user_id),
        ).fetchall()

    return {
        "lessons_completed": lessons_completed,
        "courses_completed": courses_completed,
        "watch_seconds": watch_seconds,
        "member_since": user_row["created_at"] if user_row else None,
        "streak_days": _compute_streak([r["d"] for r in date_rows]),
    }


def _course_fully_complete(conn, course_id: int, user_id: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(l.id) total, SUM(CASE WHEN p.completed = 1 THEN 1 ELSE 0 END) done "
        "FROM lessons l JOIN sections s ON l.section_id = s.id "
        "LEFT JOIN progress p ON p.lesson_id = l.id AND p.user_id = ? "
        "WHERE s.course_id = ?",
        (user_id, course_id),
    ).fetchone()
    total = row["total"] or 0
    done = row["done"] or 0
    return total > 0 and total == done


class ProgressUpdate(BaseModel):
    lesson_id: int
    position_seconds: float
    completed: bool = False


@app.post("/progress")
def update_progress(body: ProgressUpdate, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        _require_lesson_access(conn, current, body.lesson_id)
        course_row = None
        was_complete_before = False
        if body.completed:
            course_row = conn.execute(
                "SELECT s.course_id, c.title as course_title FROM lessons l "
                "JOIN sections s ON l.section_id = s.id "
                "JOIN courses c ON c.id = s.course_id "
                "WHERE l.id = ?",
                (body.lesson_id,),
            ).fetchone()
            if course_row:
                was_complete_before = _course_fully_complete(conn, course_row["course_id"], user_id)

        conn.execute(
            "INSERT INTO progress (user_id, lesson_id, completed, position_seconds) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, lesson_id) DO UPDATE SET "
            "completed = MAX(progress.completed, excluded.completed), "
            "position_seconds = excluded.position_seconds, "
            "updated_at = CURRENT_TIMESTAMP",
            (user_id, body.lesson_id, int(body.completed), body.position_seconds),
        )

        if course_row and not was_complete_before:
            if _course_fully_complete(conn, course_row["course_id"], user_id):
                notifications.notify("course_completed", {
                    "username": current.get("username", ""),
                    "course_title": course_row["course_title"],
                })
    return {"ok": True}


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

COMMENT_MAX_LEN = 2000


class CommentCreate(BaseModel):
    body: str


@app.get("/lessons/{lesson_id}/comments")
def list_comments(lesson_id: int, current=Depends(get_current_user)):
    with get_conn() as conn:
        _require_lesson_access(conn, current, lesson_id)
        rows = conn.execute(
            "SELECT c.id, c.body, c.created_at, c.user_id, u.username, u.is_admin "
            "FROM comments c JOIN users u ON u.id = c.user_id "
            "WHERE c.lesson_id = ? ORDER BY c.created_at ASC",
            (lesson_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


@app.post("/lessons/{lesson_id}/comments")
def create_comment(lesson_id: int, body: CommentCreate, current=Depends(get_current_user)):
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment can't be empty")
    if len(text) > COMMENT_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"Comment is too long ({COMMENT_MAX_LEN} character max)")

    user_id = int(current["sub"])
    with get_conn() as conn:
        _require_lesson_access(conn, current, lesson_id)
        lesson = conn.execute("SELECT id FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")

        cur = conn.execute(
            "INSERT INTO comments (lesson_id, user_id, body) VALUES (?, ?, ?)",
            (lesson_id, user_id, text),
        )
        row = conn.execute(
            "SELECT c.id, c.body, c.created_at, c.user_id, u.username, u.is_admin "
            "FROM comments c JOIN users u ON u.id = c.user_id WHERE c.id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return row_to_dict(row)


@app.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    is_admin = bool(current.get("is_admin"))
    with get_conn() as conn:
        row = conn.execute(
            "SELECT c.user_id, s.course_id FROM comments c JOIN lessons l ON l.id=c.lesson_id "
            "JOIN sections s ON s.id=l.section_id WHERE c.id = ?", (comment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")
        _require_course_access(conn, current, row["course_id"])
        if row["user_id"] != user_id and not is_admin:
            raise HTTPException(status_code=403, detail="Can't delete someone else's comment")
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin — members
# ---------------------------------------------------------------------------

class CreateMemberRequest(BaseModel):
    username: str
    password: str = ""
    email: str = ""
    send_invite: bool = False
    is_admin: bool = False


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


class ResetPasswordRequest(BaseModel):
    password: str


@app.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, body: ResetPasswordRequest, current=Depends(require_admin)):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.password), user_id))
    return {"ok": True}

class CourseAccessUpdate(BaseModel):
    course_ids: list[int] = []

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


class SettingsUpdate(BaseModel):
    jellyfin_auth_enabled: bool
    jellyfin_url: str = ""


@app.put("/admin/settings")
def update_settings(body: SettingsUpdate, current=Depends(require_admin)):
    if body.jellyfin_auth_enabled and not body.jellyfin_url.strip():
        raise HTTPException(status_code=400, detail="Jellyfin URL is required to enable Jellyfin sign-in")
    with get_conn() as conn:
        set_setting(conn, "jellyfin_auth_enabled", "1" if body.jellyfin_auth_enabled else "0")
        set_setting(conn, "jellyfin_url", body.jellyfin_url.strip())
    return {"ok": True}


class TestJellyfinRequest(BaseModel):
    jellyfin_url: str = ""


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


class NotificationSettingsUpdate(BaseModel):
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    template_course_completed: str = ""
    template_course_added: str = ""


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


class EmailSettingsUpdate(BaseModel):
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: str = "587"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_from_name: str = "uLearn"
    smtp_use_tls: bool = True
    site_url: str = ""
    template_invite: str = ""
    template_password_reset: str = ""


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


class EmailTestRequest(BaseModel):
    to_address: str


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


class CourseUpdate(BaseModel):
    tags: str = ""
    is_featured: bool = False
    is_hidden: bool = False


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
