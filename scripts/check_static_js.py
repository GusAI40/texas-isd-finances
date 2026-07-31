#!/usr/bin/env python3
"""Parse the inline JavaScript in every static page and fail if it doesn't.

Why this exists: a `const` redeclaration once killed static/map.html outright
while the page still returned 200 and still contained every string you would
grep for. Serving is not working, and grepping the HTML proves nothing — the
only check that catches a syntax error is parsing the script.

Run directly (`python scripts/check_static_js.py`) or via the test suite,
which calls the same function.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

# Inline blocks only. A block with a src= attribute has no body to parse.
SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


def inline_scripts(html_path: Path) -> list[str]:
    return SCRIPT_RE.findall(html_path.read_text(encoding="utf-8"))


def check_page(html_path: Path) -> str | None:
    """Return None if the page's script parses, else the parser's message.

    The blocks are joined the way the browser sees them — one shared scope, in
    document order — so a `const` declared twice across two blocks is caught
    exactly as the browser would catch it. A lone `;` between blocks keeps a
    trailing expression in one block from swallowing the next.
    """
    blocks = inline_scripts(html_path)
    if not blocks:
        return None
    source = "\n;\n".join(blocks)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(source)
        tmp = Path(fh.name)
    try:
        proc = subprocess.run(
            ["node", "--check", str(tmp)], capture_output=True, text=True, timeout=60
        )
    finally:
        tmp.unlink(missing_ok=True)
    return None if proc.returncode == 0 else (proc.stderr or proc.stdout).strip()


def main() -> int:
    if shutil.which("node") is None:
        print("node not found — cannot parse static JavaScript", file=sys.stderr)
        return 2
    pages = sorted(STATIC.glob("*.html"))
    if not pages:
        print(f"no HTML pages found in {STATIC}", file=sys.stderr)
        return 2
    failed = 0
    for page in pages:
        err = check_page(page)
        n = len(inline_scripts(page))
        if err is None:
            print(f"  ok    {page.name}  ({n} inline block{'s' if n != 1 else ''})")
        else:
            failed += 1
            print(f"  FAIL  {page.name}\n{err}\n")
    print(f"{len(pages) - failed}/{len(pages)} pages parse")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
