"""Authenticated lesson discussion endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from access.policies import require_course_access, require_lesson_access
from auth import get_current_user
from db import get_conn, row_to_dict
from schemas import CommentCreate

router = APIRouter()
COMMENT_MAX_LEN = 2000


@router.get("/lessons/{lesson_id}/comments")
def list_comments(lesson_id: int, current=Depends(get_current_user)):
    with get_conn() as conn:
        require_lesson_access(conn, current, lesson_id)
        rows = conn.execute(
            "SELECT c.id,c.body,c.created_at,c.user_id,u.username,u.is_admin FROM comments c "
            "JOIN users u ON u.id=c.user_id WHERE c.lesson_id=? ORDER BY c.created_at ASC", (lesson_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


@router.post("/lessons/{lesson_id}/comments")
def create_comment(lesson_id: int, body: CommentCreate, current=Depends(get_current_user)):
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment can't be empty")
    if len(text) > COMMENT_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"Comment is too long ({COMMENT_MAX_LEN} character max)")
    user_id = int(current["sub"])
    with get_conn() as conn:
        require_lesson_access(conn, current, lesson_id)
        if not conn.execute("SELECT id FROM lessons WHERE id=?", (lesson_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Lesson not found")
        cursor = conn.execute("INSERT INTO comments(lesson_id,user_id,body) VALUES(?,?,?)", (lesson_id, user_id, text))
        row = conn.execute(
            "SELECT c.id,c.body,c.created_at,c.user_id,u.username,u.is_admin FROM comments c "
            "JOIN users u ON u.id=c.user_id WHERE c.id=?", (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        row = conn.execute(
            "SELECT c.user_id,s.course_id FROM comments c JOIN lessons l ON l.id=c.lesson_id "
            "JOIN sections s ON s.id=l.section_id WHERE c.id=?", (comment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")
        require_course_access(conn, current, row["course_id"])
        if row["user_id"] != user_id and not bool(current.get("is_admin")):
            raise HTTPException(status_code=403, detail="Can't delete someone else's comment")
        conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    return {"ok": True}
