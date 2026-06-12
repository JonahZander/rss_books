# Field Research: RSS/News → E-Reader Services (Full Catalog)

*The complete per-service research record behind [`docs/landscape-and-options.md`](../landscape-and-options.md). That doc is the synthesis and decision log; this one is the evidence: every service found, what it does, what it costs, how it delivers, and where it falls short.*

**Researched:** 2026-06-11 (web search + GitHub API for stars/activity; exact `pushed_at` values from that day). Prices, policies, and maintenance status will drift — trust the links over this text. Claims that could not be verified are marked ⚠.

**Reading the entries** — each service is rated on the two axes that matter to this project:

- **Curation**: `auto` (everything in the feed gets sent) vs `pick` (the user chooses individual articles) vs `save` (saving an article *is* the pick, but bundling is automatic)
- **Delivery**: how the file reaches the device (`email` = SMTP to `@kindle.com`-style gateway, `download`, `OPDS`, `on-device`, `USB`)

---

## Quick comparison matrix

| Service | Type | Curation | Delivery | Output | Price | Status (2026-06) |
|---|---|---|---|---|---|---|
| **rss-kindle-selector** (this project) | self-hosted | **pick** | download (email + OPDS planned) | EPUB digest | free, MIT | active |
| KindleEar | self-hosted | auto | email | EPUB/MOBI w/ images, TOC | free, MIT | alive, slow cadence |
| Calibre “Fetch news” | desktop | auto | email (app must run), USB | EPUB/AZW3 | free | active |
| Calibre-Web (+ CWA) | self-hosted | n/a (library, no RSS) | email button | existing books | free | very active |
| news2kindle-style scripts | self-hosted | auto | email | EPUB/MOBI | free | mostly abandoned |
| Wallabag | self-hosted | save | export; email via stale sidecars | per-article EPUB | free | very active |
| Miniflux / FreshRSS | self-hosted | n/a | none (declined) | n/a | free | very active |
| EpubPress / EpubPressX | extension | pick (browser tabs) | download, email | merged EPUB | free/donation | semi-abandoned |
| Push to Kindle (FiveFilters) | SaaS | pick (1 article = 1 doc) | email | single-article doc | free 10/mo; $2.99/mo | active |
| KTool | SaaS | pick (custom magazines) + auto (RSS) | email | digest/magazine | $36–72/yr, no free tier | active, dev slowed |
| ReadBetter | SaaS | pick (custom digests) | email | bundled e-book, color images | free 3/mo; $6.99–9.99/mo | active |
| Instapaper | SaaS | save → auto digest | email | scheduled EPUB digest | $5.99/mo / $59.99/yr | active, paywalled 2025 |
| Readwise Reader | SaaS | save/triage → auto digest | email | daily/weekly digest | ~$120/yr | active |
| Kindle4RSS | SaaS | auto (feed-level) | email | magazine-style daily bundle | ≈$2.9/mo premium | legacy (→ QiReader) |
| QiReader | SaaS | auto | email | feed bundles | ~$1–3/mo ⚠ | active |
| Reabble | SaaS | n/a (reads in browser) | on-device (e-ink browser) + email | web reader | ~$1/mo ⚠ | alive, quiet |
| Matter | SaaS (iOS) | pick (bulk-send merge) | email | merged ebook, chapter/article | $60/yr premium | active |
| Polyreader | SaaS | pick | email | per-article + collections | ~$1/mo ⚠ | active, new |
| Amazon Send to Kindle | platform | pick (manual) | email/web/app | converts EPUB→AZW3/KFX | free | active |
| Kindle Periodicals | platform | n/a | native | sectioned newspapers | — | **dead 2023** |
| KOReader News Downloader | on-device | auto | on-device fetch | per-feed HTML files | free | active (plugin stagnant) |
| Pocket | SaaS | save | (had Kindle paths) | — | — | **dead 2025** |
| Omnivore | OSS/SaaS | save | — | — | — | **dead 2024** |

---

## 1 · Open-source / self-hosted

### KindleEar — the incumbent

