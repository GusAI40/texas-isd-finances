#!/usr/bin/env python3
"""Design-system audit: what is inconsistent across the seven pages.

Extracts every font-size, colour literal, spacing value, component variant and
emoji actually used in static/*.html, then reports the spread. The point is to
replace guesswork with an inventory: you cannot impose one type scale until you
know the fourteen sizes currently in play.

    python scripts/design_audit.py            # human-readable report
    python scripts/design_audit.py --emoji    # emoji only (used as a gate)
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
PAGES = sorted(STATIC.glob("*.html"))

# Pictographs, dingbats, arrows and variation selectors — the things that read
# as "emoji" in a UI. Kept as one expression so the gate and the report agree.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF←-⇿⌀-⏿①-⓿"
    "■-➿⬀-⯿️•·]"
)
# Characters that are legitimate typography rather than emoji, so the gate does
# not flag an en dash or a middot used as a separator.
TYPOGRAPHIC_OK = set("·•–—…‹›«»′″©®™°")

FONT_SIZE_RE = re.compile(r"font-size:\s*([^;}\n]+)")
HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
RGBA_RE = re.compile(r"rgba?\([^)]*\)")
SPACE_RE = re.compile(r"(?:padding|margin|gap):\s*([^;}\n]+)")
RADIUS_RE = re.compile(r"border-radius:\s*([^;}\n]+)")
VAR_DEF_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;}\n]+)")
SHADOW_RE = re.compile(r"box-shadow:\s*([^;}\n]+)")
FAMILY_RE = re.compile(r"font-family:\s*([^;}\n]+)")


def scan():
    data = {
        "emoji": collections.Counter(),
        "emoji_by_page": collections.Counter(),
        "font_size": collections.Counter(),
        "hex": collections.Counter(),
        "rgba": collections.Counter(),
        "space": collections.Counter(),
        "radius": collections.Counter(),
        "shadow": collections.Counter(),
        "family": collections.Counter(),
        "vars": collections.defaultdict(set),
    }
    for p in PAGES:
        s = p.read_text(encoding="utf-8")
        found = [c for c in EMOJI_RE.findall(s) if c not in TYPOGRAPHIC_OK]
        if found:
            data["emoji"].update(found)
            data["emoji_by_page"][p.name] = len(found)
        data["font_size"].update(m.strip() for m in FONT_SIZE_RE.findall(s))
        data["hex"].update(m.lower() for m in HEX_RE.findall(s))
        data["rgba"].update(m.replace(" ", "") for m in RGBA_RE.findall(s))
        for m in SPACE_RE.findall(s):
            for tok in m.split():
                if re.fullmatch(r"-?[\d.]+(rem|px|em)", tok):
                    data["space"][tok] += 1
        data["radius"].update(m.strip() for m in RADIUS_RE.findall(s))
        data["shadow"].update(m.strip()[:40] for m in SHADOW_RE.findall(s))
        data["family"].update(m.strip()[:48] for m in FAMILY_RE.findall(s))
        for name, val in VAR_DEF_RE.findall(s):
            data["vars"][name].add(val.strip())
    return data


def emoji_gate() -> int:
    """Exit non-zero if any emoji remain. Used as the definition-of-done check."""
    offenders = {}
    for p in PAGES:
        found = [c for c in EMOJI_RE.findall(p.read_text(encoding="utf-8"))
                 if c not in TYPOGRAPHIC_OK]
        if found:
            offenders[p.name] = collections.Counter(found)
    if not offenders:
        print("emoji: 0 — clean")
        return 0
    total = sum(sum(c.values()) for c in offenders.values())
    print(f"emoji: {total} remaining")
    for name, c in offenders.items():
        print(f"  {name:16} {sum(c.values()):3}  {' '.join(c)}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emoji", action="store_true", help="emoji gate only")
    args = ap.parse_args()
    if args.emoji:
        return emoji_gate()

    d = scan()
    print("=" * 66)
    print("DESIGN AUDIT — static/*.html")
    print("=" * 66)

    total_emoji = sum(d["emoji"].values())
    print(f"\nEMOJI  {total_emoji} occurrences, {len(d['emoji'])} distinct")
    for page, n in d["emoji_by_page"].most_common():
        print(f"   {page:18} {n}")
    print("   glyphs:", " ".join(g for g, _ in d["emoji"].most_common(30)))

    print(f"\nTYPE SCALE  {len(d['font_size'])} distinct font-size values")
    for v, n in d["font_size"].most_common():
        print(f"   {v:34} x{n}")

    print(f"\nCOLOUR  {len(d['hex'])} hex literals, {len(d['rgba'])} rgba literals")
    for v, n in d["hex"].most_common(24):
        print(f"   {v:10} x{n}")
    if d["rgba"]:
        print("   rgba:", ", ".join(v for v, _ in d["rgba"].most_common(8)))

    print(f"\nSPACING  {len(d['space'])} distinct values")
    print("  ", ", ".join(f"{v}(x{n})" for v, n in d["space"].most_common(28)))

    print(f"\nRADIUS  {len(d['radius'])} distinct")
    print("  ", ", ".join(f"{v}(x{n})" for v, n in d["radius"].most_common(16)))

    print(f"\nSHADOW  {len(d['shadow'])} distinct")
    for v, n in d["shadow"].most_common(8):
        print(f"   {v:42} x{n}")

    print(f"\nFONT FAMILIES  {len(d['family'])} distinct declarations")
    for v, n in d["family"].most_common(8):
        print(f"   {v:50} x{n}")

    drifted = {k: v for k, v in d["vars"].items() if len(v) > 2}
    print(f"\nTOKENS DEFINED MORE THAN TWICE (light+dark is 2; more means drift): "
          f"{len(drifted)}")
    for k, v in sorted(drifted.items())[:14]:
        print(f"   {k:16} {len(v)} values: {sorted(v)[:4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
