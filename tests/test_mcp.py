"""Tests for the MCP 2026-07-28 server.

Three things are being protected here.

**The wire format.** A client that speaks the spec must work without special
casing, and one that does not must get the error the spec names. Version,
`_meta` and the mirrored headers are all validated, because a load balancer
routing on `Mcp-Method` while the server executes on the body is a real hole —
which is exactly why the spec made the mismatch its own error code.

**The blast radius.** These tools read committed JSON. They must not reach the
database, must not reach the LLM, and must not expose `/query`. If any of that
changes, an outage or an injected prompt reaches a surface that today cannot be
touched.

**The caveats.** The point of this server is that the limits travel with the
numbers into someone else's chat window. A result without its `limits` is worse
than no result, because it reads as certainty.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import mcp_protocol as P  # noqa: E402
from src import mcp_tools  # noqa: E402
from src.api import app  # noqa: E402

V = P.PROTOCOL_VERSION
DALLAS = "057905"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def rpc(client, method, params=None, *, rid=1, version=V, headers=None, body=None):
    """Send a request the way a conforming client does: `_meta` in the body and
    the mirrored headers on the envelope."""
    params = dict(params or {})
    params.setdefault("_meta", {
        P.META_VERSION: version,
        P.META_CLIENT_INFO: {"name": "test-client", "version": "0.0.1"},
        P.META_CLIENT_CAPS: {},
    })
    payload = body if body is not None else {
        "jsonrpc": "2.0", "id": rid, "method": method, "params": params}
    h = {"MCP-Protocol-Version": version, "Mcp-Method": method,
         "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    if method in P.NAME_SOURCE and P.NAME_SOURCE[method] in params:
        h["Mcp-Name"] = params[P.NAME_SOURCE[method]]
    h.update(headers or {})
    return client.post("/mcp", content=json.dumps(payload), headers=h)


def call(client, tool, args=None, rid=1):
    return rpc(client, "tools/call", {"name": tool, "arguments": args or {}}, rid=rid)


# --- discovery and listing --------------------------------------------------

def test_discover_reports_the_version_and_capabilities(client):
    res = rpc(client, "server/discover", {})
    assert res.status_code == 200
    r = res.json()["result"]
    assert r["resultType"] == "complete"
    assert r["supportedVersions"] == [V]
    assert "tools" in r["capabilities"]
    assert r["_meta"][P.META_SERVER_INFO]["name"]
    assert r["instructions"]
    assert r["cacheScope"] == "public" and r["ttlMs"] > 0


def test_tools_list_is_cacheable_and_deterministic(client):
    first = rpc(client, "tools/list", {}).json()["result"]
    second = rpc(client, "tools/list", {}).json()["result"]
    assert first["tools"] == second["tools"], "tool order must be stable for caching"
    # The underlying data moves once a year; saying so is the whole caching win.
    assert first["ttlMs"] >= 3_600_000 and first["cacheScope"] == "public"


def test_every_tool_is_well_formed(client):
    tools = rpc(client, "tools/list", {}).json()["result"]["tools"]
    assert len(tools) >= 6
    seen = set()
    for t in tools:
        assert t["name"] not in seen
        seen.add(t["name"])
        assert t["name"].replace("_", "").isalnum() and len(t["name"]) <= 128
        assert t["description"] and t["title"]
        assert t["inputSchema"]["type"] == "object"
        # 2020-12 is the default dialect; declaring another would need $schema.
        assert "$schema" not in t["inputSchema"]
        assert "handler" not in t, "the callable must never reach the wire"
        assert t["annotations"]["readOnlyHint"] is True


def test_x_mcp_header_annotations_are_legal(client):
    """The spec makes a client REJECT a tool whose annotation is invalid, so a
    malformed one silently removes the tool from every client."""
    tools = rpc(client, "tools/list", {}).json()["result"]["tools"]
    for t in tools:
        names = []
        for prop in (t["inputSchema"].get("properties") or {}).values():
            hdr = prop.get("x-mcp-header")
            if hdr is None:
                continue
            assert hdr and hdr.strip() == hdr and "\r" not in hdr and "\n" not in hdr
            # Only primitives may be mirrored, and `number` is excluded.
            assert prop.get("type") in {"string", "integer", "boolean"}
            names.append(hdr.lower())
        assert len(names) == len(set(names)), f"{t['name']} reuses a header name"


# --- the header contract ----------------------------------------------------

def test_a_missing_method_header_is_rejected(client):
    res = client.post("/mcp", content=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        "params": {"_meta": {P.META_VERSION: V, P.META_CLIENT_CAPS: {}}}}),
        headers={"MCP-Protocol-Version": V})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == P.HEADER_MISMATCH


def test_a_header_that_disagrees_with_the_body_is_rejected(client):
    """A gateway routing on the header while the server executes the body is
    the attack this error code exists for."""
    res = rpc(client, "tools/list", {}, headers={"Mcp-Method": "tools/call"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == P.HEADER_MISMATCH


def test_the_tool_name_header_must_match_the_body(client):
    res = rpc(client, "tools/call", {"name": "texas_overview", "arguments": {}},
              headers={"Mcp-Name": "district_money"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == P.HEADER_MISMATCH


def test_a_base64_encoded_name_header_is_decoded_before_comparing(client):
    import base64
    enc = "=?base64?" + base64.b64encode(b"texas_overview").decode() + "?="
    res = rpc(client, "tools/call", {"name": "texas_overview", "arguments": {}},
              headers={"Mcp-Name": enc})
    assert res.status_code == 200, res.text
    assert res.json()["result"]["isError"] is False


def test_the_protocol_version_header_must_match_the_body(client):
    res = rpc(client, "tools/list", {}, headers={"MCP-Protocol-Version": "2025-11-25"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == P.HEADER_MISMATCH


# --- version and _meta ------------------------------------------------------

def test_an_unsupported_version_lists_what_is_supported(client):
    res = rpc(client, "tools/list", {}, version="1900-01-01")
    assert res.status_code == 400
    err = res.json()["error"]
    assert err["code"] == P.UNSUPPORTED_VERSION
    assert err["data"]["supported"] == [V]
    assert err["data"]["requested"] == "1900-01-01"


def test_missing_required_meta_is_invalid_params(client):
    for missing in (P.META_VERSION, P.META_CLIENT_CAPS):
        meta = {P.META_VERSION: V, P.META_CLIENT_CAPS: {}}
        meta.pop(missing)
        res = rpc(client, "tools/list", {"_meta": meta})
        assert res.status_code == 400, missing
        assert res.json()["error"]["code"] == P.INVALID_PARAMS, missing


def test_client_info_is_optional(client):
    res = rpc(client, "tools/list",
              {"_meta": {P.META_VERSION: V, P.META_CLIENT_CAPS: {}}})
    assert res.status_code == 200


# --- method and transport rules ---------------------------------------------

def test_an_unknown_method_is_404_with_a_jsonrpc_body(client):
    """404 lets a client tell a modern server from a legacy one with no MCP
    endpoint; the JSON-RPC body is what makes the difference visible."""
    res = rpc(client, "resources/list", {})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == P.METHOD_NOT_FOUND


def test_a_notification_gets_202_and_no_body(client):
    res = client.post("/mcp", content=json.dumps({
        "jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}}),
        headers={"MCP-Protocol-Version": V, "Mcp-Method": "notifications/cancelled"})
    assert res.status_code == 202
    assert not res.content


def test_get_and_delete_are_405(client):
    """The GET stream and DELETE teardown were removed in this revision."""
    for m in ("get", "delete"):
        res = getattr(client, m)("/mcp")
        assert res.status_code == 405
        assert res.headers.get("allow") == "POST"


def test_a_legacy_initialize_is_told_what_this_server_speaks(client):
    """Legacy clients cannot fall forward, so the error is their only clue."""
    res = client.post("/mcp", content=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        headers={"Mcp-Method": "initialize"})
    assert res.status_code == 400
    assert V in json.dumps(res.json())


def test_malformed_json_is_a_parse_error(client):
    res = client.post("/mcp", content=b"{not json",
                      headers={"MCP-Protocol-Version": V, "Mcp-Method": "tools/list"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == P.PARSE_ERROR


def test_a_foreign_origin_is_refused(client):
    """DNS-rebinding guard. Absent Origin is fine — that is not a browser."""
    res = rpc(client, "tools/list", {}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_the_scanner_filter_does_not_eat_the_mcp_endpoint():
    from src.scanner import is_scanner_path
    assert not is_scanner_path("/mcp")


# --- the tools --------------------------------------------------------------

def test_find_district_resolves_a_name(client):
    res = call(client, "find_district", {"name": "dallas"})
    r = res.json()["result"]
    assert r["isError"] is False
    nums = [m["district_number"] for m in r["structuredContent"]["matches"]]
    assert DALLAS in nums
    assert r["structuredContent"]["limits"]


def test_find_district_warns_that_a_name_is_not_an_identifier(client):
    """Thirteen Texas names are shared by two districts. A model that does not
    know that will quote the wrong district's figures."""
    r = call(client, "find_district", {"name": "wylie"}).json()["result"]
    assert len({m["district_number"] for m in r["structuredContent"]["matches"]}) >= 2
    assert "not an identifier" in json.dumps(r["structuredContent"]["limits"]).lower()


