from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from rss_kindle.models import Article, ArticleDetail
from rss_kindle.services.content_extractor import extract_html

router = APIRouter(prefix="/api/articles", tags=["articles"])

ARTICLE_COLUMNS = (
    "id, feed_id, title, url, summary, published_at, read_at, "
    "(full_content IS NOT NULL) AS has_full_content"
)


async def fetch_url_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "rss-kindle-selector/1.0"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


def _to_article(row: object) -> Article:
    data = dict(row)  # type: ignore[call-overload]
    return Article.model_validate({**data, "has_full_content": bool(data["has_full_content"])})


@router.get("", response_model=list[Article])
async def list_articles(
    request: Request,
    feed_id: int | None = None,
    unread: bool = False,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Article]:
    db = request.app.state.db
    clauses: list[str] = []
    params: list[object] = []
    if feed_id is not None:
        clauses.append("feed_id = ?")
        params.append(feed_id)
    if unread:
        clauses.append("read_at IS NULL")
    if q:
        clauses.append("(title LIKE ? OR summary LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])

    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {ARTICLE_COLUMNS} FROM articles {where} "
            "ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = await cur.fetchall()
    return [_to_article(r) for r in rows]


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: int, request: Request) -> ArticleDetail:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {ARTICLE_COLUMNS}, full_content FROM articles WHERE id = ?",
            (article_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")
    return ArticleDetail.model_validate(
        {**dict(row), "has_full_content": bool(row["has_full_content"])}
    )


@router.post("/{article_id}/fetch", response_model=ArticleDetail)
async def fetch_full_content(article_id: int, request: Request) -> ArticleDetail:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute("SELECT url FROM articles WHERE id = ?", (article_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")

    raw = await fetch_url_bytes(row["url"])
    content = extract_html(raw, url=row["url"])
    if not content:
        raise HTTPException(status_code=422, detail="could not extract article content")

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE articles SET full_content = ?, fetched_at = CURRENT_TIMESTAMP WHERE id = ?",
            (content, article_id),
        )
        await conn.commit()

    return await get_article(article_id, request)


async def _set_read(request: Request, article_id: int, read: bool) -> Article:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            "UPDATE articles SET read_at = "
            + ("CURRENT_TIMESTAMP" if read else "NULL")
            + " WHERE id = ?",
            (article_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="article not found")
        await conn.commit()
        cur = await conn.execute(
            f"SELECT {ARTICLE_COLUMNS} FROM articles WHERE id = ?", (article_id,)
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")
    return _to_article(row)


@router.post("/{article_id}/read", response_model=Article)
async def mark_read(article_id: int, request: Request) -> Article:
    return await _set_read(request, article_id, True)


@router.post("/{article_id}/unread", response_model=Article)
async def mark_unread(article_id: int, request: Request) -> Article:
    return await _set_read(request, article_id, False)
