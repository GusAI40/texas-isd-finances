"""The answer contract — what /query returns and what the sheet may draw.

The defect this whole layer exists to fix was invisible in a passing suite: the
API returned one string of the model's prose and the sheet printed it with
textContent, so readers saw `**bold**` and `| pipes |` as punctuation. That
looked like a missing Markdown renderer. It was presentation delegated to the
model.

So these tests do not check that Markdown "works". They check the boundary:

  * the model's prose becomes DATA (typed blocks, inline runs) and never markup;
  * the figures and the ranking come from the committed artefacts, so a model
    that hallucinates a number cannot get it into a metric card or a table;
  * every follow-up is a question this product can actually answer;
  * the composed total still gets no division lineage, because there is no
    division behind it.

The ten questions in REGRESSION are the ones a reader actually asks. They are
run through classification and follow-up generation so a change to the
patterns cannot silently make "how much does X spend" stop being a spending
question.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import answer

ROOT = Path(__file__).resolve().parent.parent
ECON = ROOT / "static" / "economics_data.json"

# One district that is certainly in the artefact, used wherever a real
# district is needed. Dallas ISD — the leading zero matters.
DALLAS = "057905"


# --------------------------------------------------------------------------
# the ten questions
# --------------------------------------------------------------------------

REGRESSION: list[tuple[str, str]] = [
    ("How much does Dallas ISD spend per student?", "spending"),
    ("Which district spends the most per student?", "ranking"),
    ("Compare Plano ISD and Frisco ISD", "comparison"),
    ("Which districts are most comparable to Argyle ISD?", "peer"),
    ("How has Houston ISD's budget changed since 2009?", "trend"),
    ("How much debt does Katy ISD owe?", "debt"),
    ("What bonds have voters approved in Leander ISD?", "bond"),
    ("How many students attend Austin ISD?", "enrollment"),
    ("Is Highland Park ISD spending too much on administration?", "diagnostic"),
    ("How many school districts are in Texas?", "fact"),
]


@pytest.mark.parametrize("question,kind", REGRESSION)
def test_each_question_gets_the_shape_it_deserves(question, kind):
    assert answer.classify(question) == kind


@pytest.mark.parametrize("question,kind", REGRESSION)
def test_every_follow_up_is_a_question_this_product_can_answer(question, kind):
    ups = answer.follow_ups(kind, "Dallas ISD", question)
    assert 3 <= len(ups) <= 4, f"{kind}: {len(ups)} suggestions"
    for f in ups:
        assert f["question"].endswith("?")
        assert len(f["label"]) <= 26, f["label"]        # it has to fit a chip
        assert "{d}" not in f["question"]               # the template filled in
        # a suggestion that names no subject is the generic one this replaced
        assert f["question"] != f["label"]


def test_a_follow_up_never_asks_back_what_was_just_asked():
    asked = "How much does Dallas ISD spend per student?"
    ups = answer.follow_ups("spending", "Dallas ISD", asked)
    for f in ups:
        assert f["question"] != asked
    assert not any("spend per student" in f["question"].lower() for f in ups)


def test_follow_ups_carry_the_district_in_context():
    ups = answer.follow_ups("debt", "Katy ISD", "How much debt does Katy ISD owe?")
    assert all("Katy ISD" in f["question"] for f in ups)
    # and degrade to something still answerable with no district in context
    ups = answer.follow_ups("debt", None, "How much debt is there?")
    assert all("this district" in f["question"] for f in ups)


# --------------------------------------------------------------------------
# prose -> data
# --------------------------------------------------------------------------

SAMPLE = """Dallas ISD spent **$23,420 per student** in fiscal 2024.

### How that compares

| District | Spend/Student |
|---|---|
| Dallas ISD | $23,420 |
| Houston ISD | $12,910 |

