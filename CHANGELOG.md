# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[semver](https://semver.org/).

## [Unreleased]

The near-term polish backlog: hardening, triage-desk ergonomics, and a
first-run path.

### Added

- **First-run checklist** on the triage desk: a dismissible "First edition"
  card walks a fresh install through adding a feed, queuing an article,
  compiling, and setting up delivery; it tracks real state and disappears
  once the desk is running (or when dismissed).
- **Mark seen / mark unseen** per article, plus a **"Mark all seen"** action
  scoped to the current feed or group filter
  (`POST /api/articles/mark-all-read`); the button is disabled while a search
  is active, since the bulk action ignores search terms.
- **Queue reordering**: move queued articles up/down; the order is the
  edition's article order (persisted via the existing `PUT /api/queue`).
- **Per-feed poll interval** control in the sidebar (presets or a custom
  number of minutes; "Default" copies the current global default).
- **Feed error details on tap**: the error badge now opens an inline panel
  with the full fetch error, failure count, and a *Retry now* button.
- **"View edition →"** link on freshly compiled editions, deep-linking to the
  Editions page with that edition's review panel open
  (`/editions?open=<id>`).
- **Import skip reporting**: OPML/JSON feed imports list exactly which URLs
  were skipped and why (duplicate, invalid URL) instead of a bare count.
- **epubcheck CI gate**: CI now builds a fixture edition (tables, code,
  images, unicode, cover) and validates it with epubcheck 5.3.0; the test
  self-skips locally unless `EPUBCHECK_JAR` is set.

### Changed

- **SSRF guard on outbound fetches** (feeds, article pages, images), enabled
  by default: private, loopback, link-local, and otherwise reserved addresses
  are refused, including via DNS and redirects. LAN-hosted feeds need an
  explicit `SSRF_ALLOWED_HOSTS` allowlist entry (hostnames, IPs, or CIDRs);
  `SSRF_GUARD_ENABLED=false` disables the guard outright. **Breaking** for
  setups whose feeds/images live on private addresses.
- **Feed import responses changed shape** (breaking for API consumers):
  `skipped` is now a list of `{url, reason}` objects, and a bad-scheme URL in
  a JSON import no longer rejects the whole file — it's skipped per-row.
  Structurally broken files still get a 400.
- OPDS acquisition links now point at `/opds/digests/{id}/download`, which
  honours the catalog's Basic auth; the plain `/api` download stays open for
  the same-origin web UI.
- Manual feed refresh now uses conditional GET (ETag/Last-Modified) through
  the same code path as the scheduler, so it can answer "0 new" cheaply and
  records feed health exactly once.
- EPUB builds and image recompression run off the event loop, so the UI and
  API stay responsive during a compile.
- Send-to-e-reader stays visible when SMTP isn't configured — as a "Set up
  delivery" link into Settings — instead of vanishing.
- Feed and queue row tools are always visible on touch screens (they were
  hover-only), without covering the unread badge.
- Cover typography enlarged (title and source list) for small e-ink screens,
  with the layout re-derived so worst-case titles and long source lists
  cannot clip off-canvas.
- Custom render profiles' photo width is clamped to 1600px so high-res
  device profiles don't inflate editions.

### Fixed

- **Every cover-bearing EPUB was technically non-conformant** (epubcheck
  OPF-096: the cover page sat in the spine unreferenced); editions now emit
  a cover landmark. Found by the new CI gate on day one.
- Image fetches are now hardened against decompression bombs: downloads cap
  at 25 MiB (streamed, not trusting Content-Length) and images over 40M
  decoded pixels are dropped before decode.
- Fast filter/search/page switching can no longer let a slow, stale article
  list response overwrite a newer one.
- A failed press-deadline compile no longer retries every scheduler tick
  against an already-drained queue; the failure stays visible as a failed
  edition and the deadline waits for its next occurrence.

## [Unreleased]

### Changed

- Triage rows: the per-row "Mark seen" toggle is gone (the row itself and
  bulk *Mark all seen* cover it) and the lifecycle stamp reads **Fetched**
  instead of *Seen*.
- Queue titles are clickable and open the article in the reader drawer —
  including links queued via *Add a link*, which can now be read before
  compiling.

### Fixed

- Extraction no longer runs trafilatura in `favor_recall` mode first: on
  boilerplate-heavy news pages (theregister.com) that mode extracted the
  "most popular" link rail instead of the article. Default extraction runs
  first; recall mode remains as the rescue pass when the default finds
  nothing.

## [1.2.0] - 2026-07-02

Better article fetching, and a clearer triage desk.

### Added

