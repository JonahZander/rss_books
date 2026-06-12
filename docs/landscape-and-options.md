# The Lay of the Land: News-to-E-Reader in 2026

*Why rss-kindle-selector exists, what else is out there, and the decision log behind how we’re polishing it.*

**Researched:** 2026-06-11. Stars/activity were checked against the GitHub API that day; prices and policies come from the linked pages and will rot — trust the links over this text.
**Companion:** the [v2 design spec](superpowers/specs/2026-06-11-rss-kindle-selector-v2-design.md) turns the conclusions here into a concrete plan.
**Evidence base:** the full per-service research catalog (every tool, feature set, price, and weakness found) lives in [`docs/research/2026-06-11-rss-to-ereader-services.md`](research/2026-06-11-rss-to-ereader-services.md).

## The short version

People have wanted “my own newspaper on my e-reader” since the Kindle 1. In 2023 Amazon killed the first-party answer (Kindle newspaper subscriptions). In 2024–2025 the free third-party answers died too: **Omnivore shut down** (Nov 2024), **Pocket shut down** (July 2025), and **Instapaper put Kindle digests behind a paywall** (Feb 2025). What remains is either *auto-send-everything* automation (KindleEar, Calibre recipes) or *hand-pick-your-articles* curation at $36–120/year of SaaS (KTool, ReadBetter, Readwise).

Map the field on two axes and one cell is empty:

| | **Auto-send whole feeds** | **Hand-pick articles into one edition** |
|---|---|---|
| **SaaS** | Kindle4RSS/QiReader, KTool RSS, Instapaper & Readwise digests (semi-auto) | KTool Custom Magazines, ReadBetter digests, Matter bulk-send, EpubPress (hosted) |
| **Self-hosted** | KindleEar, Calibre recipes, the news2kindle script graveyard, KOReader plugin | **← nobody (this project)** |

