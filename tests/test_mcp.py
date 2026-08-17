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
    "district_money", "district_forensics", "district_trends", "district_bonds",
    "district_national"])
def test_each_district_tool_answers_and_carries_its_limits(client, tool):
    r = call(client, tool, {"district_number": DALLAS}).json()["result"]
    assert r["isError"] is False, r["content"][0]["text"]
    assert r["structuredContent"]["limits"], f"{tool} returned no limits"
    assert "Dallas" in r["content"][0]["text"]


def test_national_gives_a_charter_the_cannot_exist_reason(client):
    """A charter has no Census row anywhere in the country — the Census
    surveys governments. The tool must serve src/absences.py's wording (one
    wording, two surfaces), never 'missing information', including for
    CLOSED charters that live only in the crosswalk."""
    r = call(client, "district_national", {"district_number": "014802"}).json()["result"]
    assert r["isError"] is True
    text = r["content"][0]["text"]
    assert "cannot exist" in text
    assert "charter" in text.lower()
    assert "missing information" not in text


def test_national_explains_a_row_with_no_figure_instead_of_crashing(client):
    """Twenty artifact rows resolve to a TEA number but carry only the NCES
    id — the Census reports no positive spending for them. The first cut
    crashed with a bare KeyError here (review-caught); it must be an
    explained absence."""
    r = call(client, "district_national", {"district_number": "015950"}).json()["result"]
    assert r["isError"] is True
    text = r["content"][0]["text"]
    assert "KeyError" not in text
    assert "no usable per-pupil spending figure" in text


def test_national_quotes_the_state_rank_from_the_artifact(client):
    """The MCP instructions once claimed '4,588 bond elections' long after the
    refresh. Every figure this tool speaks must come from the payload."""
    import json as _json
    from pathlib import Path
    art = _json.loads((Path(__file__).resolve().parent.parent
                       / "static" / "national_data.json").read_text())
    r = call(client, "district_national", {"district_number": DALLAS}).json()["result"]
    tx = art["states"]["texas"]
    assert f"ranks {tx['rank']} of {tx['of']}" in r["content"][0]["text"]
    assert r["structuredContent"]["states"]["texas"]["rank"] == tx["rank"]


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


# --- MRTR: the protocol refuses to guess between two same-named districts ---
#
# SEP-2322 replaced server-initiated elicitation with multi round-trip requests.
# It is used here for exactly one thing, and it is the failure this whole
# project has been burned by most: thirteen Texas district names belong to two
# districts each. Guessing between them is how bond history was attributed to
# the wrong district and how one district's debt was nearly counted twice.
#
# Before this, an ambiguous name came back as prose telling the model to go and
# disambiguate. That relies on the model reading and obeying the prose. MRTR
# makes it structural: the call does not complete until someone chooses.

def test_an_ambiguous_district_name_asks_instead_of_guessing(client):
    r = rpc(client, "tools/call", {"name": "district_debt",
            "arguments": {"district_number": "Wylie ISD"}}).json()["result"]
    assert r["resultType"] == "input_required"
    req = r["inputRequests"]["district_number"]
    assert req["method"] == "elicitation/create"
    assert req["params"]["mode"] == "form"
    enum = req["params"]["requestedSchema"]["properties"]["district_number"]["enum"]
    assert len(enum) == 2 and all(len(e) == 6 and e.isdigit() for e in enum)
    # Enrolment has to be in the prompt: without it the two options are the
    # same string and nobody can choose between them.
    assert "students" in req["params"]["message"]


def test_an_input_required_result_is_not_labelled_complete(client):
    """Relabelling it would tell the client the call finished when it did not."""
    r = rpc(client, "tools/call", {"name": "district_debt",
            "arguments": {"district_number": "Wylie ISD"}}).json()["result"]
    assert r["resultType"] != "complete"
    assert "content" not in r, "an unfinished call must not carry an answer"


def test_the_retry_carries_the_answer_and_completes(client):
    """The spec has the client re-send the arguments plus inputResponses under
    a different JSON-RPC id."""
    first = rpc(client, "tools/call", {"name": "district_debt",
                "arguments": {"district_number": "Wylie ISD"}}, rid=101).json()["result"]
    pick = first["inputRequests"]["district_number"]["params"][
        "requestedSchema"]["properties"]["district_number"]["enum"][0]
    second = rpc(client, "tools/call", {
        "name": "district_debt",
        "arguments": {"district_number": "Wylie ISD"},
        "inputResponses": {"district_number": {"action": "accept",
                                               "content": {"district_number": pick}}},
    }, rid=102).json()["result"]
    assert second["resultType"] == "complete"
    assert second["isError"] is False
    assert pick in second["content"][0]["text"]


def test_declining_the_choice_does_not_pick_one_anyway(client):
    r = rpc(client, "tools/call", {
        "name": "district_debt",
        "arguments": {"district_number": "Wylie ISD"},
        "inputResponses": {"district_number": {"action": "decline"}},
    }).json()["result"]
    assert r["isError"] is True
    assert "nothing was looked up" in r["content"][0]["text"].lower()


