"""Re-derive the newer layers' headlines from source, longhand.

`tests/test_provenance.py` does this for the PEIMS layers: it recomputes every
published figure from the state's own file without importing a builder, so a
wrong number cannot validate itself. Four layers arrived after it and were
never brought into that chain — bonds, debt outstanding, campuses, and the
forensic quality tests. Their builders check themselves, which is not the same
thing at all: a builder that computes a figure wrongly will also assert it
wrongly, and the test suite stays green.

So everything here reaches past the builder to the raw file and counts by hand,
with the `csv` module and arithmetic. If a builder is edited and starts
producing a different number, these fail; if the upstream file is restated,
these fail; and neither failure depends on the code that produced the artefact
agreeing with itself.

Skips cleanly when a source file is absent — the raw CSVs are not committed
(too large), so in CI this covers what it can and says so rather than passing
vacuously.
"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA, STATIC = ROOT / "data", ROOT / "static"
EXCEL_EPOCH = dt.date(1899, 12, 30)


def _need(*paths: Path):
    for p in paths:
        if not p.exists():
            pytest.skip(f"{p.name} not present (raw sources are not committed)")


def _rows(p: Path, encoding: str = "utf-8"):
    with p.open(encoding=encoding, newline="") as fh:
        return list(csv.DictReader(fh))


def _art(name: str) -> dict:
    p = STATIC / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return json.loads(p.read_text())


# --- bonds -------------------------------------------------------------------

def test_the_bond_counts_come_from_the_ballot_file():
    src = DATA / "texas_bond_elections.csv"
    _need(src)
    rows = _rows(src, "utf-8-sig")
    decided = [r for r in rows if (r.get("Result") or "").strip() in ("Carried", "Defeated")]
    meta = _art("bond_data.json")["meta"]
    assert meta["propositions"] == len(decided)

    asked = sum(float(r["$ Amount"]) for r in decided if (r.get("$ Amount") or "").strip())
    assert abs(meta["total_asked"] - asked) < 1.0
    approved = sum(float(r["$ Amount"]) for r in decided
                   if r["Result"].strip() == "Carried" and (r.get("$ Amount") or "").strip())
    assert abs(meta["total_approved"] - approved) < 1.0


def test_the_bond_year_range_comes_from_the_ballot_file():
    src = DATA / "texas_bond_elections.csv"
    _need(src)
    years = []
    for r in _rows(src, "utf-8-sig"):
        if (r.get("Result") or "").strip() not in ("Carried", "Defeated"):
            continue
        v = (r.get("Elect. Date") or "").strip()
        if v.lstrip("-").isdigit():
            years.append(dt.date.fromordinal(EXCEL_EPOCH.toordinal() + int(v)).year)
    meta = _art("bond_data.json")["meta"]
    assert meta["first_year"] == min(years)
    assert meta["last_year"] == max(years)


# --- debt outstanding --------------------------------------------------------

def test_the_debt_totals_are_the_fiscal_2025_column_summed():
    src = DATA / "brb_debt_outstanding.csv"
    _need(src)
    principal = interest = 0.0
    for r in _rows(src):
        if r["fiscal_year"].strip() != "2025" or not r["district_number"].strip():
            continue
        principal += float(r["cib_principal_outstanding"]) + float(r["cab_principal_outstanding"])
        interest += float(r["cib_interest_outstanding"]) + float(r["cab_interest_outstanding"])
    t = _art("debt_data.json")["texas"]
    assert abs(t["principal"] - principal) < 2
    assert abs(t["interest"] - interest) < 2
    assert abs(t["total"] - (principal + interest)) < 2


def test_the_cab_deferred_interest_is_the_cab_column_alone():
    """The whole CAB finding rests on this one column being read correctly."""
    src = DATA / "brb_debt_outstanding.csv"
    _need(src)
    deferred = 0.0
    districts = set()
    for r in _rows(src):
        if r["fiscal_year"].strip() != "2025" or not r["district_number"].strip():
            continue
        p, i = float(r["cab_principal_outstanding"]), float(r["cab_interest_outstanding"])
        deferred += i
        if p or i:
            districts.add(r["district_number"])
    cab = _art("debt_data.json")["texas"]["cab"]
    assert abs(cab["deferred_interest"] - deferred) < 2
    assert cab["districts"] == len(districts)


def test_the_payoff_year_is_the_last_year_with_anything_owed():
    src = DATA / "brb_debt_outstanding.csv"
    _need(src)
    last = 0
    for r in _rows(src):
        if not r["district_number"].strip():
            continue
        owed = sum(float(r[c]) for c in (
            "cib_principal_outstanding", "cib_interest_outstanding",
            "cab_principal_outstanding", "cab_interest_outstanding"))
        y = int(r["fiscal_year"])
        if owed > 0 and y > last:
            last = y
    assert _art("debt_data.json")["texas"]["clears_in"] == last


# --- campuses ----------------------------------------------------------------

def test_the_campus_headline_is_recomputable_from_the_tea_file():
    """138,664 students, counted again from TEA's rows rather than the builder's."""
    src = DATA / "tea_accountability.csv"
    _need(src)
    grade = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    rows = _rows(src)
    district_rating = {r["district_number"]: r["rating"]
                       for r in rows if r["is_district_row"].upper() == "TRUE"}
    students = campuses = 0
    districts = set()
    for r in rows:
        if r["is_district_row"].upper() == "TRUE":
            continue
        if r["is_aea"].upper() == "TRUE":
            continue
        cg = grade.get(r["rating"])
        dg = grade.get(district_rating.get(r["district_number"], ""))
        if cg is None or dg is None or not r["students"].strip():
            continue
        if dg >= 3 and cg <= 1:
            campuses += 1
            students += int(float(r["students"]))
            districts.add(r["district_number"])
    h = _art("campus_data.json")["texas"]["hidden_by_the_district_average"]
    assert h["campuses"] == campuses
    assert h["students"] == students
    assert h["districts"] == len(districts)


def test_the_not_rated_count_is_what_tea_published():
    src = DATA / "tea_accountability.csv"
    _need(src)
    n = sum(1 for r in _rows(src)
            if r["is_district_row"].upper() != "TRUE" and r["rating"] == "Not Rated")
    assert _art("campus_data.json")["meta"]["campuses_not_rated"] == n


# --- the crosswalk is a derivation too ---------------------------------------

def test_the_crosswalk_counts_match_the_files_it_was_built_from():
    xw, fin = DATA / "district_crosswalk.csv", DATA / "texas_finance_clean.csv"
    _need(xw, fin)
    rows = _rows(xw)
    want = {r["district_number"] for r in _rows(fin) if r["district_number"]}
    assert {r["district_number"] for r in rows} == want

    debt = DATA / "brb_debt_outstanding.csv"
    if debt.exists():
        ids = {r["district_number"]: r["brb_id"] for r in _rows(debt)
               if r["district_number"].strip()}
        for r in rows:
            if r["brb_id"]:
                assert ids.get(r["district_number"]) == r["brb_id"], r["district_number"]


# --- spending detail: the sixteen function codes -----------------------------

FINANCE = DATA / "texas_finance_clean.csv"

# (artefact key, the column in TEA's own file). Re-listed here on purpose: if
# the builder ever remaps a function to the wrong column, this file still holds
# the right pairing and the test fails.
_FUNCTION_COLUMNS = {
    "instruction": "all_funds_instruction_transfer_expend_fct11_95",
    "transportation": "all_funds_transportation_expenditures_fct34",
    "food": "all_funds_food_service_expenditures_fct35",
    "extracurricular": "all_funds_extracurricular_expenditures_fct36",
    "general_admin": "all_funds_general_administrat_expend_fct41_92",
    "counseling": "all_funds_guidance_counseling_services_exp_fct31",
    "security": "all_funds_security_monitoring_service_expend_fct52",
    "health": "all_funds_health_services_exp_fct33",
}
_OPERATING = "all_funds_total_operating_expenditures_by_obj"


def _finance_year_rows(year: int):
    return [r for r in _rows(FINANCE) if r.get("year") and int(float(r["year"])) == year]


def test_the_statewide_function_shares_are_the_columns_summed():
    """The headline split of the operating dollar, recomputed by hand.

    Counted with the csv module straight off TEA's file. No builder is
    imported, so a builder that sums the wrong column cannot make this pass.
    """
    art = _art("spending_detail.json")
    _need(FINANCE)
    year = art["meta"]["year"]
    rows = _finance_year_rows(year)
    assert rows, f"no rows for fiscal {year} in {FINANCE.name}"

    def total(col):
        return sum(float(r[col]) for r in rows if r.get(col) not in (None, "", "nan"))

    operating = total(_OPERATING)
    for key, col in _FUNCTION_COLUMNS.items():
        published = art["texas"]["functions"][key]["share_of_operating"]
        recomputed = total(col) / operating * 100
        assert abs(published - recomputed) < 0.02, (
            f"{key}: artefact says {published}% of operating, TEA's own file "
            f"says {recomputed:.2f}%")


def test_the_sixteen_functions_sum_to_the_operating_total():
    """The whole layer rests on this identity: a share is only meaningful if
    the parts add to the whole it is a share OF. Checked against the raw file
    rather than against the builder's own reconciliation figure."""
    art = _art("spending_detail.json")
    _need(FINANCE)
    rows = _finance_year_rows(art["meta"]["year"])
    fcols = [c for c in rows[0] if c.startswith("all_funds_") and "fct" in c]
    assert len(fcols) == 16, f"expected 16 function columns, found {len(fcols)}"

    def num(r, c):
        v = r.get(c)
        return float(v) if v not in (None, "", "nan") else 0.0

    parts = sum(sum(num(r, c) for c in fcols) for r in rows)
    operating = sum(num(r, _OPERATING) for r in rows)
    ratio = parts / operating
    assert 0.999 <= ratio <= 1.001, (
        f"the sixteen functions sum to {ratio:.4f} of operating spend; every "
        f"share this layer publishes is taken against that total")


