"""Regression evidence for the authorized October 2026 MCP release."""
import base64
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.build_forensic_data import annual_debt_service, build
from src import mcp_protocol as P
from src import mcp_tools
from src.api import app

ROOT = Path(__file__).resolve().parent.parent


def artifact(name):
    return json.loads((ROOT / "static" / f"{name}_data.json").read_text())


VALID_CALLS = [
    (tool["name"], {"name": "Argyle"} if tool["name"] == "find_district" else
     {"district_numbers": ["061910", "057905"]} if tool["name"] == "compare_districts" else
     {} if tool["name"] == "texas_overview" else {"district_number": "061910"})
    for tool in mcp_tools.list_tools()
] + [("find_district", {"name": "Wylie"}),
     ("district_debt", {"district_number": "057905"}),
     ("district_money", {"district_number": "057905"})]


@pytest.mark.parametrize("name,args", VALID_CALLS)
def test_14_valid_wire_calls(name, args):
    with TestClient(app) as client:
        response = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args, "_meta": {
                P.META_VERSION: P.PROTOCOL_VERSION, P.META_CLIENT_CAPS: {}}}},
            headers={"MCP-Protocol-Version": P.PROTOCOL_VERSION,
                     "Mcp-Method": "tools/call", "Mcp-Name": name})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["limits"]
    assert result["content"][0]["text"]


@pytest.mark.parametrize("name,args", [
    ("find_district", {"name": "a"}),
    ("district_debt", {"district_number": "999999"}),
    ("compare_districts", {"district_numbers": ["061910"]}),
    ("district_money", {"district_number": "NoSuchDistrictZZZ"}),
])
def test_4_invalid_calls_are_controlled(name, args):
    result = mcp_tools.call_tool(name, args)
    assert result["isError"] is True
    assert "structuredContent" not in result
    assert not re.search(r"Traceback|KeyError|TypeError|AttributeError", str(result))


def test_argyle_disagreement_is_visible_and_dates_are_separate():
    result = mcp_tools.call_tool("district_debt", {"district_number": "061910"})
    data = result["structuredContent"]
    assert (data["principal"], data["interest"], data["total"], data["clears_in"]) == (
        670626909, 554498697, 1225125606, 2056)
    assert data["source"]["as_of_date"] is None
    assert data["fiscal_year"] == 2025
    review = data["source_review"]
    assert review["status"] == "unresolved"
    html, hb1378, filing = review["sources"][1:]
    assert html["as_of_date"] == hb1378["fiscal_period_end"] == "2025-08-31"
    assert filing["principal_as_of_date"] == "2026-02-15"
    assert filing["last_payment_fiscal_year"] == 2057
    assert sum(Decimal(str(filing[k])) for k in ("principal", "interest")) == Decimal("1273804554.70")
    text = result["content"][0]["text"]
    for value in ("Unresolved", "1,225,125,606", "1,225,069,254", "1,273,804,555", "2057", "February 15, 2026"):
        assert value in text
    assert "not a verified final payment or maturity year" in text
    assert review["summary"] in data["limits"]
    with TestClient(app) as client:
        web = client.get("/district/061910/debt").json()
    assert web["source_review"] == review
    assert web["limits"] == data["limits"]


def test_annual_debt_uses_source_dollars_and_rebuilds_exactly():
    econ, forensic = artifact("economics"), artifact("forensic")
    assert forensic["districts"]["061910"]["outside_operating"]["annual_total"] == 31498615
    assert 5152 * 6114 == 31499328  # the discarded rounded reconstruction
    assert forensic["statewide"]["debt_total"] == 13859481756
    fixture = json.loads((ROOT / "tests/fixtures/provenance.json").read_text())
    fiscal_2025 = next(y for y in fixture["years"] if y["year"] == 2025)
    assert fiscal_2025["debt_service"] == forensic["statewide"]["debt_total"]
    assert forensic["statewide"]["debt_total_districts"] == 1202
    assert build(econ, artifact("bond"), artifact("outcomes")) == forensic
    missing = {**econ["districts"]["061910"], "allocation": {"debt_per_student": 5152}}
    assert annual_debt_service(missing) is None


def test_year_labels_do_not_mix_finance_outcomes_and_ratings():
    def result(name):
        return mcp_tools.call_tool(name, {"district_number": "061910"})
    for name, key, year in (("district_campuses", "rating_year", 2025),
                            ("district_national", "fiscal_year", 2024)):
        r = result(name)
        assert r["structuredContent"][key] == year
        assert str(year) in r["content"][0]["text"]
    text = result("district_forensics")["content"][0]["text"]
    assert "finance fiscal 2025" in text and "TEA Snapshot 2024" in text
    r = mcp_tools.call_tool("compare_districts", {"district_numbers": ["061910", "057905"]})
    assert r["structuredContent"]["fiscal_year"] == 2025
    assert r["structuredContent"]["districts"][0]["outcomes_year"] == 2024


def test_display_typo_preserves_source_and_does_not_reclassify():
    r = mcp_tools.call_tool("district_bonds", {"district_number": "061910"})
    data = r["structuredContent"]
    election = next(e for e in data["elections"] if "Atheltics" in e["purpose"])
    assert election["purpose_display"] == "School Building, Athletics, Renovations"
    assert election["category"] == "buildings & other"
    assert any("have not been reclassified" in x for x in data["limits"])
    description = next(t["description"] for t in mcp_tools.list_tools() if t["name"] == "district_bonds")
    assert "1958-2024" not in description


def test_internal_errors_do_not_expose_exception_details(monkeypatch):
    def broken(args):
        raise RuntimeError("private-path/private-configuration")
    monkeypatch.setitem(mcp_tools._BY_NAME["district_money"], "handler", broken)
    result = mcp_tools.call_tool("district_money", {"district_number": "061910"})
    assert result["isError"] is True
    assert not re.search(r"RuntimeError|private-path|private-configuration", str(result))
    assert "unavailable data" in result["content"][0]["text"]


def test_server_branding_reuses_the_portal_favicon():
    assert P.SERVER_INFO["title"] == "Texas ISD Finance Intelligence"
    html = (ROOT / "static/index.html").read_text()
    encoded = re.search(r'rel="icon" href="data:image/svg\+xml;base64,([^"]+)', html)[1]
    assert (ROOT / "static/txisd-icon.svg").read_bytes().strip() == base64.b64decode(encoded)
    with TestClient(app) as client:
        icon = client.get("/static/txisd-icon.svg")
        discovery = client.get("/.well-known/mcp.json").json()
    assert icon.status_code == 200
    assert discovery["mcpServers"]["texas-isd"]["name"] == P.SERVER_INFO["title"]
