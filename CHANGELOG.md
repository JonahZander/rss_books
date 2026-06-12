# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[semver](https://semver.org/).

## [1.1.0] — 2026-06-12

Feed groups & split editions — the
[feed-groups spec](docs/superpowers/specs/2026-06-12-feed-groups-design.md).

### Added

- **Feed groups** (folder model, migration 7): a `groups` table and
  `feeds.group_id`; collapsible sidebar sections with rolled-up unread
  badges, group filtering, inline rename/dissolve (feeds survive), a
  move-to-group picker on every feed row, and a "New group" form
- **Split compiles**: choose *Combined* or *One per group* at compile time
  (remembered locally) — per-group mode presses one edition per group,
  titled `<date> — <Group>`, with the Ungrouped bucket last; the press
  deadline gets the same choice (`deadline_split` in Settings)
- **Group-sectioned TOC**: combined editions section their table of contents
  by group (groups in queue order, Ungrouped last, feed names in bylines);
  per-group editions keep per-feed sections; no groups ⇒ the 1.0 shape
- **OPML folders**: import maps top-level folders to groups (deep nesting
  flattens; existing feeds adopt a folder only while ungrouped — re-import
  is the upgrade path); export nests feeds under their group
- **JSON feed lists**: import/export `{"group name": ["feed url", …]}` with
  `"ungrouped"` reserved (`POST /api/feeds/import-json`,
  `GET /api/feeds/export.json`); titles default to the hostname and adopt
  the feed's own `<title>` on first poll unless renamed
- `GET /api/articles?group_id=` filter (`0` = ungrouped feeds)

### Fixed

- Fetching the full text of articles on bot-walled sites (e.g. openai.com)
  returned an unhandled **500**; it is now a **502** carrying the upstream
  status, and the article keeps its summary + original link. All outbound
  fetches (feeds, articles, images) share one browser-shaped User-Agent —
  with `rss-kindle-selector` kept in the string — so UA-only bot filters
  no longer refuse us
- EPUB filenames are sanitized; titles containing `/` or `:` (possible via
  custom titles, easier via group suffixes) can no longer break the build

### Changed

- `POST /api/digests` returns a **list** of digests (length 1 in combined
  mode); the bundled web client is updated in step

## [1.0.0] — 2026-06-12

The 1.0 release: the full
[v2 spec](docs/superpowers/specs/2026-06-11-rss-kindle-selector-v2-design.md),
milestones M1–M6.

### Added — packaging (M6)

- Single-container deploy: multi-stage `Dockerfile` + `docker-compose.yml`
  with a named `/data` volume; `docker compose up` is the entire story
- Next.js static export served same-origin by the API with an SPA fallback —
  the CORS allowlist and web/API port coupling are gone (dev uses rewrites)
- `/health` reports `{status, version, db}`

### Added — curation UX (M5, v0.6)

- Read state: expanding marks read (toggleable), compiling always marks read,
  unread-only filter (default on), unread counts and dimmed read rows
- Editions page: status, article count, size, delivery history,
  download / send / delete with confirm dialogs
- Settings page: SMTP with a step-by-step Kindle wizard and test email, OPDS
  catalog URL + optional Basic auth, polling, press deadline, retention,
  reading preferences
- Search (`q`), OPML import/export buttons, inline feed rename, per-feed
  refresh, feed error badges
- Toast notifications; motion pass (staggered rows, readout pops, button
  micro-interactions) under `prefers-reduced-motion`; mobile triage via
  tabbed panels; focus-visible outlines and ≥24px hit targets
- `docs/design-language.md`

### Added — always fresh (M4, v0.5)

- In-process asyncio scheduler: due-feed polling with conditional GET
  (ETag/Last-Modified), exponential backoff capped at 24h, feed health
  columns and sidebar badges
- Press deadline: compile-and-deliver the queue daily/weekly at HH:MM
- Daily retention cleanup (default 90 days; queued/pressed articles exempt)
- `PATCH /api/feeds/{id}` (rename, poll interval)

### Added — delivery (M3, v0.4)

- Server-side digest queue (survives reloads, ordered, API-visible)
- Send-to-Kindle email via SMTP (aiosmtplib): per-edition send,
  email-on-ready, 45MB guard, delivery log; works for PocketBook too
- OPDS 1.2 catalog (`/opds`) with optional Basic auth — KOReader,
  Xteink/CrossPoint, Kobo, Boox, Calibre
- Settings store (DB-backed, env-var overrides for SMTP credentials)

### Added — the beautiful EPUB (M2, v0.3)

- Content pipeline stores sanitized HTML (trafilatura 2.x + nh3 allowlist;
  TEI vocabulary normalized) — tables, code blocks, lists, links and images
  survive extraction
- EPUB: Pillow-rendered cover, title page, TOC sectioned by feed, per-article
  byline + reading time + original link, colophon, e-ink stylesheet,
  UTF-8 declarations everywhere
- Image pipeline: download, downscale to 1200px JPEG q75 (PNG when alpha),
  10MB per-article budget, alt text preserved
- Summary fallback with a visible marker when extraction fails

### Added — a repo a stranger can trust (M1, v0.2)

- `PRAGMA user_version` migrations (legacy 0.1 databases adopted in place)
- Digest builds that fail land in `failed` with the error stored and shown
- Poll failures logged and reported (`{inserted, errors}`)
- MIT `LICENSE`, `README`, `CONTRIBUTING`, GitHub Actions CI,
  `example-feeds.opml`, pinned web dependencies

### Changed

- Markdown content storage replaced by sanitized HTML (cached extractions
  are invalidated by migration; articles re-fetch on demand)
- `assert`-based control flow replaced with explicit errors

## [0.1.0] — 2026-04-16

Initial personal build: feed CRUD, on-demand refresh, trafilatura extraction,
hand-picked digests, background EPUB build, download. See the
[v1 spec](docs/superpowers/specs/2026-04-16-rss-kindle-selector-design.md).