def test_a_district_figure_is_the_districts_own_row():
    """Spot-checks the largest districts end to end — dollars, per-student and
    share — against their own row in TEA's file."""
    art = _art("spending_detail.json")
    _need(FINANCE)
    year = art["meta"]["year"]
    by_num = {r["district_number"]: r for r in _finance_year_rows(year)}
    checked = 0
    for dn in ("057905", "101912", "015907", "227901", "043910"):
        rec = art["districts"].get(dn)
        raw = by_num.get(dn)
        if rec is None or raw is None:
            continue
        students = float(raw["fall_survey_enrollment"])
        operating = float(raw[_OPERATING])
        for key, col in _FUNCTION_COLUMNS.items():
            v = raw.get(col)
            if v in (None, "", "nan") or float(v) == 0:
                assert key not in rec["functions"], (
                    f"{dn} reports nothing for {key} but the artefact "
                    f"publishes a figure — an absence must never become a zero")
                continue
            amount = float(v)
            assert abs(rec["functions"][key]["amount"] - round(amount)) <= 1
            assert abs(rec["functions"][key]["per_student"]
                       - amount / students) < 0.01
            assert abs(rec["functions"][key]["share_of_operating"]
                       - amount / operating * 100) < 0.01
            checked += 1
    assert checked >= 20, f"only {checked} figures checked; the spot-check is too thin"


