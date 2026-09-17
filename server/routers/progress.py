"""Learner progress, resume, and statistics endpoints."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends

import notifications
from access.policies import require_lesson_access
from auth import get_current_user
from db import get_conn, row_to_dict
from schemas import ProgressUpdate

router = APIRouter()


def compute_streak(date_strings: list[str]) -> int:
    if not date_strings:
        return 0
    dates = set(date_strings)
    cursor = date.today()
    if cursor.isoformat() not in dates:
        cursor -= timedelta(days=1)
        if cursor.isoformat() not in dates:
            return 0
    streak = 0
    while cursor.isoformat() in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def course_fully_complete(conn, course_id: int, user_id: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(l.id) total, SUM(CASE WHEN p.completed = 1 THEN 1 ELSE 0 END) done "
        "FROM lessons l JOIN sections s ON l.section_id = s.id "
        "LEFT JOIN progress p ON p.lesson_id = l.id AND p.user_id = ? "
        "WHERE s.course_id = ?",
        (user_id, course_id),
    ).fetchone()
    return (row["total"] or 0) > 0 and (row["total"] or 0) == (row["done"] or 0)


@router.get("/continue-watching")
def continue_watching(current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT p.position_seconds, p.updated_at, l.id as lesson_id, l.title as lesson_title, "
            "l.duration_seconds, s.title as section_title, c.id as course_id, c.title as course_title "
            "FROM progress p JOIN lessons l ON l.id=p.lesson_id JOIN sections s ON s.id=l.section_id "
            "JOIN courses c ON c.id=s.course_id WHERE p.user_id=? AND p.completed=0 AND p.position_seconds>5 "
            "AND (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=c.id)) "
            "ORDER BY p.updated_at DESC",
            (user_id, int(bool(current.get("is_admin"))), user_id),
        ).fetchall()
    seen, result = set(), []
    for row in rows:
        if row["course_id"] in seen:
            continue
        seen.add(row["course_id"])
        result.append(row_to_dict(row))
        if len(result) >= 8:
            break
    return result


@router.get("/me/stats")
def my_stats(current=Depends(get_current_user)):
    user_id = int(current["sub"])
    admin = int(bool(current.get("is_admin")))
    with get_conn() as conn:
        lessons_completed = conn.execute(
            "SELECT COUNT(*) c FROM progress p JOIN lessons l ON l.id=p.lesson_id JOIN sections s ON s.id=l.section_id "
            "WHERE p.user_id=? AND p.completed=1 AND (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id))",
            (user_id, admin, user_id),
        ).fetchone()["c"]
        courses_completed = conn.execute(
            "SELECT COUNT(*) c FROM (SELECT s.course_id, COUNT(l.id) total, SUM(CASE WHEN p.completed=1 THEN 1 ELSE 0 END) done "
            "FROM lessons l JOIN sections s ON l.section_id=s.id LEFT JOIN progress p ON p.lesson_id=l.id AND p.user_id=? "
            "WHERE (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id)) "
            "GROUP BY s.course_id HAVING total>0 AND total=done)",
            (user_id, admin, user_id),
        ).fetchone()["c"]
        watch_seconds = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(l.duration_seconds,p.position_seconds)),0) s FROM progress p "
            "JOIN lessons l ON l.id=p.lesson_id JOIN sections s ON s.id=l.section_id WHERE p.user_id=? AND p.completed=1 "
            "AND (?=1 OR EXISTS (SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id))",
            (user_id, admin, user_id),
        ).fetchone()["s"]
        user = conn.execute("SELECT created_at FROM users WHERE id=?", (user_id,)).fetchone()
        dates = conn.execute(
            "SELECT DISTINCT DATE(p.updated_at) d FROM progress p JOIN lessons l ON l.id=p.lesson_id "
            "JOIN sections s ON s.id=l.section_id WHERE p.user_id=? AND (?=1 OR EXISTS "
            "(SELECT 1 FROM course_access a WHERE a.user_id=? AND a.course_id=s.course_id)) ORDER BY d DESC",
            (user_id, admin, user_id),
        ).fetchall()
    return {"lessons_completed": lessons_completed, "courses_completed": courses_completed,
            "watch_seconds": watch_seconds, "member_since": user["created_at"] if user else None,
            "streak_days": compute_streak([row["d"] for row in dates])}


@router.post("/progress")
def update_progress(body: ProgressUpdate, current=Depends(get_current_user)):
    user_id = int(current["sub"])
    with get_conn() as conn:
        require_lesson_access(conn, current, body.lesson_id)
        course = None
        was_complete = False
        if body.completed:
            course = conn.execute(
                "SELECT s.course_id,c.title course_title FROM lessons l JOIN sections s ON l.section_id=s.id "
                "JOIN courses c ON c.id=s.course_id WHERE l.id=?", (body.lesson_id,),
            ).fetchone()
            if course:
                was_complete = course_fully_complete(conn, course["course_id"], user_id)
        conn.execute(
            "INSERT INTO progress(user_id,lesson_id,completed,position_seconds) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id,lesson_id) DO UPDATE SET completed=MAX(progress.completed,excluded.completed), "
            "position_seconds=excluded.position_seconds, updated_at=CURRENT_TIMESTAMP",
            (user_id, body.lesson_id, int(body.completed), body.position_seconds),
        )
        if course and not was_complete and course_fully_complete(conn, course["course_id"], user_id):
            notifications.notify("course_completed", {"username": current.get("username", ""), "course_title": course["course_title"]})
    return {"ok": True}
