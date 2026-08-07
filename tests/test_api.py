"""API tests that run without a database or OpenAI key.

The app must boot and serve the portal, docs and health endpoints even when
no credentials are configured; data endpoints must fail cleanly with 503.
"""
import pytest
from fastapi.testclient import TestClient

from src.api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_portal_page_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Texas ISD Finances" in res.text


def test_api_info(client):
    res = client.get("/api")
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "Texas School Finance API"
    assert "endpoints" in body


def test_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_health_degraded_without_db(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded"
    assert body["database"] == "not configured"
    # /health also names the live model provider, so a provider switch can be
    # confirmed from outside. It must never carry the API key itself.
    assert "llm" in body
    for provider in ("deepseek", "openai"):
        if provider in body["llm"]:
            break
    else:
        raise AssertionError(f"/health does not name a provider: {body['llm']!r}")
    assert "sk-" not in body["llm"]


@pytest.mark.parametrize("path", [
    "/districts",
    "/district/057905/summary",
    "/anomalies",
    "/stats",
    "/benchmarks",
    "/district/057905/peers",
    "/district/057905/breakdown",
    "/district/057905/turnarounds",
    "/district/057905/spending-detail",
    "/district/057905/insights",
    "/district/057905/dollar",
])
def test_data_endpoints_return_503_without_db(client, path):
    res = client.get(path)
    assert res.status_code == 503
    assert "Database not configured" in res.json()["detail"]


def test_query_returns_503_without_credentials(client):
    res = client.post("/query", json={"question": "How much does Dallas ISD spend?"})
    assert res.status_code == 503


def test_query_validates_question_length(client):
    assert client.post("/query", json={"question": ""}).status_code == 422
    assert client.post("/query", json={"question": "x" * 501}).status_code == 422


def test_sample_queries(client):
    res = client.get("/sample-queries")
    assert res.status_code == 200
    assert len(res.json()["sample_queries"]) == 10


def test_query_rate_limit():
    from src import api as api_mod

    api_mod._rate_buckets.clear()
    ip = "203.0.113.5"
    for _ in range(api_mod._RATE_LIMIT):
        assert api_mod._rate_limited(ip) is False
    assert api_mod._rate_limited(ip) is True
    api_mod._rate_buckets.clear()


def test_anomalies_district_filter_validated(client):
    # district_number longer than 6 chars is rejected before touching the DB
    res = client.get("/anomalies?district_number=1234567")
    assert res.status_code == 422


def test_outcomes_served_without_a_database(client):
    """Outcomes come from a precomputed static file, so this endpoint must work
    even with no database configured — unlike every other data endpoint."""
    res = client.get("/district/043905/outcomes")
    if res.status_code == 503:
        pytest.skip("outcomes_data.json not built in this checkout")
    assert res.status_code == 200
    body = res.json()
    assert body["district_number"] == "043905"
    assert body["meta"]["model_r2"] > 0
    # peer comparison must be present and structured [own value, peer median]
    for key, pair in body["measures"].items():
        assert len(pair) == 2, key
    assert client.get("/district/999999/outcomes").status_code == 404


def test_security_headers_present(client):
    """Only HSTS was set before. A public data site should not be framable,
    sniffable, or able to load third-party script."""
    h = client.get("/").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "SAMEORIGIN"
    assert "strict-origin" in h["Referrer-Policy"]
    csp = h["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'self'" in csp
    # /docs must stay usable — Swagger UI pulls its assets from a CDN
    assert "Content-Security-Policy" not in client.get("/docs").headers


def test_query_has_a_global_spend_ceiling():
    """X-Forwarded-For is spoofable, so a per-IP limit alone cannot bound cost.
    A caller presenting a fresh IP every time must still hit a wall."""
    from src import api as api_mod

    api_mod._rate_buckets.clear()
    api_mod._global_hits.clear()
    allowed = 0
    for i in range(api_mod._GLOBAL_LIMIT * 3):
        if not api_mod._rate_limited(f"198.51.100.{i % 250}.{i}"):
            allowed += 1
    assert allowed <= api_mod._GLOBAL_LIMIT
    api_mod._rate_buckets.clear()
    api_mod._global_hits.clear()


def test_robots_and_sitemap(client):
    """Search engines must be able to find the district pages. The dashboard
    renders districts client-side from ?d=, so without a sitemap they are
    invisible no matter how good the data is."""
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Sitemap: https://txisd.dev/sitemap.xml" in r.text
    assert "Disallow: /query" in r.text          # don't spend crawl budget on the paid path

    s = client.get("/sitemap.xml")
    assert s.status_code == 200
    assert s.headers["content-type"].startswith("application/xml")
    assert "https://txisd.dev/geomap" in s.text
    # every district in the outcomes payload should be linkable
    if "?d=" in s.text:
        assert s.text.count("<loc>") > 1000


def test_no_stale_prototype_domain_in_pages():
    """Shared links and citations must point at txisd.dev, not the vercel.app
    prototype URL — those are what get screenshotted and quoted."""
    from pathlib import Path

    for name in ("index.html", "geomap.html", "map.html"):
        text = (Path("static") / name).read_text()
        assert "texas-isd-finances.vercel.app" not in text, name


def test_economics_served_without_a_database(client):
    """Like outcomes, the economics layer is precomputed, so it must answer with
    no database configured — it is the only thing on the page a taxpayer can
    check against their own tax statement."""
    res = client.get("/district/165901/economics")
    if res.status_code == 503:
        pytest.skip("economics_data.json not built in this checkout")
    body = res.json()
    a = body["allocation"]
    # debt service sits outside TEA's operating total, so the parts compose
    assert a["instruction_per_student"] + a["other_operating_per_student"] == \
        a["operating_per_student"]
    assert a["operating_per_student"] + a["debt_per_student"] == a["total_per_student"]
    # a tax bill that is present must be internally consistent
    if body["tax"]:
        t = body["tax"]
        assert t["mo_rate"] + t["is_rate"] == pytest.approx(t["total_rate"], abs=1e-4)
        assert 0 <= t["leaves_district"] <= t["bill_on_home"]
    assert client.get("/district/999999/economics").status_code == 404


def test_economics_effects_carry_confidence_intervals(client):
    """An effect size without an interval invites the reader to treat noise as a
    finding — the spending effect in particular straddles zero and the page must
    be able to say so."""
    res = client.get("/economics/texas")
    if res.status_code == 503:
        pytest.skip("economics_data.json not built in this checkout")
    mp = res.json()["micro"]["marginal_product"]
    assert mp["n_districts"] > 500 and mp["horizon_years"] >= 1
    for lever, e in mp["effects"].items():
        assert e["ci_low"] <= e["per_unit"] <= e["ci_high"], lever


def test_charter_districts_are_not_counted_as_data_quality_failures(client):
    """A charter levies no property tax, so it has no rate by nature. Folding
    those into the withheld-for-QA count would overstate our own error rate."""
    res = client.get("/economics/texas")
    if res.status_code == 503:
        pytest.skip("economics_data.json not built in this checkout")
    meta = res.json()["meta"]
    assert meta["no_tax_jurisdiction"] > 100        # Texas has ~295 charters
    assert meta["tax_figures_withheld_qa"] < 50     # genuine disagreements are rare
    assert meta["split_half_reliability"] > 0.5     # the score must actually repeat


def test_bond_history_served_without_a_database(client):
    """The ballot is the only public record of what school debt was FOR — TEA
    does not itemise facilities. It must serve with no database, like outcomes."""
    res = client.get("/district/165901/bonds")
    if res.status_code == 503:
        pytest.skip("bond_data.json not built in this checkout")
    b = res.json()
    assert b["elections"], "a district in the payload must have at least one election"
    t = b["totals"]
    assert t["passed"] <= t["props"]
    assert t["approved"] <= t["asked"]
    for e in b["elections"]:
        assert isinstance(e["passed"], bool)
        # a district with no bond on record is a 404, not an empty list
    assert client.get("/district/999999/bonds").status_code == 404


def test_implausible_vote_tallies_are_not_published(client):
    """A fifth of source records show a multi-million-dollar bond as '1 for,
    0 against'. Those are placeholders, not turnout; printing them would put an
    obviously false number in front of a reader."""
    res = client.get("/bonds/texas")
    if res.status_code == 503:
        pytest.skip("bond_data.json not built in this checkout")
    meta = res.json()["meta"]
    assert 50 < meta["votes_reported_pct"] < 100
    d = client.get("/district/165901/bonds").json()
    for e in d["elections"]:
        if not e["votes_reported"]:
            assert e["for"] is None and e["against"] is None
        else:
            assert (e["for"] or 0) + (e["against"] or 0) >= 20


def test_bond_athletics_is_reported_as_an_upper_bound(client):
    """Propositions bundle, so athletics dollars include classrooms sold
    alongside. Both the bundled and the alone figure must ship — quoting only
    the flattering one would be a lie of selection."""
    res = client.get("/bonds/texas")
    if res.status_code == 503:
        pytest.skip("bond_data.json not built in this checkout")
    body = res.json()
    b = body["bundling"]
    assert {"athletics_alone", "athletics_with_buildings", "buildings_alone"} <= set(b)
    assert any("upper bound" in x for x in body["meta"]["limits"])
    # the finding itself: bundling helps, and it raises the ask
    assert b["athletics_with_buildings"]["pass_rate"] > b["athletics_alone"]["pass_rate"]


def test_results_are_reported_at_the_meets_bar_not_approaches(client):
    """TEA publishes three bars. 74% of Texas students reach "Approaches", 46%
    reach "Meets", 18% "Masters". A parent told 74% hears "at grade level",
    which Approaches is not, so the portal must report Meets. This is a
    correction to something that shipped, and it must not silently regress."""
    from pathlib import Path

    res = client.get("/district/043905/outcomes")
    if res.status_code == 503:
        pytest.skip("outcomes_data.json not built in this checkout")
    body = res.json()
    measures = body["measures"]
    # All three bars ship, so a reader can see the lower one too — but MEETS
    # must be the bar the expectation model scores against.
    assert "test_all_meets" in measures
    assert body["expectation"]["actual"] == measures["test_all_meets"][0], \
        "the district is scored against Meets, not Approaches"
    # Meets is the middle bar, so it must be lower than Approaches for the
    # same district — if this flips, the two have been swapped somewhere.
    if "test_all_approaches" in measures:
        assert measures["test_all_meets"][0] <= measures["test_all_approaches"][0]

    # and the page must not quietly go back to driving off Approaches
    page = Path("static/index.html").read_text()
    assert "test_all_approaches" not in page
    assert "percent-at-approaches" not in page


def test_negative_scaling_keeps_intervals_ordered(client):
    """The page scales effects for display: "cut turnover by 10" multiplies the
    per-unit effect by -10, which FLIPS the confidence interval. If the bounds
    are not re-sorted, the "crosses zero" test fails and an effect that cannot
    be told apart from zero is drawn as solid. This shipped once."""
    from pathlib import Path

    res = client.get("/economics/texas")
    if res.status_code == 503:
        pytest.skip("economics_data.json not built in this checkout")
    e = res.json()["micro"]["marginal_product"]["effects"]["teacher_turnover_pct"]
    lo, hi = sorted([e["ci_low"] * -10, e["ci_high"] * -10])
    assert lo <= e["per_unit"] * -10 <= hi
    # the page must re-sort rather than assume ci_low stays the lower bound
    page = Path("static/index.html").read_text()
    assert "Math.min(a, b)" in page and "Math.max(a, b)" in page


def test_hero_credentials_match_the_data(client):
    """The hero states four counted facts. Each has to be true of the whole
    portal, not of its longest single source — "67 years of records" was true
    only of the bond elections while every other dataset spans 17 years."""
    from pathlib import Path

    page = Path("static/index.html").read_text()
    assert ">17</b><i>years of budgets" in page, \
        "the years figure must describe the finance data, not the deepest source"
    assert "years of records" not in page, "that phrasing overstated every source but one"

    stats = client.get("/stats").json() if client.get("/stats").status_code == 200 else None
    if stats:
        span = stats["end_year"] - stats["start_year"] + 1
        assert span == 17, f"finance data spans {span} years; the hero says 17"


def test_equity_headlines_the_level_not_the_gap(client):
    """Ranking districts on the poor/non-poor gap is the obvious feature and it
    is wrong: the gap correlates about zero with how well poor students
    actually do, because a gap narrows just as easily when the top falls as
    when the bottom rises. The payload must headline the LEVEL and must publish
    the evidence for that choice rather than assert it."""
    res = client.get("/equity/texas")
    if res.status_code == 503:
        pytest.skip("equity_data.json not built in this checkout")
    body = res.json()
    st = body["state"]
    assert abs(st["gap_vs_level_correlation"]) < 0.25, \
        "if the gap ever did predict outcomes, this design decision needs revisiting"
    assert any("NOT the" in x and "gap" in x for x in body["meta"]["limits"])
    # leaders are ranked on how poor students do, so the list must descend on it
    poor = [x["poor_meets"] for x in body["leaders"]]
    assert poor == sorted(poor, reverse=True)
    assert all(x["tests"] >= 2000 for x in body["leaders"]), "leaders must not be noise"


def test_equity_reports_meets_and_flags_thin_cells(client):
    """Results are at Meets, and a district-group cell built on a handful of
    children is not published at all."""
    res = client.get("/district/227901/equity")
    if res.status_code == 503:
        pytest.skip("equity_data.json not built in this checkout")
    b = res.json()
    assert b["meta"]["bar"] == "Meets grade level"
    assert b["poor"]["tests"] >= b["meta"]["min_tests"]
    # Meets sits between Masters and Approaches for the same students
    p = b["poor"]
    if p["approaches"] is not None and p["masters"] is not None:
        assert p["masters"] <= p["meets"] <= p["approaches"]
    assert 0 <= p["percentile"] <= 100
    assert client.get("/district/999999/equity").status_code == 404


def test_takeover_ships_its_own_falsification_checks(client):
    """A difference-in-differences on one treated district is only as good as
    the checks around it. The payload must carry the parallel-trends test, the
    placebo across every district, and the composition check — and must not
    claim a p-value it cannot have."""
    res = client.get("/takeover/houston")
    if res.status_code == 503:
        pytest.skip("takeover_data.json not built in this checkout")
    d = res.json()
    assert d["parallel_trends"]["holds"] is True, \
        "if pre-trends stop being parallel the comparison is invalid and must not ship"
    assert d["placebo"]["districts_tested"] > 1000
    assert d["composition"]["houston"]["enrolment_change_pct"] is not None
    assert any("p-value" in x for x in d["meta"]["limits"])
    # the headline must be the difference, not Houston's raw change
    h = d["headline"]
    assert h["difference"] == pytest.approx(
        h["houston_change"] - h["comparison_change"], abs=0.05)


def test_takeover_reports_the_group_that_went_backwards(client):
    """Special education students in Houston fell relative to the comparison
    group. A result that only lists the groups that improved is advocacy, not
    analysis, so every tracked group must ship whatever its sign."""
    res = client.get("/takeover/houston")
    if res.status_code == 503:
        pytest.skip("takeover_data.json not built in this checkout")
    groups = res.json()["by_group"]
    assert len(groups) >= 5
    assert any(g["difference"] < 0 for g in groups), \
        "at least one group did worse; if that stops being true, re-verify rather than assume"
    for g in groups:
        assert g["difference"] == pytest.approx(
            g["houston_change"] - g["comparison_change"], abs=0.05)


def test_vercel_json_has_no_rewrites(client):
    """Vercel changed routing for backend-framework projects: an internal
    rewrite now passes the DESTINATION path to the app. The old
    `/(.*) -> /api/index` rewrite therefore handed FastAPI the literal path
    "/api/index" on every request, and the whole site 404'd while the build
    still reported READY. The fastapi preset routes to api/index.py by itself."""
    import json as _json
    from pathlib import Path

    cfg = _json.loads(Path("vercel.json").read_text())
    assert "rewrites" not in cfg, \
        "a rewrite here silently 404s every route in production"
    # the entrypoint the preset looks for must exist
    assert Path("api/index.py").exists()


def test_tutorial_covers_every_section_on_the_page(client):
    """The tour was written before four sections existed and silently stopped
    describing half the page. Every section a reader can reach should have a
    tour step, and every step should point at a section that exists."""
    import re
    from pathlib import Path

    page = Path("static/index.html").read_text()
    sections = set(re.findall(r'<section id="([a-z-]+)"', page))
    tour = set(re.findall(r"'([a-z-]+-section)'\]", page.split("const TOUR = [")[1]
                          .split("];")[0]))
    assert tour <= sections, f"tour points at sections that do not exist: {tour - sections}"
    # the sections carrying the findings must all be described
    must = {"kpi-section", "dollar-section", "outcomes-section", "econ-section",
            "equity-section", "bond-section", "takeover-section", "insights-section"}
    assert must <= tour, f"tour never mentions: {must - tour}"


def test_tutorial_doc_uses_the_corrected_bar(client):
    """The written tutorial has to carry the same correction the site does, or
    it teaches people to read the wrong number."""
    from pathlib import Path

    doc = Path("docs/TUTORIAL.md").read_text()
    assert "Meets" in doc and "46.5" in doc
    assert "Approaches is not grade level" in doc
    for topic in ("recapture", "bond", "low-income", "takeover"):
        assert topic in doc.lower(), f"tutorial never mentions {topic}"


def test_displayed_figures_add_up_for_every_district(client):
    """A superintendent reading their own page will add the column. Rounding
    each component independently left a quarter of districts off by a dollar —
    explainable, and still the first thing anyone notices. Every district, not
    a sample."""
    import json as _json
    from pathlib import Path

    path = Path("static/economics_data.json")
    if not path.exists():
        pytest.skip("economics_data.json not built in this checkout")
    data = _json.loads(path.read_text())
    for num, r in data["districts"].items():
        a = r["allocation"]
        assert a["instruction_per_student"] + a["other_operating_per_student"] == \
            a["operating_per_student"], num
        assert a["operating_per_student"] + a["debt_per_student"] == \
            a["total_per_student"], num
        t = r.get("tax")
        if t:
            # the bill must be what the PUBLISHED rate implies, so a reader
            # multiplying it by their own home value lands on the same answer
            assert t["bill_on_home"] == round(t["home_value"] / 100 * t["total_rate"]), num
            assert t["mo_rate"] + t["is_rate"] == pytest.approx(t["total_rate"], abs=1e-4), num


def test_revenue_shows_who_pays_from_gross_local_collections(client):
    """Where the money GOES was answered; where it comes FROM was not. TEA
    reports local M&O revenue net of recapture, so a property-wealthy district
    looks state-funded unless the local share is built from gross collections —
    its taxpayers did pay, the state simply took a share away."""
    res = client.get("/district/165901/economics")
    if res.status_code == 503:
        pytest.skip("economics_data.json not built in this checkout")
    r = res.json().get("revenue")
    assert r, "every taxing district must report where its money comes from"
    assert r["local_pct"] + r["state_pct"] + r["federal_pct"] == 100, \
        "shares are forced to 100 so the labels on the bar agree with each other"
    assert "gross" in r["note"] and "recapture" in r["note"]
    # Midland is heavily property-funded; net-of-recapture would understate it
    assert r["local_pct"] > 50
    tx = client.get("/economics/texas").json()["macro"]["revenue"]
    assert tx["local_pct"] + tx["state_pct"] + tx["federal_pct"] == 100


def test_bond_outcome_test_ships_and_refuses_to_overclaim(client):
    """Every bond campaign argues the buildings help children learn. The test
    ships whatever it finds, and where the interval includes zero the payload
    must say so rather than let the point estimate read as a result."""
    res = client.get("/district/165901/bonds")
    if res.status_code == 503:
        pytest.skip("bond_data.json not built in this checkout")
    w = res.json().get("did_it_work")
    assert w, "the bonds endpoint must carry the outcome test, not just the ballots"
    assert w["bonds_tested"] > 100 and w["districts"] > 50
    assert w["difference"] == pytest.approx(
        w["passed_change"] - w["defeated_change"], abs=0.02)
    # significance and the flag must agree — this is what stops a null being
    # presented as a finding
    assert w["distinguishable_from_zero"] == (w["p_value"] < 0.05)
    assert "seats, not scores" in w["caveat"]


def test_maps_ship_a_table_twin():
    """Both maps draw to a canvas, which no keyboard or screen reader can enter.
    Each must publish the same data as a real table. The styles alone once
    shipped without the markup, so check for all three parts."""
    from pathlib import Path

    for name in ("geomap.html", "map.html"):
        text = (Path("static") / name).read_text()
        assert '<details class="a11y"' in text, f"{name}: no table twin markup"
        assert "function renderA11yTable()" in text, f"{name}: no render function"
        assert "renderA11yTable();" in text, f"{name}: render function never called"
        # the caption must be written with the rest of the table, not before it
        assert "$('a11y-cap').textContent" not in text, name
        assert "getElementById('a11y-cap').textContent" not in text, name


def test_pennies_always_sum_to_one_hundred():
    """The dollar must never gain or lose a penny to rounding, whatever the mix."""
    from src.api import _to_pennies

    cases = [
        {"a": 1.0},
        {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3},
        {"a": 0.435, "b": 0.185, "c": 0.075, "d": 0.071, "e": 0.064,
         "f": 0.041, "g": 0.038, "h": 0.031, "i": 0.06},
        dict.fromkeys("abcdefghijk", 1 / 11),
        {"a": 0.9994, "b": 0.0003, "c": 0.0003},
    ]
    for shares in cases:
        cents = _to_pennies(shares)
        assert sum(cents.values()) == 100, shares
        assert all(v >= 0 for v in cents.values())
        assert set(cents) == set(shares)


def test_dollar_shares_residual_and_rejection():
    """Named categories become shares of total spend; the gap becomes
    'Everything else'; a row whose parts exceed its stated total is rejected."""
    from src.api import _DOLLAR_CATEGORIES, _dollar_shares

    zero = {c: 0 for _k, _l, cols, _d, _co in _DOLLAR_CATEGORIES for c in cols}

    row = dict(zero, total_spend=1000, classroom_instruction=400, debt_service=100)
    shares = _dollar_shares(row)
    assert shares["classroom"] == pytest.approx(0.4)
    assert shares["debt"] == pytest.approx(0.1)
    assert shares["other"] == pytest.approx(0.5)
    assert sum(shares.values()) == pytest.approx(1.0)

    # residual never goes negative, and impossible rows are dropped, not fudged
    assert _dollar_shares(dict(zero, total_spend=0)) is None
    assert _dollar_shares(dict(zero, total_spend=100, classroom_instruction=900)) is None


def test_year_bounds_validated(client):
    res = client.get("/district/057905/summary?start_year=1990")
    assert res.status_code == 422
    res = client.get("/anomalies?year=2050")
    assert res.status_code == 422


# --- endpoints that had no test at all until the July 2026 audit -------------
# All four served 200 in production the whole time; none of them would have
# caught a regression. /dollar/texas in particular feeds the landing-page hero.

def test_static_map_pages_served(client):
    """/map and /map-data need no database and must survive an outage."""
    res = client.get("/map")
    assert res.status_code == 200
    assert "<canvas" in res.text

    res = client.get("/map-data")
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["year"] >= 2024
    assert len(body["nodes"]) > 1000


def test_district_geo_served_without_database(client):
    res = client.get("/district-geo")
    assert res.status_code == 200
    body = res.json()
    # Charters have no boundary, so this is short of the 1,310 finance districts
    # by design. The meta says so; assert it keeps saying so.
    assert len(body["d"]) > 900
    assert "Charter" in body["meta"]["note"]
    assert "TIGER" in body["meta"]["source"]


def test_dollar_texas_requires_database(client):
    """The landing hero's figure. Database-backed, so 503 without one — the
    page falls back to /fallback-index rather than rendering '$—'."""
    assert client.get("/dollar/texas").status_code == 503


def test_fallback_index_survives_a_dead_database(client):
    """The survival kit: picker + statewide figures with no database at all.

    Fourteen endpoints here are static JSON and sail through an outage. The
    front door did not, so a paused free tier blanked a site full of healthy
    data. This endpoint is what the page falls back to.
    """
    res = client.get("/fallback-index")
    assert res.status_code == 200
    body = res.json()

    assert len(body["districts"]) > 1000
    assert all({"district_number", "district_name"} <= set(d) for d in body["districts"][:50])
    # Every district listed must be findable in the payloads that render it,
    # or the picker promises a page with nothing on it.
    assert any(d["district_number"] == "101912" for d in body["districts"]), "Houston ISD missing"

    assert body["stats"]["total_districts"] > 1000
    assert len(body["benchmarks"]) >= 15
    assert body["dollar_texas"]["total_spend"] > 0
    assert body["captured"], "the snapshot must be dated — the page shows the date"


def test_fallback_districts_all_have_static_content():
    """A district in the picker with no payload behind it is a dead end."""
    import json
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "static"
    listed = {d["district_number"] for d in json.loads((static / "fallback_index.json").read_text())["districts"]}
    covered = set()
    for name, key in (("economics_data.json", "districts"), ("outcomes_data.json", "districts"),
                      ("equity_data.json", "districts"), ("bond_data.json", "districts"),
                      ("district_geo.json", "d")):
        covered |= set(json.loads((static / name).read_text())[key])
    orphans = listed - covered
    assert not orphans, f"{len(orphans)} districts in the picker have no data to show: {sorted(orphans)[:5]}"


# --- the shared spend ceiling (audit finding H-2) ----------------------------
# The old limiter counted in process memory, so on serverless "60 per minute"
# meant "60 per minute PER INSTANCE" and the real bound was however many
# instances an attacker could provoke. These tests pin the replacement.

class _FakePool:
    """Minimal asyncpg-pool stand-in backed by a dict, honouring the SQL's
    conditional-increment semantics: return the new count while under the cap,
    return None once it is reached."""

    def __init__(self, fail=False):
        self.counts: dict = {}
        self.fail = fail
        self.calls = 0

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                if pool.fail:
                    raise RuntimeError("database unreachable")
                return pool

            async def __aexit__(self, *a):
                return False
        return _Ctx()

    async def fetchval(self, _sql, kind, _trunc, cap):
        self.calls += 1
        cur = self.counts.get(kind, 0)
        if cur >= cap:
            return None
        self.counts[kind] = cur + 1
        return cur + 1


@pytest.mark.anyio
async def test_shared_limit_blocks_at_the_ceiling():
    import src.api as api
    pool = _FakePool()
    allowed = 0
    for _ in range(api._GLOBAL_LIMIT + 5):
        if await api._shared_limit_reached(pool):
            break
        allowed += 1
    assert allowed == api._GLOBAL_LIMIT, "the shared ceiling did not hold"


@pytest.mark.anyio
async def test_daily_ceiling_is_independent_of_the_minute_ceiling():
    """A per-minute cap alone still bills 86,400 calls a day. The daily cap is
    the one that protects the bill, so it must be counted separately."""
    import src.api as api
    pool = _FakePool()
    await api._shared_limit_reached(pool)
    assert pool.counts["minute"] == 1 and pool.counts["day"] == 1


@pytest.mark.anyio
async def test_metering_outage_does_not_take_down_the_feature():
    """Fails open on availability: /query's own connection is separate, so a
    metering outage must not break a working feature. The per-instance limit
    still applies, so this is the old exposure, not a new one."""
    import src.api as api
    assert await api._shared_limit_reached(_FakePool(fail=True)) is False
    assert await api._shared_limit_reached(None) is False


@pytest.mark.anyio
async def test_refused_calls_cost_nothing():
    """The ceiling is checked before the engine is constructed, so a refused
    request never builds an OpenAI client or opens the agent's connection."""
    import inspect

    import src.api as api
    src = inspect.getsource(api.nlp_query)
    assert src.index("_shared_limit_reached") < src.index("get_nlp_engine")


def test_usage_table_is_not_readable_by_the_metered_role():
    """nlp_reader is what the language model runs as. It must not be able to
    read its own meter, and certainly not edit it."""
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent / "sql" / "create_nlp_usage.sql").read_text()
    assert "REVOKE ALL ON public.nlp_usage FROM nlp_reader" in sql
    assert "REVOKE ALL ON public.nlp_usage FROM anon, authenticated" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql


# --- Texas ISD Intelligence: cron auth + briefing endpoint --------------------

def test_cron_requires_secret_configured(client, monkeypatch):
    """With no CRON_SECRET set, the endpoint refuses rather than running open."""
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert client.get("/api/cron/isd-intelligence").status_code == 503


def test_cron_rejects_missing_or_wrong_bearer(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert client.get("/api/cron/isd-intelligence").status_code == 401
    assert client.get("/api/cron/isd-intelligence",
                      headers={"authorization": "Bearer wrong"}).status_code == 401


def test_cron_is_not_in_the_public_schema(client):
    """It must not appear in OpenAPI — it is infrastructure, not a public route."""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/cron/isd-intelligence" not in paths


def test_briefing_served_from_committed_snapshot_without_db(client):
    """/briefing works at Tier 1 — no database — from the committed snapshot."""
    res = client.get("/briefing")
    assert res.status_code == 200
    body = res.json()
    assert "meta" in body and "top_findings" in body
    assert body["meta"]["run_date"]


class _RecordingConn:
    def __init__(self, store):
        self.store = store

    async def fetchval(self, _sql, arg):
        self.store.setdefault("fetchval_args", []).append(arg)
        return None            # today's run does not exist yet

    async def execute(self, _sql, *args):
        self.store["execute_args"] = args
        return "INSERT 0 1"


class _RecordingPool:
    def __init__(self):
        self.store: dict = {}

    def acquire(self):
        conn = _RecordingConn(self.store)

        class _Ctx:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False
        return _Ctx()


def test_cron_binds_a_date_not_a_string(client, monkeypatch):
    """asyncpg binds a `date` column from a datetime.date, never a str. Passing
    the isoformat string raises 'str object has no attribute toordinal' and the
    store fails silently — the intel cron never persisted in production until
    this was fixed. Pin the argument type so the regression cannot return."""
    import datetime as _dt

    import src.api as api
    from scripts import isd_intel
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    monkeypatch.setattr(isd_intel, "fetch_tea_newsroom", lambda *a, **k: [])
    monkeypatch.setattr(isd_intel, "fetch_google_news_rss", lambda *a, **k: [])
    pool = _RecordingPool()
    monkeypatch.setattr(api.app.state, "db_pool", pool, raising=False)

    res = client.get("/api/cron/isd-intelligence",
                     headers={"authorization": "Bearer s3cret"})
    assert res.status_code == 200
    assert res.json()["stored"] is True
    # The run_date bound to BOTH the idempotency check and the INSERT must be a
    # date object, not the isoformat string.
    assert pool.store["execute_args"], "the INSERT never ran"
    assert isinstance(pool.store["execute_args"][0], _dt.date)
    assert not isinstance(pool.store["execute_args"][0], str)
    assert all(isinstance(a, _dt.date) for a in pool.store.get("fetchval_args", []))


def test_vercel_json_still_has_no_rewrites():
    """A rewrites block 404s the whole site (CLAUDE.md invariant). The cron
    addition must not have introduced one."""
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).resolve().parent.parent / "vercel.json").read_text())
    assert "rewrites" not in cfg
    assert cfg["crons"][0]["path"] == "/api/cron/isd-intelligence"


