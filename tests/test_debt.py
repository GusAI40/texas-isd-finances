"""Tests for the debt-outstanding layer.

This layer carries two hazards the rest of the site does not.

The first is that it runs into the FUTURE. Rows after the current fiscal year
are the amortisation schedule for debt already sold, not history and not a
forecast. Plotted or summed together with history they would show Texas owing
about twice what it owes. Several tests here exist only to keep the two apart.

The second is the capital-appreciation-bond ratio. "Dollars repaid per dollar
borrowed" is the number that makes this story legible, and computed on an
outstanding balance it is fabricated: as principal retires the denominator
shrinks while accreted interest does not, so the ratio climbs on its own.
Leander ISD reads 4.5x in 2014 and would read 396x in 2030 with no deal having
changed. The ratio is therefore only ever taken at a district's peak year, and
`test_the_repayment_ratio_is_never_taken_on_a_residual_balance` is what stops a
future maintainer from "simplifying" that back to the current year.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.api import app  # noqa: E402

DATA = ROOT / "static" / "debt_data.json"
pytestmark = pytest.mark.skipif(
    not DATA.exists(),
    reason="run scripts/ingest_brb_debt.py then scripts/build_debt_data.py")

CURRENT_FY = 2025


@pytest.fixture(scope="module")
def d():
    return json.loads(DATA.read_text())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- the totals are the sum of their parts --------------------------------

def test_the_statewide_total_is_the_sum_of_its_districts(d):
    t = d["texas"]
    assert t["principal"] + t["interest"] == t["total"]
    for key in ("principal", "interest", "total"):
        summed = sum(r[key] for r in d["districts"].values())
        # rounding per district against rounding on the whole
        assert abs(summed - t[key]) <= len(d["districts"])
    assert t["districts_reporting"] == len(d["districts"])


def test_the_cib_and_cab_split_accounts_for_everything(d):
    t = d["texas"]
    assert t["cib"]["principal"] + t["cab"]["principal_outstanding"] == \
        pytest.approx(t["principal"], abs=2)
    assert t["cib"]["interest"] + t["cab"]["deferred_interest"] == \
        pytest.approx(t["interest"], abs=2)


def test_interest_is_a_real_share_and_is_reported_as_one(d):
    t = d["texas"]
    assert 20 < t["interest_share_pct"] < 60, "implausible interest share"
    assert t["interest_share_pct"] == pytest.approx(
        100 * t["interest"] / t["total"], abs=0.1)


# --- history and schedule must never be mixed ------------------------------

def test_district_history_stops_at_the_current_year(d):
    """A scheduled future balance is not something that happened."""
    for num, r in d["districts"].items():
        years = [y for y, _ in r["history"]]
        assert years == sorted(years), num
        assert max(years) <= CURRENT_FY, f"{num} has history from the future"


def test_the_schedule_starts_after_the_current_year_and_only_falls(d):
    sched = d["texas"]["schedule"]
    assert sched, "no amortisation schedule published"
    assert min(y for y, _ in sched) > CURRENT_FY
    values = [v for _, v in sched]
    assert values == sorted(values, reverse=True), \
        "the schedule rises — that would mean borrowing not yet done"


def test_the_schedule_is_labelled_as_a_floor_not_a_forecast(d):
    limits = " ".join(d["meta"]["limits"]).lower()
    assert "schedule" in limits and "floor" in limits
    assert "not a forecast" in limits


def test_the_payoff_year_is_the_end_of_the_schedule(d):
    assert d["texas"]["clears_in"] == max(y for y, _ in d["texas"]["schedule"])


# --- the ratio that had to be thrown away ----------------------------------

def test_the_repayment_ratio_is_never_taken_on_a_residual_balance(d):
    """The whole point. A ratio may only be quoted at a peak year.

    If a `repaid_per_dollar_borrowed` ever appears outside a `peak` object, some
    later change has started dividing accreted interest by a balance that is
    being paid off, and the site will print a number like 396x about a real
    district that describes nothing.
    """
    blob = json.dumps(d)
    assert blob.count('"repaid_per_dollar_borrowed"') == \
        blob.count('"peak":{"year"') + blob.count('"peak": {"year"'), \
        "a repayment ratio exists outside a peak block"


def test_every_peak_is_in_the_past_and_plausible(d):
    for num, r in d["districts"].items():
        peak = (r.get("cab") or {}).get("peak")
        if not peak:
            continue
        assert 2005 <= peak["year"] <= CURRENT_FY, num
        assert peak["principal"] > 0, num
        assert peak["principal"] >= 5_000_000, f"{num}: ratio on a residual balance"
        # A CAB repaying less than its principal is arithmetically impossible.
        # The upper bound is the artifact detector: Texas capped new CABs at 4:1
        # in 2015 and the worst pre-cap deals reported publicly ran to roughly
        # 10x. Anything past 12x is far likelier to be a nearly-retired balance
        # inflating its own ratio than a deal anyone actually signed.
        assert 1.0 < peak["repaid_per_dollar_borrowed"] < 12, num


def test_a_district_with_a_gap_in_its_record_gets_no_ratio(d):
    """Ysleta ISD reports CAB balances for 2005-2012 and again from 2020, with
    nothing between. Its largest REPORTED total is 2020, which reads as 11.3x —
    in a year after Texas capped new capital appreciation bonds at 4:1, so no
    such deal could have been signed. The peak is inside the missing years, and
    a discontinuous series must therefore publish no ratio at all."""
    ysleta = next((r for r in d["districts"].values()
                   if r["district_name"].upper().startswith("YSLETA")), None)
    if ysleta and ysleta.get("cab"):
        assert ysleta["cab"]["peak"] is None, \
            "a ratio was published from a series with a seven-year hole in it"
        assert ysleta["cab"]["deferred_interest"] > 0, \
            "the debt itself is known and must still be reported"


def test_the_leander_peak_matches_the_documented_deal(d):
    """The worked example in the builder's docstring, asserted.

    If this drifts, either the source restated or someone changed how the peak
    is picked, and the docstring that explains the whole restraint is now lying.
    """
    leander = next(r for r in d["texas"]["cab"]["largest"]
                   if r["district_name"].upper().startswith("LEANDER"))
    peak = leander["peak"]
    assert peak["year"] == 2014
    assert peak["repaid_per_dollar_borrowed"] == pytest.approx(4.48, abs=0.02)
    assert peak["repaid_per_dollar_borrowed"] < 5, \
        "the residual-balance ratio (20x in 2025) has leaked back in"


# --- restraint --------------------------------------------------------------

def test_nothing_here_alleges_wrongdoing(d):
    banned = ("fraud", "corrupt", "illegal", "criminal", "reckless",
              "embezzl", "misappropriat", "scandal")
    blob = json.dumps(d).lower()
    for w in banned:
        assert w not in blob, f"the debt layer says '{w}'"


def test_the_layer_states_that_borrowing_is_lawful(d):
    note = d["meta"]["what_this_is_not"].lower()
    assert note.startswith("none of")
    assert "lawful" in note and "ballot" in note


def test_the_limits_name_what_is_excluded(d):
    limits = " ".join(d["meta"]["limits"]).lower()
    assert "commercial paper" in limits
    assert "attorney general" in limits
    assert "operating" in limits, "must say this is not comparable to a budget"


# --- the join ---------------------------------------------------------------

def test_no_district_number_appears_twice(d):
    """The Board lists three issuers under two names each, including one id
    serving identical data under two different county labels. Deduplicating by
    name instead of by id would have added $406m of one district's debt to the
    statewide total a second time."""
    nums = list(d["districts"])
    assert len(nums) == len(set(nums))
    for n in nums:
        assert len(n) == 6 and n.isdigit(), n


def test_per_student_figures_are_plausible(d):
    """A wide bound on purpose: this catches a decimal slip or a collapsed join,
    not an unusual district.

    Sands CISD really does owe $601,000 per student — 229 students in the
    Permian Basin sitting on enough oil-and-gas property value to service $138m
    of debt. It is a genuine outlier, not a bad match, so the bound is set to
    catch errors of magnitude rather than to make the distribution look tidy.
    """
    for num, r in d["districts"].items():
        if r["per_student"] is None:
            continue
        assert 0 < r["per_student"] < 2_000_000, f"{num} {r['district_name']}"


def test_the_historically_mis_joined_names_are_still_right(d):
    """Sands CISD (Dawson) and S and S CISD (Grayson) both squash to SANDSCISD,
    and one collected the other's records before county resolution was added.
    Sands is now also the largest per-student debt in Texas, so a regression
    here would put a spectacular number on the wrong district."""
    sands = d["districts"]["058909"]
    assert sands["district_name"].upper().startswith("SANDS")
    assert sands["students"] and sands["students"] < 500
    ss = d["districts"].get("091914")
    if ss:
        assert "S AND S" in ss["district_name"].upper()


# --- the endpoints ----------------------------------------------------------

def test_the_statewide_endpoint_serves_the_layer(client):
    body = client.get("/debt/texas").json()
    assert {"meta", "principal", "interest", "total", "cab", "schedule",
            "clears_in"} <= set(body)
    assert body["meta"]["limits"]


def test_a_district_endpoint_serves_one_district(client):
    body = client.get("/district/057905/debt").json()          # Dallas ISD
    assert body["district_number"] == "057905"
    assert body["total"] > 0 and body["history"]
    assert body["clears_in"] > CURRENT_FY


def test_a_district_with_no_bonded_debt_gets_a_finding_not_a_blank(client):
    """Owing nothing is the strongest version of this section, and it used to be
    the one most likely to render as an empty box."""
    body = client.get("/district/999999/debt").json()
    a = body["absence"]
    assert a["kind"] == "did_not_happen" and a["is_finding"] is True
    assert "no outstanding bonded debt" in a["sentence"].lower()


def test_the_endpoints_need_no_database(client):
    import src.api as api
    saved, api.app.state.db_pool = getattr(api.app.state, "db_pool", None), None
    try:
        assert client.get("/debt/texas").status_code == 200
        assert client.get("/district/057905/debt").status_code == 200
    finally:
        api.app.state.db_pool = saved
