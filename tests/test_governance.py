"""The two ends of the loop an AI Employee needs: supervision and a result.

A forensic audit on 2026-08-24 found both missing. `isd_review_queue` had been
written on every cron firing and read by nothing — a human gate that refuses to
publish and then loses the refusal. And 671 emails had gone to named
superintendents with no table anywhere able to say whether one conversation
resulted.

These tests hold the fixes to the properties that make them worth having:
the surfaces exist and are token-gated, decisions cannot be silently
overwritten, outcomes cannot be double-counted, and nothing in the outcome path
is ever inferred from behaviour.
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import migrations, outreach_runner  # noqa: E402
from src.api import app  # noqa: E402

client = TestClient(app)

REVIEW_ROUTES = ["/ops/review", "/ops/review-data"]
OUTCOME_ROUTES = ["/ops/outcomes"]


# --- the gate has a reader ---------------------------------------------------

def test_the_review_queue_finally_has_a_reader():
    """The P0 finding. isd_review_queue was written by
    src/isd_cron_runtime.py and read by no route, script or page — a gate in
    name only. This asserts a reader exists in the routing table, which is the
    thing that was actually missing."""
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/ops/review-data" in paths
    assert "/ops/review-decide" in paths
    assert (ROOT / "static" / "opsreview.html").exists()


def test_a_human_can_reach_the_queue_from_the_page():
    """A route nobody can get to is the same defect one layer up."""
    page = (ROOT / "static" / "opsreview.html").read_text()
    assert "/ops/review-data" in page
    assert "/ops/review-decide" in page


@pytest.mark.parametrize("path", REVIEW_ROUTES + OUTCOME_ROUTES)
def test_governance_routes_are_404_not_403_without_a_token(monkeypatch, path):
    """Same rule as every /ops route: answering 403 confirms the route exists,
    which is what a token gate is meant to conceal."""
    monkeypatch.setenv("OPS_TOKEN", "x" * 24)
    assert client.get(path).status_code == 404
    assert client.get(f"{path}?token=wrong").status_code == 404


def test_a_non_ascii_token_is_a_404_not_a_500(monkeypatch):
    """secrets.compare_digest raises TypeError on a non-ASCII str, and a 500
    tells anyone who tries `?token=café` that the route is real. This
    shipped once on a different private route."""
    monkeypatch.setenv("OPS_TOKEN", "x" * 24)
    for path in REVIEW_ROUTES + OUTCOME_ROUTES:
        assert client.get(f"{path}?token=café").status_code == 404


def test_review_decisions_are_restricted_to_the_three_real_ones(monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "t" * 24)
    r = client.post("/ops/review-decide?token=" + "t" * 24,
                    json={"id": 1, "decision": "published", "by": "gus"})
    assert r.status_code == 400
    assert "approved" in r.json()["detail"]


# --- the decision surface cannot publish -------------------------------------

def _code_of(func_name: str, module: str = "api") -> str:
    """The function's CODE, with its docstring removed.

    Scanning the raw source matches the docstring's own explanation of what the
    function must not do — the first version of the test below failed because
    the handler's docstring contains the word "sends" in the sentence promising
    it never sends anything. A check that a prose warning defeats is not a
    check.
    """
    import ast
    src = (ROOT / "src" / f"{module}.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == func_name):
            body = list(node.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]              # drop the docstring
            return "\n".join(ast.unparse(n) for n in body)
    raise AssertionError(f"{func_name} not found in src/{module}.py")


def test_the_review_surface_can_record_a_judgement_and_nothing_else():
    """Narrow authority on purpose. A review page that could also publish
    would be a second, unaudited path into the public feed — the queue's job
    is to record the human judgement; republishing is the builder's job."""
    body = _code_of("ops_review_decide")
    for forbidden in ("isd_briefings", "INSERT INTO", "resend", "send_email"):
        assert forbidden not in body, (
            f"the review decision handler references {forbidden!r}; it must "
            f"only UPDATE a status")
    assert "UPDATE public.isd_review_queue" in body


def test_resolving_twice_is_refused_not_overwritten():
    """Two people reaching opposite conclusions must stay visible. Last-write
    wins would erase the disagreement, which is the one thing a review trail
    exists to preserve."""
    body = _code_of("ops_review_decide")
    assert "AND status = 'open'" in body
    assert "already resolved" in body
    assert "409" in body


# --- outcomes are recorded, never inferred -----------------------------------

def test_no_outcome_is_ever_inferred_from_behaviour():
    """The failure this table exists to prevent. An open is a mail scanner as
    often as a reader; a click proves a URL was fetched. If the outcome path
    ever reads visitor_event or outreach_status, the funnel has started
    inventing results."""
    body = _code_of("ops_record_outcome")
    for inferred in ("visitor_event", "outreach_status", "dwell", "pageview",
                     "opened", "clicked"):
        assert inferred not in body, (
            f"the outcome recorder references {inferred!r} — an outcome must "
            f"be entered by a person, never derived from behaviour")


def test_an_outcome_needs_an_author():
    body = _code_of("ops_record_outcome")
    assert "noted_by is required" in body


def test_a_milestone_cannot_be_double_counted():
    """UNIQUE(district_number, kind, campaign) plus ON CONFLICT DO NOTHING.
    Recording 'meeting_held' twice would double the only number anyone quotes."""
    ddl = (ROOT / "sql" / "create_outcomes.sql").read_text()
    assert "UNIQUE (district_number, kind, campaign)" in ddl
    body = _code_of("ops_record_outcome")
    assert "ON CONFLICT (district_number, kind, campaign) DO NOTHING" in body
    assert "already recorded" in body