The gap is driven by:
- debt service, which sits outside the operating total
- capital projects in the same year
"""


def test_the_models_prose_becomes_typed_blocks_not_markup():
    got = answer.blocks(SAMPLE)
    assert [b["type"] for b in got] == ["paragraph", "heading", "table", "paragraph", "list"]
    assert got[1]["text"] == "How that compares"
    assert got[2]["head"] == ["District", "Spend/Student"]
    assert len(got[2]["rows"]) == 2
    assert len(got[4]["items"]) == 2
    # nothing anywhere is a string the renderer could interpret
    flat = json.dumps(got)
    assert "<" not in flat and "|---" not in flat


def test_bold_survives_as_data_and_the_asterisks_do_not():
    r = answer.runs("Dallas ISD spent **$23,420 per student** in 2024.")
    assert [x["b"] for x in r] == [False, True, False]
    assert r[1]["t"] == "$23,420 per student"
    assert "**" not in "".join(x["t"] for x in r)


def test_a_script_tag_in_the_answer_stays_one_inert_string():
    """The renderer only ever makes a text node or a <b>, so the worst a
    hostile answer can do is read oddly — but the parser must not help it."""
    got = answer.blocks("<script>alert(1)</script> and **bold**")
    assert got[0]["type"] == "paragraph"
    joined = "".join(r["t"] for r in got[0]["runs"])
    assert joined.startswith("<script>alert(1)</script>")
    assert all(set(r) == {"t", "b"} for r in got[0]["runs"])


def test_a_one_row_table_is_a_fragment_not_a_table():
    """A header with nothing under it is a table that says a computation
    happened when none did."""
    got = answer.blocks("| District | Spend |\n|---|---|")
    assert [b["type"] for b in got] == ["paragraph"]


def test_the_lead_is_the_whole_opening_paragraph_and_loses_nothing():
    """An earlier lead took the first sentence or two and asked the renderer to
    skip block 0 if their first 40 characters matched. They always did — so a
    single paragraph of three or four sentences, the most likely answer shape,
    had everything after sentence two DELETED from the screen while the
    screen-reader announcement still read it."""
    para = ("Dallas ISD spent $17,788 per student in fiscal 2025. That is above "
            "the state median. It enrolled 139,776 students, the largest in "
            "Texas. Most of the gap is debt service, not teaching.")
    built = answer.build("How much does Dallas ISD spend per student?", para)
    assert built["lead"] == para
    assert not built["blocks"], "the promoted paragraph must not also be a block"
    assert built["lead"].count(".") == 4


def test_an_answer_that_opens_with_a_table_gets_no_lead_at_all():
    """Slicing the first chunk of raw text off such an answer put
    `| District | Per student |` into the biggest type on the card — the exact
    defect this module exists to remove, reintroduced above the fold."""
    built = answer.build("Which districts spend the most?",
                         "| District | Spend |\n|---|---|\n| A ISD | $1 |\n| B ISD | $2 |")
    assert built["lead"] == ""
    assert built["lead_runs"] is None
    assert [b["type"] for b in built["blocks"]] == ["table"]


def test_bold_reaches_the_lead_as_runs_not_asterisks():
    built = answer.build("q", "Dallas ISD spent **$17,788 per student** in 2025.")
    assert "**" not in built["lead"]
    assert any(r["b"] for r in built["lead_runs"])


def test_an_empty_answer_never_crashes_the_contract():
    built = answer.build("How many districts?", "")
    assert built["blocks"] == []
    assert built["lead"] == ""
    assert built["lead_runs"] is None
    assert built["follow_ups"]          # still offers somewhere to go


# --------------------------------------------------------------------------
# the figures and the ranking are OURS, not the model's
# --------------------------------------------------------------------------

@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_metric_cards_match_the_artefact_exactly():
    """Not parsed from prose. A figure lifted from a sentence is only as right
    as the sentence."""
    rec = json.loads(ECON.read_text())["districts"][DALLAS]
    alloc = rec["allocation"]
    got = answer.figures(DALLAS)
    by_label = {c["label"]: c["value"] for c in got["cards"]}
    assert by_label["Students"] == f"{int(rec['students']):,}"
    assert by_label["Operating per student"] == f"${int(alloc['operating_per_student']):,}"
    assert by_label["Debt service per student"] == f"${int(alloc['debt_per_student']):,}"
    assert got["year"] == rec["year"]


@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_the_composed_total_gets_no_division_lineage():
    """operating + debt is a SUM. Publishing a 'calculation' for it would
    invent a denominator — the same rule that keeps federal_pct unlineaged."""
    got = answer.figures(DALLAS)
    labels = [c["label"] for c in got["cards"]]
    assert "Total per student" not in labels
    counts = {c["label"]: c["metric"] for c in got["cards"]}
    assert counts["Students"] is None          # a count, not a division
    assert counts["Operating per student"] == "spend_operating_per_student"


def test_no_district_in_context_means_no_invented_figures():
    assert answer.figures(None) is None
    assert answer.figures("999999") is None
    assert answer.comparison("peer", None) is None


@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_the_ranking_comes_from_the_build_not_the_model():
    rec = json.loads(ECON.read_text())["districts"][DALLAS]
    cmp_ = answer.comparison("peer", DALLAS)
    assert cmp_ is not None
    assert len(cmp_["rows"]) == min(5, len(rec["who_does_better"]))
    assert cmp_["rows"][0][0] == rec["who_does_better"][0]["name"]
    # and it says out loud where it came from
    assert "not written by the AI" in cmp_["basis"]


@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_a_fact_question_gets_no_comparison_table():
    """A table implies a computation. Attaching one to 'how many students'
    would dress an answer in evidence it does not need."""
    assert answer.comparison("fact", DALLAS) is None
    assert answer.comparison("enrollment", DALLAS) is None


@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_the_district_name_is_resolved_from_the_artefact_not_the_client():
    """The sheet sends only the number in its own URL, so a page can never
    label an answer with a district it is not showing."""
    built = answer.build("How much does it spend per student?", "It spent $1.",
                         district_number=DALLAS)
    assert built["district"]["name"] == "Dallas ISD"
    assert all("Dallas ISD" in f["question"] for f in built["follow_ups"])


def test_the_contract_always_carries_its_sources_and_limits():
    built = answer.build("How many districts are in Texas?", "There are 1,310.")
    assert built["sources"] and all(s["url"] for s in built["sources"])
    assert built["limitations"]
    assert "can make" in built["limitations"][0] or "misread" in built["limitations"][0]


# --------------------------------------------------------------------------
# the wire: /query must actually carry the contract
# --------------------------------------------------------------------------

def test_query_returns_the_structured_answer_beside_the_text(monkeypatch):
    """The renderer is only reachable if the endpoint ships the contract. A
    green parser test with an unwired endpoint is the exact shape of bug this
    project keeps finding after deploy."""
    from fastapi.testclient import TestClient

    from src import api

    class FakeEngine:
        def query(self, question):
            return {"success": True, "question": question,
                    "answer": "Dallas ISD spent **$23,420 per student** in fiscal 2025.",
                    "sql": "SELECT 1"}

    monkeypatch.setattr(api, "get_nlp_engine", lambda: FakeEngine())
    monkeypatch.setattr(api, "_check_query_budget", lambda *a, **k: None, raising=False)
    with TestClient(api.app) as c:
        r = c.post("/query", json={"question": "How much does Dallas ISD spend per student?",
                                   "district_number": DALLAS})
        if r.status_code == 429:                       # a ceiling, not a defect
            pytest.skip("rate limited in this run")
        assert r.status_code == 200, r.text
        body = r.json()
        s = body["structured"]
        assert s["kind"] == "spending"
        assert "**" not in s["lead"]
        assert any(run["b"] for run in s["lead_runs"])   # bold survived as data
        assert s["follow_ups"] and s["sources"]
        # the answer names Dallas ISD, so its filed figures belong beside it
        assert s["figures"]["district_number"] == DALLAS


def test_a_structuring_failure_never_loses_the_answer(monkeypatch):
    """Presentation is a nicety; the answer is the product. If build() throws,
    the reader still gets the text they would have had before any of this."""
    from fastapi.testclient import TestClient

    from src import api

    class FakeEngine:
        def query(self, question):
            return {"success": True, "question": question, "answer": "1,310 districts.",
                    "sql": "SELECT 1"}

    def boom(*a, **k):
        raise RuntimeError("structuring blew up")

    monkeypatch.setattr(api, "get_nlp_engine", lambda: FakeEngine())
    monkeypatch.setattr(api.answer, "build", boom)
    with TestClient(api.app) as c:
        r = c.post("/query", json={"question": "How many districts are in Texas?"})
        if r.status_code == 429:
            pytest.skip("rate limited in this run")
        assert r.status_code == 200, r.text
        assert r.json()["answer"] == "1,310 districts."
        assert r.json().get("structured") is None


# The phrasings a reader actually types, which match none of the formal words.
# Every one of these was misclassified until it was tried.
COLLOQUIAL = [
    ("show me districts like Katy ISD", "peer"),
    ("which districts are similar to Argyle ISD", "peer"),
    ("is my district in trouble", "diagnostic"),
    ("is anything wrong with our finances", "diagnostic"),
    ("what is the budget of Plano ISD", "spending"),
    ("dallas vs houston", "comparison"),
    ("enrollment trend for Frisco", "trend"),
]


@pytest.mark.parametrize("question,kind", COLLOQUIAL)
def test_plain_phrasing_still_lands_in_the_right_shape(question, kind):
    assert answer.classify(question) == kind


def test_no_pattern_names_a_single_district():
    """`like argyle` sat in the peer patterns as a leftover placeholder — a
    rule that matched exactly one district in Texas and looked like coverage."""
    for _kind, needles in answer._PATTERNS:
        for n in needles:
            assert " isd" not in n, f"pattern {n!r} is hardcoded to one district"


# --------------------------------------------------------------------------
# whose district is this answer about
# --------------------------------------------------------------------------

@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_the_reader_page_never_lends_its_figures_to_another_district():
    """The number comes from the page's URL, not the question. Attaching it
    blindly put four large Dallas figures and a Dallas ranking table under a
    headline about Argyle — a figure reading as support for a claim it does not
    support."""
    built = answer.build("How much does Argyle ISD spend per student?",
                         "Argyle ISD spent $12,345 per student in fiscal 2025.",
                         district_number=DALLAS)
    assert built["figures"]["district_number"] != DALLAS
    assert built["district"]["name"] == "Argyle ISD"
    assert all("Argyle ISD" in f["question"] for f in built["follow_ups"])


@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_a_question_naming_no_district_belongs_to_the_page_it_was_asked_on():
    built = answer.build("how much do we spend per student", "It spent $1.",
                         district_number=DALLAS)
    assert built["figures"]["district_number"] == DALLAS


@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
@pytest.mark.parametrize("question,answer_text", [
    ("Compare Plano ISD and Frisco ISD", "Plano ISD spent more than Frisco ISD."),
    ("Which district spends the most?", "Argyle ISD, then Dallas ISD, then Katy ISD."),
])
def test_more_than_one_district_named_means_no_single_subject(question, answer_text):
    """A comparison and a ranking have no one subject. Picking one would put a
    'comparable districts' table under a statewide question."""
    built = answer.build(question, answer_text, district_number=DALLAS)
    assert built["figures"] is None
    assert built["comparison"] is None
    assert built["district"] is None


@pytest.mark.skipif(not ECON.exists(), reason="economics artefact not built")
def test_a_statewide_ranking_never_gets_a_peer_table():
    assert answer.comparison("ranking", DALLAS) is None


def test_the_builder_takes_no_district_name_from_the_caller():
    """A `district_name` field was accepted for one revision. It let a caller
    post {"district_number": "057905", "district_name": "Anything"} and get
    follow-ups reading "How much does Anything spend per student?" — the name
    is resolved from the artefact for the number, or it is not used."""
    import inspect
    assert "district_name" not in inspect.signature(answer.build).parameters

    from src.api import NLPQueryRequest
    assert "district_name" not in NLPQueryRequest.model_fields


def test_markup_the_parser_does_not_keep_is_removed_not_displayed():
    """Dropping a mark from the PARSER means the raw characters reach the
    reader, which is the bug being fixed. Backticks are always markup; a single
    *emphasis* loses its emphasis and keeps its words."""
    got = answer.plain(answer.runs(
        "using *all funds* and the `total_spend` column"))
    assert got == "using all funds and the total_spend column"


def test_underscores_inside_a_column_name_survive():
    """An earlier lead stripped [*_#`] wholesale and announced
    `all_funds_total_disbursements` as `allfundstotaldisbursements`."""
    got = answer.plain(answer.runs("the all_funds_total_disbursements column"))
    assert "all_funds_total_disbursements" in got
