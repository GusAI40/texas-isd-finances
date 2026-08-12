"""The per-district head-injection edge function is what makes a shared district
link preview as THAT district and lets a crawler rank it. Before it, every
/?d= URL served byte-identical HTML — homepage canonical, generic card, no
district name a scraper could see. These tests lock the behaviour and the one
rule that must travel with it: the card never contradicts the page.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import og  # noqa: E402

INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_district_meta_names_the_district():
    m = og.district_meta("061910")
    assert m and m["name"] == "Argyle ISD"
    assert m["canonical"] == "https://txisd.dev/?d=061910"
    assert m["image"].endswith("/share/061910.png")


def test_unknown_or_malformed_number_is_none():
    assert og.district_meta("999999") is None      # not a real district
    assert og.district_meta("61910") is None        # not 6 digits
    assert og.district_meta("abcdef") is None
    assert og.district_meta("") is None


def test_head_injection_rewrites_the_district_identity():
    """A crawler and a link scraper must see Argyle's name, its own canonical,
    and its own image — not the homepage's."""
    out = og.render_head(INDEX, "061910")
    assert '<link rel="canonical" href="https://txisd.dev/?d=061910">' in out
    assert '<meta property="og:url" content="https://txisd.dev/?d=061910">' in out
    assert "Argyle ISD" in out.split("</head>")[0]
    assert '<title>Argyle ISD' in out
    assert 'property="og:image" content="https://txisd.dev/share/061910.png"' in out
    # the old homepage canonical must be gone, not merely supplemented
    assert '<link rel="canonical" href="https://txisd.dev/">' not in out


def test_homepage_keeps_its_identity_but_gains_image_and_dataset():
    out = og.render_head(INDEX, None)
    assert '<link rel="canonical" href="https://txisd.dev/">' in out
    assert "/share/default.png" in out
    assert '"@type": "Dataset"' in out
    # no district JSON-LD on the homepage
    assert "GovernmentOrganization" not in out


def test_card_and_meta_never_contradict_the_page_all_funds_figure():
    """The site's hero shows Argyle at $31,704 all-funds; that total lives only
    in the DB view. The card/meta must NOT print a different 'all-funds' number
    — it leads with the operating figure, which every artefact agrees on."""
    m = og.district_meta("061910")
    assert "$10,357" in m["description"]            # the operating figure
    assert "31,704" not in m["description"]         # never the DB-only total
    assert "15,509" not in m["description"]         # never the wrong total
    assert "all-funds" not in m["description"]      # the ambiguous frame is avoided


def test_jsonld_is_valid_json_in_each_block():
    import json
    out = og.render_head(INDEX, "061910")
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', out)
    assert len(blocks) == 2                          # Dataset + GovernmentOrganization
    for b in blocks:
        json.loads(b)                                # raises if malformed


def test_the_default_share_card_is_committed():
    """A fresh clone must always have a fallback image so no link is imageless,
    even before the 1,216 district cards are built."""
    assert (ROOT / "static" / "share" / "default.png").exists()


def test_the_share_route_and_edge_function_are_wired():
    api = (ROOT / "src" / "api.py").read_text(encoding="utf-8")
    assert "og.render_head" in api
    assert '"/share/{name}"' in api
