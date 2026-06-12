from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, HttpUrl


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


class Article(BaseModel):
    id: int
    feed_id: int
    title: str
    url: str
    summary: str | None = None
    published_at: datetime | None = None
    has_full_content: bool = False


class ArticleDetail(Article):
    full_content: str | None = None


class DigestCreate(BaseModel):
    article_ids: list[int]
    title: str | None = None


class Digest(BaseModel):
    id: int
    title: str
    status: str
    epub_path: str | None = None
    error: str | None = None
    created_at: datetime
