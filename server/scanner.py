"""
scanner.py — walks the courses/ directory and populates courses/sections/
lessons/attachments/subtitles.

Supports four common export shapes:

    courses/
      Photoshop 2021 One-on-One Advanced/          (course)
        01-Introduction/                            (section)
          01-Welcome to Photoshop One-on-One.mp4     (lesson, flat)
          02-Previously on Photoshop One-on-One.mp4
        02-The Advanced Selection Commands/
          01-Color Range Focus Area and more.mp4
          resources/
            exercise-files.zip                       (attachment)

    courses/
      Mr Paid Social - The Ai Ad Alchemists/        (course)
        1.Understanding Andromeda/                   (section)
          3 Setting up your dev environment/          (per-lesson folder)
            3 Setting up your dev environment.mp4       (lesson, nested)
            Setting up your dev environment..html        (skipped snapshot)

    courses/
      Kubernetes Zero to Hero/                      (course, NO subfolders —
        1 - Welcome to Kubernetes Zero to Hero.mp4    lesson files sit
        2 - k8s.txt                                    directly in the
        2 - Kubernetes Architecture Explained.mp4      course root)
        ...

    courses/
      [ WebToolTip.com ] Udemy - AI for Traders/    (course, reseller-tagged
        ~Get Your Files Here !/                       folder name + wrapper
          1 - AI Foundations and Trading Readiness/    subfolder that holds
          2 - Section 2 Prompt Writing/                the REAL numbered
          ...                                          sections)
          Bonus Resources.txt
        Get Bonus Downloads Here.url                  (skipped shortcut)

Rules, applied recursively at every depth beneath a section:
  - .html / .htm / .url files are always skipped entirely — local
    snapshot pages and shortcut files some course platforms/downloaders
    bundle alongside the real content, never real content themselves.
  - video / audio / doc / quiz files are ALWAYS lessons, regardless of
    filename shape or nesting depth — a file being playable content
    matters more than where it sits or how it's named. Ordering prefers
    the file's own numeric prefix, falls back to an enclosing folder's
    numeric prefix, then falls back to stable alphabetical position.
  - .srt / .vtt files are matched against a same-folder video/audio
    lesson by filename (e.g. "3. Introduction.en_US.srt" matches
    "3. Introduction.mp4"), and become a subtitle track on that lesson
    instead of a generic attachment. If no matching lesson exists in the
    same folder, it falls back to being a normal attachment.
  - anything else (zips, exercise files, etc.) is an attachment, tied to
    whichever section it was found under.
  - Numbered folders become sections. An UNNUMBERED folder is checked for
    numbered content inside it — if it has any, it's treated as a
    transparent wrapper (like "~Get Your Files Here !") and looked
    through rather than flattened into attachments, so course tools that
    bury the real section folders one level deep still scan correctly.
    Only an unnumbered folder with no numbered content anywhere inside
    becomes a genuine flat "resources" attachment dump.
  - Loose lesson-eligible files sitting directly in the course root (or
    inside a transparent wrapper folder) get an implicit "Lessons"
    section created for them automatically — otherwise a perfectly valid
    flat course layout would silently end up with zero lessons.
  - Course titles get common reseller/platform noise stripped for
    display — a leading "[ Some Site ]" tag, and a leading known
    platform name like "Udemy - " — without touching the actual folder
    on disk. Rescanning after this changes just updates the stored
    title, no need to touch the files themselves.

Every rescan also prunes DB rows for anything no longer found on disk
(courses, sections, lessons, attachments, subtitles) — see
_cleanup_stale. As a safety net, if the scan finds zero courses at all
but the DB currently has some, cleanup is skipped rather than wiping the
whole library — that shape almost always means a mount/volume problem,
not real deletion.
"""

import os
import re
import json
import subprocess
from db import get_conn

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".aac", ".m4a", ".flac"}
DOC_EXT = {".txt", ".md", ".pdf", ".docx"}
SUBTITLE_EXT = {".srt", ".vtt"}
# Local snapshot pages / shortcut files some course platforms and bulk
# downloaders bundle alongside the real content — never real content.
SKIP_EXT = {".html", ".htm", ".url"}
# Filenames (exact, extension-agnostic, case-insensitive) that are junk
# regardless of format — promotional links back to a reseller's site, not
# real course content. Matched by name rather than extension since these
# show up as .txt, .url, .pdf depending on which tool produced the export.
# Only matches the *exact* unnumbered name, so a real numbered lesson that
# happens to share a word (e.g. "05 - Bonus Resources.mp4") is unaffected.
SKIP_NAME_PATTERNS = {"bonus resources", "get bonus downloads here", "bonus downloads"}
QUIZ_HINTS = ("quiz", "exam", "test")

