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


def _strip_required(v: str) -> str:
    """Trim a group name and reject it when nothing is left."""
    v = v.strip()
    if not v:
        raise ValueError("name must not be empty")
    return v


class GroupCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return _strip_required(v)


class GroupUpdate(BaseModel):
    name: str | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        return None if v is None else _strip_required(v)


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


# How <table> markup ships in an edition: "native" keeps HTML tables (best on
# capable readers), "image" pre-renders each sizeable table to a PNG (for
# readers with no CSS table support, e.g. the Xteink X4). Orientation and
# splitting are decided automatically from the profile's screen dimensions:
# tables wider than the portrait budget rotate 90°, taller ones split into
# screen-shaped chunks.
TableMode = Literal["native", "image"]

# How code blocks ship: "native" keeps <pre> (engines with real CSS support);
# "br" bakes the line structure in as <br/> + non-breaking indent; "image"
# rasterizes each block to a PNG for engines that ignore CSS, collapse <pre>
# whitespace AND clip oversized tokens (the Xteink X4 reader needs "image" -
# device testing showed every text-based strategy fails there).
CodeMode = Literal["native", "br", "image"]


class RenderProfile(BaseModel):
    """A named bundle of per-device EPUB rendering options. One compile can
    press one edition per selected profile, so each device gets a book it can
    actually display."""

    name: str
    link_qr: Literal["off", "articles", "all"] = "articles"
    table_mode: TableMode = "native"
    code_mode: CodeMode = "native"
    # Device screen in pixels; when both are set, table/code images are drawn
    # fitted to the screen (auto-rotation, screen-shaped splitting) and photos
    # are recompressed to 2x screen width instead of the global 1200px,
    # capped at PHOTO_WIDTH_CEILING (1600px; see digest_service.py) so an
    # oversized custom screen_width doesn't blow past any current reader.
    screen_width: int | None = Field(default=None, gt=0)
    screen_height: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return _strip_required(v)

    @field_validator("table_mode", mode="before")
    @classmethod
    def _coerce_legacy_rotated(cls, v: object) -> object:
        # profiles stored before auto-rotation carry "image_rotated"
        return "image" if v == "image_rotated" else v

    @property
    def screen(self) -> tuple[int, int] | None:
        if self.screen_width and self.screen_height:
            return (self.screen_width, self.screen_height)
        return None


def default_profiles() -> list[RenderProfile]:
    return [
        RenderProfile(name="Kindle", link_qr="articles", table_mode="native"),
        RenderProfile(
            name="Xteink X4",
            link_qr="articles",
            table_mode="image",
            code_mode="image",
            screen_width=480,
            screen_height=800,
        ),
    ]


class DigestCreate(BaseModel):
    article_ids: list[int] | None = None
    title: str | None = None
    split: Literal["combined", "per_group"] = "combined"
    # Render profile names: one edition per profile (crossed with split mode).
    # None/empty = single edition with the legacy global settings.
    profiles: list[str] | None = None


class QueueUpdate(BaseModel):
    article_ids: list[int]


class QueueLink(BaseModel):
    """Drop an arbitrary URL straight into the queue. The body is fetched at
    compile time like any enqueued article without stored content."""

    url: HttpUrl
    title: str | None = None


class DigestArticlesRemove(BaseModel):
    """Batch removal of edition members. Drops all in one transaction and
    rebuilds the EPUB once, rather than once per article."""

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
    # Inline QR codes for links the e-reader can't tap: "off" leaves links as
    # plain text, "articles" codes each article's own source link, "all" also
    # codes every hyperlink in the body.
    link_qr: Literal["off", "articles", "all"] = "off"
    # Reader fallback: when the direct (impersonating) fetch is blocked or
    # returns nothing, hand the URL to an external extraction service.
    # "none" disables it; "tavily" needs an API key, "jina" is keyless.
    reader_fallback: Literal["none", "tavily", "jina"] = "none"
    tavily_api_key: str = ""
    # Press deadline
    deadline_enabled: bool = False
    deadline_type: Literal["daily", "weekly"] = "daily"
    deadline_weekday: int = Field(default=4, ge=0, le=6)  # 0 = Monday
    deadline_time: str = Field(default="06:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    deadline_split: Literal["combined", "per_group"] = "combined"
    # Profile names the press deadline compiles for; [] = one edition with the
    # legacy global settings (pre-profile behavior).
    deadline_profiles: list[str] = []
    # Device rendering profiles. Editing/removing a profile never rewrites
    # history: digests snapshot the profile name at press time and generation
    # falls back to legacy settings if the name no longer resolves.
    # Name of the render profile the compile UI preselects. "" (or a name that
    # no longer resolves) means "the first profile". The backend never applies
    # this itself: DigestCreate.profiles=None still means legacy settings.
    default_profile: str = ""
    profiles: list[RenderProfile] = Field(default_factory=default_profiles)


class Delivery(BaseModel):
    id: int
    digest_id: int
    channel: str
    target: str | None = None
    status: str
    error: str | None = None
    created_at: datetime


# Edition compilation lifecycle: pending → generating → ready | failed.
DigestStatus = Literal["pending", "generating", "ready", "failed"]


class Digest(BaseModel):
    id: int
    title: str
    status: DigestStatus
    group_name: str | None = None
    # Render-profile name snapshotted at press time (NULL = legacy settings).
    profile: str | None = None
    epub_path: str | None = None
    error: str | None = None
    size_bytes: int | None = None
    delivered_at: datetime | None = None
    created_at: datetime
    article_count: int = 0
    deliveries: list[Delivery] = []


# Compile-time retrieval outcome for an edition member: 'full' (real body),
# 'summary' (fell back to the RSS summary), 'empty' (nothing available). Single
# source of truth shared by the model and digest_service.
FetchStatus = Literal["full", "summary", "empty"]


class DigestArticleEntry(BaseModel):
    """One member of an edition, for the Editions preview. `fetch_status` is the
    compile-time retrieval outcome, None until generated. Bodies load on demand
    via GET /api/articles/{id}."""

    article_id: int
    position: int
    title: str
    url: str
    source: str
    group_name: str | None = None
    has_full_content: bool = False
    fetch_status: FetchStatus | None = None
