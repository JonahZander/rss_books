from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class FeedCreate(BaseModel):
    url: HttpUrl
    title: str


class Feed(BaseModel):
    id: int
    url: str
    title: str
    site_url: str | None = None
    last_polled: datetime | None = None
    created_at: datetime
    poll_interval_minutes: int = 30
    last_error: str | None = None
    last_error_at: datetime | None = None
    consecutive_failures: int = 0
    unread_count: int = 0
    group_id: int | None = None


class FeedUpdate(BaseModel):
    title: str | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=1)
    group_id: int | None = None


class Group(BaseModel):
    id: int
    name: str
    position: int


class GroupCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class GroupUpdate(BaseModel):
    name: str | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class Article(BaseModel):
    id: int
    feed_id: int
    title: str
    url: str
    summary: str | None = None
    published_at: datetime | None = None
    read_at: datetime | None = None
    has_full_content: bool = False
    # Lifecycle, derived in SQL (see ARTICLE_COLUMNS): new → seen (read) →
    # queued → in_edition. Purely additive; read_at semantics are unchanged.
    state: Literal["new", "seen", "queued", "in_edition"] = "new"


class ArticleDetail(Article):
    full_content: str | None = None


class DigestCreate(BaseModel):
    article_ids: list[int] | None = None
    title: str | None = None
    split: Literal["combined", "per_group"] = "combined"


class QueueUpdate(BaseModel):
    article_ids: list[int]


class AppSettings(BaseModel):
    # Delivery: send-to-Kindle email (also works for PocketBook's gateway)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    send_to: list[str] = []
    email_on_ready: bool = False
    # Delivery: OPDS catalog
    opds_auth_enabled: bool = False
    opds_username: str = ""
    opds_password: str = ""
    # Polling
    poll_enabled: bool = True
    default_poll_minutes: int = Field(default=30, ge=1)
    # Retention
    retention_enabled: bool = True
    retention_days: int = Field(default=90, ge=1)
    # Reading
    mark_read_on_expand: bool = True
    # Press deadline
    deadline_enabled: bool = False
    deadline_type: Literal["daily", "weekly"] = "daily"
    deadline_weekday: int = Field(default=4, ge=0, le=6)  # 0 = Monday
    deadline_time: str = Field(default="06:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    deadline_split: Literal["combined", "per_group"] = "combined"


class Delivery(BaseModel):
    id: int
    digest_id: int
    channel: str
    target: str | None = None
    status: str
    error: str | None = None
    created_at: datetime


class Digest(BaseModel):
    id: int
    title: str
    status: str
    group_name: str | None = None
    epub_path: str | None = None
    error: str | None = None
    size_bytes: int | None = None
    delivered_at: datetime | None = None
    created_at: datetime
    article_count: int = 0
    deliveries: list[Delivery] = []
