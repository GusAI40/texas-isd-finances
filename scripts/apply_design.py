#!/usr/bin/env python3
"""Apply the design system to every page: stylesheet, icon sprite, no emoji.

Done as a script rather than by hand because seven pages edited by hand is
exactly how the original drift happened (45 font sizes, 84 hex literals, three
different greens named --good). A script applies one decision everywhere and
can be re-run after any future edit.

Idempotent: safe to run repeatedly. Each injected region is delimited, so a
second run replaces rather than duplicates.

    python scripts/apply_design.py            # apply
    python scripts/apply_design.py --check    # report what would change
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
SPRITE_SRC = STATIC / "_icons.svg"

LINK_START = "<!-- design-system:start -->"
LINK_END = "<!-- design-system:end -->"
SPRITE_START = "<!-- icon-sprite:start -->"
SPRITE_END = "<!-- icon-sprite:end -->"

STYLESHEET = '<link rel="stylesheet" href="/static/design.css">'


def icon(name: str, cls: str = "ico") -> str:
    return f'<svg class="{cls}" aria-hidden="true"><use href="#i-{name}"/></svg>'


# Emoji -> replacement. Icons where a mark genuinely helps scanning; plain
# removal where the emoji was decorating text that already said the same thing.
EMOJI_MAP = {
    # navigation / controls
    "🗺️": icon("map"), "🗺": icon("map"),
    "🔥": icon("activity"),
    "🔎": icon("search"), "🔍": icon("search"),
    "📍": icon("pin"),
    "🌙": icon("contrast"), "☀️": icon("contrast"), "☀": icon("contrast"),
    "◐": icon("contrast"),
    "📖": icon("book"),
    "▶︎": icon("play"), "▶": icon("play"),
    "⬇": icon("download"), "↓": icon("arrow-down"),
    "✕": icon("close"), "✖": icon("close"), "×": icon("close"),
    "→": icon("arrow-right"), "←": icon("arrow-left"),
    "▲": icon("chevron-up"), "▼": icon("chevron-down"),
    "◆": icon("marker"),
    # editorial beats
    "🏛️": icon("institution"), "🏛": icon("institution"),
    "🚪": icon("exit"),
    "💰": icon("money"), "💵": icon("money"),
    "📉": icon("trend-down"), "📈": icon("trend-up"),
    "📊": icon("chart"),
    "⚖️": icon("scale"), "⚖": icon("scale"),
    "👥": icon("people"),
    "🏗️": icon("build"), "🏗": icon("build"),
    "🚨": icon("alert"), "⚠️": icon("alert"), "⚠": icon("alert"),
    "🗳️": icon("ballot"), "🗳": icon("ballot"),
    "📚": icon("book"),
    "📌": icon("marker"),
}

# Type scale: collapse 45 measured sizes onto the nine-step scale. Chosen to
# sit closest to what was already rendering, so the system lands without
# re-flowing every page.
FONT_SIZE_MAP = {
    ".62rem": "var(--fs-micro)", ".68rem": "var(--fs-micro)",
    ".7rem": "var(--fs-micro)", ".72rem": "var(--fs-micro)",
    ".74rem": "var(--fs-micro)", ".76rem": "var(--fs-micro)",
    ".78rem": "var(--fs-xs)", ".79rem": "var(--fs-xs)", ".8rem": "var(--fs-xs)",
    ".82rem": "var(--fs-xs)", ".83rem": "var(--fs-xs)", ".84rem": "var(--fs-xs)",
    ".85rem": "var(--fs-sm)", ".86rem": "var(--fs-sm)", ".87rem": "var(--fs-sm)",
    ".88rem": "var(--fs-sm)", ".89rem": "var(--fs-sm)",
    ".9rem": "var(--fs-base)", ".92rem": "var(--fs-base)",
    ".94rem": "var(--fs-base)", ".95rem": "var(--fs-base)",
    "1rem": "var(--fs-md)", "1.02rem": "var(--fs-md)", "1.05rem": "var(--fs-md)",
    "1.1rem": "var(--fs-md)", "1.15rem": "var(--fs-md)",
    "1.25rem": "var(--fs-lg)", "1.3rem": "var(--fs-lg)", "1.32rem": "var(--fs-lg)",
    "1.35rem": "var(--fs-lg)",
    "1.4rem": "var(--fs-xl)", "1.5rem": "var(--fs-xl)", "1.6rem": "var(--fs-xl)",
    "1.7rem": "var(--fs-2xl)", "1.75rem": "var(--fs-2xl)", "1.9rem": "var(--fs-2xl)",
    "2.1rem": "var(--fs-2xl)",
}

# Colour literals -> tokens. Same value, one name.
COLOR_MAP = {
    "#fff": "var(--surface)", "#ffffff": "var(--surface)",
    "#1a1a1a": "var(--ink)", "#17171a": "var(--ink)",
    "#55534e": "var(--ink-2)",
    "#8b897f": "var(--ink-3)",
    "#b8b6ad": "var(--ink-4)", "#c9c7be": "var(--ink-4)",
    "#e9e8e3": "var(--rule)",
    "#f7f7f5": "var(--surface-2)",
    "#2a78d6": "var(--accent)", "#1c5cab": "var(--accent)",
    "#eef4fd": "var(--accent-soft)",
    "#eb6834": "var(--compare)",
    "#006300": "var(--pos)", "#0a7a34": "var(--pos)",
    "#c23934": "var(--neg)", "#d9534f": "var(--neg)",
}

RADIUS_MAP = {
    "2px": "var(--r-sm)", "3px": "var(--r-sm)", "4px": "var(--r-sm)",
    "5px": "var(--r-sm)", "6px": "var(--r-md)", "7px": "var(--r-md)",
    "8px": "var(--r-md)", "10px": "var(--r-lg)", "12px": "var(--r-lg)",
    "14px": "var(--r-lg)", "20px": "var(--r-pill)", "99px": "var(--r-pill)",
    "999px": "var(--r-pill)",
}


def pages() -> list[Path]:
    return sorted(p for p in STATIC.glob("*.html"))


def inject_stylesheet(html: str) -> str:
    """Link design.css as the FIRST stylesheet, before any page CSS."""
    block = f"{LINK_START}\n{STYLESHEET}\n{LINK_END}"
    if LINK_START in html:
        return re.sub(re.escape(LINK_START) + r".*?" + re.escape(LINK_END),
                      block, html, flags=re.S)
    # Before the first <style> so page rules can override system defaults.
    m = re.search(r"[ \t]*<style>", html)
    if m:
        return html[:m.start()] + block + "\n" + html[m.start():]
    return html.replace("</head>", block + "\n</head>", 1)


def inject_sprite(html: str, sprite: str) -> str:
    block = f"{SPRITE_START}\n{sprite.strip()}\n{SPRITE_END}"
    if SPRITE_START in html:
        return re.sub(re.escape(SPRITE_START) + r".*?" + re.escape(SPRITE_END),
                      block, html, flags=re.S)
    m = re.search(r"<body[^>]*>", html)
    if not m:
        return html
    return html[:m.end()] + "\n" + block + html[m.end():]


def replace_emoji(html: str) -> tuple[str, int]:
    n = 0
    # Longest first so "🗺️" (with variation selector) beats "🗺".
    for glyph in sorted(EMOJI_MAP, key=len, reverse=True):
        if glyph in html:
            n += html.count(glyph)
            html = html.replace(glyph, EMOJI_MAP[glyph])
    # Any stray variation selectors left behind by a partial match.
    html = html.replace("️", "")
    # An icon immediately followed by a space then text is fine; collapse the
    # double spaces a removed glyph can leave inside a label.
    html = re.sub(r"(</svg>)\s{2,}", r"\1 ", html)
    return html, n


def map_values(html: str, prop: str, table: dict) -> tuple[str, int]:
    """Rewrite `prop: <literal>` to the matching token, inside CSS only."""
    n = 0

    def sub(m):
        nonlocal n
        val = m.group(2).strip()
        repl = table.get(val.lower())
        if repl and repl != val:
            n += 1
            return f"{m.group(1)}{repl}"
        return m.group(0)

    return re.sub(rf"({prop}:\s*)([^;}}\n]+)", sub, html), n


def process(path: Path, sprite: str, check: bool) -> dict:
    original = path.read_text(encoding="utf-8")
    html = original
    stats = {}

    html = inject_stylesheet(html)
    html = inject_sprite(html, sprite)
    html, stats["emoji"] = replace_emoji(html)
    html, stats["font-size"] = map_values(html, "font-size", FONT_SIZE_MAP)
    html, stats["color"] = map_values(html, "color", COLOR_MAP)
    html, stats["background"] = map_values(html, "background", COLOR_MAP)
    html, stats["radius"] = map_values(html, "border-radius", RADIUS_MAP)

    stats["changed"] = html != original
    if stats["changed"] and not check:
        path.write_text(html, encoding="utf-8")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report, do not write")
    args = ap.parse_args()

    if not SPRITE_SRC.exists():
        print(f"missing {SPRITE_SRC}", file=sys.stderr)
        return 2
    # Strip the file's leading comment; the page copy carries its own marker.
    sprite = re.sub(r"^<!--.*?-->\s*", "", SPRITE_SRC.read_text(encoding="utf-8"), flags=re.S)

    print(f"{'page':18} {'emoji':>6} {'type':>6} {'colour':>7} {'radius':>7}")
    print("-" * 50)
    total = 0
    for p in pages():
        s = process(p, sprite, args.check)
        total += s["emoji"]
        print(f"{p.name:18} {s['emoji']:>6} {s['font-size']:>6} "
              f"{s['color'] + s['background']:>7} {s['radius']:>7}"
              f"{'' if s['changed'] else '   (no change)'}")
    print(f"\n{total} emoji replaced with icons"
          f"{' (dry run)' if args.check else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