@pytest.mark.parametrize("tool", [
    "district_money", "district_forensics", "district_trends", "district_bonds"])
def test_each_district_tool_answers_and_carries_its_limits(client, tool):
    r = call(client, tool, {"district_number": DALLAS}).json()["result"]
    assert r["isError"] is False, r["content"][0]["text"]
    assert r["structuredContent"]["limits"], f"{tool} returned no limits"
    assert "Dallas" in r["content"][0]["text"]


def test_a_dropped_leading_zero_is_repaired_not_rejected(client):
    """Models drop leading zeros from `057905` constantly. Failing on that
    wastes a turn on a mistake the server can simply fix."""
    r = call(client, "district_money", {"district_number": "57905"}).json()["result"]
    assert r["isError"] is False
    assert r["structuredContent"]["district_number"] == DALLAS


def test_a_bad_district_number_is_a_tool_error_not_a_protocol_error(client):
    """isError lets the model self-correct; a JSON-RPC error usually ends the
    attempt."""
    body = call(client, "district_money", {"district_number": "banana"}).json()
    assert "error" not in body
    assert body["result"]["isError"] is True
    assert "six digits" in body["result"]["content"][0]["text"]


def test_an_unknown_district_says_so(client):
    r = call(client, "district_money", {"district_number": "999999"}).json()["result"]
    assert r["isError"] is True