def test_no_function_absence_was_written_as_a_zero():
    """The refusal that keeps a ranking honest. A district reporting no food
    service usually runs none; publishing a zero would rank every other
    district up and invent a finding about children's meals."""
    art = _art("spending_detail.json")
    for dn, rec in art["districts"].items():
        for key, f in rec["functions"].items():
            assert f["amount"] != 0, (
                f"{dn} publishes {key} as $0 — an absence must be omitted, "
                f"not recorded as spending nothing")


def test_percentiles_rank_only_districts_that_reported():
    """A percentile over all 1,202 districts would score every non-reporter as
    the thriftiest in Texas."""
    art = _art("spending_detail.json")
    floor = art["meta"]["min_students_for_percentile"]
    for dn, rec in art["districts"].items():
        if rec["students"] >= floor:
            continue
        for key, f in rec["functions"].items():
            assert "percentile" not in f, (
                f"{dn} has {rec['students']} students but {key} carries a "
                f"percentile; below {floor} one purchase is an outlier")


def test_the_program_figures_are_the_program_columns_summed():
    """PROGRAM codes are a second cut of the same operating dollar — who the
    money served, rather than what it was spent on. Re-derived from TEA's file
    by hand, like the functions.

    The first draft of the coverage report called special-education spending
    "a different PEIMS product" that this repo did not hold. That was wrong —
    the column is right here — so this test exists partly to keep the claim
    honest in both directions.
    """
    art = _art("spending_detail.json")
    _need(FINANCE)
    rows = _finance_year_rows(art["meta"]["year"])
    cols = {
        "special_ed": "all_funds_students_with_disabilities_pgm_expend_23",
        "bilingual": "all_funds_bilingual_program_exp_25_35",
        "athletics": "all_funds_athletics_program_expend_91",
        "gifted": "all_funds_gifted_talented_program_expend_21",
        "career_tech": "all_funds_career_technology_pgm_expend_22",
    }

    def total(col):
        return sum(float(r[col]) for r in rows if r.get(col) not in (None, "", "nan"))

    enrolled = sum(float(r["fall_survey_enrollment"]) for r in rows
                   if r.get("fall_survey_enrollment") not in (None, "", "nan"))
    for key, col in cols.items():
        published = art["texas"]["programs"][key]["per_student"]
        recomputed = total(col) / enrolled
        assert abs(published - recomputed) < 0.02, (
            f"{key}: artefact says ${published}/student, TEA's file says "
            f"${recomputed:.2f}")


