"""Pydantic request models for the public API.

Keeping transport validation separate from route handlers makes endpoint modules
smaller while preserving the existing request fields, defaults, and validation.
"""

from pydantic import BaseModel, Field


class BrandingUpdate(BaseModel):
    site_name: str = "uLearn"
    accent_color: str = "#e8a33d"


class SetupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class SetPasswordRequest(BaseModel):
    password: str


class NoteUpdate(BaseModel):
    content_html: str = ""


class DurationUpdate(BaseModel):
    duration_seconds: float


class ProgressUpdate(BaseModel):
    lesson_id: int
    position_seconds: float
    completed: bool = False


class CommentCreate(BaseModel):
    body: str


class CreateMemberRequest(BaseModel):
    username: str
    password: str = ""
    email: str = ""
    send_invite: bool = False
    is_admin: bool = False


class ResetPasswordRequest(BaseModel):
    password: str


class CourseAccessUpdate(BaseModel):
    course_ids: list[int] = Field(default_factory=list)


class SettingsUpdate(BaseModel):
    jellyfin_auth_enabled: bool
    jellyfin_url: str = ""


class TestJellyfinRequest(BaseModel):
    jellyfin_url: str = ""


class NotificationSettingsUpdate(BaseModel):
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    template_course_completed: str = ""
    template_course_added: str = ""


class EmailSettingsUpdate(BaseModel):
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: str = "587"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_from_name: str = "uLearn"
    smtp_use_tls: bool = True
    site_url: str = ""
    template_invite: str = ""
    template_password_reset: str = ""


class EmailTestRequest(BaseModel):
    to_address: str


class CourseUpdate(BaseModel):
    tags: str = ""
    is_featured: bool = False
    is_hidden: bool = False
