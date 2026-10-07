"""Independent public-artifact oracles for all eleven MCP contracts."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import mcp_protocol as P
from src import mcp_tools, sources
from src.api import app

ROOT = Path(__file__).resolve().parent.parent
CASE = json.loads((ROOT / "tests/fixtures/mcp_cases.json").read_text(encoding="utf-8"))
TOOL_NAMES = (
    "find_district",
    "district_money",
    "district_lineage",
    "district_forensics",
    "district_trends",
    "district_bonds",
    "district_debt",
    "district_campuses",
    "district_national",
    "texas_overview",
    "compare_districts",
)


def artifact(filename):
    return json.loads((ROOT / "static" / filename).read_text(encoding="utf-8"))


def at_path(value, dotted):
    for part in dotted.split("."):
        value = value[part]
    return value


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


def call(client, name, arguments=None, *, replies=None):
    params = {
        "name": name,
        "arguments": arguments or {},
        "_meta": {P.META_VERSION: P.PROTOCOL_VERSION, P.META_CLIENT_CAPS: {}},
    }
    if replies is not None:
        params["inputResponses"] = replies
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params},
        headers={"MCP-Protocol-Version": P.PROTOCOL_VERSION, "Mcp-Method": "tools/call", "Mcp-Name": name},
    ).json()["result"]


def success(client, name, arguments=None):
    result = call(client, name, arguments)
    assert result["isError"] is False, (name, result)
    return result, result["structuredContent"]


def without_visual(value):
    value = deepcopy(value)
    value.pop("visual", None)
    return value


def expected_compare_row(record, district_number, district_name):
    outside = record.get("outside_operating") or {}
    who_pays = record.get("who_pays") or {}
    landed = record.get("where_it_landed") or {}
    return {
        "district_number": district_number,
        "district_name": district_name,
        "year": record.get("year"),
        "outcomes_year": landed.get("year"),
        "students": record.get("students"),
        "debt_per_student": outside.get("per_student"),
        "operating_per_student": outside.get("operating_per_student"),
        "local_pct": who_pays.get("local_pct"),
        "tax_on_300k_home": who_pays.get("tax_bill_on_home"),
        "recapture_per_student": who_pays.get("recapture_per_student"),
        "points_vs_predicted": landed.get("gap"),
    }


def test_registry_source_hashes_vintages_and_field_paths_are_explicit():
    assert tuple(tool["name"] for tool in mcp_tools.list_tools()) == TOOL_NAMES
    assert set(CASE["contracts"]) == set(TOOL_NAMES)
    for filename, anchor in CASE["sources"].items():
        source_path = ROOT / "static" / filename
        assert hashlib.sha256(source_path.read_bytes()).hexdigest().upper() == anchor["sha256"]
        payload = artifact(filename)
        for path, expected in anchor["vintages"].items():
            assert at_path(payload, path) == expected, (filename, path)
    for tool_name, contract in CASE["contracts"].items():
        assert contract["artifacts"] and contract["field_paths"], tool_name
        assert set(contract["artifacts"]) <= set(CASE["sources"]), tool_name


def test_identifiers_remain_six_digit_strings():
    assert all(value.isdigit() and len(value) == 6 for value in CASE["districts"].values())


def test_all_eleven_tools_match_complete_independent_artifact_contracts(client, monkeypatch):
    """Compare complete results, not a selected field or a handler snapshot."""
    from src import api

    class ForbiddenDatabase:
        def __getattr__(self, name):
            raise AssertionError(f"MCP tool touched database operation {name}")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("MCP tool touched an LLM, private, or write operation")

    # These are the concrete external boundaries present in this application.
    # Public-artifact calls must still pass while each boundary raises.
    monkeypatch.setattr(api.app.state, "db_pool", ForbiddenDatabase())
    monkeypatch.setattr(api, "get_nlp_engine", forbidden)
    monkeypatch.setattr(api, "_log_question", forbidden)
    monkeypatch.setattr(api, "_log_turn", forbidden)
    for method in ("write_text", "write_bytes", "touch", "unlink", "rename", "replace", "mkdir"):
        monkeypatch.setattr(Path, method, forbidden)

    dallas = CASE["districts"]["dallas"]
    houston = CASE["districts"]["houston"]
    fallback = artifact("fallback_index.json")
    economics = artifact("economics_data.json")
    forensic = artifact("forensic_data.json")
    trend = artifact("trend_data.json")
    bond = artifact("bond_data.json")
    debt = artifact("debt_data.json")
    campus = artifact("campus_data.json")
    national = artifact("national_data.json")

    # find_district: every returned match field is tied to the public index and
    # the public forensic enrollment table.
    _, found = success(client, "find_district", {"name": "Dallas"})
    starts = [row for row in fallback["districts"] if row["district_name"].lower().startswith("dallas")]
    contains = [
        row for row in fallback["districts"] if "dallas" in row["district_name"].lower() and row not in starts
    ]
    indexed = {row["district_number"]: row for row in starts + contains}
    enrollment = {row["n"]: row.get("students") for row in forensic["table"]}
    assert [row["district_number"] for row in found["matches"]] == list(indexed)
    for row in found["matches"]:
        source_row = indexed[row["district_number"]]
        assert row["district_name"].casefold() == source_row["district_name"].casefold()
        assert row["students"] == enrollment.get(row["district_number"])
        assert set(row) == {"district_number", "district_name", "students"}
    assert found["limits"] == [
        "A district name is not an identifier in Texas — thirteen names are shared by two districts each. "
        "Use the district_number."
    ]

    # Six tools expose a complete artifact district record plus exact artifact
    # limits (and, for forensics, the published thresholds).
    _, money = success(client, "district_money", {"district_number": dallas})
    assert without_visual(money) == {**economics["districts"][dallas], "limits": economics["meta"]["limits"]}

    _, forensics = success(client, "district_forensics", {"district_number": dallas})
    assert forensics == {
        **forensic["districts"][dallas],
        "thresholds": forensic["meta"]["thresholds"],
        "limits": forensic["meta"]["limits"],
    }

    _, trends = success(client, "district_trends", {"district_number": dallas})
    assert trends == {**trend["districts"][dallas], "limits": trend["meta"]["limits"]}

    _, bonds = success(client, "district_bonds", {"district_number": dallas})
    assert bonds == {**bond["districts"][dallas], "limits": bond["meta"]["limits"]}

    debt_result, debt_payload = success(client, "district_debt", {"district_number": dallas})
    assert debt_payload == {
        **debt["districts"][dallas],
        "fiscal_year": debt["meta"]["fiscal_year"],
        "limits": debt["meta"]["limits"],
    }

    _, campuses = success(client, "district_campuses", {"district_number": dallas})
    assert campuses == {
        **campus["districts"][dallas],
        "year": campus["meta"]["year"],
        "limits": campus["meta"]["limits"],
    }

    # Lineage is an intentional composition. Every artifact-backed field is
    # checked here, and the remaining provenance fields are checked against the
    # independent source register rather than against the handler serializer.
    _, lineage = success(client, "district_lineage", {"district_number": dallas})
    template = economics["meta"]["lineage_templates"]["total_per_student"]
    lineage_record = economics["districts"][dallas]["revenue"]["lineage"]
    figure = lineage_record["figures"]["total_per_student"]
    mapped_lineage = {
        "metric": template["metric"],
        "value": figure["value"],
        "numerator": figure["numerator"],
        "denominator": lineage_record["denominator"],
        "denominator_type": template["denominator_type"],
        "formula": template["formula"],
        "unit": template["unit"],
        "fiscal_year": template["fiscal_year"],
        "district_number": dallas,
        "source": template["source"],
        "source_vintage": str(economics["meta"]["year"]),
        "rounding": template["rounding"],
        "recomputed_value": figure["recomputed_value"],
        "recomputed_from": lineage_record["recomputed_from"],
        "artifact": template["artifact"],
    }
    for key, expected in mapped_lineage.items():
        assert lineage[key] == expected, key
    measure = next(item for item in sources.MEASURES if item["id"] == template["measure_id"])
    assert lineage["source_url"] == sources.SOURCES[template["source_id"]]["url"]
    assert lineage["independent_test"] == measure["test"]
    assert (lineage["fresh"], lineage["aim_ok"]) == sources.freshness_and_aim(template["source_id"])
    assert lineage["calculation_version"] == "1" and lineage["refused_because"] == ""
    assert lineage["notes"][0] == template["source_note"]
    assert sources.recorded_on() in lineage["notes"][1]
    assert lineage["gate"] == {
        "verdict": "VERIFIED",
        "checks": {
            "computability": "ok",
            "arithmetic": "ok",
            "correctness": "ok",
            "freshness": "ok",
            "aim": "ok",
        },
        "why": [],
    }
    assert lineage["available_metrics"] == sorted(
        (
            set(economics["districts"][dallas]["revenue"]["lineage"]["figures"])
            | set(economics["districts"][dallas]["allocation"]["lineage"]["figures"])
        )
        & set(economics["meta"]["lineage_templates"])
    )
    assert lineage["limits"] == economics["meta"]["limits"]
    assert set(lineage) == {
        "metric", "value", "numerator", "denominator", "denominator_type", "formula", "unit",
        "fiscal_year", "district_number", "source", "source_url", "source_vintage",
        "calculation_version", "rounding", "recomputed_value", "recomputed_from", "artifact",
        "independent_test", "fresh", "aim_ok", "refused_because", "notes", "gate",
        "available_metrics", "limits",
    }

    national_result, national_payload = success(client, "district_national", {"district_number": dallas})
    assert national_payload == {
        "district_number": dallas,
        "fiscal_year": national["meta"]["fiscal_year"],
        **national["districts"][dallas],
        "states": {"texas": national["states"]["texas"]},
        "national": national["national"],
        "limits": national["meta"]["limits"],
    }

    _, overview = success(client, "texas_overview")
    assert without_visual(overview) == {
        "year": forensic["meta"]["year"],
        "statewide": forensic["statewide"],
        "trend_findings": trend["findings"],
        "trend_change": trend["statewide"]["change"],
        "deficit_by_year": trend["statewide"]["deficit_by_year"],
        "balanced_panel_check": trend["meta"]["balanced_panel_check"],
        "limits": forensic["meta"]["limits"] + trend["meta"]["limits"],
    }

    _, comparison = success(client, "compare_districts", {"district_numbers": [dallas, houston]})
    assert without_visual(comparison) == {
        "districts": [
            expected_compare_row(forensic["districts"][dallas], dallas, "Dallas ISD"),
            expected_compare_row(forensic["districts"][houston], houston, "Houston ISD"),
        ],
        "not_found": [],
        "limits": forensic["meta"]["limits"],
    }

    # Years that appear in prose rather than structured artifact records remain
    # tied to the exact source metadata.
    assert f"fiscal {debt['meta']['fiscal_year']}" in debt_result["content"][0]["text"]
    assert campuses["year"] == campus["meta"]["year"]
    assert f"fiscal {national['meta']['fiscal_year']}" in national_result["content"][0]["text"]


def test_visual_values_periods_units_denominators_sources_and_limits_match_artifacts(client):
    dallas = CASE["districts"]["dallas"]
    houston = CASE["districts"]["houston"]
    economics = artifact("economics_data.json")
    forensic = artifact("forensic_data.json")

    _, money = success(client, "district_money", {"district_number": dallas})
    district_metrics = {metric["id"]: metric for metric in money["visual"]["metrics"]}
    assert set(district_metrics) == set(CASE["visual_metrics"]["district_money"])
    for key, definition in CASE["visual_metrics"]["district_money"].items():
        metric = district_metrics[key]
        assert metric["value"] == at_path(economics, definition["path"])
        for field in ("label", "unit", "denominator", "status"):
            assert metric[field] == definition[field]
        assert metric["period"] == str(economics["meta"]["year"])
        assert metric["source"]["period"] == str(economics["meta"]["year"])
        assert metric["source"]["label"] and metric["source"]["url"]
        assert metric["limits"] == economics["meta"]["limits"]
    assert money["visual"]["limits"] == economics["meta"]["limits"]

    _, comparison = success(client, "compare_districts", {"district_numbers": [dallas, houston]})
    visual_rows = {row["district_number"]: row for row in comparison["visual"]["metrics"]}
    assert set(visual_rows) == {dallas, houston}
    for district_number, visual_row in visual_rows.items():
        source_record = forensic["districts"][district_number]
        metrics = {metric["id"]: metric for metric in visual_row["values"]}
        assert set(metrics) == set(CASE["visual_metrics"]["compare_districts"])
        for key, definition in CASE["visual_metrics"]["compare_districts"].items():
            metric = metrics[key]
            assert metric["value"] == at_path(source_record, definition["path"])
            for field in ("label", "unit", "denominator", "status"):
                assert metric[field] == definition[field]
            period = at_path(source_record, definition.get("period_path", "year"))
            assert metric["period"] == str(period) if period is not None else "Not reported"
            assert metric["source"]["period"] == str(period) if period is not None else "Not reported"
            assert metric["source"]["label"] and metric["source"]["url"]
            assert metric["limits"] == forensic["meta"]["limits"]
    assert comparison["visual"]["limits"] == forensic["meta"]["limits"]

    _, overview = success(client, "texas_overview")
    statewide_metrics = {metric["id"]: metric for metric in overview["visual"]["metrics"]}
    assert set(statewide_metrics) == set(CASE["visual_metrics"]["texas_overview"])
    for key, definition in CASE["visual_metrics"]["texas_overview"].items():
        metric = statewide_metrics[key]
        assert metric["value"] == at_path(forensic, definition["path"])
        for field in ("label", "unit", "denominator", "status"):
            assert metric[field] == definition[field]
        assert metric["period"] == str(forensic["meta"]["year"])
        assert metric["source"]["period"] == str(forensic["meta"]["year"])
        assert metric["source"]["label"] and metric["source"]["url"]
        assert metric["limits"] == forensic["meta"]["limits"] + artifact("trend_data.json")["meta"]["limits"]
    assert overview["visual"]["limits"] == overview["limits"]


def test_every_tool_period_matches_its_exact_artifact(client):
    dallas = CASE["districts"]["dallas"]
    houston = CASE["districts"]["houston"]
    economics = artifact("economics_data.json")
    forensic = artifact("forensic_data.json")
    trend = artifact("trend_data.json")
    debt = artifact("debt_data.json")
    campus = artifact("campus_data.json")
    national = artifact("national_data.json")

    _, money = success(client, "district_money", {"district_number": dallas})
    _, lineage = success(client, "district_lineage", {"district_number": dallas})
    _, forensics = success(client, "district_forensics", {"district_number": dallas})
    _, trends = success(client, "district_trends", {"district_number": dallas})
    _, bonds = success(client, "district_bonds", {"district_number": dallas})
    debt_result, debt_payload = success(client, "district_debt", {"district_number": dallas})
    _, campus_payload = success(client, "district_campuses", {"district_number": dallas})
    national_result, national_payload = success(client, "district_national", {"district_number": dallas})
    _, overview = success(client, "texas_overview")
    _, comparison = success(client, "compare_districts", {"district_numbers": [dallas, houston]})

    assert money["year"] == economics["meta"]["year"]
    assert lineage["fiscal_year"] == economics["meta"]["year"]
    assert forensics["year"] == forensic["meta"]["year"]
    assert trends["years"] == list(range(trend["meta"]["first_year"], trend["meta"]["last_year"] + 1))
    assert {election["year"] for election in bonds["elections"]}
    assert bonds["totals"]["first_year"] == min(election["year"] for election in bonds["elections"])
    assert bonds["totals"]["last_year"] == max(election["year"] for election in bonds["elections"])
    assert debt_payload["fiscal_year"] == debt["meta"]["fiscal_year"]
    assert f"fiscal {debt['meta']['fiscal_year']}" in debt_result["content"][0]["text"]
    assert campus_payload["year"] == campus["meta"]["year"]
    assert national_payload["fiscal_year"] == national["meta"]["fiscal_year"]
    assert f"fiscal {national['meta']['fiscal_year']}" in national_result["content"][0]["text"]
    assert overview["year"] == forensic["meta"]["year"]
    assert overview["deficit_by_year"][0]["year"] == trend["meta"]["first_year"]
    assert overview["deficit_by_year"][-1]["year"] == trend["meta"]["last_year"]
    assert all(row["year"] == forensic["districts"][row["district_number"]]["year"] for row in comparison["districts"])
    assert all(
        row["outcomes_year"]
        == forensic["districts"][row["district_number"]]
        .get("where_it_landed", {})
        .get("year")
        for row in comparison["districts"]
    )


def test_bounds_missing_null_charter_and_multi_round_trip_paths(client, monkeypatch):
    from src import api

    charter = call(client, "district_national", {"district_number": CASE["districts"]["charter"]})
    assert charter["isError"] and "cannot exist" in charter["content"][0]["text"]
    assert "charter" in charter["content"][0]["text"].lower()

    pineywoods = call(client, "district_money", {"district_number": CASE["districts"]["pineywoods"]})
    assert pineywoods["isError"] is False and pineywoods["structuredContent"]["tax"] is None
    nullable = call(client, "find_district", {"name": "A W Brown Leadership"})
    assert nullable["structuredContent"]["matches"][0]["students"] is None

    missing = call(
        client,
        "compare_districts",
        {"district_numbers": [CASE["districts"]["dallas"], "999999"]},
    )
    assert missing["isError"] is False and missing["structuredContent"]["not_found"] == ["999999"]

    for count, expected in ((1, True), (2, False), (6, False), (7, True)):
        result = call(client, "compare_districts", {"district_numbers": [CASE["districts"]["dallas"]] * count})
        assert result["isError"] is expected

    first = call(client, "district_money", {"district_number": "Wylie ISD"})
    assert first["resultType"] == "input_required"
    declined = call(
        client, "district_money", {"district_number": "Wylie ISD"}, replies={"district_number": {"action": "decline"}}
    )
    assert declined["isError"] is True
    chosen = first["inputRequests"]["district_number"]["params"]["requestedSchema"]["properties"]["district_number"][
        "enum"
    ][0]
    accepted = call(
        client,
        "district_money",
        {"district_number": "Wylie ISD"},
        replies={"district_number": {"action": "accept", "content": {"district_number": chosen}}},
    )
    assert accepted["isError"] is False

    monkeypatch.setattr(api, "_national", lambda: None)
    unavailable = call(client, "district_national", {"district_number": CASE["districts"]["dallas"]})
    assert unavailable["isError"] is True and "not built" in unavailable["content"][0]["text"]


def test_malformed_ids_unicode_names_and_leading_zero_repair_are_bounded(client):
    assert call(client, "district_money", {"district_number": "57905"})["isError"] is False
    assert call(client, "district_money", {"district_number": "banana"})["isError"] is True
    assert call(client, "find_district", {"name": "é"})["isError"] is True
    assert call(client, "compare_districts", {"district_numbers": "057905"})["isError"] is True
