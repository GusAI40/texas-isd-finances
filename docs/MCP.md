# The MCP server

`https://txisd.dev/mcp` speaks **Model Context Protocol 2026-07-28**. It gives an
assistant eleven read-only tools over Texas school district finance, built from the
state's own records.

## Why it exists

The way people now ask "where does my school tax go" is increasingly by asking an
assistant, and those answers are ungrounded. This project's whole discipline is that
every number carries its source and its limit. An MCP server carries that discipline
*into* the assistant: **every tool result includes a `limits` array**, and the headline
caveat is stated in the text a model reads most closely — so "suggestive, not settled"
travels with the bond finding instead of being left behind on a page nobody scrolled.

## Connecting

No authentication, no account, no rate limit beyond the platform's. Every byte served
here is already public on txisd.dev.

The server is discoverable at `https://txisd.dev/.well-known/mcp.json`, which
returns the endpoint URL and transport for hosts and registries that crawl the
well-known path.

```jsonc
// Claude Desktop / any MCP host that takes an HTTP server URL
{
  "mcpServers": {
    "txisd": { "type": "http", "url": "https://txisd.dev/mcp" }
  }
}
```

Raw, for anything that speaks the wire format directly:

```bash
curl -sS https://txisd.dev/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: tools/list' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{
        "io.modelcontextprotocol/protocolVersion":"2026-07-28",
        "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

## The tools

| Tool | Answers |
|---|---|
| `find_district` | A name → the six-digit TEA district number. **Call this first.** |
| `district_money` | Per-student spending split operating/debt, revenue mix, tax on a $300k home |
| `district_lineage` | **Why is this number this number** — numerator, denominator, which student count the denominator IS, and the publication gate's verdict |
| `district_forensics` | The four questions Texas reports in four incompatible files |
| `district_trends` | Fiscal 2009–2025 in constant dollars, against the statewide line |
| `district_bonds` | Every bond proposition 1958–2026, with stated purpose and result |
| `district_campuses` | Every rated campus in a district, worst first, against the district's own A–F rating |
| `district_debt` | What is still owed — principal, unpaid interest, the year it clears, and any capital appreciation bonds |
| `district_national` | The district against every U.S. district (Census F-33 current spending + percentile), and Texas's rank among the 50 states and DC |
| `texas_overview` | Statewide totals and the six measured seventeen-year trends |
| `compare_districts` | Two to six districts side by side |

**`find_district` is not optional politeness.** Texas has thirteen pairs of districts
that share a name — two Wylie ISDs, two Highland Park ISDs, two Northside ISDs. A name
is not an identifier, and the results include enrolment so the right one can be picked.

## What it implements, exactly

Hand-written against the specification rather than an SDK. Vercel builds this function
from the `[project]` table under a 500 MB bundle cap, and a dependency that fails to
resolve fails *every* deploy, not just this feature. The surface actually needed — three
methods, no sampling, no elicitation, no subscriptions, no resources — is small enough
that the standard library is the smaller risk. `src/mcp_protocol.py` is the wire format;
`src/mcp_tools.py` is the content.

- `server/discover`, `tools/list`, `tools/call` on a single `POST /mcp`.
- Required `_meta`: `io.modelcontextprotocol/protocolVersion` and
  `…/clientCapabilities`. Missing → `-32602`, HTTP 400.
- Mirrored headers `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`, each **validated
  against the body**, including the `=?base64?…?=` sentinel. Mismatch → `-32020`,
  HTTP 400. This matters: a gateway routing on the header while the server executes on
  the body is a real hole, which is why the spec gave it its own error code.
- `x-mcp-header: District` mirrors `district_number` into `Mcp-Param-District`, so an
  intermediary can route or rate-limit per district without parsing the body.
- Unknown method → `-32601`, **HTTP 404** (lets a client tell a modern server from a
  legacy one with no MCP endpoint). Unknown tool → `-32602`. Unsupported version →
  `-32022` with the supported list.
- Notification → `202 Accepted`, empty body. `GET`/`DELETE` → `405` (the GET stream and
  DELETE teardown were removed in this revision). A legacy `initialize` gets an error
  naming the versions this server speaks, because legacy clients cannot fall forward.
- `Origin` validated when present (DNS-rebinding guard); configurable via
  `MCP_ALLOWED_ORIGINS`.
- `ttlMs: 86400000, cacheScope: "public"` on discovery and the tool list. The underlying
  data changes **once a year**, at a TEA release, so this is close to free.

## What it deliberately does not implement

- **Sampling and elicitation** — both deprecated in this revision, and every answer here
  is a lookup; there is nothing to ask a model for.
- **MRTR / `InputRequiredResult`** — follows from the above.
- **Resources, prompts, subscriptions, tasks** — no state, nothing long-running.
- **Authentication** — everything served is already public.
- **`/query`, the natural-language SQL endpoint.** This is the important one. It is the
  single path with a prompt-injection history (closed 2026-07-31 by running as
  `nlp_reader`), it spends DeepSeek tokens against a global ceiling, and exposing it
  would let arbitrary text in any chat reach a SQL agent. Every tool above is a
  deterministic read of a committed JSON artefact: nothing to inject, nothing to spend,
  and no dependency on the database — so a paused Supabase free tier cannot take it
  down. A test asserts all of that.

## Why 2026-07-28 is what made this possible

Earlier revisions established a connection-scoped session with an `initialize` handshake
and an `Mcp-Session-Id` header. This app is Vercel serverless behind a round-robin with
no sticky routing and no shared session store — the reason `/query`'s call ceiling had to
be counted in the database rather than in a process. An MCP server here would have needed
affinity the architecture does not have.

2026-07-28 removed the handshake (SEP-2575) and the session (SEP-2567) and moved protocol
version, client identity and capabilities into `_meta` on every request. Any request may
land on any instance. That turns an MCP server here into what everything else already is:
a stateless POST handler over committed JSON.

## Maintaining it

`tests/test_mcp.py` covers the wire format, the header contract, every tool, and the
blast radius (read-only, no database, `/query` not exposed, no named individuals). Run
the suite before changing anything here:

```bash
ruff check . && python -m pytest tests/test_mcp.py -q
```

If a tool's data source changes shape, the tool's test fails on the missing `limits`
before it fails on anything else — which is the intended order, because a number without
its caveat is worse than no number.


## Multi round-trip requests (SEP-2322)

Texas has thirteen district names that belong to two districts each — two Wylie
ISDs, two Highland Park ISDs, two Northside ISDs. Guessing between them is not a
theoretical risk here: it is how bond history was once attributed to the wrong
district, and how one district's debt was nearly added to the statewide total
twice.

Any tool taking a `district_number` also accepts a name. When the name is unique
statewide it is resolved silently. When it is not, the call does **not**
complete — it returns an MRTR `input_required` result listing the real
candidates with their enrolment, so whoever is choosing can tell them apart:

```jsonc
// -> tools/call  { "name": "district_debt",
//                  "arguments": { "district_number": "Wylie ISD" } }
{
  "resultType": "input_required",
  "inputRequests": {
    "district_number": {
      "method": "elicitation/create",
      "params": {
        "mode": "form",
        "message": "'Wylie ISD' matches 2 Texas districts...",
        "requestedSchema": {
          "type": "object",
          "properties": { "district_number": { "type": "string",
                          "enum": ["043914", "221912"] } },
          "required": ["district_number"]
        }
      }
    }
  }
}

// -> tools/call, NEW json-rpc id, same arguments plus the answer
//    { ..., "inputResponses": { "district_number":
//        { "action": "accept", "content": { "district_number": "043914" } } } }
```

There is deliberately **no `requestState`**. The spec has the client echo it
only if the server provides one, and since the original arguments are re-sent
there is nothing to remember — which keeps this genuinely stateless and leaves
no opaque token anyone has to validate.

Declining returns `isError` and looks nothing up. A name matching no district
stays an ordinary `isError` too: a typo is something a model can fix by itself,
and only a genuine ambiguity — where both answers are real — becomes a question.