No maintained self-hosted tool lets you subscribe to feeds in a web UI, triage individual articles, and press the picked ones into a single clean EPUB. The two biggest self-hosted RSS readers have declined to build Kindle export for years ([miniflux/v2#228](https://github.com/miniflux/v2/issues/228), [FreshRSS#2516](https://github.com/FreshRSS/FreshRSS/issues/2516)), and fresh single-purpose scripts keep appearing on GitHub in 2026 — demand that keeps regenerating without being met.

Two community threads frame the user pain precisely: people love a **bounded daily bundle** over an infinite badge-driven feed ([Ben Kuhn on Kindle4RSS](https://www.benkuhn.net/krss/)), and they complain about exactly two things — **no way to filter what gets sent** ([HN: “From RSS to my Kindle”](https://news.ycombinator.com/item?id=40773125)) and **fragile DIY pipelines** ([HN: “I turned my Kindle into my own personal newspaper”](https://news.ycombinator.com/item?id=47541969)).

## Field guide

### Open-source / self-hosted

**[KindleEar](https://github.com/cdhigh/KindleEar)** — the incumbent (≈2.8k ★, MIT, alive but slow cadence). Aggregates RSS + scraped sites into EPUB with images and TOC, **emails them to your Kindle on a daily schedule**; consumes Calibre’s recipe format with ~1,000 recipes built in; has since added AI summaries, translation, TTS. Philosophy: *automated periodical* — there is no per-article picking. Pain points are instructive: Docker users lose their DB without an explicit volume ([deployment docs](http://cdhigh.github.io/KindleEar/English/deployment.html)), you must bring working SMTP, docs are Chinese-first, and VPS install is “complex and not recommended” by its own manual.

**[Calibre “Fetch news”](https://manual.calibre-ebook.com/news.html)** — the OG. Hundreds of recipes, output is fine but dated, and scheduled email-to-Kindle requires **leaving the desktop app running** ([guide](https://www.howtogeek.com/115178/how-to-convert-news-feeds-to-ebooks-with-calibre/)); people work around it by running Calibre headless in GitHub Actions ([Calibre-News-Delivery](https://github.com/bookfere/Calibre-News-Delivery)). [Calibre-Web](https://github.com/janeczku/calibre-web) (≈17.5k ★) and [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) (≈5.7k ★) add a web UI and a send-to-Kindle button — but they’re **library managers, no RSS in**, and send-to-Kindle breakage is a recurring issue class ([#2461](https://github.com/janeczku/calibre-web/issues/2461), [CWA #724](https://github.com/crocodilestick/Calibre-Web-Automated/issues/724)).

**The script graveyard** — GitHub holds dozens of `news2kindle`-shaped repos: cron + feed list in a config file + EPUB/MOBI + SMTP ([anteprandium/news2kindle](https://github.com/anteprandium/news2kindle), last push 2021; [punchagan/r2k](https://github.com/punchagan/r2k), 2015; [MrPike/RSS2Ebook](https://github.com/MrPike/RSS2Ebook); [gonejack/rss-epub](https://github.com/gonejack/rss-epub); …). New ones still appear monthly in 2026 (e.g. [rymc/rss-kindle](https://github.com/rymc/rss-kindle) for FreshRSS, Apr 2026). Pattern: no UI, no read tracking, hardcoded feeds, auto-send everything, bitrot.

**[Wallabag](https://github.com/wallabag/wallabag)** (≈12.8k ★, very active) — self-hosted read-it-later with EPUB export, but **no digest composition and no built-in Kindle delivery** — that request is [ten years open](https://github.com/wallabag/wallabag/issues/770); community glue scripts ([wallabag-kindle-consumer](https://github.com/janLo/wallabag-kindle-consumer)) are stale. Saving an article *is* hand-picking — but the output is one-export-per-article, not an edition.

**[EpubPress](https://epub.press/)** — the closest UX relative: select open browser tabs, get one merged EPUB, optionally emailed to `@kindle.com`. Tab-based rather than feed-based, no subscriptions or archive, and the hosted compile server is the failure mode — the [server repo](https://github.com/haroldtreen/epub-press) last moved in 2023 and the community fork (EpubPressX) exists to *remove* the server dependency. Lesson received.

**[Miniflux](https://github.com/miniflux/v2)** (≈9.3k ★) **/ [FreshRSS](https://github.com/FreshRSS/FreshRSS)** (≈15.3k ★) — the self-hosted RSS readers everyone already runs. Both punt on Kindle entirely (links above). They are **adjacency, not competition**: their users are our likeliest adopters, and their APIs are a future ingestion source.

### Paid services (what curation costs with a landlord)

| Service | Model | Price | Notes |
|---|---|---|---|
| [Push to Kindle](https://www.pushtokindle.com/) (FiveFilters) | push one article at a time | free 10/mo, then $2.99/mo | one Kindle doc *per article* → library clutter |
| [KTool](https://ktool.io/) | RSS + newsletters + **custom magazines** | $36–72/yr, **no free tier** | the closest commercial analogue to this project; [changelog](https://dev.ktool.io/changelog) quiet since 2023 |
| [ReadBetter](https://www.readbetter.io/) | articles/newsletters → bundled digests | free 3 items/mo; $6.99–9.99/mo | markets “preserves images/charts” *as a differentiator* — i.e., rivals don’t |
| [Instapaper](https://www.instapaper.com/premium) | save-to-read-later → scheduled Kindle digest | $5.99/mo / $59.99/yr (free tier lost Kindle, [Feb 2025](https://goodereader.com/blog/kindle/send-to-kindle-with-instapaper-is-now-going-to-cost-money)) | CEO’s paywall rationale: digest builds (parse, images, EPUB, email) ran “at a loss” — *our* compute, *our* problem solved by self-hosting |
| [Readwise Reader](https://readwise.io/pricing) | triage into Library → auto daily/weekly Kindle digest | ~$120/yr | notably, RSS items are **excluded until you move them to the Library** — triage-then-digest as the default, validating our core flow |
| [Kindle4RSS](https://kindle4rss.com/) / [QiReader](https://www.qireader.com/) | scheduled feed bundles | ~$1–3/mo | the [beloved one](https://www.benkuhn.net/krss/); feed-level only, no picking |
| [Matter](https://hq.getmatter.com/updates/matter-kindle), [Polyreader](https://polyreader.app/) | read-later → Kindle, bulk merge | $60/yr; ~$1/mo | iOS-centric; the post-Pocket wave keeps coming, all closed |

### The substrate (what everything must build on)

- **Amazon Send to Kindle**: EPUB in, [MOBI dead since 2022](https://www.fivefilters.org/2022/kindle-epub-support/). Email gateway: [50 MB per mail, 25 attachments, max 15 approved senders](https://www.amazon.com/gp/help/customer/display.html?nodeId=G7NECT4B4ZWHQ8WV) — the approved-sender dance is the #1 support generator for every tool above. Converter gotcha: [declare UTF-8 or get mojibake](https://blog.the-ebook-reader.com/2022/05/06/how-to-fix-formatting-issues-on-epubs-sent-to-kindles/). No official API; [stkclient](https://github.com/maxdjohnson/stkclient) reverse-engineers one but is unmaintained (2023).
- **Kindle Periodicals are dead** — subscriptions [ended Sept 2023](https://www.niemanlab.org/2023/03/goodbye-newspapers-on-kindle-amazon-stops-selling-newspaper-and-magazine-subscriptions/). The sectioned, dated, wake-up-to-it newspaper experience has had **no first-party replacement for three years**. That’s the emotional job-to-be-done.
- **[KOReader](https://github.com/koreader/koreader)** (≈27k ★) runs on jailbroken Kindles, Kobos, and more; its [news plugin](https://github.com/koreader/koreader/wiki/News-downloader) fetches RSS to HTML files configured by hand-editing Lua — and it speaks **OPDS**, the catalog protocol of the e-reader world.
- **[Xteink X4 + CrossPoint](https://github.com/crosspoint-reader/crosspoint-reader)** — the 2026 community-darling pocket reader; CrossPoint firmware ships an **OPDS browser** (saved servers, search, direct download) and a Calibre-wireless flow ([walkthrough](https://www.ereadersforum.com/threads/two-ways-to-send-books-wirelessly-from-calibre-to-the-xteink-x4.13111/)); stock firmware takes EPUBs over [USB/SD or a LAN upload page](https://bluehayden.substack.com/p/how-to-import-books-to-xteink-x4). Serving OPDS makes us native on this whole device class — no Amazon required.

## What the field teaches us

1. **Deployment is the moat for self-hosted.** KindleEar’s data-loss foot-gun and “not recommended” VPS install are why a 2.8k-star tool still feels niche. → one container, volume by default, compose file in the README (spec M6).
2. **Digest-building is expensive enough that SaaS paywalls it.** Instapaper said the quiet part out loud. Self-hosting turns their cost problem into our non-problem. → lean into it in positioning.
3. **The approved-senders dance must be productized.** Every tool makes users figure out Amazon’s whitelist alone. → guided wizard + test-send button (M3).
4. **Never depend on a hosted compile server.** EpubPress died of it. → everything local (already true).
5. **Auto-send annoys the people who care most.** The HN threads ask for filtering and curation; Readwise made triage-first its default. → the queue stays the hero (M3/M5).
6. **Output beauty is an open flank.** Documented complaints: boilerplate bleed-through, broken tables/code on e-ink, illegible compressed images, flat no-TOC navigation, charset mojibake. Nobody self-hosted does typography well. → the whole of M2.
7. **EPUB + email + OPDS covers every device made this decade.** MOBI is dead; jailbreak is a ceiling; unofficial APIs rot. → three boring channels (M3).
8. **Ride the trust narrative honestly.** Pocket, Omnivore, free Instapaper: gone. “Your reading pipeline shouldn’t have a landlord” is both true and proven to resonate.

## How we compare (the README one-screen answer)

| | curation | hosting | delivery | output quality | price |
|---|---|---|---|---|---|
| **rss-kindle-selector** | **hand-pick per article** | self-hosted | email + OPDS + download | typographic EPUB editions (M2) | free, MIT |
| KindleEar | auto (recipes) | self-hosted | email | decent, utilitarian | free, MIT |
| Calibre recipes | auto | desktop | email (app running) | dated defaults | free |
| KTool | pick (magazines) | SaaS | email | good | $36–72/yr |
| Instapaper | save-then-auto | SaaS | email | good | $59.99/yr |
| KOReader plugin | auto | on-device (jailbreak) | n/a | raw HTML | free |

## Decision log

The options weighed for each polish axis, and what the spec chose. (Scope, license, and naming were decided with the project owner on 2026-06-11.)

**1 · Ambition** — *(a) minimal publishable (docs+hygiene only), (b) polished self-hosted single-user app, (c) flagship (multi-user, AI, newsletters).* Chose **(b)**: (a) ships a toy (no delivery = dealbreaker per research), (c) is a maintenance trap for a solo project. ◄ the whole milestone plan.

**2 · License** — *MIT / AGPL / Apache-2.0.* Chose **MIT**: simplicity and contributor-friendliness; the KTool-style closed-SaaS-fork risk AGPL guards against is not a real threat to a personal-infrastructure tool.

**3 · Name** — *keep `rss-kindle-selector` / rename (Kindling, Paperboy, Dispatch).* Chose **keep**: self-describing and searchable; the Kindle-only connotation is handled by the tagline (“…and any EPUB reader”), not the name.

**4 · Delivery** — *(a) download only, (b) email only, (c) stkclient API, (d) download + email + OPDS, each optional.* Chose **(d)**. Download alone is the USB-cable status quo; email alone strands non-Kindle devices (and the owner wants an Xteink to work); stkclient is unmaintained and unofficial. OPDS is one read-only Atom endpoint and instantly serves KOReader, CrossPoint, Kobo, Boox, and Calibre.

**5 · Where the queue lives** — *(a) React state (today), (b) server-side table.* Chose **(b)**: survives reloads, enables phone-triage/desk-compile, and is the prerequisite for the press-deadline feature. The queue is the product; it can’t be ephemeral.

**6 · Content pipeline** — *(a) keep markdown + hand-rolled renderer (today), (b) markdown + real renderer (markdown-it-py), (c) trafilatura HTML output + `nh3` sanitization.* Chose **(c)**: the markdown round-trip silently drops tables, code blocks, and figures — exactly the elements e-ink renders worst when mangled. (b) fixes rendering but keeps the lossy intermediate. Cost: bump the trafilatura `<2.0` pin; migration wipes cached content (re-fetched on demand).

**7 · EPUB styling** — *(a) none (today), (b) embedded CSS, reader fonts, (c) embedded fonts for full control.* Chose **(b)**: e-readers override fonts anyway and users prefer their own; embedded fonts triple file size against a 50 MB email cap. Spend the effort on spacing, TOC structure, covers, and image discipline instead.

**8 · Images** — *(a) off (today), (b) on, raw, (c) on with downscale + per-article budget at build time.* Chose **(c)**: raw images blow the email cap and load slowly on-device; “preserves images” is literally a paid differentiator at ReadBetter. Downscale to ~1200 px / JPEG q75, drop failures gracefully.

**9 · Scheduling** — *(a) manual only (today), (b) external cron hitting the API, (c) APScheduler, (d) hand-rolled asyncio loop in-process.* Chose **(d)**: (b) breaks one-command deploy, (c) is a dependency for ~40 lines of loop. Conditional GET + backoff make us a polite client; “press deadline” (scheduled compile-and-deliver of *whatever the user picked*) automates the ritual without automating the choosing.

**10 · Packaging** — *(a) two services + CORS (today), (b) Next static export served by FastAPI, one container, (c) desktop app (Tauri).* Chose **(b)**: the frontend is already fully client-side; same-origin serving deletes the CORS allowlist and the 3737/8765 port coupling — our two ugliest gotchas — and matches the single-binary ethos that makes Miniflux beloved. (c) abandons the homelab audience and the always-on scheduler. Fallback if export hits a blocker: keep (a) with env-driven CORS, documented compose.

**11 · Migrations** — *(a) keep wiping the DB, (b) Alembic, (c) `PRAGMA user_version` + ordered migration functions.* Chose **(c)**: (a) cannot ship to strangers; (b) is heavy machinery for one SQLite file. ~30 lines buys an upgrade path forever.

**12 · Auth posture** — *(a) none anywhere, (b) full login system, (c) no web-UI auth + documented reverse-proxy recipe + optional Basic auth on OPDS.* Chose **(c)**: a single-user login screen is theater; OPDS gets real (optional) auth because devices reach it across the network. README states the LAN/tailnet assumption plainly.

## Risks & watchlist

- **KindleEar grows a picking UI** — has the delivery machinery; model and codebase point the other way. Watch releases; our answer is shipping M2/M3 first.
- **Miniflux/FreshRSS accept a Kindle-export PR** — refused for years, but either doing so would shrink the gap. Mitigation: be the best *edition composer* either could point at; their APIs are our future import path.
- **Amazon tightens the email gateway** — three channels mean Kindle-email is a feature, not the foundation.
- **CrossPoint/Xteink momentum** — the OPDS-native device wave grows; serve it well and it’s free distribution among exactly our users.

## Sources

**Threads & testimony:** [HN 2026: personal Kindle newspaper](https://news.ycombinator.com/item?id=47541969) · [HN 2024: From RSS to my Kindle](https://news.ycombinator.com/item?id=40773125) · [Ben Kuhn: Kindle4RSS](https://www.benkuhn.net/krss/) · [self-hosted reading infra](https://red734.com/self-hosted-rss-reading-infrastructure/)

**Open source:** [KindleEar](https://github.com/cdhigh/KindleEar) ([deploy docs](http://cdhigh.github.io/KindleEar/English/deployment.html), [FAQ](http://cdhigh.github.io/KindleEar/English/faq.html)) · [Calibre news](https://manual.calibre-ebook.com/news.html) · [Calibre-Web](https://github.com/janeczku/calibre-web) · [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) · [Calibre-News-Delivery](https://github.com/bookfere/Calibre-News-Delivery) · [Wallabag](https://github.com/wallabag/wallabag) ([#770](https://github.com/wallabag/wallabag/issues/770)) · [Miniflux #228](https://github.com/miniflux/v2/issues/228) · [FreshRSS #2516](https://github.com/FreshRSS/FreshRSS/issues/2516) · [EpubPress](https://epub.press/) ([server](https://github.com/haroldtreen/epub-press)) · [news2kindle](https://github.com/anteprandium/news2kindle) · [r2k](https://github.com/punchagan/r2k) · [rymc/rss-kindle](https://github.com/rymc/rss-kindle) · [KOReader](https://github.com/koreader/koreader) ([news plugin](https://github.com/koreader/koreader/wiki/News-downloader), [EPUB FR #9225](https://github.com/koreader/koreader/issues/9225))

**Commercial:** [Push to Kindle](https://www.pushtokindle.com/) · [KTool](https://ktool.io/) ([pricing](https://ktool.io/pricing), [changelog](https://dev.ktool.io/changelog)) · [ReadBetter](https://www.readbetter.io/) ([pricing](https://www.readbetter.io/faq/how-much-does-readbetter-cost)) · [Instapaper Premium](https://www.instapaper.com/premium) ([paywall coverage](https://goodereader.com/blog/kindle/send-to-kindle-with-instapaper-is-now-going-to-cost-money)) · [Readwise pricing](https://readwise.io/pricing) ([Kindle docs](https://docs.readwise.io/reader/docs/faqs/exporting)) · [Kindle4RSS](https://kindle4rss.com/) · [QiReader](https://www.qireader.com/) · [Reabble](https://reabble.com/) · [Matter](https://hq.getmatter.com/updates/matter-kindle) · [Polyreader](https://polyreader.app/)

**Shutdowns:** [Pocket](https://support.mozilla.org/en-US/kb/future-of-pocket) ([TechCrunch](https://techcrunch.com/2025/05/27/read-it-later-app-pocket-is-shutting-down-here-are-the-best-alternatives/)) · [Omnivore](https://molodtsov.me/2024/10/omnivore-is-dead-where-to-go-next/)

**Amazon & devices:** [Send to Kindle file types](https://www.amazon.com/gp/help/customer/display.html?nodeId=G5WYD9SAF7PGXRNA) · [email limits](https://www.amazon.com/gp/help/customer/display.html?nodeId=G7NECT4B4ZWHQ8WV) · [MOBI deprecation / EPUB support](https://www.fivefilters.org/2022/kindle-epub-support/) · [UTF-8 gotcha](https://blog.the-ebook-reader.com/2022/05/06/how-to-fix-formatting-issues-on-epubs-sent-to-kindles/) · [stkclient](https://github.com/maxdjohnson/stkclient) · [Periodicals shutdown](https://www.niemanlab.org/2023/03/goodbye-newspapers-on-kindle-amazon-stops-selling-newspaper-and-magazine-subscriptions/) · [CrossPoint](https://github.com/crosspoint-reader/crosspoint-reader) ([Calibre/OPDS walkthrough](https://www.ereadersforum.com/threads/two-ways-to-send-books-wirelessly-from-calibre-to-the-xteink-x4.13111/), [X4 import guide](https://bluehayden.substack.com/p/how-to-import-books-to-xteink-x4), [review](https://www.svartling.net/2026/04/xteink-x4-with-crosspoint-firmware-120.html))
