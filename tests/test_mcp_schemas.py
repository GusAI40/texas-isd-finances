"""All public tool success payloads satisfy strict recursive JSON Schemas."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path

from src import mcp_apps, mcp_tools

EXPECTED = {
    "find_district",
    "district_money",
    "district_lineage",
    "district_forensics",
    "district_trends",
    "district_bonds",
    "district_campuses",
    "district_debt",
    "district_national",
    "texas_overview",
    "compare_districts",
}

CURRENT_CALLS = {
    "find_district": {"name": "Dallas"},
    "district_money": {"district_number": "057905"},
    "district_lineage": {"district_number": "057905"},
    "district_forensics": {"district_number": "057905"},
    "district_trends": {"district_number": "057905"},
    "district_bonds": {"district_number": "057905"},
    "district_campuses": {"district_number": "057905"},
    "district_debt": {"district_number": "057905"},
    "district_national": {"district_number": "057905"},
    "texas_overview": {},
    "compare_districts": {"district_numbers": ["057905", "101912"]},
}

ROOT = Path(__file__).resolve().parent.parent
AJV_VALIDATOR = ROOT / "tests" / "plugin" / "validate-tool-outputs.mjs"


def _schemas():
    return {tool["name"]: tool["outputSchema"] for tool in mcp_tools.list_tools()}


def _result(tool, arguments):
    result = mcp_tools.call_tool(tool, arguments)
    assert result.get("isError") is False, (tool, result)
    assert "structuredContent" in result, tool
    return result["structuredContent"]


def _case(label, tool, payload, valid=True):
    return {"label": label, "schema": _schemas()[tool], "payload": payload, "valid": valid}


def _run_ajv(tmp_path, cases):
    bundle = tmp_path / "tool-output-cases.json"
    bundle.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(AJV_VALIDATOR), str(bundle)],
        cwd=ROOT / "tests" / "plugin",
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "strict AJV recursively validated" in completed.stdout


def test_tool_registry_is_exact_and_every_success_schema_requires_limits():
    tools = mcp_tools.list_tools()
    assert {tool["name"] for tool in tools} == EXPECTED
    for tool in tools:
        schema = tool["outputSchema"]
        assert schema["type"] == "object"
        assert schema["required"].count("limits") == 1
        if tool["name"] in mcp_apps.VISUAL_TOOL_NAMES:
            assert tool["_meta"]["ui"]["resourceUri"] == mcp_apps.RESOURCE_URI
            assert "visual" in schema["properties"]
        else:
            assert "_meta" not in tool


def test_visual_payloads_are_additive_and_carry_status_source_and_limits():
    district = mcp_apps.visual_payload(
        "district_money",
        {
            "district_number": "057905",
            "district_name": "Dallas ISD",
            "year": 2025,
            "allocation": {"total_per_student": 1},
            "limits": ["public"],
        },
    )
    comparison = mcp_apps.visual_payload(
        "compare_districts",
        {"districts": [{"district_number": "057905", "district_name": "Dallas ISD"}], "limits": ["public"]},
    )
    statewide = mcp_apps.visual_payload("texas_overview", {"statewide": {"debt_total": 1}, "limits": ["public"]})
    for value, view in ((district, "district"), (comparison, "comparison"), (statewide, "statewide")):
        assert value["schemaVersion"] == 1 and value["view"] == view
        assert value["limits"] == ["public"] and value["websiteUrl"].startswith("https://txisd.dev/")
    metric = district["metrics"][0]
    assert metric["status"] == "observed" and metric["source"]["url"].startswith("https://txisd.dev/")


def test_visual_metadata_normalizes_identity_period_and_missing_modeled_gap():
    assert mcp_apps._district_population("  Dallas ISD ", "057905") == "Dallas ISD"
    assert mcp_apps._district_population(" ", "057905") == "District 057905"
    assert mcp_apps._district_population(None, None) == "District not reported"
    missing_period = mcp_apps._metric("x", "x", 1, "unit", None, [])
    assert missing_period["period"] == missing_period["source"]["period"] == "Not reported"
    comparison = mcp_apps.visual_payload("compare_districts", {"districts": [{
        "district_number": "057905", "district_name": "", "year": None, "outcomes_year": 2024,
        "points_vs_predicted": None,
    }], "limits": []})
    values = {metric["id"]: metric for metric in comparison["metrics"][0]["values"]}
    assert all(metric["population"] == "District 057905" for metric in values.values())
    assert values["operating_per_student"]["period"] == "Not reported"
    assert values["operating_per_student"]["source"]["period"] == "Not reported"
    assert values["points_vs_predicted"]["status"] == "missing"
    assert values["points_vs_predicted"]["period"] == "2024"
    modeled = mcp_apps.visual_payload("compare_districts", {"districts": [{
        "district_number": "057905", "district_name": "Dallas ISD", "outcomes_year": None,
        "points_vs_predicted": 0,
    }], "limits": []})
    gap = modeled["metrics"][0]["values"][-1]
    assert gap["value"] == 0 and gap["status"] == "modeled"
    assert gap["period"] == gap["source"]["period"] == "Not reported"


def test_strict_ajv_compiles_all_schemas_and_validates_all_current_tool_calls(tmp_path):
    cases = []
    for tool, arguments in CURRENT_CALLS.items():
        cases.append(_case(f"current:{tool}", tool, _result(tool, arguments)))
    _run_ajv(tmp_path, cases)


def test_saved_owner_host_successes_still_validate_as_historical_evidence(tmp_path):
    evidence = json.loads((ROOT / "docs" / "evidence" / "mcp-host" / "connector-results.json").read_text())
    assert {call["tool"] for call in evidence["calls"]} == EXPECTED
    cases = [
        _case(f"saved-owner-host:{call['tool']}", call["tool"], call["result"]["structuredContent"])
        for call in evidence["calls"]
    ]
    _run_ajv(tmp_path, cases)


def test_live_edge_payloads_preserve_nullable_and_absence_distinctions(tmp_path):
    nullable_population = _result("find_district", {"name": "A W Brown Leadership"})
    assert nullable_population["matches"][0]["students"] is None

    pineywoods = _result("district_money", {"district_number": "003801"})
    assert pineywoods["tax"] is None

    unranked_small_district = _result("district_national", {"district_number": "058905"})
    assert "pctile" not in unranked_small_district
    explicit_null_rank = {**unranked_small_district, "pctile": None}

    tioga = _result("district_trends", {"district_number": "091907"})
    houston = _result("district_forensics", {"district_number": "101912"})

    charter = mcp_tools.call_tool("district_national", {"district_number": "014802"})
    assert charter["isError"] is True
    assert "structuredContent" not in charter
    assert "charter" in charter["content"][0]["text"].lower()

    cases = [
        _case("nullable-population", "find_district", nullable_population),
        _case("nullable-tax", "district_money", pineywoods),
        _case("absent-national-rank", "district_national", unranked_small_district),
        _case("nullable-national-rank", "district_national", explicit_null_rank),
        _case("tioga-live", "district_trends", tioga),
        _case("houston-live", "district_forensics", houston),
        _case("charter-error-is-not-success", "district_national", charter, valid=False),
    ]
    _run_ajv(tmp_path, cases)


def test_recursive_validator_rejects_wrong_nested_types_and_missing_required_fields(tmp_path):
    money = _result("district_money", {"district_number": "057905"})
    wrong_nested_type = deepcopy(money)
    wrong_nested_type["allocation"]["lineage"]["figures"]["spend_instruction_per_student"]["numerator"] = "not a number"

    wrong_metric_type = deepcopy(money)
    wrong_metric_type["visual"]["metrics"][0]["source"]["period"] = 2025

    campuses = _result("district_campuses", {"district_number": "057905"})
    missing_nested_required = deepcopy(campuses)
    del missing_nested_required["campuses"][0]["campus_name"]

    missing_limits = deepcopy(money)
    del missing_limits["limits"]

    null_is_not_missing = deepcopy(money)
    null_is_not_missing["district_name"] = None

    cases = [
        _case("wrong-artifact-nested-type", "district_money", wrong_nested_type, valid=False),
        _case("wrong-metric-nested-type", "district_money", wrong_metric_type, valid=False),
        _case("missing-nested-required", "district_campuses", missing_nested_required, valid=False),
        _case("missing-top-level-limits", "district_money", missing_limits, valid=False),
        _case("null-required-string", "district_money", null_is_not_missing, valid=False),
    ]
    _run_ajv(tmp_path, cases)


def test_comparison_outcomes_year_is_optional_nullable_and_strictly_typed(tmp_path):
    comparison = _result("compare_districts", {"district_numbers": ["057905", "101912"]})
    assert all(row["outcomes_year"] == 2024 for row in comparison["districts"])
    historical = deepcopy(comparison)
    del historical["districts"][0]["outcomes_year"]
    explicit_null = deepcopy(comparison)
    explicit_null["districts"][0]["outcomes_year"] = None
    invalid = []
    for label, value in (("string", "2024"), ("boolean", True), ("fraction", 2024.5), ("out-of-range", 1800)):
        payload = deepcopy(comparison)
        payload["districts"][0]["outcomes_year"] = value
        invalid.append(_case("outcomes-year-" + label, "compare_districts", payload, valid=False))
    _run_ajv(tmp_path, [
        _case("outcomes-year-current", "compare_districts", comparison),
        _case("outcomes-year-historical-omitted", "compare_districts", historical),
        _case("outcomes-year-null", "compare_districts", explicit_null),
        *invalid,
    ])


def test_debt_history_tuple_uses_portable_object_terminator_and_rejects_extra_items(tmp_path):
    schema = _schemas()["district_debt"]
    tuple_schema = schema["properties"]["history"]["items"]
    assert tuple_schema["items"] == {"not": {}}

    debt = _result("district_debt", {"district_number": "057905"})
    overlength = deepcopy(debt)
    overlength["history"][0].append(1)
    _run_ajv(
        tmp_path,
        [
            _case("portable-debt-history-tuple", "district_debt", debt),
            _case("overlength-debt-history-tuple", "district_debt", overlength, valid=False),
        ],
    )


def test_error_and_mrtr_envelopes_remain_separate_from_success_schemas(tmp_path):
    error = mcp_tools.call_tool("district_money", {"district_number": "999999"})
    mrtr = mcp_tools.call_tool("district_debt", {"district_number": "Wylie ISD"})
    assert error["isError"] is True and "structuredContent" not in error
    assert mrtr["resultType"] == "input_required" and "structuredContent" not in mrtr
    _run_ajv(
        tmp_path,
        [
            _case("plain-error-envelope", "district_money", error, valid=False),
            _case("mrtr-envelope", "district_debt", mrtr, valid=False),
        ],
    )
