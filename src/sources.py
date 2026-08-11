"""The source of truth register: where every number came from, and how to check it.

Why this file exists
--------------------
"Is this accurate?" is not answerable by asserting yes. It is answerable by
telling a sceptic exactly which government file a figure came from, which
column, what was done to it, and where to download the original so they can
redo the arithmetic and disagree.

Before this register, that information existed but was scattered: some layers
carried a prose `meta.sources` string, five carried nothing at all, and none
carried a URL, a column name, or a vintage. A reader could not follow any
number back to its origin without reading the build scripts.

Everything here is a public record. No source requires a login, a licence or a
FOIA request, which is the point: anyone can repeat this work from scratch.

Two registers
-------------
`SOURCES`  — the upstream files. Publisher, product name, download URL, what
             period it covers, and what it is authoritative for.
`MEASURES` — every published figure, tied to a source id, the exact column(s)
             used, the transformation in one sentence, where it surfaces on the
             site, and the test that re-derives it from source.

The rule this enforces: a figure that cannot name its source id and its
re-derivation test does not belong on the site.
"""
from __future__ import annotations

SITE = "https://txisd.dev"

SOURCES: dict[str, dict] = {
    "tea_peims": {
        "title": "Summarized PEIMS Actual Financial Data",
        "publisher": "Texas Education Agency",
        "url": "https://tea.texas.gov/finance-and-grants/state-funding/"
               "state-funding-reports-and-data/peims-financial-data-downloads",
        "covers": "fiscal 2009–2025, every Texas school district",
        "authoritative_for": "revenue, spending by object and by function, debt "
                             "service, capital outlay, payroll, enrolment",
        "local_file": "data/texas_finance_clean.csv",
        "proves_it": ["PEIMS", "Texas Education Agency"],
        "note": "Districts file this with TEA and it is corrected over time. The "
                "newest year has had the least time to be corrected.",
    },
    "tea_snapshot": {
        "title": "Snapshot — District and Charter Detail",
        "publisher": "Texas Education Agency",
        "url": "https://rptsvr1.tea.texas.gov/perfreport/snapshot/download.html",
        "covers": "2009–2024",
        "authoritative_for": "student demographics, teacher counts, turnover, "
                             "experience and salary, class size, attendance, "
                             "graduation, STAAR at three bars, county and region",
        "local_file": "data/snapshot_all.csv",
        "proves_it": ["Snapshot", "Texas Education Agency"],
    },
    "tea_staar_district": {
        "title": "STAAR Aggregate District-Level Results",
        "publisher": "Texas Education Agency",
        "url": "https://tea.texas.gov/student-assessment/student-assessment-results/"
               "statewide-summary-reports",
        "covers": "school years 2024 and 2025",
        "authoritative_for": "results by student group, including economically "
                             "disadvantaged students specifically",
        "local_file": "data/staar_district_long.csv",
        "proves_it": ["STAAR", "Texas Education Agency"],
        "note": "District-level aggregates are also downloadable from the "
                "Texas Assessment Research Portal at https://txresearchportal.com/ .",
    },
    "tea_property": {
        "title": "School District Property Values and Tax Rates",
        "publisher": "Texas Education Agency with the Texas Comptroller",
        "url": "https://tea.texas.gov/finance-and-grants/state-funding/"
               "additional-finance-resources/"
               "school-district-property-values-and-tax-rates",
        "covers": "certified property values tax years 2015–2025; adopted tax "
                  "rates 2005-06 to 2023-24",
        "authoritative_for": "taxable value, M&O and I&S tax rates",
        "local_file": "data/tea_property.csv",
        "proves_it": ["Property Value", "Tax Rate", "Texas Education Agency"],
        "note": "Tax year N is TEA fiscal year N+1. Figures are withheld where "
                "two independent estimates of the tax base disagree by >25%.",
    },
    "tea_recapture": {
        "title": "Excess Local Revenue (recapture) paid by district",
        "publisher": "Texas Education Agency",
        "url": "https://tea.texas.gov/finance-and-grants/state-funding/"
               "excess-local-revenue",
        "covers": "fiscal 1994–2026",
        "authoritative_for": "how much local tax revenue each district sends "
                             "back to the state",
        "local_file": "data/tea_property.csv",
        "proves_it": ["Excess Local Revenue", "Texas Education Agency"],
    },
    "bond_elections": {
        "title": "Texas school district bond election results",
        "publisher": "Texas Bond Review Board",
        "url": "https://data.texas.gov/d/kbmc-qmvg",
        "covers": "4,992 decided propositions, 1958–2026",
        "authoritative_for": "what school debt was asked FOR, the amount, and "
                             "whether voters carried or defeated it",
        "local_file": "data/texas_bond_elections.csv",
        "ingested_by": "scripts/ingest_bond_elections.py",
        # data.texas.gov renders its dataset page in the browser, so the page a
        # reader sees carries no server-side text to assert on. The portal's own
        # metadata API does, and it is the stronger proof anyway: it is Texas
        # stating who published this dataset, rather than us claiming it.
        "attribution_url": "https://data.texas.gov/api/views/kbmc-qmvg.json",
        "proves_it": ["Texas Bond Review Board", "Local Debt Bond Election Results",
                      "kbmc-qmvg"],
        "note": "Corrected 2026-08-11. This entry previously credited the file to "
                "compiled county returns from the Secretary of State and stated that "
                "no single agency publishes school bond elections statewide. Both "
                "were wrong: the Bond Review Board publishes all of them, back to "
                "1958, on the state's own open-data portal, and always had. The "
                "site had been shipping a municipal-advisory vendor's Excel export "
                "of that same file — two years stale, 404 propositions short, and "
                "carrying spreadsheet subtotal rows. verify_sources.py did not "
                "catch it because the Secretary of State URL returns 200; it proved "
                "the link was alive, not that it was the right link. It now checks "
                "attribution as well. Every row carries the Board's own provenance "
                "mark in a Source column (TBR, Issuer, OAG, TSB, BB, Other). This "
                "is still the only layer joined on district NAME rather than TEA "
                "number; scripts/audit_bond_match.py prints the whole join and "
                "fails the build if a shared name is resolved without the county "
                "agreeing. Two companion files from the former vendor carry a "
                "private CRM and are deliberately never ingested — going "
                "first-party removes the temptation permanently.",
    },
    "brb_debt_outstanding": {
        "title": "Local government debt outstanding — school districts",
        "publisher": "Texas Bond Review Board",
        "url": "https://data.brb.texas.gov/",
        "covers": "fiscal 2005–2025 actual, plus the amortisation schedule for "
                  "debt already sold out to 2061; 967 districts",
        "authoritative_for": "principal and interest still owed, split into "
                             "current interest bonds and capital appreciation "
                             "bonds, and the year the borrowing clears",
        "local_file": "data/brb_debt_outstanding.csv",
        "ingested_by": "scripts/ingest_brb_debt.py",
        "attribution_url": "https://data.brb.texas.gov/main_search.json",
        "proves_it": ["ISD", "issuer_name", "government_type"],
        "note": "The Board's own issuer index and per-issuer series, taken "
                "first-party. A commercial aggregator republishes the same data "
                "and is how it was found; it is deliberately not the source, "
                "because a re-publisher breaks the provenance chain at its first "
                "link. Joined to TEA numbers by name plus county via "
                "scripts/district_match.py — the index lists three issuers under "
                "two names each, so it is deduplicated by the Board's id rather "
                "than by name, which is what stops one district's debt being "
                "counted twice. Excludes obligations under one year, commercial "
                "paper, and special obligations not needing Attorney General "
                "approval, per the Board's scope note.",
    },
    "census_tiger": {
        "title": "TIGER/Line Unified School Districts, Texas",
        "publisher": "US Census Bureau (public domain)",
        "url": "https://www2.census.gov/geo/tiger/TIGER2024/UNSD/tl_2024_48_unsd.zip",
        # A zip has no prose to check, but it names its own members in the local
        # file headers at the very front of the archive — so a ranged read of the
        # first bytes proves this is the Texas (FIPS 48) school-district file and
        # not some other TIGER product served from the same directory.
        "proves_it": ["PK\u0003\u0004", "tl_2024_48_unsd.dbf"],
        "covers": "2024 boundaries, 1,005 districts",
        "authoritative_for": "district geographic boundaries",
        "note": "Charter districts have no attendance boundary, so ~8% of "
                "students are not on the map by construction.",
    },
    "bls_cpi": {
        "title": "CPI-U, annual average",
        "publisher": "US Bureau of Labor Statistics",
        "url": "https://www.bls.gov/cpi/",
        "proves_it": ["Consumer Price Index", "Bureau of Labor Statistics"],
        "covers": "2009–2025",
        "authoritative_for": "converting past dollars to constant 2024 dollars",
    },
}

