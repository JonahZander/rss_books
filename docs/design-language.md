# Design language

The web UI is a **print shop with a signal running through it**: the structure
is a newspaper composing room — hairline rules, mono labels on data, sharp
corners — set on a crisp cool-white canvas, with a retrofuturistic dual accent
(blue and pink) carrying interaction state. The metaphor lives in structure and
type, never in decoration; contributions should read like they came off the
same press.

## Tokens

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#f2f4f7` | Background (crisp cool white) |
| `--paper-2` | `#e9ecf2` | Raised surfaces, active rows |
| `--paper-3` | `#dde1e9` | Deep surfaces |
| `--ink` | `#101828` | Primary text, solid buttons, rules |
| `--ink-2` | `#1d2939` | Body copy |
| `--ink-3` | `#475467` | Secondary text, eyebrows |
| `--mute` | `#98a2b3` | Disabled/placeholder |
| `--hairline` | `#d0d5dd` | Soft 1px separators |
| `--rule` | `#101828` | Hard 1px rules (section heads) |
| `--accent-blue` | `#3d8bff` | Primary action, nav, focus, links |
| `--accent-pink` | `#ff4d9d` | Selection, queued, "important" |
| `--danger` | `#a03a2a` | Errors, destructive actions |

`--amber` still exists as a **deprecated alias of `--accent-blue`** so legacy
references keep working; don't use it in new code.

The body background is plain paper — no grid/texture overlays.

### Accents

- **Blue** means "act / navigate / focus": buttons, active nav, links, focus
  on dark surfaces.
- **Pink** means "selected / queued / armed": queued rows, selection state,
  the compile pipeline.
- The **pink→blue gradient** (`linear-gradient(135deg, --accent-pink,
  --accent-blue)`) is the brand signature. It appears only on identity
  moments: the "Books" wordmark (`.brand-accent`), the logo mark's signal
  wave, and the occasional 1px gradient hairline border on hero buttons. It
  is not a general-purpose fill.
- **Glow shadows** (`--glow-blue`, `--glow-pink`) appear on hover / active /
  focus only — never at rest.

## Logo

`components/LogoMark.tsx` (mirrored in `app/icon.svg` on an ink tile): a
dog-eared folio outline in `currentColor` carrying the RSS quarter-wave and
dot in the signature gradient. Sharp corners, 5px strokes on a 64 grid. The
mark inherits ink in the masthead; contexts may restyle via `color`.

## Type

| Face | Variable | Role |
|---|---|---|
| **Archivo** (500/700/900) | `--font-display` | Masthead, headings, article titles; 900 uppercase for mastheads |
| **IBM Plex Sans** (300/400/500) | `--font-body` | Body copy, summaries |
| **JetBrains Mono** (400/500) | `--font-mono` | Eyebrows, counters, buttons, metadata; always uppercase + letterspaced for labels |

Eyebrows are plain mono labels, 10–11px, `0.14em` tracking, uppercase —
never numbered ("Configuration", not "05 - Configuration"). Numbers are
tabular (`tnum`) everywhere.

## Rules of composition

- **Sharp corners.** `border-radius: 0`, no exceptions.
- **1px rules, not boxes.** Sections separate with `--rule` underlines;
  rows with `--hairline`. Borders are structure, not decoration.
- **Two accents, two meanings.** Blue acts, pink selects. Don't introduce
  new accent colors; errors use `--danger` only.
- **No decorative marks.** No registration `+` glyphs, corner marks, fake
  model numbers, or grid textures; ornament that organizes nothing is noise.
- **Left-edge indicators.** Hover/active/queued states show as a 2px left
  bar (`::before`) — ink on hover, pink (with glow) for active/queued.
- **Numbers on data.** Indexes (`01/12`), counters, refs (`#0004`), all
  padded, mono, tabular.

## Motion

Easing is always `cubic-bezier(0.2, 0.7, 0.2, 1)`: quick out, no bounce.
Durations 120–620ms. Established moves:

- rows stagger in (`rowIn`, 26ms/index, capped at 12)
- masthead readouts pop on change (`valuePop`)
- queued rows flash pink on the left rule (`queuedFlash`)
- toasts slide from the right; dialogs rise 8px
- button arrows nudge on hover; buttons sink 1px on press
- active nav underline draws in from the left
- glows fade in with hover/focus, never linger at rest

Everything must stay usable under `prefers-reduced-motion: reduce` (a global
override disables animation, so keep state changes visible without it).

## Accessibility

- `:focus-visible` = 2px ink outline (blue on dark surfaces), offset 2px
- hit targets ≥ 24px (checkboxes wrapped in `.checkbox-hit`)
- landmarks: `header`, `nav`, `main`, `aside`/`section` with `aria-label`s
- toasts render into an `aria-live="polite"` region

## The EPUB is part of the design

The edition itself follows the same language translated to e-ink: serif body
(reader's font wins), mono code, hairline rules. The cover **deliberately
keeps the warm print palette** (paper `#f2f1ec`, ink `#0e0f11`, amber
`#c97a1e`) — e-ink is grayscale, so the cover optimizes for contrast and a
printed feel rather than matching the screen accents. See
`services/api/src/rss_kindle/services/epub_builder.py` (stylesheet) and
`cover.py`.
