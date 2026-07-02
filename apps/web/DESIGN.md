# DESIGN.md - RSS-to-Kindle Selector

> **Purpose:** This is the design-system anchor for Google Stitch. Every generated
> screen MUST conform to the values below. When in doubt, prefer *fewer, sharper,
> darker* over *more, softer, lighter*. This is a technical, sci-fi instrument
> panel, not a friendly consumer app.

---

## 1. Mood & Principles

A sleek, dark, terminal-grade reading console. Think a mission-control HUD for
your reading queue: angular, quiet, precise, with thin **pink and blue**
retrofuturistic accent lines that glow against near-black. Restraint is the rule
- color is information, not decoration. The chrome stays monochrome and
structural; the pink/blue only appears to signal state, focus, or action.

Inspired by the Nous Research / Hermes agent aesthetic (dark, technical,
monospace-flavored, terminal/sci-fi) but it must NOT be a clone: Hermes leans
amber/teal on black; **we are pink + blue**, and we are more angular and more
minimal.

**Five rules:**
1. **Angular, never soft.** Sharp 0px corners almost everywhere. No drop-shadow puffiness.
2. **Lines do the work.** Structure is communicated with thin 1px hairlines and grids, not fills or shadows.
3. **Color = signal.** Pink and blue glows mark interactive/active/important state only. Idle UI is grayscale.
4. **Monospace for data, grotesque for prose.** Metadata, counts, timestamps, labels are mono; article body/titles are sans.
5. **Calm darkness.** Generous negative space on a deep void background; let content breathe between hairlines.

---

## 2. Color Palette

### Base (the void): use 90% of the time
| Token | Hex | Use |
|---|---|---|
| `--bg-void` | `#08090C` | App background, deepest layer |
| `--bg-surface` | `#0E1015` | Cards, panels, sidebar |
| `--bg-raised` | `#14171E` | Hover rows, popovers, inputs |
| `--bg-inset` | `#05060A` | Recessed wells, code/preview areas |

### Lines & text (monochrome structure)
| Token | Hex | Use |
|---|---|---|
| `--line` | `#1E222B` | Default 1px hairline borders, grid lines |
| `--line-strong` | `#2C3240` | Emphasized dividers, table header rule |
| `--text-primary` | `#E8EBF0` | Headings, body text |
| `--text-secondary` | `#9AA3B2` | Labels, secondary copy |
| `--text-muted` | `#5A6373` | Metadata, timestamps, placeholder |

### Accents: pink + blue (signal only)
| Token | Hex | Use |
|---|---|---|
| `--accent-blue` | `#3D8BFF` | Primary actions, focus rings, active nav, links |
| `--accent-blue-dim` | `#1E4E99` | Inactive/border variants of blue |
| `--accent-pink` | `#FF4D9D` | Highlights, selection, "queued"/important, hot CTAs |
| `--accent-pink-dim` | `#99245E` | Inactive/border variants of pink |
| `--accent-cyan` | `#5FE3FF` | Rare tertiary accent / hover sparkle on blue |

### Status
| Token | Hex | Use |
|---|---|---|
| `--ok` | `#3DE0A0` | Success / sent to Kindle |
| `--warn` | `#FFB347` | Pending / needs attention |
| `--err` | `#FF5C5C` | Failed / errors |

**Gradient lines (the signature motif):** thin 1px–2px rules and underlines may
use a linear gradient from `--accent-pink` → `--accent-blue`
(`linear-gradient(90deg, #FF4D9D 0%, #3D8BFF 100%)`). Use sparingly: top edge of
the active panel, the digest-queue header, the primary button border.

---

## 3. Typography

Two-font system. Pull both from Google Fonts.

- **Sans (UI + prose):** `Space Grotesk` for headings, article titles, and body. Weights 400 / 500 / 700.
  - Fallback stack: `"Space Grotesk", "Inter", system-ui, sans-serif`
- **Mono (data + chrome):** `JetBrains Mono` for labels, metadata, counts, timestamps, feed URLs, nav items, table column headers, buttons.
  - Fallback stack: `"JetBrains Mono", "IBM Plex Mono", monospace`

**Rules:**
- All chrome labels, nav, and metadata: mono, `UPPERCASE`, `letter-spacing: 0.08em`, size 11–12px, color `--text-muted`.
- Article titles: Space Grotesk 500, 16–18px, `--text-primary`.
- Body/excerpt: Space Grotesk 400, 14px, `--text-secondary`, line-height 1.6.
- Numerals (counts, unread badges): JetBrains Mono; the tabular feel reinforces the instrument vibe.

**Type scale (px):** 11 · 12 · 14 · 16 · 18 · 22 · 28 · 36.

---

## 4. Spacing & Grid

- **Base unit: 4px.** Scale: `4, 8, 12, 16, 24, 32, 48, 64`.
- **Layout:** Fixed left sidebar (feeds/nav), main content column, optional right rail (digest queue). Panels sit edge-to-edge separated by 1px `--line` hairlines, with **gap: 0 between adjacent structural panels** and internal padding of 16–24px.
- A faint background grid is encouraged on empty/hero areas: 1px `--line` lines on a ~32px grid at very low opacity (~`#12151C`), evoking graph paper / a HUD.
- Content max-width for reading lists: 760–900px; never full-bleed prose.

