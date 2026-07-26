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
    assert res.json() == {"status": "degraded", "database": "not configured"}


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