def test_texas_overview_carries_the_fragile_bond_finding(client):
    """This is the claim most likely to be over-read. The word has to be in the
    text a model reads, not only in a field it may ignore."""
    r = call(client, "texas_overview").json()["result"]
    assert r["isError"] is False
    text = r["content"][0]["text"]
    assert "SUGGESTIVE, NOT SETTLED" in text
    assert "p=0.038" in text or "p=" in text


def test_texas_overview_reports_the_seventeen_year_trend(client):
    sc = call(client, "texas_overview").json()["result"]["structuredContent"]
    keys = {f["key"] for f in sc["trend_findings"]}
    assert {"classroom_share", "debt", "security", "federal_cliff"} <= keys
    assert sc["balanced_panel_check"]["districts"] > 1000


def test_compare_districts_lines_them_up(client):
    r = call(client, "compare_districts",
             {"district_numbers": [DALLAS, "101912", "043914"]}).json()["result"]
    assert r["isError"] is False
    rows = r["structuredContent"]["districts"]
    assert len(rows) == 3
    assert all(row["district_number"] and row["district_name"] for row in rows)


def test_compare_rejects_a_single_district(client):
    r = call(client, "compare_districts", {"district_numbers": [DALLAS]}).json()["result"]
    assert r["isError"] is True


