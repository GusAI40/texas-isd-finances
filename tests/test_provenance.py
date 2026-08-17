"""Every published headline, recomputed from the SOURCE, not from the artifact.

The gap this closes
-------------------
The other tests assert that a payload is internally consistent: that a headline
matches the series in the same file. That catches a rendering bug and misses a
build bug entirely, because a wrong number validates itself. If
`build_trend_data.py` divided by the wrong denominator, every other test would
still pass and every figure would still be wrong.

These go back to the state's own file and recompute each published figure
independently, with the arithmetic written out longhand here rather than by
calling the builder. Duplicated arithmetic is the feature: a disagreement means
one of the two is wrong, and both are then worth reading.

Chain of custody
----------------
    TEA file -> texas_finance_clean.csv -> tests/fixtures/provenance.json
             -> static/*.json -> the page

- The CSV is 18 MB and deliberately not committed, so the fixture carries the
  per-year statewide sums (26 KB) plus a SHA-256 of the CSV it came from. That
  is what makes this hold **in CI**, where the source is absent — a guarantee
  that only runs on one laptop is not a guarantee.
- `test_the_fixture_still_matches_the_source` is the one test that needs the
  real CSV, and it checks the hash. Everything else runs off the fixture, in
  plain Python, with no pandas.
- `test_the_committed_artifacts_match_a_fresh_build` closes the last link by
  rebuilding every artifact and diffing it against what is committed.

What this can and cannot establish
----------------------------------
It establishes **faithfulness to source**: what is published is what the state
reported. It cannot establish that TEA is right, that a district filed
correctly, or that fiscal 2025 will not be restated. Those limits are real and
are published on the site rather than hidden here.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "data" / "texas_finance_clean.csv"
FIXTURE = ROOT / "tests" / "fixtures" / "provenance.json"
STATIC = ROOT / "static"
FIRST, LAST = 2009, 2025


@pytest.fixture(scope="module")
def fx():
    assert FIXTURE.exists(), "run scripts/build_provenance_fixture.py"
    d = json.loads(FIXTURE.read_text())
    return {"meta": d["meta"],
            "years": {r["year"]: r for r in d["years"]},
            "functions": {int(k): v for k, v in d["functions"].items()},
            "panel": d["balanced_panel"]}


@pytest.fixture(scope="module")
def trends():
    return json.loads((STATIC / "trend_data.json").read_text())


@pytest.fixture(scope="module")
def forensic():
    return json.loads((STATIC / "forensic_data.json").read_text())


@pytest.fixture(scope="module")
def econ():
    return json.loads((STATIC / "economics_data.json").read_text())


def deflator(econ):
    """The CPI-U factors the site uses, read from the one layer that defines
    the price base. If this ever disagreed with the trend layer the two would
    be on different bases and nothing would line up."""
    return {int(r["year"]): r["spend_per_student_real"] / r["spend_per_student_nominal"]
            for r in econ["macro"]["spending"] if r.get("spend_per_student_nominal")}


# --- the fixture is the source ----------------------------------------------

def test_the_fixture_still_matches_the_source(fx):
    """The one test that needs the real CSV. Everything else trusts the
    fixture, so the fixture has to be provably the source."""
    import hashlib
    if not SOURCE.exists():
        pytest.skip("source CSV not present (18 MB, deliberately not committed)")
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == fx["meta"]["source_sha256"], \
        "the source CSV changed — re-run scripts/build_provenance_fixture.py"


def test_the_fixture_covers_the_published_window(fx):
    assert set(fx["years"]) == set(range(FIRST, LAST + 1))
    assert fx["meta"]["rows"] > 20000 and fx["meta"]["districts"] > 1300


# --- the six trend headlines ------------------------------------------------

def test_instruction_share_recomputes_from_source(fx, trends):
    """57.8% -> 54.5%. The most-quoted number on the site."""
    pub = trends["statewide"]["change"]["instruction_share"]
    for year, want in ((FIRST, pub["first"]), (LAST, pub["last"])):
        y = fx["years"][year]
        assert round(y["instruction"] / y["operating"] * 100, 1) == want, year


def test_debt_per_student_recomputes_from_source(fx, trends, econ):
    """$1,507 -> $2,441 in constant 2024 dollars."""
    defl, pub = deflator(econ), trends["statewide"]["change"]["debt_ps"]
    for year, want in ((FIRST, pub["first"]), (LAST, pub["last"])):
        y = fx["years"][year]
        got = y["debt_service"] / y["enrollment"] * defl[year]
        assert abs(round(got) - want) <= 1, f"{year}: {got:.0f} vs {want}"


def test_security_per_student_recomputes_from_source(fx, trends, econ):
    """$96 -> $232, the 2.4x behind the security headline."""
    defl, pub = deflator(econ), trends["statewide"]["change"]["security_ps"]
    for year, want in ((FIRST, pub["first"]), (LAST, pub["last"])):
        y = fx["years"][year]
        got = y["security"] / y["enrollment"] * defl[year]
        assert abs(round(got) - want) <= 1, f"{year}: {got:.0f} vs {want}"


def test_the_federal_peak_year_is_the_real_peak(fx, trends, econ):
    """The cliff headline names a year. If the peak moved, the sentence is wrong."""
    defl = deflator(econ)
    per_year = {y: r["federal_revenue"] / r["enrollment"] * defl[y]
                for y, r in fx["years"].items()}
    peak = max(per_year, key=per_year.get)
    finding = next(f for f in trends["findings"] if f["key"] == "federal_cliff")
    assert str(peak) in finding["figure"], f"the real peak is {peak}"


def test_the_operating_deficit_uses_operating_revenue_only(fx, trends):
    """The definition that moved this answer by 30 points.

    Operating revenue against operating spending. `all_funds_other_revenue`
    tracks debt service almost exactly — it IS the I&S debt levy — so counting
    it as operating revenue while excluding debt service from operating cost
    understates deficits badly. This asserts the number AND the reason.
    """
    pub = trends["statewide"]["deficit_by_year"][-1]
    y = fx["years"][LAST]
    assert pub["year"] == LAST
    assert abs(y["districts_in_operating_deficit"] - pub["in_deficit"]) <= 1
    assert abs(round(y["districts_in_operating_deficit"] / y["districts"] * 100, 1)
               - pub["pct"]) <= 0.2
    for year, r in fx["years"].items():
        ratio = r["other_revenue"] / r["debt_service"]
        assert 0.9 <= ratio <= 1.15, (
            f"{year}: other_revenue/debt_service = {ratio:.2f}; it no longer "
            "tracks the debt levy, so re-check the operating-balance definition")


def test_the_statewide_balance_really_did_flip_in_2025(fx, trends):
    """The headline claims a FIRST. Every earlier year must be positive."""
    margins = {y: r["operating_revenue"] - r["operating"] for y, r in fx["years"].items()}
    assert margins[LAST] < 0, "2025 is not negative; the 'first time' claim is wrong"
    assert all(v > 0 for y, v in margins.items() if y < LAST), \
        "an earlier year was also negative; it is not a first"
    pub = trends["statewide"]["deficit_by_year"][-1]["statewide_margin"]
    assert abs(margins[LAST] - pub) / abs(margins[LAST]) < 0.001


def test_enrollment_figures_recompute(fx, trends):
    pub = trends["statewide"]["series"]["enrollment"]
    assert abs(fx["years"][FIRST]["enrollment"] - pub[0]) <= 1
    assert abs(fx["years"][LAST]["enrollment"] - pub[-1]) <= 1


def test_the_balanced_panel_agrees(fx, trends):
    """A trend that only exists because the roster changed is not a trend."""
    rows = {r["year"]: r for r in fx["panel"]["years"]}
    change = (rows[LAST]["instruction"] / rows[LAST]["operating"] * 100
              - rows[FIRST]["instruction"] / rows[FIRST]["operating"] * 100)
    pub = trends["meta"]["balanced_panel_check"]
    assert fx["panel"]["districts"] == pub["districts"]
    assert abs(round(change, 1) - pub["instruction_share_panel"]) <= 0.15


# --- the reclassification verdict -------------------------------------------

def test_the_function_taxonomy_is_closed(fx, trends):
    """Every published function share depends on the parts summing to the whole.
    If TEA adds a function code and the sum stops matching, every share on the
    site is quietly wrong."""
    for year, funcs in fx["functions"].items():
        parts = sum(funcs.values())
        op = fx["years"][year]["operating"]
        assert parts / op > 0.999, f"{year}: functions sum to {parts / op:.4f} of operating"
    assert trends["meta"]["reclassification_check"]["functions"] == len(
        next(iter(fx["functions"].values())))


def test_no_single_function_absorbs_the_instruction_decline(fx, trends):
    """This is what separates reallocation from a recoding, and it is the
    evidence behind retiring the caveat. Recomputed here from the raw function
    sums rather than taken from the builder's own verdict."""
    def shares(year):
        f = fx["functions"][year]
        tot = sum(f.values())
        return {k: v / tot * 100 for k, v in f.items()}

    a, b = shares(FIRST), shares(LAST)
    moves = {k: b[k] - a[k] for k in a}
    inst = next(k for k in moves if "instruction_transfer" in k)
    risers = {k: v for k, v in moves.items() if v > 0}
    assert moves[inst] < 0
    assert abs(sum(moves.values())) < 0.01, "risers and fallers no longer cancel"
    assert max(risers.values()) < abs(moves[inst]) / 2, \
        "one function now absorbs most of the decline — re-open the caveat"
    check = trends["meta"]["reclassification_check"]
    assert check["verdict"] == "reallocation"
    assert abs(check["largest_single_riser_pts"] - max(risers.values())) < 0.02