# Separator can be a dash/dot/underscore OR plain whitespace ("3 Setting up...").
# Also accept common section folders such as "Part1- Introduction" and
# "Part 2 - Ethernet LANs".
NUM_PREFIX_RE = re.compile(r"^(?:(?:part|chap(?:ter)?)\s*)?(\d+)[\s\-._]+(.+)$", re.IGNORECASE)
# A subtitle file's stem may end in a language code before its real
# extension, e.g. "3. Introduction.en_US" (from "3. Introduction.en_US.srt")
# — this strips that suffix to get the stem to match against a video by.
SUBTITLE_LANG_SUFFIX_RE = re.compile(r"^(.+?)\.([a-zA-Z]{2,3}(?:[_-][A-Za-z]{2,4})?)$")
LESSON_AD_SUFFIX_RE = re.compile(r"\s*\(\s*khoahocgiahoi\.com\s+zalo\s+0583953426\s*\)\s*$", re.IGNORECASE)

COURSES_ROOT = os.environ.get("COURSES_ROOT", "/app/courses")

# Sentinel folder_name for the auto-created section that holds lesson files
# found directly in a course's root folder (flat, no-subfolder layout) or
# inside a transparent wrapper folder. Unlikely to collide with any real
# folder name; used as the ON CONFLICT key so rescans reuse the same
# implicit section rather than duplicating it.
ROOT_SECTION_KEY = "__root__"
ROOT_SECTION_TITLE = "Lessons"

# Strips a leading bracketed reseller/attribution tag, e.g. "[ WebToolTip.com ] ".
RESELLER_TAG_RE = re.compile(r"^\s*\[[^\]]*\]\s*")
# Strips a leading known platform name used as a prefix, e.g. "Udemy - ".
PLATFORM_PREFIX_RE = re.compile(
    r"^(udemy|skillshare|coursera|linkedin learning|pluralsight|edx|skool)\s*[-:|]\s*",
    re.IGNORECASE,
)

# Common language codes -> friendly display labels, for the subtitle
# track picker. Falls back to the raw code (uppercased) if not listed —
# still functional, just less pretty.
LANGUAGE_LABELS = {
    "en": "English", "en_us": "English", "en_gb": "English",
    "es": "Spanish", "es_es": "Spanish", "es_mx": "Spanish",
    "fr": "French", "fr_fr": "French",
    "de": "German", "de_de": "German",
    "it": "Italian", "pt": "Portuguese", "pt_br": "Portuguese",
    "nl": "Dutch", "pl": "Polish", "ru": "Russian",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "zh_cn": "Chinese",
    "ar": "Arabic", "hi": "Hindi", "tr": "Turkish", "vi": "Vietnamese",
}


def parse_numeric_prefix(name: str):
    """Returns (order_index, clean_title) or (None, name) if no numeric prefix."""
    match = NUM_PREFIX_RE.match(name)
    if not match:
        return None, name
    return int(match.group(1)), match.group(2)


def clean_lesson_title(file_name: str) -> str:
    stem = os.path.splitext(file_name)[0]
    # Keep the lesson numbering ("Buổi 01", etc.) but remove the reseller
    # advertisement suffix from the display title. The file on disk is untouched.
    return LESSON_AD_SUFFIX_RE.sub("", stem).strip()


def clean_course_title(folder_name: str) -> str:
    """Strips common reseller-tag / platform-prefix noise from a course
    folder name for display, without touching the folder on disk."""
    title = RESELLER_TAG_RE.sub("", folder_name).strip()
    title = PLATFORM_PREFIX_RE.sub("", title).strip()
    return title or folder_name


def is_skipped(file_name: str) -> bool:
    stem, ext = os.path.splitext(file_name.lower())
    if ext in SKIP_EXT:
        return True
    return stem.strip() in SKIP_NAME_PATTERNS