def test_a_program_share_is_never_taken_against_operating_spend():
    """Programme codes do not tile operating spend — code 99 holds what TEA
    does not attribute — so a share against operating would silently understate
    every programme. Shares must be of TEA's own programme total."""
    art = _art("spending_detail.json")
    for dn, rec in art["districts"].items():
        shares = [p["share_of_program_total"] for p in rec.get("programs", {}).values()
                  if p.get("share_of_program_total") is not None]
        if len(shares) < 5:
            continue
        assert sum(shares) <= 100.5, (
            f"{dn}: programme shares sum to {sum(shares):.1f}%, so they are not "
            f"shares of the programme total")
    tx = art["texas"]["programs"]
    assert "undistributed" in tx, (
        "code 99 must be published, or the other programmes look like they "
        "account for the whole dollar when they do not")


PROPERTY = DATA / "tea_property.csv"


def test_the_tax_rates_are_the_comptrollers_own_numbers():
    """Rates recomputed off data/tea_property.csv by hand. The bill is a
    multiplication the reader can redo: rate x $300,000 / 100."""
    art = _art("tax_history.json")
    _need(PROPERTY)
    rows = [r for r in _rows(PROPERTY) if r.get("total_tax_rate") not in (None, "", "nan")]
    by = {}
    for r in rows:
        by.setdefault(r["district_number"], {})[int(float(r["year"]))] = float(r["total_tax_rate"])
    checked = 0
    for dn in ("057905", "101912", "015907", "227901", "043910"):
        rec, raw = art["districts"].get(dn), by.get(dn)
        if not rec or not raw:
            continue
        for i, y in enumerate(rec["series"]["years"]):
            assert abs(rec["series"]["total_rate"][i] - raw[y]) < 0.0001, (
                f"{dn} {y}: artefact {rec['series']['total_rate'][i]}, "
                f"Comptroller {raw[y]}")
            assert rec["series"]["bill_on_fixed_home"][i] == round(
                raw[y] * art["meta"]["home_value"] / 100)
            checked += 1
    assert checked >= 40, f"only {checked} rate-years checked"


def test_the_headline_that_rates_fell_is_true_of_the_rate_file():
    """The finding that makes this layer worth publishing — most districts'
    RATES fell while bills rose — recounted from the source."""
    art = _art("tax_history.json")
    _need(PROPERTY)
    rows = [r for r in _rows(PROPERTY) if r.get("total_tax_rate") not in (None, "", "nan")]
    by = {}
    for r in rows:
        by.setdefault(r["district_number"], []).append(
            (int(float(r["year"])), float(r["total_tax_rate"])))
    fell = 0
    total = 0
    for dn, pairs in by.items():
        if len(pairs) < 2:
            continue
        pairs.sort()
        total += 1
        if pairs[-1][1] < pairs[0][1]:
            fell += 1
    assert total > 900, f"only {total} districts have a rate series"
    assert fell / total > 0.85, (
        f"only {fell}/{total} districts' rates fell; the published reading says "
        f"most of them did")
    published = sum(1 for r in art["districts"].values()
                    if (r["change"]["rate_change_pct"] or 0) < 0)
    assert abs(published - fell) <= 2, (
        f"artefact counts {published} falling rates, the source says {fell}")


def test_a_bill_is_never_presented_as_somebodys_actual_bill():
    """No appraisal roll is involved and exemptions are not modelled, so the
    payload must keep saying so."""
    art = _art("tax_history.json")
    blob = " ".join(art["meta"]["limits"]).lower()
    assert "not anyone's actual bill" in blob
    assert "exemption" in blob
    assert art["meta"]["home_value"] == 300000


def test_every_published_layer_has_a_provenance_test_here_or_upstream():
    """The gap this file was written to close, kept closed.

    A new committed artefact with no re-derivation anywhere is a published
    number that only its own builder vouches for.
    """
    covered = {
        "bond_data.json", "debt_data.json", "campus_data.json",   # this file
        "forensic_data.json", "trend_data.json",                  # test_provenance.py
        "economics_data.json", "outcomes_data.json",              # ditto
        "national_data.json",                                     # test_national.py
        "erate_data.json",                                        # test_erate.py
        "spending_detail.json", "tax_history.json",                # this file
    }
    known_uncovered = {
        # Derived entirely from artefacts already covered above, so a wrong
        # number cannot enter here without failing one of those first.
        "forensic_quality.json", "fallback_index.json", "district_geo.json",
        "map_data.json", "equity_data.json", "takeover_data.json",
        "isd_briefing.json", "source_fingerprint.json", "similarity_graph.json",
    }
    published = {p.name for p in STATIC.glob("*.json")}
    orphans = published - covered - known_uncovered
    assert not orphans, (
        f"published with no re-derivation: {sorted(orphans)}. Add a test here or "
        f"list it as derived from a covered artefact.")
