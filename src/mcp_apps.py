"""Bounded MCP App resource and visual-payload adapters.

These functions only reshape the public tool result already produced in
``mcp_tools``.  They neither open another data source nor calculate a second
set of finance figures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

RESOURCE_URI = "ui://txisd/report/v1.html"
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"
VISUAL_TOOL_NAMES = frozenset({"district_money", "compare_districts", "texas_overview"})

_ROOT = Path(__file__).resolve().parent.parent
_STATIC = _ROOT / "static"


def _metric(
    key: str,
    label: str,
    value: Any,
    unit: str,
    period: Any,
    limits: list[Any],
    *,
    denominator: str | None = None,
    population: str | None = None,
    status: str | None = None,
    source_label: str = "Texas Education Agency public artifacts",
) -> dict[str, Any]:
    normalized_period = str(period) if period is not None else "Not reported"
    return {
        "id": key,
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "period": normalized_period,
        "population": population or "Texas public school districts",
        "denominator": denominator or "Not reported",
        "status": status or ("missing" if value is None else "observed"),
        "source": {"label": source_label, "url": "https://txisd.dev/transparency", "period": normalized_period},
        "limits": [str(limit) for limit in limits if limit],
    }


def _district_population(name: Any, number: Any) -> str:
    if isinstance(name, str) and name.strip():
        return name.strip()
    if isinstance(number, str) and len(number) == 6 and number.isdigit():
        return f"District {number}"
    return "District not reported"


def visual_payload(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Return a versioned, additive display model for the three visual tools."""
    limits = list(data.get("limits") or [])
    if tool_name == "district_money":
        allocation = data.get("allocation") or {}
        number, name, year = data.get("district_number"), data.get("district_name"), data.get("year")
        metrics = [
            _metric(
                "total_per_student",
                "Operating plus debt service per student",
                allocation.get("total_per_student"),
                "USD per student",
                year,
                limits,
                denominator="fall survey enrollment",
                population=_district_population(name, number),
            ),
            _metric(
                "operating_per_student",
                "Operating spending per student",
                allocation.get("operating_per_student"),
                "USD per student",
                year,
                limits,
                denominator="fall survey enrollment",
                population=_district_population(name, number),
            ),
            _metric(
                "debt_per_student",
                "Debt service per student",
                allocation.get("debt_per_student"),
                "USD per student",
                year,
                limits,
                denominator="fall survey enrollment",
                population=_district_population(name, number),
            ),
            _metric(
                "instruction_per_student",
                "Instruction per student",
                allocation.get("instruction_per_student"),
                "USD per student",
                year,
                limits,
                denominator="fall survey enrollment",
                population=_district_population(name, number),
            ),
        ]
        return {
            "schemaVersion": 1,
            "view": "district",
            "districts": [{"district_number": number, "district_name": name}],
            "metrics": metrics,
            "limits": limits,
            "websiteUrl": f"https://txisd.dev/?d={number}",
        }
    if tool_name == "compare_districts":
        rows = data.get("districts") or []
        metrics = []
        for row in rows:
            metrics.append(
                {
                    "district_number": row.get("district_number"),
                    "district_name": row.get("district_name"),
                    "values": [
                        _metric(
                            "operating_per_student",
                            "Operating spending per student",
                            row.get("operating_per_student"),
                            "USD per student",
                            row.get("year") if row.get("year") is not None else "Not reported",
                            limits,
                            denominator="fall survey enrollment",
                            population=_district_population(row.get("district_name"), row.get("district_number")),
                        ),
                        _metric(
                            "debt_per_student",
                            "Debt service per student",
                            row.get("debt_per_student"),
                            "USD per student",
                            row.get("year") if row.get("year") is not None else "Not reported",
                            limits,
                            denominator="fall survey enrollment",
                            population=_district_population(row.get("district_name"), row.get("district_number")),
                        ),
                        _metric(
                            "local_pct",
                            "Local revenue share",
                            row.get("local_pct"),
                            "percent",
                            row.get("year") if row.get("year") is not None else "Not reported",
                            limits,
                            denominator="gross local + state + federal revenue",
                            population=_district_population(row.get("district_name"), row.get("district_number")),
                        ),
                        _metric(
                            "points_vs_predicted",
                            "Points vs predicted",
                            row.get("points_vs_predicted"),
                            "percentage points",
                            row.get("outcomes_year") if row.get("outcomes_year") is not None else "Not reported",
                            limits,
                            denominator="predicted Meets rate from the district need model",
                            status="modeled" if row.get("points_vs_predicted") is not None else "missing",
                            population=_district_population(row.get("district_name"), row.get("district_number")),
                        ),
                    ],
                }
            )
        return {
            "schemaVersion": 1,
            "view": "comparison",
            "districts": [
                {"district_number": row.get("district_number"), "district_name": row.get("district_name")}
                for row in rows
            ],
            "metrics": metrics,
            "limits": limits,
            "websiteUrl": "https://txisd.dev/",
        }
    statewide = data.get("statewide") or {}
    metrics = [
        _metric(
            "debt_total",
            "Annual debt service",
            statewide.get("debt_total"),
            "USD per fiscal year",
            data.get("year"),
            limits,
            denominator="sum across Texas districts reporting enrollment and debt service",
        ),
        _metric(
            "debt_median",
            "Median debt service per student",
            statewide.get("debt_median"),
            "USD per student",
            data.get("year"),
            limits,
            denominator="fall survey enrollment",
        ),
    ]
    return {
        "schemaVersion": 1,
        "view": "statewide",
        "districts": [],
        "metrics": metrics,
        "limits": limits,
        "websiteUrl": "https://txisd.dev/",
    }


def list_resources() -> list[dict[str, Any]]:
    return [
        {
            "uri": RESOURCE_URI,
            "name": "Texas ISD visual report",
            "description": "Accessible visual report for selected public finance tools.",
            "mimeType": RESOURCE_MIME_TYPE,
            "_meta": {
                "ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": [], "frameDomains": []}}
            },
        }
    ]


def read_resource(uri: str) -> dict[str, Any]:
    if uri != RESOURCE_URI:
        raise KeyError(uri)
    template = (_STATIC / "mcp-app.html").read_text(encoding="utf-8")
    helper = (_STATIC / "visual-components.js").read_text(encoding="utf-8")
    css = (_STATIC / "design.css").read_text(encoding="utf-8")
    markers = {
        "/*__TXISD_VISUAL_COMPONENTS__*/": helper.replace("</script", "<\\/script"),
        "/*__TXISD_DESIGN_CSS__*/": css.replace("</style", "<\\/style"),
    }
    for marker, contents in markers.items():
        if template.count(marker) != 1:
            raise RuntimeError(f"mcp app template marker missing or repeated: {marker}")
        template = template.replace(marker, contents)
    return {
        "contents": [
            {
                "uri": RESOURCE_URI,
                "mimeType": RESOURCE_MIME_TYPE,
                "text": template,
                "_meta": {
                    "ui": {
                        "prefersBorder": True,
                        "csp": {"connectDomains": [], "resourceDomains": [], "frameDomains": []},
                    }
                },
            }
        ]
    }
