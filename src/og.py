"""Per-district social + search metadata, built from the committed artefacts.

The blind spot this closes: every district URL (`/?d=NNNNNN`) served byte-
identical HTML — same <title>, same canonical pointing at the homepage, same
generic OG card, no district name anywhere a crawler or a link-preview scraper
can see it (neither runs the client JS that fills the page). So Google could
never rank "Argyle ISD spending" to this site, and every link a superintendent
shared previewed as the same generic card.

This module returns the per-district head — title, description, canonical,
image, JSON-LD — from the same committed JSON the site already serves, so it
needs no database and survives a paused Supabase exactly like the rest of the
DB-free layer. Frame honesty travels: where construction and debt are a
material share of outlay, the all-funds figure never appears without the
operating figure (the Argyle rule).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from src import format as fmt

STATIC = Path(__file__).resolve().parent.parent / "static"
SITE = "https://txisd.dev"

_OG_DESC_TAG = (
    '<meta property="og:description" content="Texas school districts spend '
    "$109 billion a year. Here is where every penny goes — and what it "
    'actually buys. 17 years of official state records, in plain English.">')
_TW_DESC_TAG = (
    '<meta name="twitter:description" content="$109 billion a year across '
    '1,310 districts. Where every penny goes, and what it actually buys.">')


@lru_cache(maxsize=1)
def _artifact(name: str) -> dict:
    p = STATIC / name
    return json.loads(p.read_text()) if p.exists() else {}


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    fb = _artifact("fallback_index.json")
    return {d["district_number"]: fmt.district_name(d["district_name"])
            for d in fb.get("districts", [])}


def _frame_line(num: str, name: str) -> str:
    """One frame-honest sentence for the meta description and card.

    Leads with the OPERATING per-student figure — the cost of running schools,
    identical across every committed artefact and the honest number to compare
    districts on. The all-funds total (which balloons in a district's building
    years) lives only in the database view, so reproducing it here risks a card
    that contradicts the page; we don't.
    """
    econ = _artifact("economics_data.json").get("districts", {}).get(num, {})
    alloc = econ.get("allocation") or {}
    ops = alloc.get("operating_per_student")
    if ops:
        return (f"{name} spends {fmt.usd(ops)} per student running schools — "
                f"every figure traced to the State of Texas' own records, with "
                f"bonds, debt and results beside it.")
    return (f"Everything the State of Texas records about {name}: what it "
            f"collects, spends, borrowed, and what its students achieved.")


def district_meta(num: str) -> dict | None:
    """Head metadata for one district, or None if the number is unknown.

    Keys: name, title, description, canonical, image (absolute URLs).
    """
    if not (isinstance(num, str) and len(num) == 6 and num.isdigit()):
        return None
    name = _names().get(num)
    if not name:
        return None
    desc = _frame_line(num, name)
    return {
        "num": num,
        "name": name,
        "title": f"{name} — every number Texas publishes, in one place",
        "description": desc,
        "canonical": f"{SITE}/?d={num}",
        "image": f"{SITE}/share/{num}.png",
    }


def jsonld(meta: dict | None) -> str:
    """schema.org markup: the site is a Dataset; a district page is also a
    GovernmentOrganization. Earns Google Dataset Search + rich results."""
    dataset = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "Texas ISD Financial Resource Guide",
        "description": ("Every number the State of Texas publishes about its "
                        "1,310 school districts — finances, results, bonds, "
                        "debt — synthesized from official first-party records, "
                        "fiscal 2009–2025."),
        "url": f"{SITE}/", "license": "https://opensource.org/licenses/MIT",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "TAG ai"},
        "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                          "contentUrl": f"{SITE}/districts"}],
        "spatialCoverage": "Texas, USA", "temporalCoverage": "2009/2025",
    }
    blocks = [dataset]
    if meta:
        blocks.append({
            "@context": "https://schema.org", "@type": "GovernmentOrganization",
            "name": meta["name"], "url": meta["canonical"],
            "areaServed": {"@type": "State", "name": "Texas"},
            "description": meta["description"],
        })
    return "".join(
        f'<script type="application/ld+json">{json.dumps(b)}</script>'
        for b in blocks)


def render_head(html: str, num: str | None) -> str:
    """Rewrite the shared index.html head for the requested district.

    Homepage (num is None or unknown) gets Dataset JSON-LD and a default share
    image only; a valid district additionally gets its name in the title,
    canonical, and every OG/Twitter tag. Pure string replacement on the known
    tags — the client app below the head is untouched.
    """
    meta = district_meta(num) if num else None
    default_img = f"{SITE}/share/default.png"

    if meta:
        html = html.replace(
            '<link rel="canonical" href="https://txisd.dev/">',
            f'<link rel="canonical" href="{meta["canonical"]}">')
        html = html.replace(
            '<meta property="og:url" content="https://txisd.dev/">',
            f'<meta property="og:url" content="{meta["canonical"]}">')
        html = html.replace(
            '<meta property="og:title" content="Texas ISD Financial Resource Guide — a story of Texas ISD">',
            f'<meta property="og:title" content="{_esc(meta["title"])}">')
        html = html.replace(
            '<meta name="twitter:title" content="Texas ISD Financial Resource Guide">',
            f'<meta name="twitter:title" content="{_esc(meta["name"])}">')
        for prop, kind, tag in (
                ("property", "og:description", _OG_DESC_TAG),
                ("name", "twitter:description", _TW_DESC_TAG)):
            html = html.replace(
                tag, f'<meta {prop}="{kind}" content="{_esc(meta["description"])}">')
        html = html.replace(
            "<title>Texas ISD Finances — District Dashboard</title>",
            f"<title>{_esc(meta['title'])}</title>")

    img = meta["image"] if meta else default_img
    # inject image tags + JSON-LD once, right before </head>
    inject = (f'<meta property="og:image" content="{img}">'
              f'<meta property="og:image:width" content="1200">'
              f'<meta property="og:image:height" content="630">'
              f'<meta name="twitter:image" content="{img}">'
              + jsonld(meta))
    return html.replace("</head>", inject + "</head>", 1)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))
