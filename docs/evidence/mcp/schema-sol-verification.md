# D-SCHEMA-01 independent verification

**Verifier:** fresh Luna pass, 2026-10-07 21:00 UTC
**Code under test:** working tree at `37ec5d23c7e8380531db7507bb15c3950ea1d9f1` (schema changes are present in the working tree)

## Result

**PASS for the local implementation.** Successful structured results validate against the announced schemas with strict AJV 8.20.0, including recursive nested constraints. Error and MRTR envelopes remain outside the success schema. The actual deployed host is tracked separately below and is not credited for the new schemas.

| Acceptance condition | Result | Evidence |
|---|---|---|
| All eleven announced tool schemas compile and current direct successes validate | PASS | `tests/test_mcp_schemas.py::test_strict_ajv_compiles_all_schemas_and_validates_all_current_tool_calls`; direct calls for all 11 tools; AJV subprocess reports strict recursive validation. |
| Saved owner-host successes remain valid historical evidence | PASS | `::test_saved_owner_host_successes_still_validate_as_historical_evidence`; all 11 names from `docs/evidence/mcp-host/connector-results.json` validate. |
| Nullable, absent, invalid nested, and MRTR/error cases are covered | PASS | `::test_live_edge_payloads_preserve_nullable_and_absence_distinctions`, `::test_recursive_validator_rejects_wrong_nested_types_and_missing_required_fields`, and `::test_error_and_mrtr_envelopes_remain_separate_from_success_schemas`. |
| No duplicate `limits` requirement / registry remains exact | PASS | `::test_tool_registry_is_exact_and_every_success_schema_requires_limits`; exact 11 names and one required `limits` entry per schema. |
| Focused regression suite | PASS | `python -m pytest tests/test_mcp.py tests/test_mcp_parity.py tests/test_mcp_schemas.py tests/test_plugin_package.py -q` → **69 passed**, 1 unrelated Starlette deprecation warning. |

The validator is genuinely recursive: `tests/plugin/validate-tool-outputs.mjs` imports `ajv/dist/2020.js`, pins strict mode (`strict: true`, `allErrors: true`), compiles each schema, and the negative fixtures mutate nested artifact, metric, campus, required, and null/string fields. It is not a top-level mirror check.

## Host/release boundary

The saved host evidence records endpoint revision `73df1896ed0818020ec1c15c06f5ee823db7ec0f`; it predates the local schema changes. Therefore this verification does **not** claim that `https://txisd.dev/mcp` currently serves these output schemas. A fresh Inspector run and new host output capture against the released revision remain required after deployment. The recorded Inspector warning is the prior legal JSON-Schema nullable spelling; its disposition says to use `anyOf` single-type branches and repeat Inspector against the implemented deployment.
