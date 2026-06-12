# ── Stage 1: build the static web app ─────────────────────────────
FROM node:20.19.6-slim AS web
WORKDIR /build
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web apps/web
ENV STATIC_EXPORT=1
RUN npm run build:web

# ── Stage 2: API runtime + static assets ──────────────────────────
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY services/api/pyproject.toml services/api/uv.lock ./
# dependencies first for layer caching; the project itself comes next
RUN uv sync --frozen --no-dev --no-install-project
COPY services/api .
RUN uv sync --frozen --no-dev

COPY --from=web /build/apps/web/out /app/static

ENV DB_PATH=/data/rss_kindle.db \
    EPUB_DIR=/data/epubs \
    STATIC_DIR=/app/static \
    PATH="/app/.venv/bin:$PATH"

VOLUME /data
EXPOSE 8765

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if b'ok' in urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4).read() else 1)"

CMD ["uvicorn", "rss_kindle.api.main:app", "--host", "0.0.0.0", "--port", "8765"]