def test_design_stylesheet_is_actually_served(client):
    """Every page links /static/design.css. There is no StaticFiles mount, so
    without an explicit route that link 404s and the entire site renders
    unstyled — which is exactly what happened the first time."""
    res = client.get("/static/design.css")
    assert res.status_code == 200, "the design system 404s; every page would be unstyled"
    assert "text/css" in res.headers.get("content-type", "")
    assert "--accent" in res.text and ':root[data-theme="dark"]' in res.text


def test_static_directory_is_not_blanket_mounted(client):
    """The committed data artefacts live in static/ too. Serving one stylesheet
    must not expose the rest at guessable URLs."""
    for leaky in ("/static/outcomes_data.json", "/static/bond_data.json",
                  "/static/index.html", "/static/isd_briefing.json"):
        assert client.get(leaky).status_code == 404, f"{leaky} should not be served"


def test_vercelignore_ships_the_runtime_script():
    """The cron does `from scripts import isd_intel` at request time. If
    .vercelignore excludes it, the daily run ImportErrors in production and the
    feed can never refresh past its snapshot. Ship the package marker + module."""
    from pathlib import Path
    lines = (Path(__file__).resolve().parent.parent / ".vercelignore").read_text().splitlines()
    assert "!scripts/isd_intel.py" in lines, "cron's module is not un-ignored for deploy"
    assert "!scripts/__init__.py" in lines, "scripts package marker is not un-ignored"
    # And a blanket `scripts/` (without the negations) must not slip back in —
    # it would re-exclude the file the negations just rescued.
    assert "scripts/" not in lines, "blanket scripts/ exclude would defeat the negation"


