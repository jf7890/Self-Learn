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

from db import init_db, get_conn, row_to_dict, get_setting, set_setting
from auth import (
    hash_password,
    get_current_user,
    require_admin,
)
from scanner import scan_all, COURSES_ROOT
import mailer
import auth
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
from routers.auth_routes import router as auth_router
from routers.branding import router as branding_router
from routers.courses import router as courses_router
from routers.admin import router as admin_router
from services.ranges import RANGE_WINDOW_BYTES, parse_single_range
from schemas import (
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
app.include_router(auth_router)
app.include_router(branding_router)
app.include_router(courses_router)
app.include_router(admin_router)

# Compatibility alias retained for existing helper tests and callers.
_parse_single_range = parse_single_range

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

@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Database check failed: {error}")


# Compatibility aliases retained for helper tests and older imports.
_can_access_course = can_access_course
_require_course_access = require_course_access
_course_id_for_lesson = course_id_for_lesson
_require_lesson_access = require_lesson_access

def _safe_course_path(relative_path: str) -> str:
    return safe_course_path(COURSES_ROOT, relative_path)
