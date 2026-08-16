"""Tests for clickable lineage — the evidence behind one published number.

What is actually at risk here is not a crash. It is a badge that says checked
when nothing was checked. Every reader-visible error this project has shipped
survived a green suite, and each one had the same shape: a check that looked
slightly to the left of the thing that mattered. The bond layer ran two years
stale while `verify_sources` proved its link was alive. Five districts were
drawn on another district's land while the build printed "unmatched: 0". A twin
test compared an artefact against a column generated from that same artefact.

So these tests are mostly about what the gate REFUSES to certify:

  * a figure whose recomputation comes from the artefact being checked
  * a per-unit figure that will not name its denominator
  * a figure nobody independently recomputed at all
  * a source the publisher has moved past

and one structural test that the second road really is a second road — that
scripts/recompute_revenue.py cannot quietly become a wrapper around the builder
it is supposed to disagree with.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src import lineage, sources  # noqa: E402
from src.api import app  # noqa: E402

ECON = ROOT / "static" / "economics_data.json"
DALLAS = "057905"


def _ev(**kw) -> lineage.Evidence:
    """A figure with every question answered, so each test breaks exactly one."""
    base = dict(
        metric="revenue_total_per_student", value=17053,
        numerator=2383669437, denominator=139776,
        denominator_type="fall survey enrollment",
        artifact="economics_data.json",
        recomputed_value=17053, recomputed_from="data/texas_finance_clean.csv",
        fresh=True, aim_ok=True)
    base.update(kw)
    return lineage.Evidence(**base)


# ---------------------------------------------------------------- the gate

def test_a_figure_that_answers_every_question_is_verified():
    assert lineage.gate(_ev())["verdict"] == lineage.VERIFIED


def test_a_recomputation_that_disagrees_fails():
    g = lineage.gate(_ev(recomputed_value=99999))
    assert g["verdict"] == lineage.FAILED
    assert g["checks"]["correctness"] == "FAILED"


def test_a_figure_validated_against_itself_can_never_be_verified():
    """The exact mistake this repo shipped: comparing an artefact with something
    generated from that artefact proves the generator ran, not that the number
    is right. It stayed green through a real bug for weeks."""
    g = lineage.gate(_ev(recomputed_from="economics_data.json"))
    assert g["verdict"] == lineage.FAILED
    assert "the very artefact" in " ".join(g["why"])


def test_a_figure_nobody_recomputed_is_unverified_not_verified():
    """A badge nobody earned is worse than no badge. This is the whole reason
    UNVERIFIED exists as a separate word from VERIFIED."""
    g = lineage.gate(_ev(recomputed_value=None, recomputed_from=""))
    assert g["verdict"] == lineage.UNVERIFIED
    assert g["checks"]["correctness"] == "unchecked"


def test_a_stale_source_is_reported_as_stale():
    g = lineage.gate(_ev(fresh=False))
    assert g["verdict"] == lineage.STALE


def test_a_source_check_aimed_at_the_wrong_file_fails():
    g = lineage.gate(_ev(aim_ok=False))
    assert g["verdict"] == lineage.FAILED


def test_unknown_freshness_is_not_treated_as_fine():
    """None must mean 'we do not know'. Rendering unknown as ok is how a
    two-year-old dataset kept a clean bill of health."""
    g = lineage.gate(_ev(fresh=None))
    assert g["verdict"] != lineage.VERIFIED
    assert g["checks"]["freshness"] == "unchecked"


def test_a_per_unit_figure_must_name_its_denominator():
    """'Per student' is not a definition. This site publishes per-student
    figures on different denominators that legitimately disagree."""
    g = lineage.gate(_ev(denominator_type=""))
    assert g["verdict"] == lineage.FAILED
    assert "not a definition" in " ".join(g["why"])


def test_a_zero_denominator_is_refused_not_divided():
    g = lineage.gate(_ev(denominator=0, value=0))
    assert g["verdict"] == lineage.REFUSED


def test_a_deliberate_refusal_says_why():
    ev = lineage.refuse("debt_repayment_ratio",
                        "the district's reported series has a gap")
    g = lineage.gate(ev)
    assert g["verdict"] == lineage.REFUSED
    assert "gap" in " ".join(g["why"])


def test_arithmetic_is_checked_separately_from_correctness():
    """These are different claims and must not share a name. Arithmetic says the
    published value follows from the published components — both of which live
    in the same file. Correctness says an independent read of the publisher's
    own file agreed."""
    g = lineage.gate(_ev(value=99999, recomputed_value=99999))
    assert g["checks"]["arithmetic"] == "FAILED"
    assert g["verdict"] == lineage.FAILED
    assert "imply" in " ".join(g["why"])


def test_rounding_tolerance_does_not_swallow_a_real_error():
    # Rounded to whole dollars: 0.4 apart is rounding, 2 apart is a defect.
    assert lineage.gate(_ev(value=17053, numerator=17053, denominator=1)
                        )["checks"]["arithmetic"] == "ok"
    assert lineage.gate(_ev(value=17055, numerator=17053, denominator=1)
                        )["checks"]["arithmetic"] == "FAILED"


def test_an_exact_halfway_quotient_is_not_reported_as_broken_arithmetic():
    """278,038 / 212 is exactly 1311.5 — a real district, not a contrived case.
    Rounding lands exactly `rounding` from the quotient, so the comparison has to
    be inclusive with headroom rather than passing on floating-point luck."""
    for value in (1311, 1312):    # either rounding convention is correct here
        g = lineage.gate(_ev(value=value, numerator=278038, denominator=212))
        assert g["checks"]["arithmetic"] == "ok", f"{value} flagged as bad arithmetic"
    assert lineage.gate(_ev(value=1315, numerator=278038, denominator=212)
                        )["checks"]["arithmetic"] == "FAILED"


# ------------------------------------------------- freshness from the register

def test_a_source_nobody_recorded_is_unknown_never_fine():
    assert sources.freshness_and_aim("no_such_source") == (None, None)


def test_a_known_stale_source_reports_stale():
    """tea_staar_district is genuinely a release behind and needs a human to
    download it. That fact was only in prose; it is now machine-readable, which
    is why it can reach a reader instead of only a JSON comment."""
    fresh, _ = sources.freshness_and_aim("tea_staar_district")
    assert fresh is False


def test_a_source_with_no_freshness_signal_returns_unknown():
    assert sources.freshness_and_aim("bls_cpi") == (None, None)


def test_a_page_check_with_no_product_proof_does_not_claim_good_aim():
    """tea_staar_district's year pattern matches a statewide PDF, not the
    district file it is supposed to watch — right about the year by coincidence.
    Coincidence must not be reported as aim."""
    _, aim = sources.freshness_and_aim("tea_staar_district")
    assert aim is None


def test_the_files_the_running_service_reads_actually_ship():
    """`.vercelignore` excludes all of scripts/, and src/sources.py reads a file
    that lives there. Without a re-include the deployed site answers "we do not
    know" for freshness on every figure — the honest fallback, and completely
    invisible from outside unless someone clicks a number. The tests would stay
    green because the repo checkout has the file.

    This is the same shape as the cron import that ImportError'd in production
    for the same reason, which is why that re-include has a warning above it.
    """
    ignore = (ROOT / ".vercelignore").read_text().splitlines()
    for needed in ("scripts/freshness_vintages.json", "scripts/isd_intel.py",
                   "scripts/__init__.py"):
        assert f"!{needed}" in ignore, (
            f"{needed} is read by the running service but .vercelignore drops "
            "it — the deploy will behave differently from every test")


def test_every_source_the_lineage_can_cite_is_in_both_registers():
    vintages = json.loads(
        (ROOT / "scripts" / "freshness_vintages.json").read_text())["sources"]
    assert set(vintages) <= set(sources.SOURCES), (
        "a vintage record names a source the register does not know")


# ----------------------------------------- the second road must stay a second road

def test_the_recomputation_shares_no_code_with_the_builder():
    """If this ever imports pandas or the builder, it stops being independent
    evidence and becomes a second copy of the same mistake.

    The imports are read from the parsed syntax tree, not grepped out of the
    text. A first draft of this test searched the file for the strings and
    failed on its own docstring, which names both — a check that fires on prose
    about the thing instead of the thing is the exact class of error the rest of
    this file exists to catch.
    """
    import ast
    tree = ast.parse((ROOT / "scripts" / "recompute_revenue.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned = {"pandas", "numpy", "build_economics_data", "src"}
    assert not (imported & banned), (
        f"recompute_revenue.py imports {imported & banned} — its whole value is "
        "arriving at the answer by a different road")


@pytest.mark.skipif(not (ROOT / "data" / "texas_finance_clean.csv").exists(),
                    reason="source CSV is not committed (18 MB)")
def test_the_second_road_reaches_the_published_figure_for_dallas():
    import recompute_revenue
    table = recompute_revenue.recompute()
    row = table[DALLAS]
    per_student = round(row["total"] / row["enrollment"])
    published = json.loads(ECON.read_text())["districts"][DALLAS]
    assert per_student == published["revenue"]["total_per_student"]


# ------------------------------------------------------------- the artefact

@pytest.mark.skipif(not ECON.exists(), reason="run build_economics_data.py first")
class TestPublishedArtifact:
    @pytest.fixture(scope="class")
    def econ(self):
        return json.loads(ECON.read_text())

    def test_the_recomputation_record_proves_the_check_ran(self, econ):
        """A check that ran and found nothing must not be indistinguishable from
        a check that never ran — that is how the intel cron failed silently for
        four days."""
        rec = econ["meta"]["lineage_recomputation"]
        assert rec["figures_checked"] > 4000, "the second road barely ran"
        assert rec["disagreements"] == 0
        assert "recompute_revenue" in rec["road"]

    def test_the_road_named_is_not_the_artefact_being_checked(self, econ):
        assert "economics_data.json" not in econ["meta"]["lineage_recomputation"]["road"]

    def test_every_template_names_its_denominator_and_its_source(self, econ):
        for key, t in econ["meta"]["lineage_templates"].items():
            assert t["denominator_type"], f"{key} does not name its denominator"
            assert t["source_id"] in sources.SOURCES, f"{key} cites an unknown source"
            assert t["measure_id"] in {m["id"] for m in sources.MEASURES}

    def test_every_district_with_revenue_carries_its_evidence(self, econ):
        missing = [n for n, d in econ["districts"].items()
                   if d.get("revenue") and not (d["revenue"].get("lineage") or {}).get("figures")]
        assert not missing, f"{len(missing)} districts publish revenue with no evidence"

    def test_the_percentages_deliberately_have_no_lineage(self, econ):
        """federal_pct is 100 minus the other two so the bar's labels add to 100.
        Publishing a numerator for it would describe a division that never
        happened, which is worse than publishing nothing."""
        figures = econ["districts"][DALLAS]["revenue"]["lineage"]["figures"]
        assert not any(k.endswith("_pct") for k in figures)


# ---------------------------------------------------------------- the route

@pytest.mark.skipif(not ECON.exists(), reason="run build_economics_data.py first")
class TestLineageEndpoint:
    @pytest.fixture(scope="class")
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_a_real_figure_comes_back_verified_with_its_working(self, client):
        r = client.get(f"/district/{DALLAS}/lineage/total_per_student")
        assert r.status_code == 200
        body = r.json()
        assert body["gate"]["verdict"] == lineage.VERIFIED
        assert body["numerator"] and body["denominator"]
        assert body["value"] == round(body["numerator"] / body["denominator"])
        assert body["source_url"].startswith("https://tea.texas.gov")

    def test_all_four_revenue_figures_are_clickable(self, client):
        for metric in ("total_per_student", "local_per_student",
                       "state_per_student", "federal_per_student"):
            r = client.get(f"/district/{DALLAS}/lineage/{metric}")
            assert r.status_code == 200, metric
            assert r.json()["gate"]["verdict"] == lineage.VERIFIED, metric

    def test_a_metric_with_no_evidence_404s_and_lists_what_there_is(self, client):
        r = client.get(f"/district/{DALLAS}/lineage/made_up")
        assert r.status_code == 404
        assert "total_per_student" in r.json()["detail"]

    def test_an_unknown_district_404s(self, client):
        r = client.get("/district/999999/lineage/total_per_student")
        assert r.status_code == 404

    def test_the_response_never_certifies_itself_against_itself(self, client):
        body = client.get(f"/district/{DALLAS}/lineage/total_per_student").json()
        assert body["recomputed_from"] != body["artifact"]


# ------------------------------------------------------------------- MCP

@pytest.mark.skipif(not ECON.exists(), reason="run build_economics_data.py first")
class TestLineageOverMCP:
    """An assistant handed a figure has no way to tell a real number from a
    fluent one. This is the tool that lets it check, and the verdict has to
    travel whatever it says — a model that only ever hears good news reports
    good news."""

    def test_the_tool_returns_the_working_and_the_verdict(self):
        from src import mcp_tools
        r = mcp_tools.call_tool("district_lineage", {"district_number": DALLAS})
        sc = r["structuredContent"]
        assert sc["gate"]["verdict"] == lineage.VERIFIED
        assert sc["value"] == round(sc["numerator"] / sc["denominator"])
        text = r["content"][0]["text"]
        assert "fall survey enrollment" in text, "the denominator must be named"
        assert "VERIFIED" in text
        # The two corrections a review forced, locked so they cannot drift back.
        # A model reads this text closely and will repeat its claims verbatim.
        assert "does NOT mean the figure is true" in text, (
            "agreement between two roads must not be sold to an assistant as truth")
        assert "same cleaned CSV" in text, (
            "the tool must say the two roads share an upstream file, so a mistake "
            "made before either of them would be reproduced by both")

    def test_asking_for_a_figure_with_no_working_says_what_there_is(self):
        from src import mcp_tools
        r = mcp_tools.call_tool("district_lineage",
                                {"district_number": DALLAS, "metric": "made_up"})
        assert r.get("isError")
        assert "total_per_student" in r["content"][0]["text"]

    def test_the_documented_tool_count_matches_the_code(self):
        """A hand-typed count that nothing checks is how the connect-time blurb
        claimed 4,588 bond elections for weeks after the number changed."""
        from src import mcp_tools
        words = {9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen"}
        n = len(mcp_tools.list_tools())
        doc = (ROOT / "docs" / "MCP.md").read_text()
        assert f"{words[n]} read-only tools" in doc, (
            f"docs/MCP.md does not say there are {n} ({words[n]}) tools")
        for tool in mcp_tools.list_tools():
            assert f"`{tool['name']}`" in doc, f"{tool['name']} is undocumented"


# --------------------------------------------------------------- the page

def test_the_number_on_the_page_is_actually_clickable():
    """An endpoint nobody can reach from the page is documentation, not lineage.
    This locks the affordance itself: the button, the handler that fetches the
    evidence, and the verdict badge that shows a result other than VERIFIED."""
    page = (ROOT / "static" / "index.html").read_text()
    assert "function linBtn(" in page, "no way to render a clickable figure"
    assert 'data-lineage' in page, "nothing on the page carries a metric to look up"
    assert "/lineage/" in page, "the page never calls the lineage endpoint"
    assert "showLineage" in page
    for verdict in ("VERIFIED", "UNVERIFIED", "STALE", "FAILED"):
        assert f"v-{verdict}" in page, (
            f"{verdict} has no style, so it would render unlabelled — the point "
            "is that a reader sees the bad verdicts too")