# Every published figure. `source` is a key in SOURCES; `test` is the test that
# re-derives it from that source rather than from our own artifact.
MEASURES: list[dict] = [
    {
        "id": "spend_per_student",
        "label": "Spending per student",
        "source": "tea_peims",
        "columns": ["all_funds_total_operating_expenditures_by_obj",
                    "all_funds_total_debt_service_expend_by_obj",
                    "fall_survey_enrollment"],
        "method": "Operating spend plus debt service, divided by fall enrolment. "
                  "Composed, never subtracted — TEA's operating total excludes "
                  "debt service.",
        "shown_on": ["/", "/forensics"],
        "api": "/district/{n}/summary",
        "test": "tests/test_provenance.py::test_statewide_debt_total_recomputes_from_source",
    },
    {
        "id": "instruction_share",
        "label": "Share of the operating dollar reaching a classroom",
        "source": "tea_peims",
        "columns": ["all_funds_instruction_transfer_expend_fct11_95",
                    "all_funds_total_operating_expenditures_by_obj"],
        "method": "Function 11–95 (instruction) as a percentage of total "
                  "operating expenditure, summed across districts.",
        "shown_on": ["/forensics"],
        "api": "/trends/texas",
        "test": "tests/test_provenance.py::test_instruction_share_recomputes_from_source",
    },
    {
        "id": "debt_per_student",
        "label": "Debt service per student",
        "source": "tea_peims",
        "columns": ["all_funds_total_debt_service_expend_by_obj",
                    "fall_survey_enrollment"],
        "method": "Debt service divided by enrolment, deflated to constant 2024 "
                  "dollars with CPI-U.",
        "shown_on": ["/", "/forensics"],
        "api": "/district/{n}/forensics",
        "test": "tests/test_provenance.py::test_debt_per_student_recomputes_from_source",
    },
    {
        "id": "security_per_student",
        "label": "Security and monitoring per student",
        "source": "tea_peims",
        "columns": ["all_funds_security_monitoring_service_expend_fct52",
                    "fall_survey_enrollment"],
        "method": "Function 52 divided by enrolment, in constant 2024 dollars.",
        "shown_on": ["/forensics"],
        "api": "/trends/texas",
        "test": "tests/test_provenance.py::test_security_per_student_recomputes_from_source",
    },
    {
        "id": "operating_balance",
        "label": "Operating revenue minus operating spending",
        "source": "tea_peims",
        "columns": ["all_funds_total_operating_revenue",
                    "all_funds_total_operating_expenditures_by_obj"],
        "method": "Operating revenue against operating spending ONLY. Debt "
                  "service is excluded from the cost side and the I&S debt levy "
                  "(all_funds_other_revenue) from the income side — it tracks "
                  "debt service to within 15% every year, so counting it as "
                  "operating income understates deficits badly.",
        "shown_on": ["/", "/forensics"],
        "api": "/trends/texas",
        "test": "tests/test_provenance.py::test_the_operating_deficit_uses_operating_revenue_only",
    },
    {
        "id": "revenue_mix",
        "label": "Who pays: local, state and federal shares",
        "source": "tea_peims",
        "columns": ["all_funds_local_tax_revenue_from_m_o", "all_funds_state_revenue",
                    "all_funds_federal_revenue"],
        "method": "Shares of GROSS local collections. TEA reports M&O revenue net "
                  "of recapture, which makes a paying district look less locally "
                  "funded than it is.",
        "shown_on": ["/", "/forensics"],
        "api": "/district/{n}/economics",
        "test": "tests/test_forensics.py::test_local_revenue_is_gross_not_net_of_recapture",
    },
    {
        "id": "tax_on_a_home",
        "label": "School tax on a $300,000 home",
        "source": "tea_property",
        "columns": ["adopted M&O rate", "adopted I&S rate"],
        "method": "Adopted total rate applied to a $300,000 taxable value. Null "
                  "for charters (no property tax) and where two independent "
                  "estimates of the tax base disagree by more than 25%.",
        "shown_on": ["/", "/forensics"],
        "api": "/district/{n}/economics",
        "test": "tests/test_forensics.py::test_the_revenue_shares_are_a_whole_dollar",
    },
    {
        "id": "recapture",
        "label": "Recapture paid to the state",
        "source": "tea_recapture",
        "columns": ["recapture paid by district"],
        "method": "As published by TEA, divided by enrolment.",
        "shown_on": ["/", "/forensics"],
        "api": "/district/{n}/economics",
        "test": "tests/test_forensics.py::test_local_revenue_is_gross_not_net_of_recapture",
    },
    {
        "id": "debt_outstanding",
        "label": "Debt still owed — principal plus interest not yet paid",
        "source": "brb_debt_outstanding",
        "columns": ["CIBPrincipalOutstanding", "CIBInterestOutstanding",
                    "CABPrincipalOutstanding", "CABInterestOutstanding"],
        "method": "Summed per district for fiscal 2025, the Board's most recent "
                  "completed year. Years after 2025 are the amortisation "
                  "schedule for debt already sold and are never added to it.",
        "shown_on": ["/forensics"],
        "api": "/district/{n}/debt",
        "test": "tests/test_debt.py::test_the_statewide_total_is_the_sum_of_its_districts",
    },
    {
        "id": "cab_deferred_interest",
        "label": "Interest deferred to maturity on capital appreciation bonds",
        "source": "brb_debt_outstanding",
        "columns": ["CABPrincipalOutstanding", "CABInterestOutstanding"],
        "method": "Reported as an absolute stock for the current year. Dollars "
                  "repaid per dollar borrowed is reported at each district's "
                  "PEAK year only — on a shrinking balance the ratio rises on "
                  "its own and measures nothing.",
        "shown_on": ["/forensics"],
        "api": "/debt/texas",
        "test": "tests/test_debt.py::test_the_repayment_ratio_is_never_taken_on_a_residual_balance",
    },
    {
        "id": "bond_history",
        "label": "Every bond proposition and how the vote went",
        "source": "bond_elections",
        "columns": ["Issuer", "County", "Elect. Date", "$ Amount",
                    "Purpose Description", "Result", "Votes For", "Votes Against"],
        "method": "Matched to TEA district numbers by stemmed name plus county — "
                  "Texas has thirteen pairs of districts sharing a name. 100% "
                  "matched, 0 resolved without the county agreeing.",
        "shown_on": ["/", "/forensics"],
        "api": "/district/{n}/bonds",
        "test": "tests/test_district_match.py::test_published_bond_data_matched_everything_and_says_how",
    },
    {
        "id": "beats_prediction",
        "label": "Results against what student need predicts",
        "source": "tea_snapshot",
        "columns": ["test_all_meets", "pct_econ_disadv", "pct_emergent_bilingual",
                    "pct_special_ed"],
        "method": "Least squares of the Meets rate on three need measures; the "
                  "published figure is the residual. The model explains about "
                  "half the spread between districts — it is an estimate with "
                  "real uncertainty, not a fact.",
        "shown_on": ["/", "/forensics"],
        "api": "/district/{n}/outcomes",
        "test": "tests/test_forensics.py::test_percentiles_are_in_range_and_mean_the_same_thing_everywhere",
    },
    {
        "id": "equity",
        "label": "How a district's low-income students do",
        "source": "tea_staar_district",
        "columns": ["economically disadvantaged group, Meets grade level"],
        "method": "Reported at the Meets bar and benchmarked against poor "
                  "students statewide — never as a gap, which correlates about "
                  "zero with how poor students actually do.",
        "shown_on": ["/"],
        "api": "/district/{n}/equity",
        "test": "tests/test_api.py",
    },
    {
        "id": "boundaries",
        "label": "District boundaries on the map",
        "source": "census_tiger",
        "columns": ["GEOID", "geometry"],
        "method": "Joined to TEA district numbers. Geolocation is resolved "
                  "entirely in the browser; a visitor's location is never sent "
                  "anywhere.",
        "shown_on": ["/geomap"],
        "api": "/district-geo",
        "test": "tests/test_static_pages.py",
    },
    {
        "id": "constant_dollars",
        "label": "Constant 2024 dollars",
        "source": "bls_cpi",
        "columns": ["CPI-U annual average"],
        "method": "One price base for the whole site. The trend layer reuses the "
                  "economics layer's factors rather than defining a second.",
        "shown_on": ["/forensics"],
        "api": "/economics/texas",
        "test": "tests/test_provenance.py::test_debt_per_student_recomputes_from_source",
    },
]

