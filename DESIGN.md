# Design system

The interface should make a reader trust the numbers before they read a word:
quiet, dense, typographically disciplined, nothing decorative. This document is
the contract. `static/design.css` is its implementation.

## Why it exists

Seven pages each carried their own copy of the palette, and they drifted. An
audit (`python scripts/design_audit.py`) measured what that produced:

| | Before | After |
|---|---|---|
| Emoji | 82 occurrences, 31 glyphs | **0** |
| Font sizes | **45 distinct** (15 between .78–.95rem) | 9-step scale |
| Colour literals | 84 hex + 11 rgba | tokens only |
| Spacing values | 46 distinct | 8-step grid |
| Border radii | 16 distinct | 4 |
| Token definitions | 35 names across 16 blocks | one file |

`--good` existed as three different greens. `--bg` as both `#fff` and
`#ffffff`. Divergence was inevitable because there was no shared definition to
diverge from.

## Rules

1. **Every page links `design.css` first**, then adds only page-specific
   layout. No page redefines a token — a test enforces this.
2. **One accent.** `--accent` carries the data story; grey carries all
   context. Semantic colour (`--pos`, `--neg`, `--warn`) appears only where a
   value is genuinely directional.
3. **One type scale.** Nine steps, no values between them. Serif for editorial
   headlines, grotesque for data and UI, tabular figures on every number.
4. **One spacing grid.** 8px base, eight steps. Hairlines over boxes,
   whitespace over borders.
5. **No emoji.** They render differently on every platform and carry colour
   nobody chose. Use the icon set.
6. **Maximise data-ink.** No gradients, no shadows on data, no chartjunk.
   Every chart states its finding in the title, not its subject.

## Tokens

Defined once in `:root`, with dark redefining only what must change.

**Surfaces** `--bg` `--surface` `--surface-2` `--overlay`
**Ink** `--ink` (headlines) `--ink-2` (body) `--ink-3` (secondary)
`--ink-4` (disabled) `--on-ink` (text on an ink surface — never plain white)
**Lines** `--rule` `--rule-2`
**Accent** `--accent` `--accent-ink` `--accent-soft`
**Directional** `--pos` `--neg` `--warn` (+ `-soft` tints), `--compare`
**Categorical data** `--c-teach` `--c-debt` `--c-other` `--c-no` `--c-yes`
`--c-focus` — chosen for distinguishability, not brand.

### Type

| Token | Size | Use |
|---|---|---|
| `--fs-micro` | 12px | eyebrows, badges, table micro-labels |
| `--fs-xs` | 13px | dense UI, table cells |
| `--fs-sm` | 14px | secondary text, captions |
| `--fs-base` | 15px | body |
| `--fs-md` | 16px | lead paragraphs |
| `--fs-lg` | 20px | h3, card headlines |
| `--fs-xl` | 24px | h2 |
| `--fs-2xl` | 30px | h1 |
| `--fs-display` | fluid | hero only |

Line height: `--lh-tight` 1.15 (headlines), `--lh-snug` 1.35 (subheads),
`--lh-body` 1.6 (prose). Weights: 400 / 500 / 700 only.

### Space and shape

`--s-1`…`--s-8` = 4, 8, 12, 16, 24, 32, 48, 64px.
`--r-sm` 4px · `--r-md` 8px · `--r-lg` 12px · `--r-pill` 999px.

## Components

`.btn` (`.btn-primary`, `.btn-quiet`, `.btn-sm`) · `.chip` (state via
`aria-pressed`, not a colour class) · `.card` · `.badge` (`-solid`, `-accent`,
`-pos`, `-neg`, `-warn`) · `.stat` + `.stat-value` + `.stat-label` · `.table` ·
`.input` · `.note` (`-warn`, `-neg`) · `.eyebrow` · `.skiplink`.

Identical construction on every page. No page-local variants.

## Icons

`static/_icons.svg` — 20+ marks on a 16-unit grid, 1.5 stroke, round caps, no
fills, `currentColor` throughout, so an icon inherits its context's colour and
works unchanged in light, dark, on an accent button, and in print.

```html
<svg class="ico" aria-hidden="true"><use href="#i-map"/></svg>
```

The sprite is injected into each page by `scripts/apply_design.py`. Edit
`_icons.svg` and re-run; never edit the copies.

**`textContent` cannot render markup.** Assigning icon HTML that way prints the
raw `<svg …>` tag on screen — three of these shipped and were invisible until a
specific state fired. Use `innerHTML` for trusted static markup. A test greps
for the pattern.

## Verifying

```bash
python scripts/design_audit.py            # full inventory
python scripts/design_audit.py --emoji    # gate: must be 0
python scripts/contrast_check.py          # WCAG AA, both themes
python scripts/check_static_js.py         # every inline script parses
python -m pytest -q                       # includes all of the above
```

Contrast is measured, not eyeballed: 20 foreground/background pairs × 2 themes,
all passing AA (4.5:1 text, 3:1 large/UI). The lowest margin is 4.82:1
(captions on a well, light theme).

## Extending it

- Need a size the scale lacks? Question the need first. The old file had
  fifteen sizes between .78 and .95rem — differences no reader could see and
  every maintainer had to guess at.
- Need a colour? Use an existing token. A new one needs a contrast check and a
  row in this document.
- Need a component? Add it to `design.css`, not to a page.
- After any change: `python scripts/apply_design.py` then the checks above.

## Legacy aliases

`design.css` maps the old names (`--hair`, `--wash`, `--muted`, `--card`,
`--blue`, …) onto system tokens, so the existing rules in each page keep
working without a large, risky rewrite. **New work should use the system names
directly.** The aliases are a bridge, not an API.
