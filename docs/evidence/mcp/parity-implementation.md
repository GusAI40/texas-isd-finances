# D-PARITY-01 local implementation evidence

`tests/test_mcp_parity.py` reads the committed source artifacts directly before
calling the MCP endpoint. It anchors their SHA-256 hashes and fiscal vintages in
`tests/fixtures/mcp_cases.json`, then compares independent Dallas source fields
for each of the eleven tools. The comparison spans economics, forensic, trend,
bond, debt, campus, and national artifacts and includes Houston in the comparison
tool. The fixture retains Tioga and Pineywoods identifiers to protect leading
zero/string handling, and the charter national case verifies the explicit
not-applicable reason.

The suite also verifies malformed IDs/types, leading-zero repair, a Unicode name
failure path, comparison bounds 1/2/6/7, ambiguous Wylie MRTR, declined choice,
and accepted retry. Existing `tests/test_mcp.py` covers header charset decoding,
unknown tools, unavailable national rows, null students, cache/origin/version,
and no-DB operation. These are local artifact and protocol results; a new host
probe remains required after deployment.
