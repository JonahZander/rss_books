from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from rss_kindle.models import Article, ArticleDetail

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=list[Article])
async def list_articles(
    request: Request,
    feed_id: int | None = None,
    limit: int = 200,
) -> list[Article]:
    db = request.app.state.db
    if feed_id is not None:
        query = (
            "SELECT id, feed_id, title, url, summary, published_at, "
            "(full_content IS NOT NULL) AS has_full_content "
            "FROM articles WHERE feed_id = ? "
            "ORDER BY published_at DESC, id DESC LIMIT ?"
        )
        params: tuple = (feed_id, limit)
    else:
        query = (
            "SELECT id, feed_id, title, url, summary, published_at, "
            "(full_content IS NOT NULL) AS has_full_content "
            "FROM articles ORDER BY published_at DESC, id DESC LIMIT ?"
        )
        params = (limit,)
    async with db.connect() as conn:
        cur = await conn.execute(query, params)
        rows = await cur.fetchall()
    return [
        Article.model_validate({**dict(r), "has_full_content": bool(r["has_full_content"])})
        for r in rows
    ]


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: int, request: Request) -> ArticleDetail:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT id, feed_id, title, url, summary, full_content, published_at, "
            "(full_content IS NOT NULL) AS has_full_content "
            "FROM articles WHERE id = ?",
            (article_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")
    return ArticleDetail.model_validate(
        {**dict(row), "has_full_content": bool(row["has_full_content"])}
    )
