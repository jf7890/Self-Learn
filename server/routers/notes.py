"""Private per-user lesson notes and note-image endpoints."""

import imghdr
import os
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from access.policies import can_access_course, require_lesson_access
from auth import get_current_user
from db import get_conn, row_to_dict
from schemas import NoteUpdate
from services.note_sanitizer import sanitize_note_html

router = APIRouter()
DATA_DIR = os.path.dirname(os.environ.get("ULEARN_DB", "/data/ulearn.db"))
NOTE_IMAGES_DIR = os.path.join(DATA_DIR, "note-images")
MAX_NOTE_IMAGE_BYTES = 8 * 1024 * 1024


@router.get("/lessons/{lesson_id}/note")
def get_lesson_note(lesson_id: int, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        require_lesson_access(conn, current, lesson_id)
        row = conn.execute("SELECT content_html,updated_at FROM lesson_notes WHERE user_id=? AND lesson_id=?", (user_id, lesson_id)).fetchone()
    return row_to_dict(row) if row else {"content_html": "", "updated_at": None}


@router.put("/lessons/{lesson_id}/note")
def save_lesson_note(lesson_id: int, body: NoteUpdate, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    clean = sanitize_note_html(body.content_html)
    with get_conn() as conn:
        require_lesson_access(conn, current, lesson_id)
        conn.execute(
            "INSERT INTO lesson_notes(user_id,lesson_id,content_html,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(user_id,lesson_id) DO UPDATE SET content_html=excluded.content_html,updated_at=CURRENT_TIMESTAMP",
            (user_id, lesson_id, clean),
        )
        row = conn.execute("SELECT content_html,updated_at FROM lesson_notes WHERE user_id=? AND lesson_id=?", (user_id, lesson_id)).fetchone()
    return row_to_dict(row)


@router.post("/lessons/{lesson_id}/note-images")
async def upload_note_image(lesson_id: int, file: UploadFile = File(...), current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        require_lesson_access(conn, current, lesson_id)
    data = await file.read(MAX_NOTE_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_NOTE_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be between 1 byte and 8 MB")
    extension = {"jpeg": "jpg", "png": "png", "webp": "webp", "gif": "gif"}.get(imghdr.what(None, data))
    if not extension:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, WebP and GIF images are allowed")
    user_dir = os.path.join(NOTE_IMAGES_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    name = f"{uuid.uuid4()}.{extension}"
    with open(os.path.join(user_dir, name), "wb") as output:
        output.write(data)
    with get_conn() as conn:
        conn.execute("INSERT INTO note_images(name,user_id,lesson_id) VALUES(?,?,?)", (name, user_id, lesson_id))
    return {"url": f"/api/notes/images/{name}"}


@router.get("/notes/images/{name}")
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
            "SELECT s.course_id FROM note_images i JOIN lessons l ON l.id=i.lesson_id JOIN sections s ON s.id=l.section_id "
            "WHERE i.user_id=? AND i.name=? UNION SELECT s.course_id FROM lesson_notes n JOIN lessons l ON l.id=n.lesson_id "
            "JOIN sections s ON s.id=l.section_id WHERE n.user_id=? AND instr(n.content_html,?)>0 LIMIT 1",
            (user_id, name, user_id, reference),
        ).fetchone()
        if not row or not can_access_course(conn, current, row["course_id"]):
            raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