- **Repo:** <https://github.com/cdhigh/KindleEar> — 2,843 ★, last push 2026-04-23 (prior: 2026-01-31, 2025-09-15 — alive, slow cadence, only 3 open issues). Last tagged release [3.3, 2024-12-25](https://github.com/cdhigh/KindleEar/releases); a 3.3.1 image exists on [Docker Hub](https://hub.docker.com/r/kindleear/kindleear). MIT.
- **What it does:** aggregates RSS/Atom/JSON and scraped web content into EPUB/MOBI with images and TOC, **pushed by email to `@kindle.com` on a daily schedule**. The Docker version adds an e-ink-optimized online reader. Rewritten for Python 3 after Google App Engine dropped Python 2; now targets Docker/VPS/GAE ([readme](https://github.com/cdhigh/KindleEar/blob/master/readme.md), [MobileRead "KindleEar has been reborn"](https://www.mobileread.com/forums/showthread.php?t=360906)).
- **Feature set (the high-water mark for OSS):** consumes **Calibre recipes unmodified, ~1,000 built in**; browser extension that scrapes arbitrary sites into recipes; **AI article summarizer** (since v3.2, Nov 2024 — Gemini/Grok/Mistral/Groq); bilingual translation; TTS audio ([FAQ](http://cdhigh.github.io/KindleEar/English/faq.html)).
- **Curation:** auto — a recipe/feed produces, KindleEar sends. No per-article picking anywhere in the model.
- **Weaknesses:** Docker DB-persistence foot-gun (database lost on container stop without a volume) and gunicorn `WORKER TIMEOUT` tuning ([deployment docs](http://cdhigh.github.io/KindleEar/English/deployment.html), [community image notes](https://github.com/coekfung/KindleEar-Docker)); bring-your-own SMTP; docs/UI Chinese-first with English translation; manual VPS install "complex and not recommended" per its own docs.

### Calibre "Fetch news" + recipes

- **Docs:** <https://manual.calibre-ebook.com/news.html> (calibre 9.x, actively maintained). Hundreds of bundled recipes; full-content feeds work nearly zero-config; recipe authoring is Python.
- **Delivery:** can email scheduled news to `@kindle.com` ("Sharing books by email") — but **the desktop app must be left running** ([HowToGeek](https://www.howtogeek.com/115178/how-to-convert-news-feeds-to-ebooks-with-calibre/), [XDA](https://www.xda-developers.com/kindle-set-up-daily-news/), [MobileRead](https://www.mobileread.com/forums/showthread.php?t=359032)).
- **Headless workaround:** [bookfere/Calibre-News-Delivery](https://github.com/bookfere/Calibre-News-Delivery) runs Calibre inside GitHub Actions (53 ★, last push 2024-06-01) — from the Chinese "书伴/bookfere" Kindle ecosystem.
- **Weaknesses:** desktop-bound scheduling; dated-looking conversion defaults; EPUBs without an explicit charset get mangled by Amazon's converter (ISO-8859-1 assumption — [fix guide](https://blog.the-ebook-reader.com/2022/05/06/how-to-fix-formatting-issues-on-epubs-sent-to-kindles/)).

### Calibre-Web and Calibre-Web-Automated

- [janeczku/calibre-web](https://github.com/janeczku/calibre-web) — 17,480 ★, pushed 2026-05-24. Hot fork: [crocodilestick/Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated) — 5,742 ★, pushed 2026-03-11.
- Web UI over a Calibre library with a per-book **"Send to eReader/Kindle"** email button ([setup guide](https://www.nodinrogers.com/post/2021-04-03-how-to-enable-emailing-books-to-your-kindle-from-calibre-web/)).
- **Not a news pipeline:** no RSS ingestion. Relevant as evidence: send-to-Kindle email breakage is a recurring issue class ([calibre-web #2461](https://github.com/janeczku/calibre-web/issues/2461), [#2301](https://github.com/janeczku/calibre-web/issues/2301), [CWA #724](https://github.com/crocodilestick/Calibre-Web-Automated/issues/724)) — the approved-sender/SMTP dance trips users constantly.

### The news2kindle script graveyard

Dozens of single-user scripts on GitHub; the pattern is cron + hardcoded feed list + EPUB/MOBI build + SMTP, no UI, no read tracking, eventual bitrot:

| Repo | Shape | Status |
|---|---|---|
| [anteprandium/news2kindle](https://github.com/anteprandium/news2kindle) | Docker, RSS→MOBI→email | 54 ★, last push 2021-05-04 |
| [gabrielconstantin02/kindle-newspaper](https://github.com/gabrielconstantin02/kindle-newspaper) | RSS→EPUB/MOBI→daily email | stale |
| [MrPike/RSS2Ebook](https://github.com/MrPike/RSS2Ebook) | pandoc, single feed→ePub/PDF/docx | stale |
| [gonejack/rss-epub](https://github.com/gonejack/rss-epub) | CLI | stale |
| [dhvcc/rss-reader](https://github.com/dhvcc/rss-reader) | CLI→epub | stale |
| [punchagan/r2k](https://github.com/punchagan/r2k) | rss2email-based | 2015 |
| jobleier/feed2ebook, [lazzarello/rss-epub-archiver](https://github.com/lazzarello/rss-epub-archiver) | misc | stale |

**Still spawning in 2026** — demand persists, nothing has won: kunalsojatia/send-newsletters-to-kindle ("zero-maintenance pipeline… native EPUBs… strict HTML sanitization", updated 2026-04-26), [rymc/rss-kindle](https://github.com/rymc/rss-kindle) ("self-hosted Kindle-friendly reading interface for FreshRSS", 2026-04-05), zzzdrv/calibre-news-to-kindle (2026-01-13), diegoqueres/newsletter-to-kindle-legacy (2026-04-14). Also notable: [KindleRSS](https://kindle.hluvmiku.tech/en/) — the "no server, just GitHub Actions" pattern with image optimization and full-text extraction.

### Wallabag

- <https://github.com/wallabag/wallabag> — 12,770 ★, pushed 2026-06-11 (very active). Self-hosted read-it-later.
- **Native EPUB/MOBI/PDF export** of saved articles ([since 1.9](https://wallabag.org/news/wallabag-1-9-many-features/)) — but **no built-in send-to-Kindle**: that request is [ten years open (#770)](https://github.com/wallabag/wallabag/issues/770).
- Community sidecars do email delivery by tag: [janLo/wallabag-kindle-consumer](https://github.com/janLo/wallabag-kindle-consumer) (48 ★, pushed 2023-12-31), dschoepe/wallabag-kindle (auto-MOBI-email per saved article). Both stale.
- **Curation:** saving is picking — but export is per-article or whole-archive; **no "compose N articles into one digest" flow.**

### Miniflux and FreshRSS

- [Miniflux v2](https://github.com/miniflux/v2) — 9,340 ★, pushed 2026-06-11. **No Kindle integration**; Send2Kindle proposed and not implemented ([#228](https://github.com/miniflux/v2/issues/228)). Sidecar [lucaswilric/miniflux-epub](https://github.com/lucaswilric/miniflux-epub) ("epub of your unread entries") — 8 ★, pushed 2022-06-02. Some users restyle Miniflux CSS for the Kindle browser ([writeup](https://red734.com/self-hosted-rss-reading-infrastructure/)).
- [FreshRSS](https://github.com/FreshRSS/FreshRSS) — 15,276 ★, pushed 2026-06-11. No Kindle feature; open idea issue ([#2516](https://github.com/FreshRSS/FreshRSS/issues/2516)). The gap is filled by DIY blog posts: ["Creating Your Own Kindle Newspaper"](https://danpker.com/posts/creating-your-own-kindle-newspaper/), ["From RSS to my Kindle"](https://olano.dev/blog/from-rss-to-my-kindle/) ([HN thread](https://news.ycombinator.com/item?id=40773125)).
- **Takeaway:** the two biggest self-hosted readers punt on Kindle entirely — adjacency, not competition (both expose APIs usable as future ingestion sources).

### EpubPress

- <https://epub.press/> — Chrome/Firefox extension: open articles in tabs, select and order them, receive **one merged EPUB** (or .mobi), downloaded **or emailed including to `@kindle.com`** (sender whitelisting required). Free/donation-funded.
- The closest existing match to a hand-picked digest UX — but **tab-based, not feed-based**: no subscriptions, no archive, no schedule.
- **Status:** server repo [haroldtreen/epub-press](https://github.com/haroldtreen/epub-press) last pushed 2023-10-10 (336 ★); the community fork **[EpubPressX](https://chromewebstore.google.com/detail/epubpressx-read-the-web-o/akgkfegkiajbamekmkcafnfckmhgcnpa)** exists specifically to build books locally because the hosted compile server was dying. [HN launch, 2016](https://news.ycombinator.com/item?id=11400769). Semi-abandoned.

### Kindle-browser readers (adjacent)

- [kinss](https://github.com/xizeyoupan/kinss) — Reabble clone for the Kindle browser, **archived May 2024**.
- [inkfeed](https://github.com/adhamsalama/inkfeed) — FOSS Kindle-browser RSS reader, 20 ★, pushed 2026-06-02.
- These read *in* the e-ink browser rather than producing documents — a different answer to the same itch.

---

## 2 · Commercial / SaaS

### Push to Kindle (FiveFilters)

- <https://www.pushtokindle.com/> — browser extensions, iOS/Android apps, and an [email-a-link service](https://www.fivefilters.org/push-to-kindle/email/). Sends a cleaned single article from `kindle@fivefilters.org` to your `@kindle.com` address ([help](https://help.fivefilters.org/push-to-kindle/)).
- **Pricing:** free = 10 articles/month; Premium **$2.99/mo** unlimited. Can also target the Kindle app, Apple Books, PocketBook, Dropbox.
- **Curation:** inherently manual — but **one article = one Kindle document**: no subscriptions, no digest, home-screen clutter.
- **Status:** active; FiveFilters also wrote the canonical post on [Kindle EPUB support](https://www.fivefilters.org/2022/kindle-epub-support/). KTool's founder cites Push to Kindle's "multiple limitations" as the reason KTool exists.

### KTool — the closest commercial analogue

- <https://ktool.io/> — "send web articles, newsletters and RSS feeds to your Kindle." Extensions (Chrome/Safari/Firefox/Brave) + iOS/Android. Email delivery; ad/boilerplate cleaning; auto-TOC detection; special handling for HN threads, Twitter, Wikipedia, Markdown, DOCX, PDF ([HN-to-Kindle page](https://ktool.io/hacker-news-to-kindle)).
- **Feature timeline** ([changelog](https://dev.ktool.io/changelog)): **Personal Magazines/Periodicals** — daily/weekly compiled digests you add articles to (Oct 2022); **RSS subscriptions** (Dec 2022); **Custom Magazine builder** (Mar 2023); newsletter inbox with 100+ format parsers. ⚠ The marketing homepage still shows RSS "coming soon" in places while the changelog/pricing confirm it shipped — messy site, live feature.
- **Pricing** ([pricing page](https://ktool.io/pricing)): **no free tier**, 7-day trial. Basic $4.99/mo ($36/yr) = unlimited single articles; Premium $6.99/mo ($48/yr) = custom digests/magazines + newsletters; Platinum $10/mo ($72/yr) = EPUB downloads, document sending, full-text search, unlimited retention.
- **Significance:** RSS + pick-into-magazine + Kindle is exactly this project's shape — closed-source, cloud-only, $48–72/yr. Changelog appears to stop at April 2023 → development slowed.

### ReadBetter

- <https://www.readbetter.io/> — converts articles/newsletters to "Kindle native format," **bundles multiple items into one e-book** ("custom digests & magazines"), and markets **preservation of color images, charts, and graphs** as a differentiator ([vs Amazon's own service](https://www.readbetter.io/faq/how-is-readbetter-different-from-amazons-own-send-to-kindle-service)). Substack-focused landing pages ([Substack on Kindle](https://www.readbetter.io/read-substack-on-kindle)).
- **Pricing** ([FAQ](https://www.readbetter.io/faq/how-much-does-readbetter-cost)): Free = 3 items/month; Plus $6.99/mo (10/month); Unlimited $9.99/mo ($83.88/yr).
- **Status:** active. Priciest per feature; no self-host, no API.

### Reabble / Kindle4RSS / QiReader (one developer, "oxyry")

- **[Reabble](https://reabble.com/)** (© 2013–2025): RSS reader running **inside the Kindle's e-ink browser**, backed by an Inoreader account; includes [send-to-kindle](https://send.reabble.com/) via `send@reabble.com`. ⚠ Pricing reports conflict: 15 articles/day free, ~$0.90–0.99/mo unlimited per 2016-era coverage ([GoodEReader](https://goodereader.com/blog/electronic-readers/amazon-kindle-gets-a-brand-new-rss-reader), [Gigazine](https://gigazine.net/gsc_news/en/20160830-reabble/)) — unverified today. [Repo](https://github.com/oxyry/reabble) is just a landing page (2020).
- **[Kindle4RSS](https://kindle4rss.com/)** (© to 2026; China mirror inkread.com): scheduled magazine-style daily RSS bundles emailed to Kindle, full-text extraction; premium ≈$2.9/mo for daily delivery + >25 feeds. The subject of Ben Kuhn's ["The best RSS reader is Kindle4RSS"](https://www.benkuhn.net/krss/) — praised precisely for the **distraction-free bounded daily bundle**; noted limits: 1×/day sync ceiling, and (aside) Instapaper's Kindle delivery "randomly failed to actually deliver articles on many days."
- **[QiReader](https://www.qireader.com/)** — advertised by Kindle4RSS as its "next-gen RSS to Kindle service" ([repo](https://github.com/oxyry/qireader) pushed 2026-04-02); subscriptions ~$1–3/mo incl. "Kindle automatic push" ⚠ (per [AlternativeTo](https://alternativeto.net/software/qireader/about/)). Kindle4RSS is alive-but-legacy.
- **Curation:** feed-level only across all three — auto-bundles, no article picking.

### Instapaper

- Send to Kindle = scheduled EPUB digests of your saved articles, emailed to `@kindle.com`. **Paywalled since Feb 19, 2025**: requires Premium **$5.99/mo / $59.99/yr**; the free tier lost Kindle delivery entirely ([GoodEReader](https://goodereader.com/blog/kindle/send-to-kindle-with-instapaper-is-now-going-to-cost-money), [HowToGeek](https://www.howtogeek.com/free-kindle-feature-is-about-to-be-put-behind-a-paywall/), [Premium page](https://www.instapaper.com/premium)).
- The CEO's stated rationale is this project's engineering spec in one sentence — digests are costly: "parsing articles, downloading images for each article, writing everything to disk, creating an ePub file, and emailing it," run "at a loss" for 100k+ digest signups ([Pocket-lint](https://www.pocket-lint.com/instapaper-send-to-kindle-going-behind-paywall/)). Reddit reaction ranged from "appalled fury" to willing-to-pay ([Android Police](https://www.androidpolice.com/your-amazon-kindle-is-losing-yet-another-free-feature/)).
- **Curation:** save-to-read-later = manual pick; digest assembly itself is automatic (the unread queue/folder), not per-issue composition. Delivery-reliability complaints predate the paywall (Ben Kuhn, above).

### Readwise Reader

- **Pricing:** $9.99/mo billed annually / $12.99 monthly, 30-day trial ([pricing](https://readwise.io/pricing), [2026 overview](https://www.readless.app/blog/readwise-reader-pricing-2026)).
- **Kindle features** ([docs](https://docs.readwise.io/reader/docs/faqs/exporting)): manual per-document "Send to Kindle," plus **automatic daily/weekly digest** of documents added to your Library. Crucially, **RSS feed items are excluded unless you move them to the Library** — Readwise made *triage-then-digest* the default flow. Digests go out midnight ET; weekly editions on Fridays.
- **Position:** the premium do-everything reading hub and main Pocket/Omnivore refugee destination; not Kindle-first, no self-hosting.

### Matter, Polyreader, Readry (the post-Pocket wave)

- **[Matter](https://hq.getmatter.com/updates/matter-kindle):** free read-later; **$60/yr Premium** includes Send to Kindle, newsletter sync, RSS; bulk-send **merges multiple selected articles into one ebook with a chapter per article** ([pricing overview](https://www.readless.app/blog/matter-app-pricing-2026)). iOS-centric.
- **[Polyreader](https://polyreader.app/):** extension + iOS, one-click article→Kindle with "collections"; ~$1/mo ⚠ per [HN commenters](https://news.ycombinator.com/item?id=47541969).
- **Readry:** Substack→Kindle forwarding (mentioned in the same HN thread).
- Confirms steady new *commercial* entry; all closed-source, all email-delivery.

### The dead pool (context for the whole category)

- **Omnivore** — open-source read-it-later, shut down Nov 30, 2024 after the ElevenLabs acqui-hire; Readwise and Instapaper shipped dedicated importers ([migration guide](https://molodtsov.me/2024/10/omnivore-is-dead-where-to-go-next/), [alternatives](https://danielprindii.com/blog/read-it-later-alternatives-after-omnivore-shutting-down)).
- **Pocket** — shut down July 8, 2025 (exports until Oct/Nov 2025) ([Mozilla notice](https://support.mozilla.org/en-US/kb/future-of-pocket), [TechCrunch](https://techcrunch.com/2025/05/27/read-it-later-app-pocket-is-shutting-down-here-are-the-best-alternatives/), [alternatives roundup](https://web-highlights.com/blog/pocket-shuts-down-in-july-2025-the-10-best-alternatives/)).
- Net effect: within 14 months users lost two free/open options, and every surviving Kindle workflow became paid. The strongest tailwind a self-hosted free alternative could ask for.

---

## 3 · Native / platform substrate

### Amazon Send to Kindle (what everyone builds on)

- **Supported types** ([help page](https://www.amazon.com/gp/help/customer/display.html?nodeId=G5WYD9SAF7PGXRNA)): PDF, DOC(X), TXT, RTF, HTM(L), PNG/GIF/JPG/BMP, **EPUB**. EPUB accepted since mid/late 2022; **MOBI/AZW dropped from personal docs Aug 2022** ([coverage](https://blog.the-ebook-reader.com/2022/05/03/amazon-dropping-mobi-support-on-send-to-kindle-apps/), [FiveFilters](https://www.fivefilters.org/2022/kindle-epub-support/)) — never ship MOBI. Amazon converts EPUB→AZW3/KFX internally.
- **Email gateway limits** ([help page](https://www.amazon.com/gp/help/customer/display.html?nodeId=G7NECT4B4ZWHQ8WV)): **50 MB per email, 25 attachments, max 15 approved sender addresses** (sender must be whitelisted in Personal Document Settings). [Web upload](https://www.amazon.com/sendtokindle) allows 200 MB.
- **Converter quirk:** charset defaults to ISO-8859-1 if the EPUB doesn't declare UTF-8 ([fix guide](https://blog.the-ebook-reader.com/2022/05/06/how-to-fix-formatting-issues-on-epubs-sent-to-kindles/)).
- **Programmatic option:** no official public API. [stkclient](https://github.com/maxdjohnson/stkclient) (Python) speaks the private Send-to-Kindle HTTP API with OAuth2 — avoids email limits, lists devices — but 21 ★, last push 2023-05-03, unofficial and fragile ([docs](https://stkclient.readthedocs.io/)). Everyone serious uses SMTP.

### Kindle Periodicals / Newsstand — dead

- Amazon stopped selling new newspaper/magazine subscriptions March 9, 2023 and ended delivery of existing Kindle subscriptions Sept 4, 2023 ([Nieman Lab](https://www.niemanlab.org/2023/03/goodbye-newspapers-on-kindle-amazon-stops-selling-newspaper-and-magazine-subscriptions/), [GoodEReader](https://goodereader.com/blog/electronic-readers/amazon-will-discontinue-newspaper-and-magazine-subscriptions-in-september)).
- The sectioned periodical AZW format with real section→article navigation died with it; personal documents are plain ebooks. **No first-party "wake up to today's paper" experience has existed for ~3 years** — the emotional job-to-be-done every tool in this document is chasing.

### KOReader + News Downloader

- [KOReader](https://github.com/koreader/koreader) — 27,220 ★, pushed 2026-06-11, extremely active. Runs on jailbroken Kindles, Kobos, PocketBooks, Android, and more.
- The bundled [News Downloader plugin](https://github.com/koreader/koreader/wiki/News-downloader): RSS/Atom → local **HTML files** per feed; optional full-article scraping that "may not always work correctly"; configuration is a Lua table edited by hand. A rebuild to output EPUB has been an [open feature request since 2022 (#9225)](https://github.com/koreader/koreader/issues/9225); a community [QuickRSS plugin](https://www.mobileread.com/forums/showthread.php?t=372354) exists.
- On Kindle this requires **jailbreak** — "Not all Kindles can be jailbroken. It's a constant cat and mouse game" ([HN, Apr 2026](https://news.ycombinator.com/item?id=47541969)). On-device pull also means the e-reader does the slow fetching itself.
- **KOReader is also an OPDS client** — which makes any OPDS-serving app (like this one, post-M3) a delivery channel for every KOReader device.

### Xteink X4 + CrossPoint firmware

- The 2026 community-darling pocket e-reader ([Tao of Mac review](https://taoofmac.com/space/reviews/2026/04/04/1800), [CrossPoint 1.2.0 review](https://www.svartling.net/2026/04/xteink-x4-with-crosspoint-firmware-120.html)).
- **Stock firmware:** EPUB/TXT via USB/SD drag-and-drop, a **LAN Wi-Fi upload page** (device runs a small web server; ~10 MB per 30 s), or the XT Cloud app (pushes to a "PUSHED BOOKS" folder) ([import guide](https://bluehayden.substack.com/p/how-to-import-books-to-xteink-x4)).
- **[CrossPoint firmware](https://github.com/crosspoint-reader/crosspoint-reader)** (open source, Xteink X3/X4): ships an **OPDS browser** — up to 8 saved servers, search, pagination, direct download — plus a Calibre wireless-connect flow ([two-ways walkthrough](https://www.ereadersforum.com/threads/two-ways-to-send-books-wirelessly-from-calibre-to-the-xteink-x4.13111/), [user guide](https://github.com/crosspoint-reader/crosspoint-reader/blob/master/USER_GUIDE.md)).
- **Implication:** serving OPDS makes this project natively compatible with the entire KOReader + CrossPoint device class, no Amazon account anywhere in the loop.

---

## 4 · Feature menu observed across the field

Features that exist somewhere in the landscape, with who does them — a checklist of what users have been taught to expect (✓ = in our 1.0 spec, ◇ = spec cut-line/future, ✗ = explicit non-goal):

| Feature | Who does it | Us |
|---|---|---|
| Email push to `@kindle.com` | KindleEar, KTool, ReadBetter, Instapaper, Readwise, Kindle4RSS, PTK, Calibre(-Web), Matter | ✓ M3 |
| Scheduled/automated delivery | KindleEar (daily), Kindle4RSS (daily), Instapaper, Readwise (daily/weekly), KTool magazines | ✓ M4 ("press deadline", queue-driven) |
| Hand-pick articles into one bundle | KTool Custom Magazines, ReadBetter digests, Matter bulk-send, EpubPress (tabs) | ✓ core |
| Full-text extraction from partial feeds | KindleEar, Kindle4RSS, KTool, KindleRSS | ✓ exists (trafilatura) |
| Boilerplate/ad cleaning | KTool, PTK, ReadBetter, all read-laters | ✓ M2 (sanitizer allowlist) |
| Images preserved + optimized | ReadBetter (markets it), KindleEar, KindleRSS | ✓ M2 (downscale + budget) |
| Real TOC / sectioned navigation | KindleEar, Kindle4RSS ("easy-to-navigate ToC"), KTool (auto-TOC) | ✓ M2 (sections by feed) |
| Cover page / issue identity | Kindle Periodicals (dead), partially KindleEar | ✓ M2 |
| OPDS catalog serving | Calibre content server; clients: KOReader, CrossPoint | ✓ M3 |
| OPML import/export | Miniflux, FreshRSS, most readers | ✓ M5 |
| Read-state tracking | Miniflux, FreshRSS, read-laters | ✓ M5 (web UI only) |
| Newsletter ingestion (inbox address, parsers) | KTool (100+ formats), ReadBetter, Readwise | ✗ future (kill-the-newsletter interop) |
| AI summaries | KindleEar v3.2 (Gemini/Grok/Mistral/Groq) | ✗ future-maybe |
| Translation | KindleEar (bilingual) | ✗ |
| TTS audio | KindleEar | ✗ |
| Calibre recipe compatibility | KindleEar (~1,000 recipes), Calibre | ✗ (different model; OPML covers feeds) |
| Browser-extension clipper | PTK, KTool, ReadBetter, EpubPress, Polyreader | ✗ future |
| Special-source rendering (HN threads, Twitter, Wikipedia) | KTool | ◇ future |
| E-ink browser web reader | Reabble, KindleEar online reader, inkfeed, rymc/rss-kindle | ✗ (we ship documents, not a reader) |
| Highlights/clippings round-trip | Readwise ecosystem (via My Clippings export) | ✗ research item |
| Read-state sync back from device | **nobody** | ✗ research item |
| Send-to-Kindle private API (no email) | stkclient (unmaintained) | ✗ rejected |
| GitHub Actions as the scheduler | Calibre-News-Delivery, KindleRSS | ✗ (we have a server) |

---

## 5 · Verification notes

- Stars and `pushed_at` dates: GitHub API, 2026-06-11 — point-in-time accurate.
- ⚠-marked items could not be fully verified: Reabble's current pricing (sources are 2016-era), QiReader/Polyreader pricing (third-party listings/HN comments), KTool homepage vs changelog inconsistency on RSS.
- One aggregator misdates Instapaper's paywall to 2026; the announcement and cutover were Jan–Feb 2025 — the 2025 date is used here.
- Xteink/CrossPoint findings were verified separately on 2026-06-11 (firmware repo, user guide, reviews, transfer guides) during spec design.