---

## 5. Borders, Corners & "Angular" Treatment

- **Corner radius: `0px`** for cards, buttons, inputs, tables, panels. Sharp by default.
- Optional signature flourish: **notched/clipped corners** on key cards (cut a 45° corner via `clip-path: polygon(...)`, ~10–12px notch); use on the primary CTA card and the "current edition" card only. Don't notch everything.
- Borders are **1px solid `--line`**. Active/focused elements get a 1px `--accent-blue` border. Selected items get 1px `--accent-pink` (or a left 2px pink bar).
- No rounded pills, no soft chips. Tags/badges are sharp rectangles with a 1px border.

---

## 6. Elevation & Glow

There are no soft material shadows. "Elevation" is expressed with **glow** and **hairline contrast**, not blur-drop shadows.

- **Glow (focus/active only):** `box-shadow: 0 0 0 1px <accent>, 0 0 12px -2px <accent>` where `<accent>` is `--accent-blue` for focus and `--accent-pink` for selection/important. Keep glow tight and low-opacity; it should feel like a backlit edge, not a halo.
- **Popovers/modals:** `--bg-raised` surface, 1px `--line-strong` border, plus a faint outer ring `0 0 0 1px #000`. A backdrop of `rgba(5,6,10,0.7)`.
- **Scanline overlay (optional, subtle):** a full-viewport `repeating-linear-gradient(rgba(255,255,255,0) 0 2px, rgba(255,255,255,0.015) 2px 3px)` for texture. Keep it nearly invisible; it's a whisper, not a CRT.
- **Text glow:** reserve for the active nav item and primary headings only: `text-shadow: 0 0 8px rgba(61,139,255,0.4)`.

---

## 7. Component Guidance

**Sidebar (feeds / nav)**
- `--bg-surface`, 1px right border `--line`. Width ~240px.
- Nav items: mono uppercase, 12px, `--text-muted`. Active item: `--text-primary` + 2px left bar in pink→blue gradient + subtle blue text-glow.
- Unread counts right-aligned, JetBrains Mono, `--text-secondary`, in a sharp bordered box.

**Article list (the core view)**
- Dense rows separated by 1px `--line`. Row hover: `--bg-raised`.
- Each row: title (Space Grotesk 500), source + timestamp (mono, `--text-muted`), and a star/queue action on the right.
- Selected row: 1px `--accent-pink` left bar + faint pink glow. "Queued for digest" rows get a pink dot/tag.

**Digest queue (right rail)**
- Panel header with a pink→blue gradient top rule and a mono uppercase title "DIGEST QUEUE / N ITEMS".
- Items as compact stacked cards, sharp corners, 1px border, draggable handles drawn as mono `::` glyphs.

**Buttons**
- *Primary:* transparent fill, 1px `--accent-blue` border, blue text, mono uppercase, sharp corners; hover adds the blue glow. The single most important CTA (e.g. "SEND EDITION") may use a pink→blue gradient 1px border.
- *Secondary:* 1px `--line` border, `--text-secondary` text.
- *Ghost:* no border, `--text-muted`, underline-on-hover (gradient underline).
- No filled solid-color buttons; this is a line-driven UI.

**Tables (editions / history)**
- Header row: mono uppercase, `--text-muted`, bottom border `--line-strong`. Body rows separated by `--line`. Zebra optional via `--bg-surface`/`--bg-void`. Status cells use status colors as small text + a leading colored square.

**Inputs / forms (settings)**
- `--bg-inset` field, 1px `--line` border, sharp corners. Focus: 1px `--accent-blue` border + blue glow. Labels above, mono uppercase 11px `--text-muted`. Toggles are sharp rectangular switches that glow blue when on.

**Cards**
- `--bg-surface`, 1px `--line` border, 0 radius, 16–24px padding. Optional notched corner + gradient top rule for hero/primary cards only.

---

## 8. Iconography

- **Thin line icons, 1.5px stroke, sharp/geometric** (Lucide or Phosphor "thin"/"light"). No filled or rounded-bubble icons.
- Default icon color `--text-muted`; active icon `--accent-blue`; alert icon `--err`/`--warn`.
- Allowed decorative glyphs from the terminal vocabulary: `>`, `//`, `::`, `[ ]`, `▸`, `█` used in mono labels for a console feel (e.g. section headers like `// FEEDS`).

---

## 9. Motion

- Fast, mechanical, minimal. 120–180ms, `ease-out`. Hover glows fade in over ~120ms.
- Allowed: a 1px gradient line "sweep" on load for the active panel; a brief blue underline draw on focus. Avoid bouncy/spring easing and large slide-ins.

---

## 10. Do / Don't (for Stitch)

**Do:** near-black backgrounds, 1px hairlines, sharp corners, monospace metadata in uppercase, thin pink/blue accent lines and tight glows, generous spacing, line icons.

**Don't:** rounded cards, soft drop shadows, gradient *fills* over large areas, pastel or light backgrounds, emoji, filled candy-colored buttons, more than ~2 accent hits per screen, heavy CRT/scanline noise.
