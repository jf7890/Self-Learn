"""Authorized media, attachment, and subtitle delivery."""

import mimetypes
import os
import re

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from access.policies import require_course_access, require_lesson_access, safe_course_path
from auth import get_current_user
from db import get_conn
from scanner import COURSES_ROOT
from services.playback_tickets import issue_playback_ticket, validate_playback_ticket
from services.ranges import RANGE_WINDOW_BYTES, parse_single_range

router = APIRouter()
CHUNK_SIZE = 1024 * 1024
SRT_TIMESTAMP_RE = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


def range_not_satisfiable(file_size: int):
    return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}", "Accept-Ranges": "bytes"})


def srt_to_vtt(srt_text: str) -> str:
    return "WEBVTT\n\n" + SRT_TIMESTAMP_RE.sub(r"\1.\2", srt_text).strip() + "\n"


@router.get("/media/{lesson_id}")
def get_document_media(lesson_id: int, current=Depends(get_current_user)):
    """Compatibility delivery for non-video lessons; video/audio require a ticket."""
    with get_conn() as conn:
        lesson = conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        require_lesson_access(conn, current, lesson_id)
    path = safe_course_path(COURSES_ROOT, lesson["relative_path"])
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if content_type.startswith(("video/", "audio/")):
        raise HTTPException(status_code=403, detail="Playback ticket required")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, media_type=content_type)

@router.post("/media/{lesson_id}/ticket")
def create_media_ticket(
    lesson_id: int,
    current=Depends(get_current_user),
    session_token: str = Cookie(default=None),
):
    if not session_token:
        raise HTTPException(status_code=401, detail="Session cookie required")
    with get_conn() as conn:
        lesson = conn.execute("SELECT id FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        require_lesson_access(conn, current, lesson_id)
    ticket = issue_playback_ticket(current["sub"], lesson_id, session_token)
    return {"url": f"/api/play/{ticket}"}

@router.api_route("/play/{ticket}", methods=["GET", "HEAD"])
def stream_media(
    ticket: str,
    request: Request,
    current=Depends(get_current_user),
    session_token: str = Cookie(default=None),
):
    if not session_token:
        raise HTTPException(status_code=401, detail="Session cookie required")
    record = validate_playback_ticket(ticket, current["sub"], session_token)
    if not record:
        raise HTTPException(status_code=403, detail="Playback link expired or invalid")
    lesson_id = record["lesson_id"]
    with get_conn() as conn:
        lesson = conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        require_lesson_access(conn, current, lesson_id)
    path = safe_course_path(COURSES_ROOT, lesson["relative_path"])
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    size = os.path.getsize(path)
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    common = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    range_header = request.headers.get("range")
    if not range_header:
        if request.method == "HEAD":
            return Response(status_code=200, media_type=content_type, headers={**common, "Content-Length": str(size)})
        return FileResponse(path, media_type=content_type, headers=common)
    byte_range = parse_single_range(range_header, size)
    if byte_range is None:
        return range_not_satisfiable(size)
    start, end = byte_range
    length = end - start + 1
    headers = {**common, "Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(length)}
    if request.method == "HEAD":
        return Response(status_code=206, media_type=content_type, headers=headers)

    def chunks():
        with open(path, "rb") as source:
            source.seek(start)
            remaining = length
            while remaining > 0:
                chunk = source.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    return StreamingResponse(chunks(), status_code=206, media_type=content_type, headers=headers)


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, current=Depends(get_current_user)):
    with get_conn() as conn:
        attachment = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
        if attachment:
            require_course_access(conn, current, attachment["course_id"])
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = safe_course_path(COURSES_ROOT, attachment["relative_path"])
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=attachment["file_name"])


@router.get("/subtitles/{subtitle_id}")
def get_subtitle(subtitle_id: int, current=Depends(get_current_user)):
    with get_conn() as conn:
        subtitle = conn.execute("SELECT * FROM subtitles WHERE id=?", (subtitle_id,)).fetchone()
        if subtitle:
            require_lesson_access(conn, current, subtitle["lesson_id"])
    if not subtitle:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    path = safe_course_path(COURSES_ROOT, subtitle["relative_path"])
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Subtitle file missing on disk")
    with open(path, "r", encoding="utf-8-sig", errors="replace") as source:
        text = source.read()
    if path.lower().endswith(".vtt"):
        vtt = text if text.strip().upper().startswith("WEBVTT") else "WEBVTT\n\n" + text
    else:
        vtt = srt_to_vtt(text)
    return Response(content=vtt, media_type="text/vtt")
