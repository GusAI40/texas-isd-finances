#!/usr/bin/env python3
"""WCAG contrast audit of the design tokens, in both themes.

Reads the token values straight out of static/design.css, so the check can
never drift from what actually ships. Every foreground/background pair the
system actually uses must clear AA: 4.5:1 for body text, 3:1 for large text
and for UI boundaries.

    python scripts/contrast_check.py          # report + exit 1 on any failure

A palette that has not been measured is a guess. This measures it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "static" / "design.css"

# (foreground token, background token, minimum ratio, what it is)
PAIRS = [
    ("--ink",     "--bg",        4.5, "headlines on page"),
    ("--ink-2",   "--bg",        4.5, "body on page"),
    ("--ink-3",   "--bg",        4.5, "secondary on page"),
    ("--ink",     "--surface",   4.5, "headlines on card"),
    ("--ink-2",   "--surface",   4.5, "body on card"),
    ("--ink-3",   "--surface",   4.5, "captions on card"),
    ("--ink-2",   "--surface-2", 4.5, "body on well"),
    ("--ink-3",   "--surface-2", 4.5, "captions on well"),
    ("--accent",  "--bg",        4.5, "links on page"),
    ("--accent",  "--surface",   4.5, "links on card"),
    ("--accent",  "--accent-soft", 4.5, "accent badge text"),
    ("--accent-ink", "--accent", 4.5, "text on accent button"),
    ("--on-ink",  "--ink",       4.5, "text on ink surface"),
    ("--pos",     "--pos-soft",  4.5, "positive badge"),
    ("--neg",     "--neg-soft",  4.5, "negative badge"),
    ("--warn",    "--warn-soft", 4.5, "warning badge"),
    ("--pos",     "--bg",        4.5, "positive text on page"),
    ("--neg",     "--bg",        4.5, "negative text on page"),
    ("--ink-4",   "--bg",        3.0, "disabled / watermark (large only)"),
    ("--rule-2",  "--bg",        1.4, "emphasised divider (non-text)"),
]


def parse_blocks(css: str) -> tuple[dict, dict]:
    """Return (light, dark) token maps. Dark inherits light, then overrides."""
    def block(pattern: str) -> str:
        m = re.search(pattern + r"\s*\{(.*?)\n\}", css, re.S)
        return m.group(1) if m else ""

    def tokens(text: str) -> dict:
        out = {}
        for name, val in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", text):
            out[name] = val.strip()
        return out

    light = tokens(block(r":root(?!\[)"))
    dark = dict(light)
    dark.update(tokens(block(r':root\[data-theme="dark"\]')))
    return light, dark


def to_rgb(value: str, tokens: dict, depth: int = 0):
    """Resolve a token value to (r, g, b). Handles #rgb, #rrggbb, rgba()."""
    v = value.strip()
    if v.startswith("var(") and depth < 5:
        inner = v[4:v.index(")")].split(",")[0].strip()
        return to_rgb(tokens.get(inner, ""), tokens, depth + 1)
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(([^)]+)\)", v)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", ",").split(",")]
        try:
            return tuple(int(float(p)) for p in parts[:3])
        except ValueError:
            return None
    return None


def luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def main() -> int:
    css = CSS.read_text(encoding="utf-8")
    light, dark = parse_blocks(css)
    failures = 0

    for theme_name, tokens in (("LIGHT", light), ("DARK", dark)):
        print(f"\n{theme_name}")
        print(f"  {'pair':44} {'ratio':>7}  {'min':>4}  result")
        print("  " + "-" * 68)
        for fg_name, bg_name, minimum, label in PAIRS:
            fg = to_rgb(tokens.get(fg_name, ""), tokens)
            bg = to_rgb(tokens.get(bg_name, ""), tokens)
            if not fg or not bg:
                print(f"  {label:44} {'—':>7}  {minimum:>4}  MISSING TOKEN")
                failures += 1
                continue
            r = ratio(fg, bg)
            ok = r >= minimum
            if not ok:
                failures += 1
            print(f"  {label:44} {r:7.2f}  {minimum:>4}  {'pass' if ok else 'FAIL'}")

    print(f"\n{'ALL PAIRS PASS' if not failures else f'{failures} FAILURES'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
