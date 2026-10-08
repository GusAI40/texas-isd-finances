# Plain-language data dictionary

This guide explains the meanings readers need before comparing a number. For the complete generated field inventory, see [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md). For publisher, vintage, URL, and measure authority, see [src/sources.py](src/sources.py).

## Money and denominators

| Term | Meaning | Do not treat it as |
|---|---|---|
| Operating revenue (`all_funds_total_operating_revenue`) | All-funds operating revenue. | Unrestricted total receipts. |
| Total revenue (`total_revenue`) | Public API alias for `all_funds_total_operating_revenue`: all-funds operating revenue, not unrestricted receipts or a broader independently defined total. | A guarantee it has the same scope as operating spending. |
| Operating spending (`operating_spend`) | Public API alias for `all_funds_total_operating_expenditures_by_obj`: all-funds operating expenditures by object. | Total disbursements. |
| Total disbursements / total spend (`total_spend`) | Public API alias for `all_funds_total_disbursements`: all-funds disbursements, including construction and other categories outside routine operations. | Operating spending or an accounting-identity proof. |
| Operating plus debt service (`district_money.allocation.total_per_student`) | An artifact composition of operating expenditures and annual debt service, divided by the stated student count. | The API's all-funds total-disbursements measure. Dallas's published FY2025 artifact composition is $17,788/student; the corrected all-funds view expectation is $23,746.63/student. They have different numerators. |
| PEIMS denominator | Texas fall-survey enrollment used with PEIMS financial series. | Census F-33 enrollment or ADA. |
| F-33 denominator | Census's own enrollment basis for national comparisons. | A PEIMS denominator. |

Do not assume `total spend − debt − capital = operating spending`; these measures are independently defined. The audit found production precision truncation in selected FY2025 per-student view values because integer division happens before numeric cast. It did not find evidence aggregate dollars are wrong.

## Percentages, rates, and estimates

| Term | Meaning | Reading rule |
|---|---|---|
| Percentage | A share of a stated whole. | Ask “of what?” |
| Percentage-point change | Direct subtraction of percentages: 18% to 21% is 3 points. | It is not a 3% relative change. |
| Tax rate per $100 | A rate applied to each $100 of taxable value. | It is not a household bill. |
| Illustrative tax bill | A modeled calculation using a disclosed home-value assumption. | It is not an individual assessment or advice. |
| Modeled retention | A hypothetical ten-teacher district cohort over six annual periods, K through fifth grade: `10 × (1 − turnover/100)^6`. Round only the headline. | It is not student retention, a building-level forecast, or observed longitudinal teacher tracking. |
| Measured outcome | Publisher-reported result with stated cohort and year. | It is not causal proof about spending. |

## Missing, zero, time, and cohorts

**Zero** means the source reports zero. **Missing** means no usable value was published, matched, applicable, or available. Do not turn missing into zero. **Not applicable** is distinct; for example, some charters have no Census F-33 record because that survey is of governments.

PEIMS finance covers fiscal 2009–2025; the national F-33 comparison is FY2024. Outcomes, equity, property, debt, bonds, and E-Rate have their own vintages. Compare only figures whose year and cohort label match the question. A cohort may be enrolled students, surveyed students, a subgroup, rated campuses, a district, or an F-33 universe.

Use lineage where available for numerator, denominator, formula, source, and limitations. MCP results carry a `limits` array; see [docs/MCP.md](docs/MCP.md). Current limitations are in the [2026 audit](docs/AUDIT_2026-10-07.md).

## Visual report fields

The optional MCP `visual` result reshapes the tool's existing public artifact;
it does not fetch another source. Its district, comparison, and statewide views
carry the following metric meanings in [the adapter](src/mcp_apps.py).

| Field | Meaning and reading rule |
|---|---|
| `id`, `key`, `label` | Stable measure identity and readable name. Similar names alone do not establish comparable numerators. |
| `value`, `unit` | The reported number and its unit. A null value is missing; a reported zero remains zero. |
| `period`, `source.period` | The measure's actual source period. Both say `Not reported` when unavailable. A comparison's outcome period can differ from its finance period. |
| `population`, `denominator` | The district or statewide universe and the stated basis, such as fall-survey enrollment. An unavailable denominator says `Not reported`. |
| `status` | The adapter distinguishes observed, missing, and modeled figures. The website also labels not-applicable and unverified states explicitly. |
| `source`, `limits` | Source identity, safe link, source period, and qualifications that travel with the value. A source link is not a claim that newer releases have been ingested. |

Dallas/Houston comparisons retain FY2025 finance and 2024 outcome-model measures
separately. The modeled difference from predicted performance describes an
association; it does not show that a spending change caused a result.

## Visual rule and ChatGPT access

| Term | Meaning | Evidence boundary |
|---|---|---|
| 95% visual / 5% prose | Meaningful charts, maps, numeric cards, and primary data tables occupy at least 95% of measured analytic content; standalone prose occupies at most 5%. Required labels, units, years, and status travel with the data. | Measure tight content bounds separately for the initial viewport and full report. Padding, decoration, invisible content, or prose inside a bordered card cannot improve the score. See the [visual contract](docs/VISUAL_DESIGN_CONTRACT.md). |
| MCP | The read-only tool interface through which a compatible AI host retrieves public data. | An accessible endpoint does not prove every host or account can use it. |
| MCP App | An optional visual report rendered inside a compatible host. | Useful sourced text remains available when a host cannot render it. |
| Plugin package | An installable package connecting tools, instructions, and optional visuals. | Schema validation, owner-account registration, fresh installation, and public-directory approval are distinct checks. |
| UNVERIFIED | The required source, test, or host evidence has not established a result. | It is not zero, a failure finding, or permission to label a value verified. |
