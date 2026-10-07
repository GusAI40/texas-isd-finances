# MCP compatibility record

On 2026-10-07, `@modelcontextprotocol/inspector` 2.9.0 in modern mode called all
eleven public tools at `https://txisd.dev/mcp` successfully. Its unknown-tool
command exited 5 due to the client's own guard, not a captured server response.
Legacy Inspector initialization received HTTP 400 / JSON-RPC `-32601`, as
expected for this stateless 2026-07-28 server. See
`docs/evidence/mcp-host/inspector-results.json` for the raw public evidence.

The same day, a registered no-auth ChatGPT custom MCP connection
(`plugin_asdk_app_6ac6a4e3abac81918eb91eb558cb5b9e`) reported eleven successful
tool responses in a fresh chat. Only aggregate activity and the final answer
were retained; individual host frames were not exported. This establishes the
endpoint connection, not visual-resource rendering, package installation,
independent-account access, or directory listing.

The server remains deliberately stateless. There is no evidence supporting a
legacy transport adapter or session store. The visual resource is a new
2026-07-28 capability and needs a fresh host probe after deployment.