def test_the_decline_predates_covid(fx, trends):
    """A decline that only exists in the pandemic years is a pandemic story,
    not a seventeen-year one."""
    def share(year):
        y = fx["years"][year]
        return y["instruction"] / y["operating"] * 100

    assert share(2019) < share(FIRST), "no decline before COVID"
    assert share(LAST) < share(2022), "no decline after the federal cliff"
    check = trends["meta"]["reclassification_check"]
    assert check["instruction_change_pre_covid_pts"] < 0
    assert check["instruction_change_post_cliff_pts"] < 0


# --- window robustness ------------------------------------------------------

def test_the_finding_holds_on_every_window(trends):
    """Would a shorter window be more accurate? No — and all three windows
    agreeing in direction IS the robustness result. If they ever disagreed,
    that would be the finding and the page would have to say so."""
    checks = trends["meta"]["window_checks"]
    assert len(checks) >= 3
    for c in checks:
        assert c["instruction_share_change"] < 0, \
            f"{c['first_year']}-{c['last_year']} disagrees with the headline"
        assert abs(c["instruction_share_change"]
                   - c["instruction_share_change_balanced"]) < 0.5, c


def test_shorter_windows_have_fuller_panels(trends):
    """States the trade-off in data rather than prose: a shorter window buys
    completeness and costs finding strength."""
    checks = sorted(trends["meta"]["window_checks"], key=lambda c: -c["years"])
    pcts = [c["complete_panel_pct"] for c in checks]
    assert pcts == sorted(pcts), "shorter windows should have fuller panels"
    assert checks[0]["complete_panel_pct"] > 80


