"""The model's prose, checked against what this site publishes.

Behind this file is a real failure. On 2026-08-23 a probe of twenty live
questions found `/query` answering `operating_spend` with `total_spend` four
times out of four — Tioga ISD 2014 came back as $5,603,166 against a true
$3,205,610, a 75% overstatement, with two answers volunteering "that is the
district's all-funds total disbursements" without noticing that was the wrong
figure.

Nothing in the running system noticed. SQLGlot checked the query's shape, the
role was least-privilege, the transaction was read-only and timeout-bounded,
and the answer was wrong anyway. It took a hand-built probe, run once, by
somebody who already suspected something.

These tests hold the checker to the properties that make it trustworthy rather
than merely present: it catches the failure it was built for, it never claims
to have checked something it did not, and it cannot fail the request it was
added to protect.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import answer  # noqa: E402
from src import answer_check as ac  # noqa: E402

DALLAS = "057905"


def _published(path):
    return ac._published(path, DALLAS)


def test_it_catches_the_bug_it_was_built_for():
    """The exact shape of the shipped defect: a plausible sentence carrying the
    wrong column's number."""
    true_operating = _published(("economics", "allocation",
                                 "operating_per_student"))
    wrong = true_operating * 1.75
    r = ac.check(f"Dallas ISD spent ${wrong:,.0f} per student on operations "
                 f"in fiscal 2025.", DALLAS)
    assert r["verdict"] == ac.DISAGREES
    assert any(c["metric"] == "operating_per_student" for c in r["checks"])


def test_it_agrees_with_the_published_figure():
    v = _published(("economics", "allocation", "operating_per_student"))
    r = ac.check(f"Dallas ISD spent ${v:,.0f} per student on operations.",
                 DALLAS)
    assert r["verdict"] == ac.AGREES


def test_prose_the_checker_cannot_read_is_unchecked_not_agreed():
    """The distinction that keeps the badge meaningful. `agrees` is a claim
    that something was compared; most sentences contain a number nobody can
    check, and calling those agreement is how a verifier becomes decoration."""
    r = ac.check("Dallas ISD is one of the largest districts in Texas.", DALLAS)
    assert r["verdict"] == ac.UNCHECKED
    assert r["checks"] == []
    assert "not the same as correct" in r["note"]


def test_no_district_is_unchecked_not_agreed():
    assert ac.check("Some districts spend $30,000 per student.", None)["verdict"] \
        == ac.UNCHECKED


def test_a_legitimate_difference_of_basis_is_not_called_wrong():
    """The finance view is all-funds INCLUDING construction; the economics
    artefact is operating plus debt. Both are right about different questions,
    and a checker that called one wrong would make the site quietly
    inconsistent with itself."""
    econ_total = _published(("economics", "allocation", "total_per_student"))
    bigger = econ_total * 1.3          # what the all-funds view would report
    r = ac.check(f"Dallas ISD spent ${bigger:,.0f} per student in total across "
                 f"all funds.", DALLAS)
    assert r["verdict"] == ac.DIFFERENT_BASIS
    assert "different questions" in r["note"]


def test_a_per_student_metric_needs_the_words_per_student():
    """Without this, a whole-dollar total in the same sentence is compared
    against a per-pupil figure and every answer 'disagrees'."""
    r = ac.check("Dallas ISD's total operating expenditure was $1,986,000,000.",
                 DALLAS)
    assert r["verdict"] == ac.UNCHECKED


def test_rounding_is_not_a_disagreement():
    """The DB view does integer division, so a per-student figure can differ by
    a dollar from the artefact's float. A dollar is rounding."""
    v = _published(("economics", "allocation", "operating_per_student"))
    for delta in (-1, 0, 1):
        r = ac.check(f"Dallas ISD spent ${v + delta:,.0f} per student on "
                     f"operations.", DALLAS)
        assert r["verdict"] == ac.AGREES, f"a ${delta} difference was called wrong"


def test_a_wrong_column_is_not_rounding():
    v = _published(("economics", "allocation", "operating_per_student"))
    r = ac.check(f"Dallas ISD spent ${v * 1.10:,.0f} per student on operations.",
                 DALLAS)
    assert r["verdict"] == ac.DISAGREES


def test_it_reads_millions_and_billions_the_way_a_model_writes_them():
    got = dict(ac.numbers_with_context("about $2.4 million and $1.1 billion"))
    assert 2_400_000.0 in got
    assert 1_100_000_000.0 in got


def test_the_checker_can_never_fail_the_answer():
    """A verifier that raises is a new outage, not a safeguard."""
    for bad in (None, "", "\x00\x00", "$" * 5000, "1,2,3,4,5" * 400):
        r = ac.check(bad, DALLAS)
        assert r["verdict"] in (ac.AGREES, ac.DISAGREES, ac.DIFFERENT_BASIS,
                               ac.UNCHECKED)
    assert ac.check("$14,210 per student", "999999")["verdict"] == ac.UNCHECKED


def test_it_never_rewrites_the_answer():
    """It annotates. A verifier that edits prose is a second author, and the
    second author is unreviewable."""
    text = "Dallas ISD spent $1 per student on operations."
    before = text
    ac.check(text, DALLAS)
    assert text == before
    import ast
    src = (ROOT / "src" / "answer_check.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "check":
            code = ast.unparse(node)
            assert "replace(" not in code, "check() must not rewrite prose"


def test_the_structured_answer_carries_the_verdict():
    """The point of the node is that a reader sees it. A checker whose result
    never leaves the function is a checker nobody acts on."""
    v = _published(("economics", "allocation", "operating_per_student"))
    built = answer.build(
        "How much does Dallas ISD spend per student?",
        f"Dallas ISD spent ${v:,.0f} per student on operations in 2025.",
        district_number=DALLAS)
    assert "verification" in built
    assert built["verification"]["verdict"] == ac.AGREES


def test_structuring_still_survives_a_checker_failure(monkeypatch):
    """A failure to verify must never lose the answer."""
    monkeypatch.setattr(ac, "_CHECKS", None)     # make the loop raise
    r = ac.check("Dallas ISD spent $14,210 per student on operations.", DALLAS)
    assert r["verdict"] == ac.UNCHECKED
    assert "not wrong" in r["note"]