- **Reader fallback** for bot-walled sites: when the direct fetch is refused or
  comes back empty, the article fetcher hands the URL to an external extraction
  service. Pluggable by design: **Tavily** (API key) and **Jina Reader** (free,
  keyless) ship in-box; a new provider is one class plus one registry entry.
  Configure it under Settings → *Article fetching*, or via the `READER_FALLBACK`
  / `TAVILY_API_KEY` env vars. The provider-registry pattern is adapted from
  [hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT, © 2025 Nous
  Research).
- **On-disk image cache**: compiling an edition now caches the original image
  bytes under `EPUB_DIR/.image_cache` (keyed by URL), so recompiling or pressing
  another copy of the same articles needs no network — and images that have
  since rotted or gone unreachable still make it into the book. Cache hits
  refresh the file's timestamp; daily retention prunes entries untouched for
  longer than the article-retention window.
- **Code-block mode per render profile** (`code_mode`): "image" rasterizes
  each `<pre>` block to a PNG (drawn at natural width so short blocks stay
  readable, long lines hard-wrapped), and "br" bakes line structure in as
  `<br/>` with non-breaking indentation. On-device testing showed the Xteink
  X4 engine ignores CSS and legacy size tags and clips oversized tokens, so
  every text-based strategy fails there — its preset defaults to "image";
  everything else keeps native `<pre>`.
- **Device screen dimensions per render profile** (`screen_width`/
  `screen_height`): when set, table and code images are fitted to the device
  — drawn at 2× screen pixels so the reader's downscale stays crisp, blocks
  wider than the portrait budget auto-rotate 90° to use the long screen edge,
  taller blocks split into screen-shaped chunks, and article photos are
  recompressed to 2× screen width instead of the global 1200px. This replaces
  the manual "rotated" table mode and the `table_aspect` option (stored
  profiles migrate automatically: `image_rotated` coerces to `image`,
  `table_aspect` is ignored).
- **Article lifecycle states** on the triage desk (*new → seen → queued → in
  edition*), replacing the binary read flag, so a quick preview no longer reads
  as "done" (`Article.state`, computed server-side).
- **Edition preview** on the Editions page: expand any edition to read its
  articles grouped by section (full bodies on demand), see an *"N of M links
  fetched"* summary with a collapsed list of the links that couldn't be
  retrieved, and **remove** an article or a whole section; the EPUB rebuilds
  automatically (`GET`/`DELETE /api/digests/{id}/articles`).

### Changed

- Article pages are fetched with a **browser-impersonating client** (curl_cffi,
  Chrome TLS/JA3 fingerprint) instead of a spoofed User-Agent, so
  TLS-fingerprinting bot walls stop refusing the connection outright.
- **Compile now fetches missing content itself.** Previously only *Preview*
  fetched full text, so articles enqueued without previewing shipped as summaries.
  Generation now retrieves any missing bodies with the same impersonation +
  reader fallback (and caches them back onto the article), throttled to be
  polite: same-host requests are spaced ~2 s with jitter while distinct hosts run in
  parallel (`services/article_fetcher.py`; per-member outcome in
  `digest_articles.fetch_status`, migration 9).
- Feeds that ship full content (`<content:encoded>` / Atom `<content>`) are
  stored at poll time, so full-text feeds need no page fetch at all.
- Masthead: nav links now read as interactive (hover/active affordance, rule
  separator), distinct from the static tagline.
- **Default device profile**: Settings lets you mark one device profile as the
  default, and the triage desk's compile button now names its target
  (*"Compile · Kindle"*) instead of reading as a generic action. Profile and
  edition-mode picks live behind a collapsed "Compilation options"
  disclosure, and compiling can no longer silently fall back to legacy
  settings from the UI.
- Editions: any ready edition can be **recompiled** for a chosen device
  profile; *Download* is promoted to the primary action, *Delete* demoted to
  an icon-only affordance, profile/mode chips appear per row, and the
  noisy *READY* chip is gone.
- Triage: the add-feed and add-link forms collapse behind buttons instead of
  sitting open by default, unread badges cap at *999+*, and the queue hint
  copy reads more like plain language.
- Settings: a sticky save bar with unsaved-changes detection replaces the
  header save button.
- **Covers ship as 1200×1920 JPEG** (drawn at 1600×2560, downscaled) instead
  of a 4-megapixel PNG, which budget e-ink decoders (Xteink X4) silently
  refused to display; still within Kindle's recommended cover size.

- **Rotated blocks turn clockwise**: wide tables and code images that
  auto-rotate now read top-to-bottom when the device is tilted left, with the
  beginning of the block first (previously counter-clockwise, which put the
  start at the wrong end).