# --- Mapbox heatmap: token from env, CSP scoped to one page ------------------

def test_mapbox_token_served_from_env(client, monkeypatch):
    monkeypatch.delenv("MAPBOX_TOKEN", raising=False)
    assert client.get("/mapbox-token").json() == {"token": ""}
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    assert client.get("/mapbox-token").json() == {"token": "pk.test"}


def test_secret_mapbox_key_is_not_in_the_repo():
    """The sk. token must never be committed. Guard against a paste slipping in."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    # Scan tracked text, not git history; a secret in history is a rotate-it problem.
    out = subprocess.run(["git", "grep", "-lI", "sk.eyJ", "--", ".", ":!tests"],
                         cwd=root, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"a Mapbox secret token appears in: {out.stdout}"


def test_heatmap_csp_allows_mapbox_but_home_stays_strict(client):
    hm = client.get("/heatmap").headers.get("content-security-policy", "")
    assert "api.mapbox.com" in hm and "*.tiles.mapbox.com" in hm
    home = client.get("/").headers.get("content-security-policy", "")
    assert "mapbox" not in home, "the Mapbox CSP hole must be scoped to /heatmap only"


def test_heatmap_page_served(client):
    res = client.get("/heatmap")
    assert res.status_code == 200
    assert "mapbox-gl" in res.text          # loads Mapbox GL
    assert 'id="a11y-table"' in res.text    # and carries a table twin
