"""Administrative users, settings, notifications, backup, and library routes."""
import io
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import auth
import mailer
import notifications
from auth import hash_password, require_admin
from db import get_conn, get_setting, row_to_dict, set_setting
from scanner import scan_all
from schemas import (CourseAccessUpdate, CourseUpdate, CreateMemberRequest, EmailSettingsUpdate,
                     EmailTestRequest, NotificationSettingsUpdate, ResetPasswordRequest,
                     SettingsUpdate, TestJellyfinRequest)

router = APIRouter()
BRANDING_DIR = os.path.join(os.path.dirname(os.environ.get("ULEARN_DB", "/data/ulearn.db")), "branding")

# ---------------------------------------------------------------------------
# Admin — members
# ---------------------------------------------------------------------------

@router.get("/admin/users")
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


@router.post("/admin/users")
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


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current=Depends(require_admin)):
    if user_id == int(current["sub"]):
        raise HTTPException(status_code=400, detail="Can't delete your own account")
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"ok": True}

@router.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, body: ResetPasswordRequest, current=Depends(require_admin)):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.password), user_id))
    return {"ok": True}


@router.get("/admin/users/{user_id}/course-access")
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

@router.put("/admin/users/{user_id}/course-access")
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

@router.get("/admin/settings")
def get_settings(current=Depends(require_admin)):
    with get_conn() as conn:
        return {
            "jellyfin_auth_enabled": get_setting(conn, "jellyfin_auth_enabled") == "1",
            "jellyfin_url": get_setting(conn, "jellyfin_url") or "",
        }

@router.put("/admin/settings")
def update_settings(body: SettingsUpdate, current=Depends(require_admin)):
    if body.jellyfin_auth_enabled and not body.jellyfin_url.strip():
        raise HTTPException(status_code=400, detail="Jellyfin URL is required to enable Jellyfin sign-in")
    with get_conn() as conn:
        set_setting(conn, "jellyfin_auth_enabled", "1" if body.jellyfin_auth_enabled else "0")
        set_setting(conn, "jellyfin_url", body.jellyfin_url.strip())
    return {"ok": True}

@router.post("/admin/settings/test-jellyfin")
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

@router.get("/admin/notifications")
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

@router.put("/admin/notifications")
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


@router.post("/admin/notifications/test")
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

@router.get("/admin/email-settings")
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

@router.put("/admin/email-settings")
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

@router.post("/admin/email-settings/test")
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

@router.get("/admin/login-history")
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

@router.get("/admin/courses")
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

@router.put("/admin/courses/{course_id}")
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

@router.get("/admin/backup")
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

@router.post("/admin/rescan")
def rescan(current=Depends(require_admin)):
    summary = scan_all()
    for course in summary.get("new_courses", []):
        notifications.notify("course_added", {
            "course_title": course["title"],
            "lesson_count": course["lesson_count"],
            "username": current.get("username", ""),
        })
    return summary
