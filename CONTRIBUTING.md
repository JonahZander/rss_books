# Contributing

Thanks for considering a contribution. This is a small, opinionated project —
read the [1.0 release spec](docs/superpowers/specs/2026-06-11-rss-kindle-selector-v2-design.md)
first; it defines what's in scope (and the explicit non-goals: no multi-user,
no AI summaries, no hosted service).

## Dev setup

Requirements: Node 20.19.6, [uv](https://docs.astral.sh/uv/), Python 3.12+.

```bash
npm install          # web workspace
npm run dev:api      # FastAPI on :8765 (uv manages the venv on first run)
npm run dev:web      # Next.js on :3737
```

## Checks

Run these before pushing — CI runs exactly the same set:

```bash
npm run typecheck:web && npm run lint:web && npm run build:web
npm run lint:api && npm run typecheck:api && npm run test:api
```

Run a single backend test:

```bash
uv run --directory services/api --extra dev pytest tests/test_digests.py -q
```

## Conventions

- **Migrations:** every schema change ships as a migration appended to
  `MIGRATIONS` in `services/api/src/rss_kindle/db.py`. Never edit an applied
  migration; never change a table without one.
- **API shapes are mirrored by hand** in `apps/web/lib/api.ts`. If you change a
  Pydantic model in `services/api/src/rss_kindle/models.py`, update the
  TypeScript types in the same PR.
- **Tests:** pytest with `asyncio_mode = "auto"` — plain `async def test_...`,
  no decorators. HTTP is mocked (`unittest.mock.patch` / httpx MockTransport);
  tests never hit the network.
- **Style:** ruff (rules `E,F,W,I,UP,B`, line length 100) and strict-ish mypy
  on the API; eslint + `tsc --noEmit` on the web app. Frontend follows
  [docs/design-language.md](docs/design-language.md) — paper/ink/amber tokens,
  sharp corners, mono eyebrows.
- **Commits:** conventional style (`feat:`, `fix:`, `chore:`, `docs:`...).

## Filing issues

Bug reports with a feed URL that reproduces the problem are gold — extraction
and EPUB rendering issues are usually feed-specific.
