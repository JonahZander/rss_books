from __future__ import annotations

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import HTTPError, RequestException
from fastapi import APIRouter, HTTPException, Request

from rss_kindle.models import Article, ArticleDetail
from rss_kindle.services.content_extractor import extract_html

router = APIRouter(prefix="/api/articles", tags=["articles"])


def article_state_sql(prefix: str = "articles.") -> str:
    """The derived `state` column, computed in ONE place so every Article
    response (list/detail here, the queue in queue.py) agrees.

    `state` layers queue/edition membership and the read flag over the raw row
    so the triage desk can show an article's lifecycle. Precedence, highest
    first: in an edition > queued > seen (read) > new. `prefix` qualifies the
    article's id/read_at for callers that alias the table (e.g. "a.").
    """
    return (
        "CASE "
        f"WHEN EXISTS (SELECT 1 FROM digest_articles da WHERE da.article_id = {prefix}id) "
        "THEN 'in_edition' "
        f"WHEN EXISTS (SELECT 1 FROM digest_queue dq WHERE dq.article_id = {prefix}id) "
        "THEN 'queued' "
        f"WHEN {prefix}read_at IS NOT NULL THEN 'seen' "
        "ELSE 'new' "
        "END AS state"
    )


ARTICLE_COLUMNS = (
    "id, feed_id, title, url, summary, published_at, read_at, "
    "(full_content IS NOT NULL) AS has_full_content, " + article_state_sql()
)


async def fetch_url_bytes(url: str) -> bytes:
    # Modern WAFs fingerprint the TLS handshake (JA3/JA4) and reject any
    # non-browser client regardless of User-Agent, so we impersonate Chrome
    # at the transport layer rather than just spoofing the UA header.
    async with AsyncSession() as session:
        r = await session.get(url, impersonate="chrome", timeout=20, allow_redirects=True)
        r.raise_for_status()
        return r.content


def _to_article(row: object) -> Article:
    data = dict(row)  # type: ignore[call-overload]
    return Article.model_validate({**data, "has_full_content": bool(data["has_full_content"])})


@router.get("", response_model=list[Article])
async def list_articles(
    request: Request,
    feed_id: int | None = None,
    group_id: int | None = None,
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
    if group_id is not None:
        # rowids start at 1, so 0 is reserved to mean "ungrouped feeds"
        if group_id == 0:
            clauses.append("feed_id IN (SELECT id FROM feeds WHERE group_id IS NULL)")
        else:
            clauses.append("feed_id IN (SELECT id FROM feeds WHERE group_id = ?)")
            params.append(group_id)
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

    try:
        raw = await fetch_url_bytes(row["url"])
    except HTTPError as e:
        # bot-walled sites (403/429/…) are an upstream refusal, not our crash.
        # raise_for_status() attaches the response; guard in case it's absent.
        status = e.response.status_code if e.response is not None else "error"
        raise HTTPException(
            status_code=502,
            detail=f"the site returned HTTP {status} — try the original link instead",
        ) from e
    except RequestException as e:
        raise HTTPException(status_code=502, detail=f"fetch failed: {e}") from e
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
