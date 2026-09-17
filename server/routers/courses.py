"""Course catalogue, course detail, and lesson metadata routes."""
from fastapi import APIRouter, Depends, HTTPException
from access.policies import can_access_course, require_lesson_access
from auth import get_current_user
from db import get_conn, row_to_dict
from schemas import DurationUpdate

router = APIRouter()

# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

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


@router.get("/courses")
def list_courses(current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        courses = conn.execute("SELECT * FROM courses WHERE is_hidden = 0 ORDER BY title").fetchall()
        result = []
        for course in courses:
            item = _course_with_stats(conn, course, user_id)
            item["has_access"] = bool(current.get("is_admin")) or can_access_course(conn, current, course["id"])
            # Do not expose learner-specific progress for a locked course.
            if not item["has_access"]:
                item["completed_count"] = 0
                item["percent_complete"] = 0
            result.append(item)
        return result


@router.get("/featured")
def featured_courses(current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        courses = conn.execute("SELECT * FROM courses WHERE is_featured = 1 AND is_hidden = 0 ORDER BY added_at DESC").fetchall()
        result = []
        for course in courses:
            item = _course_with_stats(conn, course, user_id)
            item["has_access"] = bool(current.get("is_admin")) or can_access_course(conn, current, course["id"])
            if not item["has_access"]:
                item["completed_count"] = 0
                item["percent_complete"] = 0
            result.append(item)
        return result


@router.get("/courses/{course_id}")
def get_course(course_id: int, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course or not can_access_course(conn, current, course_id):
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

@router.post("/lessons/{lesson_id}/duration")
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
        require_lesson_access(conn, current, lesson_id)
        conn.execute("UPDATE lessons SET duration_seconds = ? WHERE id = ?", (body.duration_seconds, lesson_id))
    return {"ok": True}