def test_an_unknown_tool_is_a_protocol_error(client):
    res = rpc(client, "tools/call", {"name": "drop_tables", "arguments": {}})
    body = res.json()
    assert body["error"]["code"] == P.INVALID_PARAMS
    assert "Unknown tool" in body["error"]["message"]


# --- blast radius -----------------------------------------------------------

def test_no_tool_writes_or_reaches_the_llm(client):
    """Every tool is a read over a committed artefact. If one ever isn't, the
    outage and injection story for this endpoint changes completely."""
    for t in mcp_tools.TOOLS:
        assert t["annotations"]["readOnlyHint"] is True
        assert t["annotations"]["openWorldHint"] is False


def test_the_nlp_query_path_is_not_exposed(client):
    """/query runs a SQL agent. Exposing it would let any text in any chat
    reach it, and would spend tokens against a global ceiling."""
    names = {t["name"] for t in mcp_tools.list_tools()}
    for banned in ("query", "ask", "sql", "nlp", "search_sql"):
        assert banned not in names
    assert not any("sql" in json.dumps(t).lower() for t in mcp_tools.list_tools())


def test_no_tool_names_a_person(client):
    """The bond source has companion files carrying a vendor's CRM. Nothing
    about a named individual may ever be reachable here."""
    blob = json.dumps(mcp_tools.list_tools()).lower()
    for w in ("superintendent", "trustee", "board member", "commission"):
        assert w not in blob


def test_tools_work_with_no_database(client):
    """The whole point of reading committed artefacts: a paused Supabase free
    tier must not take this endpoint down."""
    import src.api as api
    saved, api.app.state.db_pool = getattr(api.app.state, "db_pool", None), None
    try:
        for tool, args in (("texas_overview", {}),
                           ("district_forensics", {"district_number": DALLAS}),
                           ("find_district", {"name": "katy"})):
            r = call(client, tool, args).json()["result"]
            assert r["isError"] is False, tool
    finally:
        api.app.state.db_pool = saved


def test_the_debt_tool_carries_the_peak_year_with_every_ratio(client):
    """A repayment ratio that travels into somebody else's chat without the year
    it was taken at becomes a current-year claim, and the current-year figure is
    an artifact (Leander ISD: 4.5x in 2014, 396x in 2030, same deal)."""
    import json as _json
    payload = _json.loads(
        (ROOT / "static" / "debt_data.json").read_text()) if (
        ROOT / "static" / "debt_data.json").exists() else None
    if not payload:
        pytest.skip("debt layer not built")
    num = next((k for k, v in payload["districts"].items()
                if (v.get("cab") or {}).get("peak")), None)
    if not num:
        pytest.skip("no district has a published peak")
    res = rpc(client, "tools/call", {"name": "district_debt",
                                     "arguments": {"district_number": num}}).json()["result"]
    text = res["content"][0]["text"]
    assert "per dollar borrowed" in text
    assert "peak" in text.lower(), "a ratio was sent without its peak year"
    assert res["structuredContent"]["limits"], "limits must travel with the result"


def test_the_debt_tool_says_when_a_ratio_is_unknowable(client):
    """Districts whose reported years have a gap get their deferred interest and
    an explicit statement that the ratio is not in the record — silence there
    would read as 'no capital appreciation bonds'."""
    import json as _json
    path = ROOT / "static" / "debt_data.json"
    if not path.exists():
        pytest.skip("debt layer not built")
    payload = _json.loads(path.read_text())
    num = next((k for k, v in payload["districts"].items()
                if v.get("cab") and not v["cab"].get("peak")), None)
    if not num:
        pytest.skip("every CAB district has a peak")
    text = rpc(client, "tools/call", {"name": "district_debt",
               "arguments": {"district_number": num}}).json()["result"]["content"][0]["text"]
    assert "not published" in text or "is not" in text
    assert "deferred" in text, "the debt itself is known and must still be stated"
