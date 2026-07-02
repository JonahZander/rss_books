# Design language

The web UI is a **print shop, not a dashboard**: the metaphor is a newspaper
composing room: hairline rules, mono labels on data, one accent ink. The
metaphor lives in structure and type, never in decoration; contributions
should read like they came off the same press.

## Tokens

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#f2f1ec` | Background (warm off-white) |
| `--paper-2` | `#e9e7e0` | Raised surfaces, active rows |
| `--paper-3` | `#dedcd3` | Deep surfaces |
| `--ink` | `#0e0f11` | Primary text, solid buttons, rules |
| `--ink-2` | `#2a2b2e` | Body copy |
| `--ink-3` | `#55554f` | Secondary text, eyebrows |
| `--mute` | `#8a8983` | Disabled/placeholder |
| `--hairline` | `#c4c2b9` | Soft 1px separators |
| `--rule` | `#1a1b1e` | Hard 1px rules (section heads) |
| `--amber` | `#c97a1e` | The single accent: queue state, active nav, deadlines |
| `--danger` | `#a03a2a` | Errors, destructive actions |

The body background is plain paper — no grid/texture overlays.

## Type

| Face | Variable | Role |
|---|---|---|
| **Archivo** (500/700/900) | `--font-display` | Masthead, headings, article titles; 900 uppercase for mastheads |
| **IBM Plex Sans** (300/400/500) | `--font-body` | Body copy, summaries |
| **JetBrains Mono** (400/500) | `--font-mono` | Eyebrows, counters, buttons, metadata; always uppercase + letterspaced for labels |

Eyebrow pattern: `NN - Section name` in mono, 10–11px, `0.14em` tracking,
uppercase. Numbers are tabular (`tnum`) everywhere.

## Rules of composition

- **Sharp corners.** `border-radius: 0`, no exceptions.
- **1px rules, not boxes.** Sections separate with `--rule` underlines;
  rows with `--hairline`. Borders are structure, not decoration.
- **One accent.** Amber means "queued / armed / scheduled". Don't introduce
  new accent colors; errors use `--danger` only.
- **No decorative marks.** No registration `+` glyphs, corner marks, fake
  model numbers, or grid textures; ornament that organizes nothing is noise.
- **Left-edge indicators.** Hover/active/queued states show as a 2px left
  bar (`::before`), ink for active, amber for queued.
- **Numbers on data.** Indexes (`01/12`), counters, refs (`#0004`), all
  padded, mono, tabular — but section eyebrows are plain labels, never
  numbered ("Configuration", not "05 - Configuration").

## Motion

Easing is always `cubic-bezier(0.2, 0.7, 0.2, 1)`: quick out, no bounce.
Durations 120–500ms. Established moves:

- rows stagger in (`rowIn`, 26ms/index, capped at 12)
- masthead readouts pop on change (`valuePop`)
- queued rows flash amber on the left rule (`queuedFlash`)
- toasts slide from the right; dialogs rise 8px
- button arrows nudge on hover; buttons sink 1px on press
- active nav underline draws in from the left

Everything must stay usable under `prefers-reduced-motion: reduce` (a global
override disables animation, so keep state changes visible without it).

## Accessibility

- `:focus-visible` = 2px ink outline (amber on dark surfaces), offset 2px
- hit targets ≥ 24px (checkboxes wrapped in `.checkbox-hit`)
- landmarks: `header`, `nav`, `main`, `aside`/`section` with `aria-label`s
- toasts render into an `aria-live="polite"` region

## The EPUB is part of the design

The edition itself follows the same language translated to e-ink: serif body
(reader's font wins), mono code, hairline rules, the cover in paper/ink/amber.
See `services/api/src/rss_kindle/services/epub_builder.py` (stylesheet) and
`cover.py`.