def detect_media_type(file_name: str) -> str:
    stem, ext = os.path.splitext(file_name.lower())
    # Match quiz hints as words, not substrings: "examples" contains "exam"
    # but is still an ordinary video lesson.
    if any(re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", stem) for hint in QUIZ_HINTS):
        return "quiz"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in DOC_EXT:
        return "doc"
    return "other"


def detect_attachment_type(file_name: str) -> str:
    ext = os.path.splitext(file_name.lower())[1].lstrip(".")
    return ext or "other"


def is_subtitle_file(file_name: str) -> bool:
    return os.path.splitext(file_name.lower())[1] in SUBTITLE_EXT


def parse_subtitle_name(file_name: str):
    """Returns (matching_stem, language_code) for a subtitle file, e.g.
    "3. Introduction.en_US.srt" -> ("3. Introduction", "en_US"). If there's
    no recognizable language suffix, the whole stem is the matching stem
    and the language defaults to 'en' (e.g. "Welcome.srt" matches
    "Welcome.mp4" directly)."""
    stem, ext = os.path.splitext(file_name)
    if ext.lower() not in SUBTITLE_EXT:
        return None
    match = SUBTITLE_LANG_SUFFIX_RE.match(stem)
    if match:
        return match.group(1), match.group(2)
    return stem, "en"


def _language_label(code: str) -> str:
    return LANGUAGE_LABELS.get(code.lower().replace("-", "_"), code.upper())


def _has_numbered_content(folder_path: str) -> bool:
    """Quick peek inside a folder: does it contain any numbered subfolder
    or numbered file? Used to tell a transparent wrapper folder (like
    "~Get Your Files Here !", whose real numbered sections live one level
    deeper) apart from a genuine flat "resources" dump full of unordered
    files."""
    try:
        for entry in os.listdir(folder_path):
            if is_skipped(entry):
                continue
            order_index, _ = parse_numeric_prefix(entry)
            if order_index is not None:
                return True
        return False
    except OSError:
        return False


def scan_all():
    """Full rescan of COURSES_ROOT. Safe to re-run — upserts, doesn't duplicate,
    and prunes anything no longer on disk (see module docstring)."""
    if not os.path.isdir(COURSES_ROOT):
        raise FileNotFoundError(f"COURSES_ROOT does not exist: {COURSES_ROOT}")

    summary = {"courses": 0, "sections": 0, "lessons": 0, "attachments": 0,
               "removed_courses": 0, "removed_sections": 0, "removed_lessons": 0,
               "removed_attachments": 0, "removed_subtitles": 0, "cleanup_skipped": False}
    new_courses = []  # [{"title": ..., "lesson_count": ...}] — for notify() in main.py

    seen = {"course_ids": set(), "section_ids": set(), "lesson_ids": set(),
            "attachment_ids": set(), "subtitle_ids": set()}

    with get_conn() as conn:
        existing_course_count = conn.execute("SELECT COUNT(*) c FROM courses").fetchone()["c"]

        for course_folder in sorted(os.listdir(COURSES_ROOT)):
            course_path = os.path.join(COURSES_ROOT, course_folder)
            if not os.path.isdir(course_path):
                continue

            course_id, was_new = _upsert_course(conn, course_folder, course_path)
            seen["course_ids"].add(course_id)
            summary["courses"] += 1

            root_state = {"section_id": None, "fallback": 0, "lesson_count": 0}
            _process_course_entries(conn, course_id, course_path, seen, summary, root_state)

            if was_new:
                new_courses.append({
                    "title": clean_course_title(course_folder),
                    "lesson_count": root_state["lesson_count"],
                })

        if summary["courses"] == 0 and existing_course_count > 0:
            # Found nothing at all, but the library isn't empty — almost
            # certainly a mount/volume problem, not real deletion. Don't
            # wipe everyone's library and progress over what's probably a
            # temporary disconnect.
            summary["cleanup_skipped"] = True
        else:
            removed = _cleanup_stale(conn, seen)
            summary.update(removed)

    summary["new_courses"] = new_courses
    return summary


def _process_course_entries(conn, course_id, folder_path, seen, summary, root_state):
    """Processes one 'course-root-shaped' level: numbered folders become
    sections, unordered folders are either recursed into (if they're a
    transparent wrapper with numbered content inside) or flattened to
    attachments (if they're a genuine flat resources dump), loose
    lesson-eligible files land in a shared implicit section, and loose
    subtitle files get matched against whichever lesson they belong to.

    Called once for the actual course folder, and recursively again for
    any wrapper folder found inside it — root_state is shared across
    those calls so everything ends up in the same implicit section
    regardless of which level it was found at.
    """
    entries = sorted(os.listdir(folder_path))
    subtitle_entries = []
    lesson_stem_map = {}  # this level's own loose lesson files only

    for entry in entries:
        entry_path = os.path.join(folder_path, entry)

        if os.path.isdir(entry_path):
            order_index, title = parse_numeric_prefix(entry)

            if order_index is not None:
                section_id = _upsert_section(conn, course_id, entry, title, order_index)
                seen["section_ids"].add(section_id)
                summary["sections"] += 1
                counters = {"lessons": 0, "attachments": 0, "fallback": 0,
                            "lesson_ids": set(), "attachment_ids": set(), "subtitle_ids": set()}
                _walk_and_scan(conn, course_id, section_id, entry_path, counters)
                summary["lessons"] += counters["lessons"]
                summary["attachments"] += counters["attachments"]
                root_state["lesson_count"] += counters["lessons"]
                seen["lesson_ids"] |= counters["lesson_ids"]
                seen["attachment_ids"] |= counters["attachment_ids"]
                seen["subtitle_ids"] |= counters["subtitle_ids"]
                continue

            if _has_numbered_content(entry_path):
                # Transparent wrapper (e.g. "~Get Your Files Here !") — the
                # real numbered sections live inside it, so process it as
                # if it were the course root itself, one level deeper.
                _process_course_entries(conn, course_id, entry_path, seen, summary, root_state)
            else:
                # Genuine flat resources dump — no numbered content inside,
                # so nothing here has anywhere sensible to be a lesson.
                counters = {"lessons": 0, "attachments": 0, "fallback": 0,
                            "lesson_ids": set(), "attachment_ids": set(), "subtitle_ids": set()}
                _walk_and_scan(conn, course_id, None, entry_path, counters, lessons_allowed=False)
                summary["attachments"] += counters["attachments"]
                seen["attachment_ids"] |= counters["attachment_ids"]
            continue

        # loose file directly at this level
        if is_skipped(entry):
            continue

        if is_subtitle_file(entry):
            subtitle_entries.append(entry)
            continue

        media_type = detect_media_type(entry)
        own_order, _ = parse_numeric_prefix(entry)
        is_forced_lesson = media_type in ("video", "audio", "quiz")
        is_ordered_doc = media_type == "doc" and own_order is not None

        if is_forced_lesson or is_ordered_doc:
            if root_state["section_id"] is None:
                root_state["section_id"] = _upsert_section(conn, course_id, ROOT_SECTION_KEY, ROOT_SECTION_TITLE, -1)
                seen["section_ids"].add(root_state["section_id"])
                summary["sections"] += 1

            if own_order is None:
                root_state["fallback"] += 1
                order_index = 10_000 + root_state["fallback"]
            else:
                order_index = own_order

            lesson_id = _insert_lesson(conn, root_state["section_id"], folder_path, entry, order_index)
            summary["lessons"] += 1
            root_state["lesson_count"] += 1
            seen["lesson_ids"].add(lesson_id)
            lesson_stem_map[os.path.splitext(entry)[0]] = lesson_id
        else:
            att_id = _insert_attachment(conn, course_id, None, folder_path, entry)
            if att_id is not None:
                seen["attachment_ids"].add(att_id)
                summary["attachments"] += 1

    # Second pass: match any subtitle files found at this level against a
    # lesson found at this SAME level (loose lesson files, via the implicit
    # root section). A subtitle can sort alphabetically *before* its video
    # (".en_US.srt" < ".mp4"), so this can't happen in a single forward pass.
    for entry in subtitle_entries:
        matched_stem, lang_code = parse_subtitle_name(entry)
        lesson_id = lesson_stem_map.get(matched_stem)
        if lesson_id is not None:
            sub_id = _upsert_subtitle(conn, lesson_id, lang_code, folder_path, entry)
            seen["subtitle_ids"].add(sub_id)
        else:
            att_id = _insert_attachment(conn, course_id, None, folder_path, entry)
            if att_id is not None:
                seen["attachment_ids"].add(att_id)
                summary["attachments"] += 1


def _cleanup_stale(conn, seen: dict) -> dict:
    def not_in(table, ids):
        if not ids:
            cur = conn.execute(f"DELETE FROM {table}")
        else:
            placeholders = ",".join("?" * len(ids))
            cur = conn.execute(f"DELETE FROM {table} WHERE id NOT IN ({placeholders})", list(ids))
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    # Order matters: deleting a stale course cascades its sections, lessons,
    # attachments, subtitles, and progress; deleting a stale section
    # cascades its lessons/attachments/subtitles/progress; deleting a
    # stale lesson cascades its subtitles/progress. Doing the outer levels
    # first means the later deletes only need to catch items whose parent
    # survived but the item itself didn't (e.g. a single file removed).
    removed_courses = not_in("courses", seen["course_ids"])
    removed_sections = not_in("sections", seen["section_ids"])
    removed_lessons = not_in("lessons", seen["lesson_ids"])
    removed_attachments = not_in("attachments", seen["attachment_ids"])
    removed_subtitles = not_in("subtitles", seen["subtitle_ids"])

    return {
        "removed_courses": removed_courses,
        "removed_sections": removed_sections,
        "removed_lessons": removed_lessons,
        "removed_attachments": removed_attachments,
        "removed_subtitles": removed_subtitles,
    }


def _upsert_course(conn, folder_name: str, folder_path: str):
    """Returns (course_id, was_new) — was_new is True only the first time
    this folder_path is seen, so rescans don't re-notify for it. Stores a
    cleaned display title (reseller tags etc. stripped) while folder_path
    stays the literal, untouched path on disk."""
    existing = conn.execute("SELECT id FROM courses WHERE folder_path = ?", (folder_path,)).fetchone()
    title = clean_course_title(folder_name)
    conn.execute(
        "INSERT INTO courses (folder_path, title) VALUES (?, ?) "
        "ON CONFLICT(folder_path) DO UPDATE SET title = excluded.title",
        (folder_path, title),
    )
    course_id = conn.execute(
        "SELECT id FROM courses WHERE folder_path = ?", (folder_path,)
    ).fetchone()["id"]
    return course_id, existing is None


def _upsert_section(conn, course_id: int, folder_name: str, title: str, order_index: int) -> int:
    conn.execute(
        "INSERT INTO sections (course_id, folder_name, title, order_index) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(course_id, folder_name) DO UPDATE SET title = excluded.title, "
        "order_index = excluded.order_index",
        (course_id, folder_name, title, order_index),
    )
    return conn.execute(
        "SELECT id FROM sections WHERE course_id = ? AND folder_name = ?",
        (course_id, folder_name),
    ).fetchone()["id"]


def _probe_duration(file_path: str):
    """Read container duration without decoding/transcoding media."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", file_path],
            capture_output=True, text=True, timeout=30, check=True,
        )
        value = float(json.loads(result.stdout)["format"]["duration"])
        return value if value > 0 else None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, json.JSONDecodeError):
        return None

def _insert_lesson(conn, section_id: int, dir_path: str, file_name: str, order_index: int) -> int:
    title = clean_lesson_title(file_name)
    media_type = detect_media_type(file_name)
    file_path = os.path.join(dir_path, file_name)
    size_bytes = os.path.getsize(file_path)
    rel_path = os.path.relpath(file_path, COURSES_ROOT)
    existing = conn.execute("SELECT duration_seconds FROM lessons WHERE relative_path = ?", (rel_path,)).fetchone()
    duration = existing["duration_seconds"] if existing and existing["duration_seconds"] else None
    if duration is None and media_type in {"video", "audio"}:
        duration = _probe_duration(file_path)

    conn.execute(
        "INSERT INTO lessons (section_id, file_name, relative_path, title, "
        "media_type, duration_seconds, size_bytes, order_index) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(relative_path) DO UPDATE SET title = excluded.title, "
        "media_type = excluded.media_type, duration_seconds = COALESCE(lessons.duration_seconds, excluded.duration_seconds), "
        "size_bytes = excluded.size_bytes, order_index = excluded.order_index",
        (section_id, file_name, rel_path, title, media_type, duration, size_bytes, order_index),
    )
    return conn.execute("SELECT id FROM lessons WHERE relative_path = ?", (rel_path,)).fetchone()["id"]


def _upsert_subtitle(conn, lesson_id: int, lang_code: str, dir_path: str, file_name: str) -> int:
    rel_path = os.path.relpath(os.path.join(dir_path, file_name), COURSES_ROOT)
    label = _language_label(lang_code)
    conn.execute(
        "INSERT INTO subtitles (lesson_id, language, label, relative_path) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(relative_path) DO UPDATE SET lesson_id = excluded.lesson_id, "
        "language = excluded.language, label = excluded.label",
        (lesson_id, lang_code, label, rel_path),
    )
    return conn.execute("SELECT id FROM subtitles WHERE relative_path = ?", (rel_path,)).fetchone()["id"]


def _walk_and_scan(conn, course_id, section_id, dir_path, counters, inherited_order=None, lessons_allowed=True):
    """
    Recursively walks dir_path (any depth). Video/audio/doc/quiz files become
    lessons (if lessons_allowed — false for course-level unordered folders,
    which have no section to attach a lesson to); subtitle files are matched
    against a lesson found at the SAME directory level; everything else
    becomes an attachment. .html/.htm/.url are skipped entirely at every
    level.

    inherited_order carries a numeric prefix down from an enclosing folder,
    for the "per-lesson subfolder" export pattern where the number lives on
    the folder rather than the file itself.
    """
    entries = sorted(os.listdir(dir_path))
    subtitle_entries = []
    lesson_stem_map = {}  # this directory's own lessons only — subtitles
                           # only match a lesson in the SAME folder

    for entry in entries:
        entry_path = os.path.join(dir_path, entry)

        if is_skipped(entry):
            continue

        if os.path.isdir(entry_path):
            folder_order, _ = parse_numeric_prefix(entry)
            _walk_and_scan(
                conn, course_id, section_id, entry_path, counters,
                inherited_order=folder_order if folder_order is not None else inherited_order,
                lessons_allowed=lessons_allowed,
            )
            continue

        if is_subtitle_file(entry):
            subtitle_entries.append(entry)
            continue

        media_type = detect_media_type(entry)
        own_order, _ = parse_numeric_prefix(entry)

        # Video/audio/quiz are always trackable lessons, regardless of
        # filename shape or nesting depth. Docs (pdf/txt/md/docx) only
        # count as a curriculum lesson if they're explicitly numbered as
        # part of the sequence (own prefix or an inherited folder prefix)
        # — otherwise a folder full of PDFs (a "resources" section) should
        # stay resources, not get force-promoted into fake lessons.
        is_forced_lesson = media_type in ("video", "audio", "quiz")
        is_ordered_doc = media_type == "doc" and (own_order is not None or inherited_order is not None)

        if not lessons_allowed or not (is_forced_lesson or is_ordered_doc):
            att_id = _insert_attachment(conn, course_id, section_id, dir_path, entry)
            if att_id is not None:
                counters["attachments"] += 1
                counters["attachment_ids"].add(att_id)
            continue

        order_index = own_order
        if order_index is None:
            order_index = inherited_order
        if order_index is None:
            counters["fallback"] += 1
            order_index = 10_000 + counters["fallback"]

        lesson_id = _insert_lesson(conn, section_id, dir_path, entry, order_index)
        counters["lessons"] += 1
        counters["lesson_ids"].add(lesson_id)
        lesson_stem_map[os.path.splitext(entry)[0]] = lesson_id

    # Second pass: match subtitles against a lesson found in THIS SAME
    # folder (sorting can put ".en_US.srt" before its ".mp4", so this
    # can't be resolved in the single forward pass above).
    for entry in subtitle_entries:
        matched_stem, lang_code = parse_subtitle_name(entry)
        lesson_id = lesson_stem_map.get(matched_stem)
        if lesson_id is not None and lessons_allowed:
            sub_id = _upsert_subtitle(conn, lesson_id, lang_code, dir_path, entry)
            counters["subtitle_ids"].add(sub_id)
        else:
            att_id = _insert_attachment(conn, course_id, section_id, dir_path, entry)
            if att_id is not None:
                counters["attachments"] += 1
                counters["attachment_ids"].add(att_id)


def _insert_attachment(conn, course_id, section_id, folder_path, file_name):
    file_path = os.path.join(folder_path, file_name)
    if not os.path.isfile(file_path):
        return None
    rel_path = os.path.relpath(file_path, COURSES_ROOT)
    conn.execute(
        "INSERT INTO attachments (course_id, section_id, file_name, relative_path, "
        "file_type, size_bytes) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(relative_path) DO UPDATE SET size_bytes = excluded.size_bytes",
        (
            course_id,
            section_id,
            file_name,
            rel_path,
            detect_attachment_type(file_name),
            os.path.getsize(file_path),
        ),
    )
    return conn.execute("SELECT id FROM attachments WHERE relative_path = ?", (rel_path,)).fetchone()["id"]
