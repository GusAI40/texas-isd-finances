#!/usr/bin/env python3
"""Remove page-local :root token blocks so design.css is the only definition.

The seven pages each carried their own copy of the palette. That is why
--good existed as three different greens and --bg as both #fff and #ffffff:
there was no shared definition to diverge from, so every page was free to
drift. design.css now defines every token, including an alias for each legacy
name, so these blocks are not merely redundant — they actively override the
system and re-introduce the drift.

Only :root blocks that consist ENTIRELY of custom-property declarations are
removed. A :root block containing anything else is left alone and reported,
because deleting it could remove real styling.

    python scripts/strip_local_tokens.py --check
    python scripts/strip_local_tokens.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"

# :root { ... }  and  :root[data-theme="dark"] { ... }
ROOT_BLOCK = re.compile(r"[ \t]*:root(\[data-theme=\"dark\"\])?\s*\{([^{}]*)\}\s*\n?")
DECL = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*[^;]+;?\s*$")


def only_tokens(body: str) -> bool:
    """True when every declaration in the block is a custom property.

    Comments are stripped first: a token block annotated with /* why */ is
    still a token block, and the original check rejected exactly the largest
    and best-documented one for that reason.
    """
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    parts = [p for p in body.split(";") if p.strip()]
    if not parts:
        return False
    return all(DECL.match(p + ";") for p in parts)


def process(path: Path, check: bool):
    html = path.read_text(encoding="utf-8")
    removed, kept = 0, 0

    def sub(m: re.Match) -> str:
        nonlocal removed, kept
        body = m.group(2)
        if only_tokens(body):
            removed += 1
            return ""
        kept += 1
        return m.group(0)

    new = ROOT_BLOCK.sub(sub, html)
    # Tidy the blank run a removed block can leave behind.
    new = re.sub(r"<style>\s*\n\s*\n", "<style>\n", new)
    if new != html and not check:
        path.write_text(new, encoding="utf-8")
    return removed, kept, new != html


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    total_r = total_k = 0
    for p in sorted(STATIC.glob("*.html")):
        r, k, changed = process(p, args.check)
        total_r += r
        total_k += k
        note = "" if changed else "  (no change)"
        print(f"{p.name:18} removed {r}  kept {k}{note}")
    print(f"\n{total_r} token blocks removed, {total_k} left in place"
          f"{' (dry run)' if args.check else ''}")
    if total_k:
        print("blocks left in place contain more than custom properties — review by hand")
    return 0


if __name__ == "__main__":
    sys.exit(main())
