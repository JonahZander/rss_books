# Roadmap — future improvement ideas

Consolidated from the open items in the review docs, the "future-maybe" rows of
the v2 spec, and loose ends from recent working sessions. This is the idea
backlog, not a commitment; items graduate into a spec/plan before being built.

Last updated: 2026-07-03.

## Polish backlog (near-term, small–medium)

> **Status 2026-07-04:** shipped (see CHANGELOG *Unreleased*) — every item in
> this section, including the "Consider" tier, rendering, and onboarding,
> except *"verify rotated chunk order on device"*, which needs the physical
> X4 in hand.

Security/robustness first — these are the live backlog from
[`ux-and-optimization-review.md`](ux-and-optimization-review.md) (IDs kept):

- **BE-1** SSRF guard: block private-range/scheme targets on server-side
  fetches (feeds, articles, images).
- **BE-2** Move blocking CPU/disk work (EPUB build, image recompression)
  off the event loop (thread/process pool).
- **BE-5** OPDS *download* links must honour OPDS Basic auth.
- **BE-6** Decompression-bomb guard on image fetches.
- **BE-7** Manual refresh should use conditional GET and not double-write
  feed health.
- **BE-8** Press deadline: record "last run" only after a successful compile.
- **FE-1** Cancel in-flight list requests so stale responses can't clobber
  newer ones.
- **UX-8** Feed/queue row tools are hover-only — unusable on touch.
- **UX-9** After compiling, link straight to the new edition.
- Plus the "Consider" tier of the same review: queue reordering (UX-6),
  per-feed poll interval UI (UX-11), failing-feed retry affordance (UX-12),
  mark-unread/mark-all-read (UX-13), import skip reporting (UX-15).

Rendering / edition quality (from the Xteink device-fit sessions, 2026-07):

- **Cover title type size**: bump the cover's title/feed text so it stays
  legible at e-ink scale (user-observed: "a bit too little" on the X4).
- **Kindle photo-width clamp**: when a profile sets screen dims, photos scale
  to 2× width — add an upper clamp (~1600px) so a high-res Kindle profile
  doesn't inflate editions.
- **Verify rotated chunk order on device**: rotation is now clockwise with the
  block start first; if on-device reading order still feels wrong, reverse the
  chunk order in the HTML as the next lever.
- **epubcheck in CI** against a fixture edition, so EPUB regressions surface
  before a device does.

Onboarding (deferred pending a design decision, review Tier 1):

- **UX-1** First-run onboarding: a guided path from empty desk to first
  edition.
- **UX-2** Make the send-to-Kindle path discoverable before SMTP is
  configured.

## Bigger future-maybes (from the v2 spec non-goals)

- **Newsletter ingestion** (today: kill-the-newsletter → RSS interop).
- **Read-state sync back from the device** — KOReader sync remains the
  research item.
- **Full-text search index** when `LIKE` stops being enough.
- **AI summaries / recommendations** — explicitly after the curation-first
  identity is settled, if ever.
- Multi-user/auth and hosted SaaS remain non-goals.

## Distribution

- Make the GHCR package + repo public in the same motion; verify a
  pull-only deploy on a Proxmox Docker host end to end.
- Consider a screenshot-refresh script (seeded demo DB + Playwright) so the
  README gallery stays cheap to keep current.