# How a sceptic checks the whole thing rather than one number.
HOW_TO_VERIFY = [
    {
        "step": "Download the original",
        "detail": "Every source above links to the agency's own download page. "
                  "None requires a login or a records request.",
    },
    {
        "step": "Read the exact column",
        "detail": "Each measure names the columns it uses and the arithmetic in "
                  "one sentence. No figure on this site is derived from a column "
                  "that is not listed.",
    },
    {
        "step": "Run the re-derivation tests",
        "detail": "`python -m pytest tests/test_provenance.py` recomputes every "
                  "headline from the state's own file, longhand, without "
                  "importing any build script — so a wrong number cannot "
                  "validate itself.",
    },
    {
        "step": "Check the published files match the source",
        "detail": "`python scripts/verify_artifacts.py` rebuilds every artefact "
                  "and diffs it byte for byte against what this site serves. It "
                  "is the only check that catches a build script edited and "
                  "never re-run, or an upstream restatement absorbed silently.",
    },
    {
        "step": "Check the source has not changed under us",
        "detail": "tests/fixtures/provenance.json carries a SHA-256 of the "
                  "financial file every figure is built from. If the state "
                  "restates a year, that hash stops matching and the tests fail.",
    },
]

# What none of this can establish. Stated here so it travels with the register.
LIMITS = [
    "This is faithful to the source. It cannot make the source right: PEIMS is "
    "filed by districts and corrected over time, and the newest fiscal year has "
    "had the least time to be corrected.",
    "Figures derived from a model — anything comparing results against what "
    "student need predicts — are estimates with real uncertainty, and are "
    "published with it rather than as facts.",
    "The bond layer is joined on district name plus county because the source "
    "carries no TEA number. It is 100% matched with none resolved against a "
    "disagreeing county, but it is the only layer where that class of error is "
    "possible at all.",
    "Districts under 500 students have per-student figures that move on a single "
    "hire or retirement. They are flagged and kept out of rankings.",
    "Nothing here supports a claim about any named individual.",
]
