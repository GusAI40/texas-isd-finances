# Plain-language data dictionary

This guide explains the meanings readers need before comparing a number. For all 617 generated fields, see [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md). For publisher, vintage, URL, and measure authority, see [src/sources.py](src/sources.py).

## Money and denominators

| Term | Meaning | Do not treat it as |
|---|---|---|
| Operating revenue (`all_funds_total_operating_revenue`) | All-funds operating revenue. | Unrestricted total receipts. |
| Total revenue (`total_revenue`) | Public API alias for `all_funds_total_operating_revenue`: all-funds operating revenue, not unrestricted receipts or a broader independently defined total. | A guarantee it has the same scope as operating spending. |
| Operating spending (`operating_spend`) | Public API alias for `all_funds_total_operating_expenditures_by_obj`: all-funds operating expenditures by object. | Total disbursements. |
| Total disbursements / total spend (`total_spend`) | Public API alias for `all_funds_total_disbursements`: all-funds disbursements, including construction and other categories outside routine operations. | Operating spending or an accounting-identity proof. |
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
| Modeled retention | Teacher-cohort transition estimate under a constant annual turnover assumption. | It is not student retention or observed longitudinal teacher tracking. |
| Measured outcome | Publisher-reported result with stated cohort and year. | It is not causal proof about spending. |

## Missing, zero, time, and cohorts

**Zero** means the source reports zero. **Missing** means no usable value was published, matched, applicable, or available. Do not turn missing into zero. **Not applicable** is distinct; for example, some charters have no Census F-33 record because that survey is of governments.

PEIMS finance covers fiscal 2009–2025; the national F-33 comparison is FY2024. Outcomes, equity, property, debt, bonds, and E-Rate have their own vintages. Compare only figures whose year and cohort label match the question. A cohort may be enrolled students, surveyed students, a subgroup, rated campuses, a district, or an F-33 universe.

Use lineage where available for numerator, denominator, formula, source, and limitations. MCP results carry a `limits` array; see [docs/MCP.md](docs/MCP.md). Current limitations are in the [2026 audit](docs/AUDIT_2026-10-07.md).