- **Code images use a bundled compact monospace font** (Ubuntu Mono, Ubuntu
  Font Licence) instead of the proportional UI font, so indentation and
  ASCII diagrams align.

### Fixed

- Table images: single tokens wider than their column (long model names,
  URLs) are now hard-broken at character level instead of painting across the
  neighbouring column.
- Code blocks inside table cells are no longer ripped out by the code-image
  pass before the table is rasterized — their text now stays in the cell, so
  table images stop showing truncated sentences and orphaned commas where
  inline code used to be.

## [1.1.0] - 2026-06-12

Feed groups & split editions.

### Added

- **Feed groups** (folder model, migration 7): a `groups` table and
  `feeds.group_id`; collapsible sidebar sections with rolled-up unread
  badges, group filtering, inline rename/dissolve (feeds survive), a
  move-to-group picker on every feed row, and a "New group" form
- **Split compiles**: choose *Combined* or *One per group* at compile time
  (remembered locally); per-group mode presses one edition per group,
  titled `<date> - <Group>`, with the Ungrouped bucket last; the press
  deadline gets the same choice (`deadline_split` in Settings)
- **Group-sectioned TOC**: combined editions section their table of contents
  by group (groups in queue order, Ungrouped last, feed names in bylines);
  per-group editions keep per-feed sections; no groups ⇒ the 1.0 shape
- **OPML folders**: import maps top-level folders to groups (deep nesting
  flattens; existing feeds adopt a folder only while ungrouped, so re-import
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
  fetches (feeds, articles, images) share one browser-shaped User-Agent
  (with `rss-kindle-selector` kept in the string), so UA-only bot filters
  no longer refuse us
- EPUB filenames are sanitized; titles containing `/` or `:` (possible via
  custom titles, easier via group suffixes) can no longer break the build

### Changed

- `POST /api/digests` returns a **list** of digests (length 1 in combined
  mode); the bundled web client is updated in step

## [1.0.0] - 2026-06-12

The 1.0 release: milestones M1–M6.

### Added: packaging (M6)

- Single-container deploy: multi-stage `Dockerfile` + `docker-compose.yml`
  with a named `/data` volume; `docker compose up` is the entire story
- Next.js static export served same-origin by the API with an SPA fallback;
  the CORS allowlist and web/API port coupling are gone (dev uses rewrites)
- `/health` reports `{status, version, db}`

### Added: curation UX (M5, v0.6)

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

### Added: always fresh (M4, v0.5)

- In-process asyncio scheduler: due-feed polling with conditional GET
  (ETag/Last-Modified), exponential backoff capped at 24h, feed health
  columns and sidebar badges
- Press deadline: compile-and-deliver the queue daily/weekly at HH:MM
- Daily retention cleanup (default 90 days; queued/pressed articles exempt)
- `PATCH /api/feeds/{id}` (rename, poll interval)

### Added: delivery (M3, v0.4)

- Server-side digest queue (survives reloads, ordered, API-visible)
- Send-to-Kindle email via SMTP (aiosmtplib): per-edition send,
  email-on-ready, 45MB guard, delivery log; works for PocketBook too
- OPDS 1.2 catalog (`/opds`) with optional Basic auth for KOReader,
  Xteink/CrossPoint, Kobo, Boox, Calibre
- Settings store (DB-backed, env-var overrides for SMTP credentials)

### Added: the beautiful EPUB (M2, v0.3)

- Content pipeline stores sanitized HTML (trafilatura 2.x + nh3 allowlist;
  TEI vocabulary normalized), so tables, code blocks, lists, links and images
  survive extraction
- EPUB: Pillow-rendered cover, title page, TOC sectioned by feed, per-article
  byline + reading time + original link, colophon, e-ink stylesheet,
  UTF-8 declarations everywhere
- Image pipeline: download, downscale to 1200px JPEG q75 (PNG when alpha),
  10MB per-article budget, alt text preserved
- Summary fallback with a visible marker when extraction fails

### Added: a repo a stranger can trust (M1, v0.2)

- `PRAGMA user_version` migrations (legacy 0.1 databases adopted in place)
- Digest builds that fail land in `failed` with the error stored and shown
- Poll failures logged and reported (`{inserted, errors}`)
- MIT `LICENSE`, `README`, `CONTRIBUTING`, GitHub Actions CI,
  `example-feeds.opml`, pinned web dependencies

### Changed

- Markdown content storage replaced by sanitized HTML (cached extractions
  are invalidated by migration; articles re-fetch on demand)
- `assert`-based control flow replaced with explicit errors

## [0.1.0] - 2026-04-16

Initial personal build: feed CRUD, on-demand refresh, trafilatura extraction,
hand-picked digests, background EPUB build, download.