def test_window_checks_recompute_from_source(fx, trends):
    ten = next(c for c in trends["meta"]["window_checks"] if c["first_year"] == 2016)

    def share(year):
        y = fx["years"][year]
        return y["instruction"] / y["operating"] * 100

    got = round(share(LAST) - share(2016), 2)
    assert abs(got - ten["instruction_share_change"]) < 0.02, \
        f"{got} vs published {ten['instruction_share_change']}"


# --- the forensic headline --------------------------------------------------

def test_statewide_debt_total_recomputes_from_source(fx, forensic):
    """$13.9B a year, the lead figure on /forensics."""
    got = fx["years"][LAST]["debt_service"]
    pub = forensic["statewide"]["debt_total"]
    # The forensic layer sums per-student x students, which rounds per
    # district; 0.5% leaves room for that and nothing else.
    assert abs(got - pub) / got < 0.005, f"{got:,.0f} vs {pub:,.0f}"


def test_district_and_student_counts_agree(fx, forensic):
    y = fx["years"][LAST]
    assert abs(y["districts"] - forensic["statewide"]["districts"]) <= 2
    students = sum(r["students"] or 0 for r in forensic["table"])
    assert abs(y["enrollment"] - students) / y["enrollment"] < 0.001


def test_the_front_page_headline_recomputes_from_the_fixture(fx, econ):
    """"Public schools spent $109.4 billion" — the first number on the site,
    anchored to the SHA-hashed fixture so the guarantee holds in CI.

    The fixture sums over districts reporting enrollment; the published
    lineage additionally requires disbursements > 0. For every year on record
    those two filters admit the same districts, so the sums are asserted EQUAL
    — if a future TEA release ever ships a reporting district with zero
    disbursements, this fires and a human decides which filter the headline
    should state, rather than the difference shipping silently.
    """
    lin = econ["meta"]["lineage_statewide"]
    y = fx["years"][lin["fiscal_year"]]
    figs = lin["figures"]
    # <= 1: the fixture and the builder both use pandas but sum different row
    # partitions (fillna vs a filtered frame), and pairwise float summation at
    # $1e11 can land a rounded dollar apart. Larger than that is a real
    # disagreement between the fixture and the published headline.
    assert abs(round(y["total_disbursements"])
               - figs["statewide_total_spend"]["value"]) <= 1
    assert y["districts"] == lin["districts"]
    assert abs(round(y["total_disbursements"] / y["enrollment"])
               - figs["statewide_spend_per_student"]["value"]) <= 1