def test_a_name_unique_statewide_needs_no_round_trip(client):
    """Asking when there is only one possible answer is friction, not safety."""
    r = rpc(client, "tools/call", {"name": "district_debt",
            "arguments": {"district_number": "Leander ISD"}}).json()["result"]
    assert r["resultType"] == "complete"
    assert "246913" in r["content"][0]["text"]


def test_a_name_matching_nothing_is_still_a_plain_error(client):
    """Not every failure is an ambiguity. A typo is something the model can fix
    itself, so it stays isError rather than becoming a question."""
    r = rpc(client, "tools/call", {"name": "district_debt",
            "arguments": {"district_number": "Nowhere ISD"}}).json()["result"]
    assert r["resultType"] == "complete" and r["isError"] is True
    assert "find_district" in r["content"][0]["text"]


def test_malformed_input_responses_are_rejected(client):
    r = rpc(client, "tools/call", {"name": "district_debt",
            "arguments": {"district_number": "057905"},
            "inputResponses": "not-an-object"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == P.INVALID_PARAMS


# --- the connect-time instructions must not go stale --------------------------

def test_the_instructions_quote_the_data_not_a_hardcoded_number(client):
    """These go into the context of every assistant that connects, so a stale
    figure here is our stale figure repeated in somebody else's model. This
    said '4,588 bond elections' for as long as the bond layer was stale — and
    kept saying it after the refresh, because nothing checked it."""
    import json as _json
    d = rpc(client, "server/discover").json()["result"]
    text = d["instructions"]
    path = ROOT / "static" / "bond_data.json"
    if path.exists():
        meta = _json.loads(path.read_text())["meta"]
        assert f"{meta['propositions']:,}" in text
        assert str(meta["last_year"]) in text
    assert "Bond Review Board" in text, "the publisher must be named correctly"


# --- the HTTP header must agree with the payload's own freshness signal -------
# SEP-2549 lets a result declare `ttlMs`/`cacheScope` so a client can cache
# without a long-lived SSE stream. This endpoint answered every method with a
# flat `no-store`, which told a client to discard exactly what the protocol had
# just asked it to keep for a day. Two mechanisms pointing opposite ways.

def test_cache_directive_is_derived_from_the_body():
    from src.mcp_protocol import DAY_MS, cache_directive
    assert cache_directive(
        {"result": {"tools": [], "ttlMs": DAY_MS, "cacheScope": "public"}}
    ) == f"private, max-age={DAY_MS // 1000}"


def test_a_result_with_no_ttl_is_not_cacheable():
    """tools/call takes arguments and MRTR round-trips requestState."""
    from src.mcp_protocol import cache_directive
    assert cache_directive({"result": {"content": []}}) == "no-store"


def test_errors_are_never_cacheable():
    from src.mcp_protocol import cache_directive
    assert cache_directive({"error": {"code": -32602}}) == "no-store"
    assert cache_directive(None) == "no-store"


def test_private_scope_is_honoured():
    from src.mcp_protocol import cache_directive
    assert cache_directive(
        {"result": {"ttlMs": 60000, "cacheScope": "private"}}) == "private, max-age=60"


def test_the_header_and_the_payload_cannot_disagree_end_to_end(client):
    """The regression itself: ask the live app for tools/list and assert the
    Cache-Control it returns matches the ttlMs inside the very same body."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {}}}}
    r = client.post("/mcp", json=body, headers={
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/list", "Mcp-Name": "tools/list"})
    assert r.status_code == 200, r.text
    ttl = r.json()["result"]["ttlMs"]
    assert r.headers["cache-control"] == f"private, max-age={ttl // 1000}", (
        "the HTTP header drifted from the ttlMs in the body it was sent with")
    assert "no-store" not in r.headers["cache-control"]


def test_tools_call_still_says_no_store(client):
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "texas_overview", "arguments": {},
                       "_meta": {
                           "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                           "io.modelcontextprotocol/clientCapabilities": {}}}}
    r = client.post("/mcp", json=body, headers={
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/call", "Mcp-Name": "texas_overview"})
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"


def test_mcp_does_not_claim_a_cdn_directive_it_cannot_use():
    """/mcp is POST and Vercel's CDN caches only GET/HEAD, so an s-maxage here
    would be inert. An optimisation that cannot fire is worse than none,
    because it reads as done."""
    import ast
    import inspect

    from src import mcp_protocol

    # Parse the function and look at the CODE only. Prose legitimately mentions
    # s-maxage to explain why there isn't one; a string literal that gets
    # returned is a different matter. Checking the text after the last `return`
    # was the original bug — an s-maxage on any earlier branch sailed through.
    tree = ast.parse(inspect.getsource(mcp_protocol.cache_directive).lstrip())
    fn = tree.body[0]
    # The docstring is the first statement; exclude that NODE, not a string
    # equal to it — ast.get_docstring re-indents, so comparing text silently
    # matches nothing and the whole guard passes for the wrong reason.
    doc_node = (fn.body[0].value
                if isinstance(fn.body[0], ast.Expr)
                and isinstance(fn.body[0].value, ast.Constant) else None)
    emitted = [n.value for n in ast.walk(fn)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and n is not doc_node]
    assert not any("s-maxage" in t for t in emitted), \
        "/mcp is POST; Vercel caches only GET/HEAD, so an s-maxage here is inert"
