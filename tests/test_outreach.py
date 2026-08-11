"""The outreach email is a published surface too — the same framing rules that
govern the site govern what lands in a superintendent's inbox, plus the rules
email adds: an unsubscribe that works, a postal address, and rails that make
the accidental mass-send impossible.

These run without a network and without the gitignored merge CSV: the renderer
is a pure function of a row, so the tests hand it rows.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_outreach_merge import greeting_from, hook, insight_bonds, insight_debt, insight_trend  # noqa: E402
from scripts.send_outreach import render_email  # noqa: E402

ROW = {
    "district_number": "061910",
    "district_name": "Argyle ISD",
    "greeting": "Dr. Carpenter",
    "email": "someone@argyleisd.com",
    "deep_link": "https://txisd.dev/?d=061910",
    "hook": hook("Argyle ISD", {"year": 2025, "enrollment": 6114,
                                "all_funds_per_student": 31704,
                                "operating_per_student": 10357,
                                "construction_debt_share_pct": 67}),
    "insight_bonds": "Voters in Argyle ISD have decided 14 bond propositions "
                     "since 1997 and approved 11 of them.",
    "insight_debt": "As of fiscal 2025, Argyle ISD owes $1.2B on bonds "
                    "already sold.",
    "insight_trend": "Instruction's share rose from 53.0% to 56.2%.",
    "subject": "Every number Texas publishes about Argyle ISD",
}
POSTAL = "123 Main St, Suite 1, Dallas TX 75201"
UNSUB = "mailto:hello@txisd.dev?subject=unsubscribe"


def _rendered():
    return render_email(ROW, POSTAL, UNSUB)


# --- frame honesty travels into the inbox -------------------------------------

def test_the_hook_never_gives_all_funds_without_operating():
    """The Argyle rule, applied to the email: at 67% construction share the
    all-funds figure must arrive chained to the operating figure."""
    h = ROW["hook"]
    assert "$31,704" in h and "$10,357" in h
    assert "building them" in h


def test_the_email_carries_the_hook_in_both_parts():
    body, text = _rendered()
    assert "$10,357" in body and "$10,357" in text


def test_low_construction_districts_get_the_operating_frame_only():
    h = hook("Elkhart ISD", {"year": 2025, "enrollment": 1100,
                             "all_funds_per_student": 13284,
                             "operating_per_student": 12000,
                             "construction_debt_share_pct": 10})
    assert "operations" in h and "all-funds" not in h


# --- the greeting never guesses a gendered title ------------------------------

def test_greeting_uses_published_honorific_or_neutral_title():
    assert greeting_from("DR JOE E SATTERWHITE III") == "Dr. Satterwhite"
    assert greeting_from("MR ROB BRIGGS") == "Mr. Briggs"
    assert greeting_from("KRISTIN COOK") == "Superintendent Cook"
    assert greeting_from("") == "Superintendent"


# --- what every email must contain --------------------------------------------

def test_email_contains_deep_link_greeting_and_gift_frame():
    body, text = _rendered()
    for part in (body, text):
        assert "https://txisd.dev/?d=061910" in part
        assert "Dr. Carpenter" in part
    assert "It&rsquo;s yours." in body        # gift first, pitch second
    assert "reply" in text.lower()            # the call invitation


def test_email_carries_unsubscribe_postal_address_and_source_disclosure():
    """CAN-SPAM: physical postal address + a working opt-out. And this project
    adds its own rule: say where the data AND the recipient's address came
    from."""
    body, text = _rendered()
    for part in (body, text):
        assert POSTAL in part
        assert UNSUB in part
    assert "AskTED" in body                   # how we got their address
    assert "/sources" in body                 # how we got the numbers


def test_email_never_uses_the_word_deficit():
    """The word the frame audit banned from mixed comparisons — the email
    doesn't compare frames at all, so it must not appear."""
    body, text = _rendered()
    assert "deficit" not in body.lower() and "deficit" not in text.lower()


def test_corrections_are_invited():
    body, _ = _rendered()
    assert "corrections with credit" in body


def test_email_discloses_ai_and_links_the_transparency_page():
    """The owner's rule: never shy away from it — every communication states
    that AI was used across the whole system, that figures carry a margin of
    error, and links the page that tells the full story."""
    body, text = _rendered()
    for part in (body, text):
        assert "https://txisd.dev/transparency" in part
        assert "margin of" in part
        assert "own risk" in part
    assert "Artificial intelligence" in body


# --- insight sentences state their frame --------------------------------------

def test_debt_insight_names_the_stock_frame():
    s = insight_debt("061910", "Argyle ISD",
                     {"061910": {"total": 1225125606, "per_student": 200380,
                                 "interest_share_pct": 45.3,
                                 "clears_in": 2056}})
    assert "bonds already sold" in s          # the stock, not the flow
    assert "interest not yet paid" in s       # names what the total includes


def test_absent_records_are_reported_as_absences_not_zeros():
    assert "no school bond election" in insight_bonds("999999", "Nowhere ISD", {})
    assert "no outstanding" in insight_debt("999999", "Nowhere ISD", {})
    assert insight_trend("999999", "Nowhere ISD", {},
                         {"instruction_share": {"first": 57.8, "last": 54.5}}) == ""


def test_trend_insight_gives_the_state_line_beside_the_district():
    s = insight_trend("061910", "Argyle ISD",
                      {"061910": {"change": {"instruction_share": {
                          "first": 53.0, "last": 56.2, "change": 3.2,
                          "first_year": 2009, "last_year": 2025}}}},
                      {"instruction_share": {"first": 57.8, "last": 54.5}})
    assert "53.0%" in s and "56.2%" in s      # the district
    assert "57.8%" in s and "54.5%" in s      # the state, for scale


# --- the graphic the email hot-links is really served -------------------------

def test_the_pipeline_graphic_exists_and_has_a_route():
    assert (ROOT / "static" / "tag_pipeline.png").exists()
    api = (ROOT / "src" / "api.py").read_text()
    assert "/static/tag-pipeline.png" in api
