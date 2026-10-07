"""Resource discovery stays narrow and can never become a file reader."""

import json
import re
from pathlib import Path

from src import mcp_apps
from src import mcp_protocol as P
from scripts.check_static_js import check_page, inline_scripts


def _rpc(method, params):
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {**params, "_meta": {P.META_VERSION: P.PROTOCOL_VERSION, P.META_CLIENT_CAPS: {}}},
        }
    ).encode()


def _headers(method, name=None):
    out = {"mcp-method": method, "mcp-protocol-version": P.PROTOCOL_VERSION}
    if name is not None:
        out["mcp-name"] = name
    return out


def _handle(method, params, name=None):
    return P.handle(
        _rpc(method, params),
        _headers(method, name),
        lambda *_: {},
        lambda: [],
        list_resources=mcp_apps.list_resources,
        read_resource=mcp_apps.read_resource,
    )


def test_the_single_versioned_resource_is_advertised_with_empty_network_csp():
    status, body = _handle("resources/list", {})
    assert status == 200
    resources = body["result"]["resources"]
    assert [x["uri"] for x in resources] == [mcp_apps.RESOURCE_URI]
    assert resources[0]["mimeType"] == mcp_apps.RESOURCE_MIME_TYPE
    assert resources[0]["_meta"]["ui"]["csp"] == {"connectDomains": [], "resourceDomains": [], "frameDomains": []}


def test_resource_read_composes_the_committed_shared_assets_without_network_urls():
    status, body = _handle("resources/read", {"uri": mcp_apps.RESOURCE_URI}, mcp_apps.RESOURCE_URI)
    assert status == 200
    page = body["result"]["contents"][0]["text"]
    assert body["result"]["ttlMs"] == P.DAY_MS
    assert body["result"]["cacheScope"] == "public"
    assert "TXISD_VISUAL_COMPONENTS" not in page and "TXISD_DESIGN_CSS" not in page
    assert "window.TxisdVisual" in page
    assert "ui/initialize" in page and "ui/notifications/tool-result" in page
    assert "fetch(" not in page and "track.js" not in page and "ask.js" not in page


def test_composed_resource_has_embedded_accessibility_and_no_network_assets(tmp_path: Path):
    status, body = _handle("resources/read", {"uri": mcp_apps.RESOURCE_URI}, mcp_apps.RESOURCE_URI)
    assert status == 200
    page = body["result"]["contents"][0]["text"]
    output = tmp_path / "mcp-app.html"
    output.write_text(page, encoding="utf-8")
    assert inline_scripts(output), "the delivered embedded page must contain parseable scripts"
    assert check_page(output) is None
    assert '<html lang="en"' in page
    assert "<main" in page and 'id="status"' in page and "aria-live=\"polite\"" in page
    assert "prefers-reduced-motion" in page and ":focus-visible" in page
    assert "window.TxisdVisual" in page
    assert "TXISD_" not in page
    assert not re.search(r"<(?:script|link)\\b[^>]+(?:src|href)=", page, flags=re.I)
    assert "@import" not in page and not any(host in page for host in ("cdn.", "unpkg.", "jsdelivr"))


def test_resource_rejects_unknown_and_path_like_uris():
    for uri in ("ui://txisd/report/v2.html", "file:///etc/passwd", "ui://txisd/../report/v1.html"):
        status, body = _handle("resources/read", {"uri": uri}, uri)
        assert status == 400
        assert body["error"]["code"] == P.INVALID_PARAMS