def test_the_report_publishes_what_it_does_not_know():
    """A rate quoted over the districts we happened to follow up is not a
    conversion rate. The unchecked count must be in the payload."""
    body = _code_of("ops_outcomes")
    assert "districts_never_followed_up" in body
    assert "honest denominator" in body


def test_pipeline_figures_are_not_recordable():
    ddl = (ROOT / "sql" / "create_outcomes.sql").read_text()
    assert "must never be entered here" in ddl
    assert "invoiced" in ddl.lower() or "forecast" in ddl.lower()


# --- the run ledger ----------------------------------------------------------

def test_every_outreach_run_is_recorded_before_it_acts():
    """Written FIRST, not last. A run that dies mid-way is exactly the one
    whose trace matters; a ledger written on success is a ledger of the runs
    that did not need one."""
    src = (ROOT / "src" / "outreach_runner.py").read_text()
    assert "_open_run" in src and "_close_run" in src
    enq = src.split("async def enqueue(")[1].split("\nasync def ")[0]
    open_at = enq.index("_open_run")
    insert_at = enq.index("INSERT INTO public.outreach_queue")
    assert open_at < insert_at, (
        "the run must be opened before the queue is written, or a crash "
        "between them leaves queued rows belonging to no recorded run")


def test_the_ledger_never_stores_a_token_value():
    """authorized_by is the NAME of the gate. Storing the secret that opened
    it would put a live credential in a table built for auditing."""
    ddl = (ROOT / "sql" / "create_outcomes.sql").read_text()
    assert "Never a token value" in ddl
    src = (ROOT / "src" / "outreach_runner.py").read_text()
    assert 'authorized_by' in src
    for leak in ("OUTREACH_TOKEN\")", "os.environ[\"OUTREACH_TOKEN\"]",
                 "getenv(\"OUTREACH_TOKEN\")"):
        assert leak not in src.split("async def _open_run(")[1][:800]


def test_a_ledger_write_failure_never_fails_a_send():
    """Fail-open by design. The audit trail is worth less than not re-emailing
    a named official."""
    body = _code_of("_close_run", module="outreach_runner")
    assert "except Exception" in body
    src = (ROOT / "src" / "outreach_runner.py").read_text()
    assert "must not fail a send" in src, (
        "the reason must stay written down; a bare try/except here reads as "
        "sloppiness rather than a deliberate trade")


def test_the_queue_carries_the_run_that_created_it():
    src = (ROOT / "src" / "outreach_runner.py").read_text()
    assert "(district_number, email, campaign, run_id) VALUES ($1, $2, $3, $4)" in src


def test_run_ids_are_unique_across_two_runs_of_one_campaign():
    seen = {outreach_runner._mint_run_id("enq", "wave5") for _ in range(200)}
    assert len(seen) == 200, "run ids collided; two waves would share a trace"
    assert all(s.startswith("enq-wave5-") for s in seen)


# --- the migration actually applies ------------------------------------------

def test_the_governance_ddl_is_registered_and_verified():
    """A DDL constant nothing executes is documentation. Both the fast path
    and the slow path must check the sentinel, and the post-run verification
    loop must include it — the fast path alone would let a database that
    predates this layer skip it forever."""
    src = (ROOT / "src" / "migrations.py").read_text()
    assert "GOVERNANCE_DDL" in src and "GOVERNANCE_SENTINEL" in src
    assert src.count("GOVERNANCE_SENTINEL") >= 4
    assert "await conn.execute(GOVERNANCE_DDL)" in src


def test_the_governance_sentinel_is_created_last():
    """Same lesson INTEL_SENTINEL and OUTREACH_SENTINEL each learned: a
    sentinel created first is present on a database where the script died
    halfway, and the missing half is never applied."""
    ddl = migrations.GOVERNANCE_DDL
    sentinel = migrations.GOVERNANCE_SENTINEL.split(".")[-1]
    positions = [m.start() for m in
                 re.finditer(r"CREATE TABLE IF NOT EXISTS public\.(\w+)", ddl)]
    names = re.findall(r"CREATE TABLE IF NOT EXISTS public\.(\w+)", ddl)
    assert names, "no tables in the governance DDL"
    assert names[-1] == sentinel, (
        f"the sentinel is {sentinel} but the last table created is "
        f"{names[-1]}; a half-applied script would report success")
    assert positions == sorted(positions)


def test_the_sql_file_and_the_applied_ddl_describe_the_same_objects():
    """sql/create_outcomes.sql is documentation; migrations.GOVERNANCE_DDL is
    what runs. They drift silently unless something compares them."""
    disk = (ROOT / "sql" / "create_outcomes.sql").read_text()
    applied = migrations.GOVERNANCE_DDL
    on_disk = set(re.findall(r"CREATE TABLE IF NOT EXISTS public\.(\w+)", disk))
    in_code = set(re.findall(r"CREATE TABLE IF NOT EXISTS public\.(\w+)", applied))
    assert on_disk == in_code, f"disk has {on_disk}, code applies {in_code}"


def test_the_governance_tables_are_locked_down_like_every_other():
    """These hold named officials' behaviour. nlp_reader especially: a prompt
    injection reaching the query role must not be able to read who TAG ai is
    talking to."""
    ddl = migrations.GOVERNANCE_DDL
    for table in ("outreach_outcome", "outreach_run"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in ddl
        assert f"REVOKE ALL ON public.{table} FROM PUBLIC" in ddl
    assert "nlp_reader" in ddl
