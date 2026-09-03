"""
db.py — SQLite schema + query helpers for uLearn.

Schema:
    users        local accounts (username + password_hash). Optionally
                 linked to a Jellyfin account if Jellyfin sign-in is used.
    settings     single-row runtime config, editable from the admin
                 dashboard (e.g. whether Jellyfin sign-in is enabled)
    courses      one row per top-level course folder
    sections     ordered subfolders within a course (01-Introduction, etc.)
    lessons      ordered trackable items within a section (videos, docs)
    attachments  supplementary files (resources/, exercise files, unnumbered)
    progress     per-user, per-lesson watch state
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("ULEARN_DB", "/data/ulearn.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT,                 -- NULL if account only ever signs in via Jellyfin, or is a pending invite
    email TEXT UNIQUE,                  -- nullable — required for invite/reset emails, optional otherwise
    jellyfin_user_id TEXT UNIQUE,       -- NULL until linked / first Jellyfin sign-in
    is_admin INTEGER DEFAULT 0,
    last_login_at TIMESTAMP,
    last_login_ip TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                 -- 'invite' | 'reset'
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username TEXT NOT NULL,             -- as attempted, kept even if user_id becomes NULL later
    ip_address TEXT,
    success INTEGER NOT NULL,
    method TEXT NOT NULL DEFAULT 'local',   -- 'local' | 'jellyfin'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_login_history_created ON login_history(created_at);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_path TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    thumbnail_path TEXT,
    tags TEXT DEFAULT '',
    is_featured INTEGER DEFAULT 0,
    is_hidden INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    folder_name TEXT NOT NULL,
    title TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    UNIQUE(course_id, folder_name)
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    relative_path TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    media_type TEXT NOT NULL,   -- video | audio | doc | quiz
    duration_seconds REAL,
    size_bytes INTEGER,
    order_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id INTEGER REFERENCES sections(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    relative_path TEXT UNIQUE NOT NULL,
    file_type TEXT,             -- pdf | zip | psd | other
    size_bytes INTEGER
);

CREATE TABLE IF NOT EXISTS subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    language TEXT NOT NULL DEFAULT 'en',
    label TEXT NOT NULL DEFAULT 'English',
    relative_path TEXT UNIQUE NOT NULL   -- original file on disk (.srt or .vtt); served converted to VTT
);

CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    completed INTEGER DEFAULT 0,
    position_seconds REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lesson_notes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    content_html TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS course_access (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, course_id)
);
CREATE INDEX IF NOT EXISTS idx_course_access_course ON course_access(course_id);

CREATE TABLE IF NOT EXISTS note_images (
    name TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_note_images_user ON note_images(user_id);
"""

DEFAULT_SETTINGS = {
    "jellyfin_auth_enabled": "0",
    "jellyfin_url": "",
    "discord_enabled": "0",
    "discord_webhook_url": "",
    "telegram_enabled": "0",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "template_course_completed": "🎉 {username} just completed \"{course_title}\"!",
    "template_course_added": "📚 New course added to the library: \"{course_title}\" ({lesson_count} lessons)",
    "site_name": "Self Learn",
    "accent_color": "#e8a33d",
    "logo_ext": "",
    "favicon_ext": "",
    "smtp_enabled": "0",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from_address": "",
    "smtp_from_name": "uLearn",
    "smtp_use_tls": "1",
    "site_url": "",
    "template_invite": (
        "Hi {username},\n\n"
        "You've been invited to {site_name}. Click the link below to set your password and get started:\n\n"
        "{link}\n\n"
        "This link expires in 48 hours."
    ),
    "template_password_reset": (
        "Hi {username},\n\n"
        "We received a request to reset your password on {site_name}. Click the link below to choose a new one:\n\n"
        "{link}\n\n"
        "This link expires in 1 hour. If you didn't request this, you can ignore this email."
    ),
}


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Record whether ACL existed before applying the schema. On the first
    # ACL-aware startup, grant every existing non-admin user every existing
    # course so upgrades do not unexpectedly lock learners out. Users/courses
    # created later are deny-by-default and must be granted by an admin.
    had_course_access = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='course_access'"
    ).fetchone() is not None
    conn.executescript(SCHEMA)
    _migrate(conn)
    if not had_course_access:
        conn.execute(
            "INSERT OR IGNORE INTO course_access(user_id, course_id) "
            "SELECT u.id, c.id FROM users u CROSS JOIN courses c WHERE u.is_admin = 0"
        )
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def _add_column_if_missing(conn, table: str, column: str, coldef: str):
    """SQLite has no 'ADD COLUMN IF NOT EXISTS', so check PRAGMA table_info
    first. Lets us evolve the schema on an existing DB without requiring a
    reset — safe to call every startup."""
    existing = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def _migrate(conn):
    _add_column_if_missing(conn, "courses", "tags", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "courses", "is_featured", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "courses", "is_hidden", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "users", "email", "TEXT")
    _add_column_if_missing(conn, "users", "last_login_at", "TIMESTAMP")
    _add_column_if_missing(conn, "users", "last_login_ip", "TEXT")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row else None


def get_setting(conn, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn, key: str, value: str):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def any_users_exist(conn) -> bool:
    return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] > 0
