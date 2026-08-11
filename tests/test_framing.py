"""A correct number in the wrong frame is still a lie. These tests audit frames.

Everything else in this suite proves numbers DERIVE correctly from the state's
files. None of it could catch the bug a reader found on Argyle ISD's card:
every figure was perfectly derived, and the card said "Deficit — revenue
$63.9M vs spending $193.8M" about a district whose operations ran a $532k
surplus. The $130M gap was voter-approved school construction. Operating
revenue had been compared against ALL money out the door, and by that frame
571 districts — 48% of Texas — were branded with deficits they did not have.

Derivation tests cannot see this, because the frame is chosen in the
presentation layer. So these tests read the presentation layer and assert the
framing rules directly:

  1. An operating balance compares operating with operating, never operating
     with all-funds.
  2. Any all-funds figure shown per student names what it includes wherever
     construction and debt are a material share.
  3. A change flag on all-funds spending says what usually causes one — a bond
     construction cycle — instead of presenting itself as a bare red mark.
  4. The word "Deficit" never renders from a mixed-frame comparison.

They are deliberately string-level assertions on the shipped HTML/SQL: crude,
but the failure mode is a sentence, so the test has to read sentences.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INDEX = (ROOT / "static" / "index.html").read_text()
SQL = (ROOT / "sql" / "create_tables.sql").read_text()


# --- the view carries both frames, so the page can compare like with like ----

def test_the_summary_view_exposes_operating_spend():
    """Without this column the page physically cannot draw an operating
    balance, and the only comparison available is the misleading one."""
    assert re.search(r"all_funds_total_operating_expenditures_by_obj\s+AS\s+operating_spend",
                     SQL), "v_finance_summary no longer exposes operating_spend"


# --- rule 1: operating vs operating ------------------------------------------

def test_the_balance_card_compares_operating_with_operating():
    assert "function balanceCard" in INDEX
    body = INDEX.split("function balanceCard", 1)[1].split("\nfunction ", 1)[0]
    assert "operating_spend" in body, "the balance card no longer uses operating spend"
    assert "Operating balance" in body


def test_the_old_mixed_frame_deficit_sentence_is_gone():
    """The exact sentence a reader disproved: operating revenue labelled
    'Revenue' against total disbursements labelled 'spending', concluding
    'Deficit'. If this reappears, 571 districts get their false deficits back."""
    assert not re.search(
        r"total_revenue\s*>=\s*cur\.total_spend\s*\?\s*'Surplus'\s*:\s*'Deficit'",
        INDEX), "the mixed-frame Surplus/Deficit comparison is back"


def test_deficit_is_never_concluded_from_total_spend():
    """'Deficit' may only ever be computed against operating_spend, and the
    fallback path (column missing) must not use the word at all.

    Checked with a 400-character window around each occurrence rather than the
    single line: the ternary that decides Surplus/Deficit and the comparison
    that justifies it are legitimately on different lines, and the first
    version of this test failed its own correct code for that reason.
    """
    for m in re.finditer(r"'Deficit'", INDEX):
        window = INDEX[max(0, m.start() - 400):m.start()]
        assert "operating_spend" in window, (
            f"'Deficit' concluded without an operating frame near: "
            f"{INDEX[m.start() - 80:m.start() + 40]!r}")


# --- rule 2: all-funds per-student figures name what they include -------------

def test_the_spend_card_names_the_operating_figure():
    assert "function opsPerStudentNote" in INDEX
    body = INDEX.split("function opsPerStudentNote", 1)[1].split("\nfunction ", 1)[0]
    assert "construction" in body and "operations run" in body


def test_the_statewide_rank_names_its_frame():
    assert "counting construction & debt" in INDEX, (
        "the percentile card ranks on all-funds and must say so")


def test_the_reporter_lens_gives_both_frames():
    """The lens written for people who publish. It must never hand a reporter
    the all-funds figure without the operating figure beside it."""
    press = INDEX.split("case 'press':", 1)[1].split("default:", 1)[0]
    assert "all funds" in press
    assert "operating" in press
    assert "construction" in press


# --- rule 3: a change flag explains its usual cause ---------------------------

def test_the_spend_spike_flag_mentions_construction():
    flag = re.search(r"spend_spike_flag:\s*\[[^\]]+", INDEX)
    assert flag, "spend spike flag copy not found"
    assert "construction" in flag.group(0), (
        "an all-funds spike flag must say it is usually a bond construction "
        "year, or every growing district reads as a scandal")
    assert "All-funds" in flag.group(0)


def test_flags_are_not_called_anomalies_in_the_press_lens():
    press = INDEX.split("case 'press':", 1)[1].split("default:", 1)[0]
    assert "anomaly flags" not in press, (
        "the press lens hands 'anomaly' straight to a headline; call them "
        "change flags and say what causes them")
    assert "not an accusation" in press


# --- the blast radius stays documented ---------------------------------------

def test_the_view_comment_records_why_operating_spend_exists():
    """The comment in the SQL is the institutional memory: remove the column
    and the next maintainer re-creates the bug with no idea it ever happened."""
    idx = SQL.find("AS operating_spend")
    assert idx > -1
    context = SQL[max(0, idx - 700):idx]
    assert "Argyle" in context, "the worked example was removed from the view comment"


def test_the_deep_link_hero_does_not_lead_with_an_unqualified_all_funds_figure():
    """The headline a shared link opens on. It said "spends $31,704 per
    student" about Argyle with no qualifier — the exact sentence the forensic
    audit corrected on the cards below it."""
    body = INDEX.split("function renderWelcomeFor", 1)[1].split("\nfunction ", 1)[0]
    assert "nonOpShare" in body and "operating_spend" in body, (
        "the hero no longer checks the construction share before leading with "
        "the all-funds figure")
    assert "building them" in body