# --- the last link ----------------------------------------------------------

def test_the_committed_artifacts_match_a_fresh_build():
    """A stale artifact passes every other test in this repo, because every
    other test reads the artifact. This is the only check that catches a
    builder edited and never re-run, or an upstream restatement."""
    if not SOURCE.exists():
        pytest.skip("rebuilding needs the source CSV")
    r = subprocess.run([sys.executable, "scripts/verify_artifacts.py"],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, f"artifacts have drifted from source:\n{r.stdout}"


# --- a spot check that a district's numbers are its own ---------------------

@pytest.mark.parametrize("num", ["057905", "101912", "043914", "015915"])
def test_a_districts_own_figures_come_from_its_own_rows(econ, num):
    """Sampled across the collision-prone names: 043914 and 015915 are one half
    each of a shared-name pair, and a join error would land exactly here."""
    pd = pytest.importorskip("pandas")
    if not SOURCE.exists():
        pytest.skip("per-district check needs the source CSV")
    d = pd.read_csv(SOURCE, dtype={"district_number": str}, low_memory=False)
    row = d[(d.district_number == num) & (d.year == LAST)]
    assert len(row) == 1, f"{num} does not have exactly one {LAST} row"
    rec = econ["districts"].get(num)
    assert rec, f"{num} missing from economics"
    enr = pd.to_numeric(row["fall_survey_enrollment"], errors="coerce").iloc[0]
    assert abs(int(enr) - rec["students"]) <= 1
    debt = pd.to_numeric(row["all_funds_total_debt_service_expend_by_obj"],
                         errors="coerce").fillna(0).iloc[0]
    assert abs(debt / enr - rec["allocation"]["debt_per_student"]) <= 1.5
