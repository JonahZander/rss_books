# RSS Books

[![CI](https://github.com/JonahZander/rss_books/actions/workflows/ci.yml/badge.svg)](https://github.com/JonahZander/rss_books/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)

**The self-hosted news desk for your e-reader.** Subscribe to RSS feeds, hand-pick
the articles worth your attention, and press them into a clean, typographically
careful EPUB edition: emailed to a Kindle, pulled over OPDS by everything else.

> Pick your news. Press an edition. Read it anywhere.

![Triage desk](docs/screenshots/triage.png)

| Read before you queue | Review an edition | Fits in a pocket |
|---|---|---|
| ![Article expanded inline](docs/screenshots/article-expanded.png) | ![Editions with grouped preview](docs/screenshots/editions.png) | ![Mobile triage](docs/screenshots/mobile-triage.png) |

<details>
<summary>More screenshots: settings, device render profiles</summary>

![Settings](docs/screenshots/settings.png)
![Device render profiles](docs/screenshots/render-profiles.png)

</details>

## Why this exists

Every self-hosted RSS-to-ereader tool auto-sends whole feeds. Every
hand-pick-your-articles tool is paid SaaS, and the free options died in
2024–2025 (Pocket, Omnivore, Instapaper's free Kindle tier). The combination
*self-hosted* × *you choose each article* simply didn't exist. This fills that
gap. The full "why not KindleEar / KTool / Calibre?" answer lives in
[the landscape analysis](docs/landscape-and-options.md).

## Features

- **Curation is the product.** A triage desk built for skimming: expand an
  article inline (readable full text via trafilatura), tick the ones you want.
  The queue lives server-side, so you can triage on your phone and compile at your desk.
  Nothing is ever sent that you didn't pick.
- **Editions, not streams.** Output is a finite, dated EPUB issue with a
  cover, a sectioned table of contents, bylines, reading times, embedded
  images (downscaled for e-ink), real tables and code blocks, and a
  stylesheet tuned for 6–7″ greyscale screens.
- **Render profiles per device.** Tell it your reader's screen size and it
  fits the content to the glass: tables and code blocks are rasterized at the
  device's resolution, rotated 90° when they're wider than the screen, and
  split into screen-sized pages when they're taller — so even a budget e-ink
  engine that ignores CSS renders them readably. Photos are downscaled to
  what the screen can actually show. Downloaded images are cached on disk, so
  recompiling an edition never re-fetches.
- **Group your feeds.** Organize feeds into groups ("AI", "Gaming", …) and
  choose at press time: one combined edition with a chapter section per
  group, or **one edition per group**. Import/export grouping as OPML
  folders or a plain JSON feed list (`{"group": ["feed url", …]}`).
- **Any reader.** Kindle gets editions by send-to-Kindle email (with an
  in-app setup wizard). KOReader (including jailbroken Kindles),
  Xteink/CrossPoint, Kobo, Boox and Calibre pull them from the built-in OPDS
  catalog. Everyone can just download the file.
- **Always fresh.** Background polling with conditional GET and polite
  backoff; failing feeds get a badge, not a silent grave. An optional **press
  deadline** compiles your queue into an edition on a schedule: the
  Friday-paper ritual, but you still picked every article.
- **No landlords.** One process, one SQLite file, your own SMTP account if
  you want email. MIT licensed.

## Quickstart

Run the prebuilt image (amd64/arm64) — no clone needed:

```yaml
# docker-compose.yml
services:
  rss-books:
    image: ghcr.io/jonahzander/rss_books:latest
    ports:
      - "8765:8765"   # web UI + OPDS (plain HTTP, same-origin)
      - "8443:8443"   # HTTPS, for OPDS clients that require TLS
    volumes:
      - rss_kindle_data:/data
    restart: unless-stopped

volumes:
  rss_kindle_data:
```

```bash
docker compose up -d
```

Or build from source:

```bash
git clone https://github.com/JonahZander/rss_books.git
cd rss_books
docker compose up -d   # builds the image locally
```

Open <http://localhost:8765>, import
[`example-feeds.opml`](example-feeds.opml) (sidebar → *Import OPML*) or add a
feed by URL, hit *Refresh all*, tick a few articles, *Compile · EPUB*.

Your database and editions live on the `rss_kindle_data` volume and survive
rebuilds and image updates.

### Proxmox / home-lab deploys

The container is a single self-contained process (SQLite inside, no external
services), so it runs anywhere Docker does — including a Docker LXC or VM on
Proxmox (e.g. one created with the
[community helper scripts](https://community-scripts.github.io/ProxmoxVE/)).
Drop the compose file above into the container/VM and `docker compose up -d`.
Notes for LAN deploys:

- Point your readers at the host's LAN IP: web UI at `http://<lan-ip>:8765`,
  OPDS at `http://<lan-ip>:8765/opds`.
- If your reader insists on HTTPS (Crosspoint does), it can use port 8443.
  The self-signed certificate is generated on first boot; set
  `TLS_SAN_IPS: <lan-ip>` in the compose `environment:` so hostname-verifying
  clients accept it, and re-download the cert from Settings if the IP changes.
- Back up `/data` (the named volume): it holds the SQLite database, editions,
  the image cache and the TLS cert — everything.
- The app has no login screen; keep it on the LAN/VPN side of your firewall
  (see [Security posture](#security-posture)).

### Development mode

Requirements: Node 20.19.6, [uv](https://docs.astral.sh/uv/), Python 3.12+.

```bash
npm install
npm run dev:api   # FastAPI on :8765
npm run dev:web   # Next.js on :3737 (proxies /api to :8765, no CORS)
```

## Getting editions onto your reader

| Channel | Devices | Setup |
|---|---|---|
| **Download** | everything | Button on each ready edition |
| **OPDS catalog** | KOReader (incl. jailbroken Kindles), Xteink/CrossPoint, Kobo, Boox, Calibre | Add `http://<host>:8765/opds` as an OPDS catalog in the reader. Optional Basic auth in Settings. |
| **Send-to-Kindle email** | Kindle, PocketBook | Settings → Delivery: enter SMTP details, add your `@kindle.com` address, approve the From sender in Amazon's Personal Document Settings (the wizard links straight there), send the test email. |

Tip: with *email every edition* and a press deadline enabled, the morning
paper writes itself, from articles you picked the evening before.

## Configuration

Everything user-facing lives in the in-app **Settings** page (SMTP, OPDS auth,
polling, press deadline, retention, reading preferences). Environment
variables for operators:

| Env var | Default | Meaning |
|---|---|---|
| `DB_PATH` | `./data/rss_kindle.db` (`/data/...` in Docker) | SQLite database file |
| `EPUB_DIR` | `./data/epubs` (`/data/epubs` in Docker) | Where editions are stored |
| `STATIC_DIR` | unset (`/app/static` in Docker) | Static web app to serve same-origin |
| `SCHEDULER_ENABLED` | `1` | Set `0` to disable background polling entirely |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` | unset | Override stored SMTP settings (keep credentials out of the DB) |
| `HTTP_PORT` / `HTTPS_PORT` | `8765` / `8443` | Listener ports |
| `TLS_ENABLED` / `TLS_CERT_FILE` / `TLS_KEY_FILE` / `TLS_SAN_IPS` | `1` / `./data/certs/...` / unset | Self-signed TLS listener for clients that require HTTPS |
| `READER_FALLBACK` | unset | External extraction fallback for bot-walled sites: `tavily` or `jina` (also settable in Settings → Article fetching) |
| `TAVILY_API_KEY` | unset | API key when `READER_FALLBACK=tavily` |

## Limits worth knowing

Article text is fetched server-side. Sites behind aggressive bot walls
(Cloudflare-style TLS fingerprinting; openai.com, for example) refuse
non-browser clients no matter what; those articles show the upstream status
in the UI and fall back to the feed's own summary in editions, with the
original link one tap away.

## Security posture

Single-user app for localhost or a trusted LAN/tailnet. There is deliberately
no login screen, so don't expose it to the internet unauthenticated. If you need
remote access, put a reverse proxy with Basic auth in front (or use a VPN /
Tailscale). The OPDS catalog has its own optional Basic auth, since readers
hit it from other devices. Feed URLs are fetched server-side; keep that in
mind before adding feeds you don't trust.

## Architecture

One FastAPI process: API + in-process asyncio scheduler + background EPUB
builds. SQLite via aiosqlite with `PRAGMA user_version` migrations. Feed
parsing with feedparser (conditional GET, backoff); readable-content
extraction with trafilatura 2.x sanitized through an nh3 allowlist; EPUBs
built with ebooklib; covers with Pillow; email with aiosmtplib. The Next.js
front end is fully client-side and ships as a static export served by the
API: one container, no CORS. No Redis, no Celery, no cron.

```
feeds → poller (etag/backoff) → articles → [you pick] → queue
  → digest service → extract/sanitize → images (cached, device-fit) → EPUB (cover/TOC/css)
  → download · OPDS catalog · SMTP → your reader
```

## How it compares

See [docs/landscape-and-options.md](docs/landscape-and-options.md) for the
full market analysis (KindleEar, Calibre, KTool, Push to Kindle, Reabble,
EpubPress, …) and the
[research catalog](docs/research/2026-06-11-rss-to-ereader-services.md)
behind it.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[design language](docs/design-language.md). Changes are tracked in the
[CHANGELOG](CHANGELOG.md).

## License

[MIT](LICENSE) © Jonah Zander
