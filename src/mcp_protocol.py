"""Model Context Protocol 2026-07-28, the wire format only.

Why this exists at all
----------------------
The way people now ask "where does my school tax go" is increasingly by asking
an assistant, and those answers are ungrounded. This project's whole discipline
is that every number carries its source and its limit. An MCP server carries
that discipline INTO the assistant: the caveats travel attached to the figures
instead of being left behind on a page nobody scrolled.

Why it can exist cheaply
------------------------
2026-07-28 made the protocol stateless. The `initialize`/`initialized`
handshake is gone (SEP-2575) and `Mcp-Session-Id` is gone (SEP-2567); protocol
version, client identity and capabilities ride in `_meta` on every request, and
capabilities come from `server/discover`. Any request may land on any instance.

That is exactly the shape this app already is: Vercel serverless behind a
round-robin with no sticky routing and no shared session store — the reason
`/query`'s call ceiling had to be counted in the database rather than in a
process. Under the previous revision an MCP server here would have needed
session affinity this architecture does not have. Under this one it is just
another stateless POST handler over committed JSON.

Why it is hand-written rather than an SDK
-----------------------------------------
Vercel builds this function from the `[project]` table with a 500 MB bundle
cap, and a missing or unbuildable dependency fails every deploy, not just this
feature. The protocol surface actually needed here — three methods, no
sampling, no elicitation, no subscriptions, no resources — is small enough that
the standard library is a smaller risk than a new dependency. This module is
the wire format; `mcp_tools.py` is the content.

What is implemented, exactly
----------------------------
- `server/discover`, `tools/list`, `tools/call` over a single POST endpoint.
- Required `_meta`: `io.modelcontextprotocol/protocolVersion` and
  `io.modelcontextprotocol/clientCapabilities`; missing -> -32602 / HTTP 400.
- Header mirroring: `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`, validated
  against the body, including the `=?base64?...?=` sentinel. A mismatch is
  -32020 / HTTP 400, because a load balancer routing on the header while the
  server executes on the body is a real security hole.
- Unknown method -> -32601 / HTTP 404 (the spec asks for 404 so a client can
  tell a modern server from a legacy one that has no MCP endpoint).
- Unknown protocol version -> -32022 with the supported list.
- Notifications -> 202 Accepted with no body.
- `Origin` validated when present, to block DNS rebinding.

What is deliberately NOT implemented
------------------------------------
- **Sampling and elicitation.** Both are deprecated in this revision anyway,
  and this server has nothing to ask a model for: every answer is a lookup.
- **MRTR / `InputRequiredResult`.** Follows from the above — no tool here ever
  needs more input than its arguments.
- **Resources, prompts, subscriptions, tasks.** No state, nothing long-running.
- **Legacy `initialize`.** A legacy client gets an error naming the versions
  this server speaks, which the spec asks for because legacy clients have no
  way to fall forward.
- **Authentication.** Every byte served here is already public on txisd.dev.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any, Callable

PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = [PROTOCOL_VERSION]

SERVER_INFO = {"name": "txisd", "version": "1.0.0"}

# JSON-RPC standard codes, plus the sub-range -32020..-32099 the MCP spec
# reserves for itself. Nothing outside these may be emitted from that range.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020
MISSING_CAPABILITY = -32021          # not raised here; this server requires none
UNSUPPORTED_VERSION = -32022

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPS = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

# The methods whose Mcp-Name header mirrors a body field, and which field.
NAME_SOURCE = {"tools/call": "name", "resources/read": "uri", "prompts/get": "uri"}

_B64 = re.compile(r"^=\?base64\?(.*)\?=$")

# This data changes once a year, when TEA publishes. Telling clients that is
# most of the caching win available here.
DAY_MS = 86_400_000


def decode_header(value: str) -> str:
    """Undo the `=?base64?...?=` sentinel a client uses when a value cannot be
    expressed as plain ASCII. Servers MUST decode before comparing to the body,
    or every district name with an accent looks like a mismatch."""
    m = _B64.match(value or "")
    if not m:
        return value
    try:
        return base64.b64decode(m.group(1)).decode("utf-8")
    except Exception:
        return value


def error(rid: Any, code: int, message: str, data: Any = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    body: dict[str, Any] = {"jsonrpc": "2.0", "error": err}
    if rid is not None:
        body["id"] = rid
    return body


def result(rid: Any, payload: dict) -> dict:
    """Every result carries `resultType` — required in this revision — and
    identifies the server, which is how a stateless client knows who answered
    without a handshake to remember.

    `complete` unless the payload already declares otherwise: a tool that needs
    the caller to choose between real alternatives returns `input_required`
    (MRTR, SEP-2322) and must not be relabelled as finished.
    """
    body = {"resultType": "complete", **payload}
    body.setdefault("_meta", {})[META_SERVER_INFO] = SERVER_INFO
    return {"jsonrpc": "2.0", "id": rid, "result": body}


def _origin_ok(origin: str | None, allowed: tuple[str, ...]) -> bool:
    """DNS-rebinding guard. Absent Origin is fine — that is a direct API client,
    not a browser being used as a confused deputy."""
    if not origin:
        return True
    return any(origin == a or origin.endswith(a) for a in allowed)


def cache_directive(body: dict | None) -> str:
    """The HTTP Cache-Control for a response, DERIVED FROM THAT RESPONSE.

    SEP-2549 lets a result carry its own freshness signal (`ttlMs`,
    `cacheScope`) so a client can cache without a long-lived SSE stream. This
    endpoint used to answer every method with a flat `no-store`, which told a
    well-behaved HTTP client to discard exactly what the protocol had just
    asked it to keep for a day. Two mechanisms pointing opposite ways, and
    which one won depended on the client.

    So the header is computed from the body rather than written beside it. A
    result that declares no ttlMs gets `no-store`; one that declares a public
    ttlMs gets the matching max-age. They cannot drift because there is only
    one number.

    Note this is a CLIENT directive, not a CDN one. /mcp is POST, and Vercel's
    CDN only caches GET and HEAD, so `s-maxage` here would be inert — a real
    optimisation that cannot fire is worse than none, because it reads as done.
    """
    if not isinstance(body, dict):
        return "no-store"
    res = body.get("result")
    if not isinstance(res, dict):
        return "no-store"                     # errors are never cacheable
    ttl_ms = res.get("ttlMs")
    if not isinstance(ttl_ms, int) or ttl_ms <= 0:
        return "no-store"                     # tools/call: arguments + MRTR state
    scope = res.get("cacheScope") or "private"
    seconds = ttl_ms // 1000
    return f"{'public' if scope == 'public' else 'private'}, max-age={seconds}"


def handle(
    raw: bytes,
    headers: dict[str, str],
    call_tool: Callable[..., dict],
    list_tools: Callable[[], list[dict]],
    instructions: str = "",
    allowed_origins: tuple[str, ...] = (),
) -> tuple[int, dict | None]:
    """Process one POST. Returns (http_status, json body or None for 202).

    Header names arrive lower-cased by the caller.
    """
    origin = headers.get("origin")
    if allowed_origins and not _origin_ok(origin, allowed_origins):
        return 403, error(None, INVALID_REQUEST, "Origin not allowed")

    try:
        msg = json.loads(raw or b"")
    except Exception:
        return 400, error(None, PARSE_ERROR, "Parse error: body is not valid JSON")
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return 400, error(None, INVALID_REQUEST, "Not a JSON-RPC 2.0 message")

    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        return 400, error(rid, INVALID_PARAMS, "params must be an object")

    # A notification has no id. Nothing here acts on one, but the transport
    # contract is that it is accepted with an empty 202 rather than answered.
    if rid is None:
        return 202, None
    if not isinstance(method, str):
        return 400, error(rid, INVALID_REQUEST, "method must be a string")

    # A legacy client opens with `initialize` and has no way to fall forward,
    # so this error is the only diagnostic its user will ever see. Answer it
    # before the generic _meta check, which would otherwise reply with an
    # unhelpful "missing field" that names nothing.
    if method == "initialize":
        return 400, {**legacy_initialize_error(), "id": rid}

    meta = params.get("_meta") or {}
    if not isinstance(meta, dict):
        return 400, error(rid, INVALID_PARAMS, "_meta must be an object")

    # --- header mirroring, validated against the body -----------------------
    hdr_method = headers.get("mcp-method")
    if hdr_method is None:
        return 400, error(rid, HEADER_MISMATCH, "Missing required header Mcp-Method")
    if hdr_method != method:
        return 400, error(rid, HEADER_MISMATCH,
                          f"Header mismatch: Mcp-Method header value "
                          f"{hdr_method!r} does not match body value {method!r}")

    name_field = NAME_SOURCE.get(method)
    if name_field:
        want = params.get(name_field)
        got = headers.get("mcp-name")
        if got is None:
            return 400, error(rid, HEADER_MISMATCH,
                              f"Missing required header Mcp-Name for {method}")
        if decode_header(got) != want:
            return 400, error(rid, HEADER_MISMATCH,
                              f"Header mismatch: Mcp-Name header value "
                              f"{decode_header(got)!r} does not match body value {want!r}")

    # --- protocol version, in the body and mirrored in the header -----------
    version = meta.get(META_VERSION)
    if not version:
        return 400, error(rid, INVALID_PARAMS,
                          f"Missing required _meta field {META_VERSION}")
    hdr_version = headers.get("mcp-protocol-version")
    if hdr_version is None:
        return 400, error(rid, HEADER_MISMATCH,
                          "Missing required header MCP-Protocol-Version")
    if hdr_version != version:
        return 400, error(rid, HEADER_MISMATCH,
                          f"Header mismatch: MCP-Protocol-Version header value "
                          f"{hdr_version!r} does not match body value {version!r}")
    if version not in SUPPORTED_VERSIONS:
        return 400, error(rid, UNSUPPORTED_VERSION, "Unsupported protocol version",
                          {"supported": SUPPORTED_VERSIONS, "requested": version})

    if META_CLIENT_CAPS not in meta:
        return 400, error(rid, INVALID_PARAMS,
                          f"Missing required _meta field {META_CLIENT_CAPS}")

    # --- dispatch -----------------------------------------------------------
    if method == "server/discover":
        return 200, result(rid, {
            "supportedVersions": SUPPORTED_VERSIONS,
            "capabilities": {"tools": {}},
            "instructions": instructions,
            "ttlMs": DAY_MS,
            "cacheScope": "public",
        })

    if method == "tools/list":
        return 200, result(rid, {
            "tools": list_tools(),
            # The underlying data moves once a year, at a TEA release. A day is
            # a conservative fraction of that and costs a client nothing.
            "ttlMs": DAY_MS,
            "cacheScope": "public",
        })

    if method == "tools/call":
        tool = params.get("name")
        if not isinstance(tool, str):
            return 400, error(rid, INVALID_PARAMS, "params.name must be a string")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return 400, error(rid, INVALID_PARAMS, "params.arguments must be an object")
        # MRTR (SEP-2322): a retry re-sends the original arguments plus the
        # answers. There is deliberately no `requestState` — the spec has the
        # client echo it only "if provided by the server", and since the
        # arguments come back too there is nothing for this server to remember.
        # Not minting one keeps it genuinely stateless and leaves no opaque
        # token that would have to be validated.
        replies = params.get("inputResponses")
        if replies is not None and not isinstance(replies, dict):
            return 400, error(rid, INVALID_PARAMS,
                              "params.inputResponses must be an object")
        try:
            payload = call_tool(tool, args, replies)
        except KeyError:
            # Unknown tool is a protocol error, not something a model can fix
            # by retrying with different arguments.
            return 200, error(rid, INVALID_PARAMS, f"Unknown tool: {tool}")
        return 200, result(rid, payload)

    # 404 rather than 200, so a client can tell a modern server that lacks the
    # method from a legacy server that has no MCP endpoint at all.
    return 404, error(rid, METHOD_NOT_FOUND, f"Method not found: {method}")


def legacy_initialize_error() -> dict:
    """A legacy client has no way to fall forward, so the one error it can see
    should name what this server actually speaks."""
    return error(None, METHOD_NOT_FOUND,
                 "This server implements only stateless MCP "
                 f"({', '.join(SUPPORTED_VERSIONS)}); the initialize handshake was "
                 "removed in 2026-07-28. Send requests with per-request _meta instead.")
