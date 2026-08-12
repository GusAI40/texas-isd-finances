"""Pre-render 1200x630 social share cards — one per district, plus a default.

Link-preview scrapers (Facebook, Twitter/X, iMessage, Slack, LinkedIn) never
run the page's JS, so the client-canvas share card the site already draws is
invisible to them. This bakes the same idea to PNGs the server can hand out at
/share/{num}.png, so every shared district link — and the whole superintendent
outreach campaign — finally previews as THAT district, not a generic card.

Frame honesty travels onto the card exactly as onto the page: where
construction and debt are a material share, the all-funds figure is shown with
the operating figure beside it (the Argyle rule).

    python scripts/build_share_cards.py            # all districts + default
    python scripts/build_share_cards.py --only 061910,057905

Cards land in static/share/ (whitelisted for deploy in .vercelignore). Pillow
is a build-time dependency only; the runtime just serves the finished PNGs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import format as fmt  # noqa: E402

OUT = ROOT / "static" / "share"
W, H = 1200, 630
INK = (26, 36, 33)
INK2 = (67, 82, 77)
MUT = (113, 128, 122)
ACCENT = (47, 75, 215)
GROUND = (247, 247, 245)
RULE = (201, 210, 204)

# Category colours mirror the site's penny dollar.
DOLLAR = {"classroom": (47, 75, 215), "construction": (58, 58, 58),
          "debt": (139, 176, 224), "admin": (113, 122, 116),
          "buildings": (168, 168, 158), "transport": (214, 106, 58),
          "support": (32, 150, 110), "activities": (176, 137, 45),
          "safety": (120, 84, 180)}


def _font(size: int, bold: bool = False):
    names = (["DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf"] if bold
             else ["DejaVuSerif.ttf"])
    for n in names:
        for base in ("/usr/share/fonts/truetype/dejavu/",
                     "/usr/share/fonts/dejavu/"):
            p = Path(base) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = (line + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            line = t
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def _load():
    def art(n):
        p = ROOT / "static" / n
        return json.loads(p.read_text()) if p.exists() else {}
    fb = {d["district_number"]: fmt.district_name(d["district_name"])
          for d in art("fallback_index.json").get("districts", [])}
    econ = art("economics_data.json").get("districts", {})
    dollar = art("outcomes_data.json")  # noqa: F841 (kept for future use)
    dparts = art("economics_data.json")
    return fb, econ, dparts


def _dollar_parts(num, dollar_art):
    d = dollar_art.get("districts", {}).get(num, {})
    return (d.get("dollar") or {}).get("parts")


def card(num, name, econ, dollar_art):
    img = Image.new("RGB", (W, H), GROUND)
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, 10, H], fill=ACCENT)                 # spine
    pad = 70

    dr.text((pad, 60), "TEXAS ISD FINANCIAL RESOURCE GUIDE",
            font=_font(20), fill=MUT)

    # Lead with the OPERATING figure only — identical across every committed
    # artefact and the honest comparison number. The all-funds total lives in
    # the DB view; reproducing it here could contradict the page, so we don't.
    alloc = (econ.get(num) or {}).get("allocation") or {}
    ops = alloc.get("operating_per_student")
    if ops:
        big = fmt.usd(ops)
        sub = "per student running schools · bonds, debt & results inside"
    else:
        big, sub = name, "everything Texas records, in one place"

    # headline
    hf = _font(58, bold=True)
    for i, line in enumerate(_wrap(dr, name, hf, W - 2 * pad - 40)[:2]):
        dr.text((pad, 120 + i * 66), line, font=hf, fill=INK)

    # the number
    nf = _font(96, bold=True)
    dr.text((pad, 280), big, font=nf, fill=ACCENT)
    sf = _font(26)
    for i, line in enumerate(_wrap(dr, sub, sf, W - 2 * pad - 40)[:2]):
        dr.text((pad, 400 + i * 34), line, font=sf, fill=INK2)

    # penny strip along the bottom, if we have the breakdown
    parts = _dollar_parts(num, dollar_art)
    y = 520
    if parts:
        x = pad
        cell = (W - 2 * pad) / 100
        for p in parts:
            col = DOLLAR.get(p.get("key"), (201, 199, 190))
            for _ in range(int(p.get("cents", 0))):
                dr.rectangle([x, y, x + cell - 3, y + 26], fill=col)
                x += cell
    dr.text((pad, 575), "Every figure traced to the State of Texas  ·  txisd.dev",
            font=_font(22), fill=MUT)
    return img


def default_card(dollar_art):
    img = Image.new("RGB", (W, H), GROUND)
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, 10, H], fill=ACCENT)
    pad = 70
    dr.text((pad, 70), "TEXAS ISD FINANCIAL RESOURCE GUIDE", font=_font(22), fill=MUT)
    hf = _font(60, bold=True)
    for i, line in enumerate(["Where every dollar goes in all",
                              "1,310 Texas school districts."]):
        dr.text((pad, 150 + i * 74), line, font=hf, fill=INK)
    dr.text((pad, 330), "$109.4B a year · 17 years of state records · in plain English",
            font=_font(30), fill=INK2)
    tx = dollar_art.get("dollar_texas") or {}
    parts = tx.get("parts")
    if parts:
        x, y, cell = pad, 470, (W - 2 * pad) / 100
        for p in parts:
            col = DOLLAR.get(p.get("key"), (201, 199, 190))
            for _ in range(int(p.get("cents", 0))):
                dr.rectangle([x, y, x + cell - 3, y + 30], fill=col)
                x += cell
    dr.text((pad, 560), "Free · sourced · built for the public  ·  txisd.dev",
            font=_font(24), fill=MUT)
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated district numbers")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    fb, econ, dollar_art = _load()
    # the default card needs the statewide dollar; pull it from fallback_index
    fb_art = json.loads((ROOT / "static/fallback_index.json").read_text())
    default_card({"dollar_texas": fb_art.get("dollar_texas")}).save(
        OUT / "default.png", optimize=True)

    nums = ([n.strip() for n in args.only.split(",") if n.strip()]
            if args.only else sorted(fb))
    n = 0
    for num in nums:
        name = fb.get(num)
        if not name:
            print("skip (unknown):", num)
            continue
        card(num, name, econ, dollar_art).save(OUT / f"{num}.png", optimize=True)
        n += 1
    total = sum(p.stat().st_size for p in OUT.glob("*.png"))
    print(f"wrote {n} district cards + default to {OUT.relative_to(ROOT)} "
          f"({total / 1e6:.1f} MB total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
