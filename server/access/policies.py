"""Central course and lesson authorization policies."""

import os

from fastapi import HTTPException


def can_access_course(conn, current: dict, course_id: int) -> bool:
    if bool(current.get("is_admin")):
        return conn.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone() is not None
    return conn.execute(
        "SELECT 1 FROM course_access WHERE user_id = ? AND course_id = ?",
        (int(current["sub"]), course_id),
    ).fetchone() is not None


def require_course_access(conn, current: dict, course_id: int):
    # Hide resource existence from unauthorized users.
    if not can_access_course(conn, current, course_id):
        raise HTTPException(status_code=404, detail="Course not found")


def course_id_for_lesson(conn, lesson_id: int):
    row = conn.execute(
        "SELECT s.course_id FROM lessons l JOIN sections s ON s.id = l.section_id WHERE l.id = ?",
        (lesson_id,),
    ).fetchone()
    return row["course_id"] if row else None


def require_lesson_access(conn, current: dict, lesson_id: int):
    course_id = course_id_for_lesson(conn, lesson_id)
    if course_id is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    require_course_access(conn, current, course_id)
    return course_id


def safe_course_path(courses_root: str, relative_path: str) -> str:
    root = os.path.realpath(courses_root)
    candidate = os.path.realpath(os.path.join(root, relative_path))
    if os.path.commonpath((root, candidate)) != root:
        raise HTTPException(status_code=404, detail="File not found")
    return candidate
