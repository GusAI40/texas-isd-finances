"""The intelligence layer — the guarantees, not the arithmetic.

The point of an analytics system is that someone will make a decision from it,
so the risk is not a crash. It is a number that looks fine and is not. These
tests pin the four things that would make this dashboard lie:

  * the score being a black box, or not adding up to its own factors;
  * the sample quietly being asked to carry a claim it cannot;
  * an opportunity being invented to fill an empty panel;
  * the population widening past what the site promised the public.

The end-to-end flow — pixel to click to section to conversation to dashboard,
against a real Postgres — is proved separately by the harness described in
docs/ENGINEERING_LOG.md; these run with no database at all.
"""
from __future__ import annotations

import re

import pytest

from src import intel, migrations, tracking

# --- the score --------------------------------------------------------------

def test_the_score_is_exactly_the_sum_of_the_factors_that_fired():
    """A total a reader cannot take apart is a number they have to trust
    instead of check, which is the opposite of this project's whole argument."""
    facts = {"clicked": True, "returned": True, "asked": True}
    got = intel.score(facts)
    assert got["score"] == sum(f["weight"] for f in got["factors"] if f["fired"])
    assert got["score"] == 10 + 20 + 20


def test_every_weight_is_published_with_the_score():
    got = intel.score({})
    assert len(got["factors"]) == len(intel.WEIGHTS)
    for f in got["factors"]:
        assert f["label"] and f["weight"] > 0
        assert f["fired"] is False
    assert got["score"] == 0
    assert got["max"] == intel.MAX_SCORE


def test_doing_nothing_scores_nothing_and_says_so():
    assert intel.score({})["band"] == "no recorded activity"


def test_the_bands_describe_behaviour_not_a_sales_stage():
    """'Hot lead' would assert an intention nobody stated."""
    names = {intel.band(v) for v in (0, 10, 40, 90)}
    for n in names:
        assert not re.search(r"lead|hot|warm|qualified|prospect", n, re.I), n


def test_a_reply_outweighs_everything_a_scanner_can_fake():
    """Clicks and page loads are producible by a mail-security appliance. A
    reply is a person typing. The weights have to reflect that or the ranking
    puts appliances at the top."""
    replied = intel.score({"replied": True})["score"]
    machine_reachable = intel.score({"clicked": True, "multi_session": True,
                                     "deep_read": True})["score"]
    assert replied > machine_reachable


def test_facts_come_from_counted_behaviour_not_free_text():
    row = {"first_click_at": "t", "sessions": 3, "questions": 4,
           "distinct_sections": 5, "max_dwell_ms": 61_000, "returns": 1,
           "downloads": 0, "replied_at": None}
    f = intel.facts_from_row(row)
    assert f == {"clicked": True, "returned": True, "multi_session": True,
                 "deep_read": True, "section_depth": True, "asked": True,
                 "asked_three": True, "downloaded": False, "replied": False}


def test_a_fifty_nine_second_read_is_not_a_deep_read():
    """The threshold is a threshold, not a suggestion — an off-by-one here
    silently reclassifies every borderline reader."""
    assert intel.facts_from_row({"max_dwell_ms": 59_999})["deep_read"] is False
    assert intel.facts_from_row({"max_dwell_ms": 60_000})["deep_read"] is True


# --- what the data can carry ------------------------------------------------

def test_a_handful_of_conversions_refuses_to_carry_a_model():
    """This is the guard the spec itself asked for: regression last, because
    until the events are reliable it produces sophisticated-looking garbage."""
    p = intel.power(people=100, conversions=3)
    assert p["verdict"] == "REFUSED"
    assert p["supportable_predictors"] == 0
    assert "no predictors at all" in p["why"]


def test_the_refusal_lifts_itself_when_the_sample_grows():
    assert intel.power(1000, 12)["verdict"] == "THIN"
    assert intel.power(1000, 40)["verdict"] == "OK"
    assert intel.power(1000, 40)["supportable_predictors"] == 4


def test_zero_conversions_never_divides_by_zero():
    assert intel.power(0, 0)["verdict"] == "REFUSED"


# --- opportunities ----------------------------------------------------------

def test_no_evidence_produces_no_opportunities():
    """An empty list is a real answer. Inventing one to fill a panel is how a
    dashboard teaches its reader to stop believing it."""
    assert intel.opportunities([], [], {}) == []


def test_a_failing_engine_is_the_highest_priority_finding():
    out = intel.opportunities([], [], {"turns": 100, "failures": 20})
    assert out and out[0]["priority"] == "high"
    assert "20 of 100" in out[0]["finding"]


def test_a_handful_of_failures_in_a_tiny_sample_is_not_a_finding():
    assert intel.opportunities([], [], {"turns": 5, "failures": 1}) == []


def test_every_opportunity_carries_the_evidence_that_produced_it():
    out = intel.opportunities(
        [{"kind": "debt", "asked": 40}],
        [{"section": "bonds", "people": 9, "avg_dwell_ms": 4000}],
        {"turns": 100, "failures": 20})
    assert out
    for o in out:
        assert o["evidence"] and o["finding"] and o["recommendation"]
        # a recommendation with no number behind it is an opinion
        assert re.search(r"\d", o["finding"]), o["finding"]


# --- the population, and the promise ---------------------------------------

def test_a_client_may_only_assert_what_it_alone_witnesses():
    """Everything else is written server-side from facts a browser cannot
    fake: a page it actually requested, a pixel it actually fetched, a question
    the engine actually answered. A client that could post `reply` could
    manufacture the only conversion this product has."""
    assert tracking.CLIENT_EVENTS < tracking.EVENTS
    for forbidden in ("reply", "click", "pageview", "email_open", "question", "return"):
        assert forbidden not in tracking.CLIENT_EVENTS


def test_the_app_gate_and_the_database_constraint_list_the_same_events():
    """Two fences. A typo'd event name that slips past the Python set should
    fail loudly at the CHECK constraint rather than quietly accumulate a
    category nobody queries."""
    m = re.search(r"CHECK \(event IN \(([^)]*)\)\)", migrations.INTEL_DDL, re.S)
    assert m, "the event whitelist is gone from the DDL"
    in_db = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert in_db == set(tracking.EVENTS)


def test_an_unparseable_address_loses_the_field_not_the_event():
    """The column is inet. A hostname reaches asyncpg, raises, and — because
    every tracking write fails open — the ENTIRE event vanishes over a field
    nobody reads. Found by running the real flow against real Postgres."""
    assert tracking.client_ip(None, "testclient") is None
    assert tracking.client_ip("not-an-ip", None) is None
    assert tracking.client_ip("1.2.3.4, 5.6.7.8", None) == "1.2.3.4"
    assert tracking.client_ip(None, "::1") == "::1"


def test_the_two_populations_are_named_rather_than_implied():
    """The funnel is people we emailed; the question panels are everyone.
    Showing 1 person and 2 conversations reads as a bug until you know why."""
    assert intel.POPULATION_RECIPIENTS != intel.POPULATION_EVERYONE
    assert "emailed" in intel.POPULATION_RECIPIENTS
    assert "anonymous" in intel.POPULATION_EVERYONE


def test_the_open_rate_is_never_offered_as_a_rate():
    assert "never a rate to quote" in intel.OPEN_CAVEAT


def test_there_is_exactly_one_conversion():
    """Return visits, downloads and deep chat engagement are intent signals.
    Promoting them to conversions manufactures a funnel with four exits where
    one exists."""
    conversions = [k for k, label in intel.FUNNEL_STAGES if "conversion" in label]
    assert conversions == ["replied"]


def test_every_dashboard_metric_states_where_it_came_from():
    assert set(intel.LINEAGE) >= {"people", "clicked", "sections", "questions",
                                  "conversations", "replied", "score"}
    for key, why in intel.LINEAGE.items():
        assert len(why) > 20, key


# --- the schema -------------------------------------------------------------

_OBJECT_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:UNIQUE\s+)?(TABLE|VIEW|INDEX)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_.]+)", re.I)


def _objects(sql: str) -> set[tuple[str, str]]:
    return {(k.upper(), n.lower().replace("public.", ""))
            for k, n in _OBJECT_RE.findall(sql)}


def test_the_embedded_intel_ddl_matches_its_sql_mirror():
    """Two copies of a schema that agree today and quietly stop agreeing later
    is the exact shape of bug this project keeps finding in its data sources."""
    from pathlib import Path
    mirror = Path(__file__).resolve().parent.parent / "sql" / "create_intel.sql"
    assert _objects(migrations.INTEL_DDL) == _objects(mirror.read_text())


def test_the_intel_migration_is_additive_only():
    """It runs unattended against production on every cold start."""
    for forbidden in ("DROP TABLE", "DROP VIEW", "DROP COLUMN", "TRUNCATE",
                      "DELETE FROM", "ALTER COLUMN"):
        assert forbidden not in migrations.INTEL_DDL, forbidden
    # Dropping a CHECK is allowed and is not destructive — it removes a
    # validation rule, examines no row, and is immediately replaced by a
    # strictly MORE permissive one. Anything else named DROP is not.
    drops = re.findall(r"DROP\s+(\w+)", migrations.INTEL_DDL, re.I)
    assert set(d.upper() for d in drops) <= {"CONSTRAINT"}


def test_the_widened_constraint_still_permits_every_original_event():
    """A whitelist that narrows would reject rows the app already writes."""
    for original in ("email_open", "click", "pageview", "dwell", "question",
                     "return"):
        assert f"'{original}'" in migrations.INTEL_DDL


def test_the_intel_schema_reuses_the_event_stream_instead_of_forking_it():
    """A separate analytics-events table would be a second source of truth for
    the same journey, and the first question anyone asked of it would be which
    one to believe."""
    objs = _objects(migrations.INTEL_DDL)
    assert ("TABLE", "visitor_event") not in objs, "the event table was re-created"
    assert "ALTER TABLE public.visitor_event ADD COLUMN IF NOT EXISTS" in migrations.INTEL_DDL
    assert ("TABLE", "chat_turn") in objs


def test_idempotency_is_enforced_in_the_database_not_only_the_client():
    """sendBeacon retries and bfcache replays. Without the unique key one
    41-second read of the debt section is three rows and nothing looks wrong."""
    assert "visitor_event_key_idx" in migrations.INTEL_DDL
    assert "WHERE event_key IS NOT NULL" in migrations.INTEL_DDL


def test_the_prompt_injection_role_can_never_read_who_asked_what():
    assert "nlp_reader" in migrations.INTEL_DDL
    assert "REVOKE ALL ON public.chat_turn" in migrations.INTEL_DDL


@pytest.mark.parametrize("sql", [intel.PEOPLE_SQL, intel.TIMELINE_SQL,
                                 intel.TOP_SECTIONS_SQL, intel.TOP_QUESTIONS_SQL,
                                 intel.RECENT_QUESTIONS_SQL, intel.ACTIVITY_SQL,
                                 intel.ANSWER_QUALITY_SQL])
def test_no_query_interpolates_a_value(sql):
    """Every parameter is bound. The one place a token or a district number
    could reach SQL is the one place this must never slip."""
    assert "%" not in sql and ".format(" not in sql
    assert not re.search(r"\+\s*['\"]", sql)


# --- beta feedback ----------------------------------------------------------
# The telemetry says what people DID. A note says what they came for and did
# not find, which is the half no amount of event counting recovers.

def test_feedback_outranks_every_counted_threshold():
    """Someone who took the trouble to type a paragraph is describing a gap
    the event stream cannot show you. It goes first, or it gets buried under
    findings a machine produced."""
    out = intel.opportunities(
        [{"kind": "debt", "asked": 99}], [],
        {"turns": 100, "failures": 50},
        feedback=[{"message": "I could not find the tax rate anywhere"}])
    assert out[0]["finding"].startswith("Someone wrote in:")
    assert "volunteered, not observed" in out[0]["evidence"]


def test_no_feedback_changes_nothing():
    counted = intel.opportunities([], [], {"turns": 100, "failures": 20})
    with_none = intel.opportunities([], [], {"turns": 100, "failures": 20}, [])
    assert counted == with_none


def test_the_feedback_query_never_returns_the_email_itself():
    """A dashboard that prints the address turns a note into a contact list.
    Whether someone left one is useful; the address itself is not, until a
    human decides to reply."""
    assert "left_contact" in intel.FEEDBACK_SQL
    assert "f.contact IS NOT NULL" in intel.FEEDBACK_SQL
    # the raw column must not be selected
    select = intel.FEEDBACK_SQL[:intel.FEEDBACK_SQL.index("FROM")]
    assert "f.contact," not in select and " contact\n" not in select


def test_feedback_is_created_by_the_self_applying_schema():
    assert "CREATE TABLE IF NOT EXISTS public.site_feedback" in migrations.INTEL_DDL
    assert "REVOKE ALL ON public.site_feedback FROM PUBLIC" in migrations.INTEL_DDL


def test_the_sentinel_is_the_object_created_last():
    """It moved when site_feedback was added. If it had stayed on chat_turn, a
    database that already ran the earlier version would take the fast path
    forever and never get the new table — the migration would be a silent
    no-op on exactly the deployments that already exist."""
    assert migrations.INTEL_SENTINEL == "public.site_feedback"
    ddl = migrations.INTEL_DDL
    assert ddl.index("public.chat_turn") < ddl.index("public.site_feedback")


# --- the 2026-08-19 forensic: appliances must not read as readers -------------

def test_engaged_means_sections_read_never_dwell_alone():
    """The funnel's fourth stage counted 12 "readers"; four were one
    mail-security appliance cluster (four districts clicking 1.1s apart at
    03:47 UTC with 71-116s of headless dwell) and eight never had a single
    section on screen. Dwell measures how long a tab was open; sections
    require 4s at 50% visibility in a focused tab, three times over."""
    appliance = {"total_dwell_ms": 116_298, "distinct_sections": 1}
    parked_tab = {"total_dwell_ms": 60_007, "distinct_sections": 0}
    reader = {"total_dwell_ms": 60_001, "distinct_sections": 4}
    fast_reader = {"total_dwell_ms": 12_000, "distinct_sections": 3}
    assert not intel.engaged(appliance), "an appliance profile counted as reading"
    assert not intel.engaged(parked_tab), "an unscrolled tab counted as reading"
    assert intel.engaged(reader)
    assert intel.engaged(fast_reader), "sections are the bar — dwell is not a gate"
    assert intel.engaged({}) is False


def test_engaged_agrees_with_the_scores_own_definition_of_reading():
    """One notion of "read the report" across the dashboard: the funnel stage
    and the score's section_depth factor must fire on the same behaviour, or
    the funnel says 4 while the people table says 2."""
    for sections in (0, 1, 2, 3, 4, 10):
        row = {"distinct_sections": sections}
        assert intel.engaged(row) == intel.facts_from_row(row)["section_depth"]


def test_sessions_only_count_browser_rendered_events():
    """Session counting is a whitelist for a reason discovered one forensic
    at a time: the pixel mints a session id per fetch, the reply ingest
    writes 'reply-<message_id>', and a cookieless scanner detonating the
    tracked link twice mints two "visits" without rendering a page — each
    inflated multi_session and the score. Every Python-built query derives
    its filter from ONE constant; the two plain-SQL view copies are pinned
    to it here, normalised for whitespace so formatting cannot fake drift."""
    for kind in ("email_open", "click", "reply"):
        assert kind not in intel.BROWSER_SESSION_EVENTS, (
            f"{kind} carries session ids no browser held")
    assert intel.SESSION_FILTER_SQL in intel.PEOPLE_SQL
    assert "j.sessions" not in intel.PEOPLE_SQL, (
        "PEOPLE_SQL is back on the view's session count, which is only "
        "correct once the deployed view carries the 2026-08-19 fix")

    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    members = ", ".join(f"'{e}'" for e in intel.BROWSER_SESSION_EVENTS)
    view_fragment = f"count(DISTINCT e.session_id) FILTER (WHERE e.event IN ({members}))"
    for name, text in [
        ("sql/create_visitor_tracking.sql",
         (root / "sql" / "create_visitor_tracking.sql").read_text()),
        ("migrations.VISITOR_TRACKING_DDL", migrations.VISITOR_TRACKING_DDL),
    ]:
        flat = " ".join(text.split())
        assert view_fragment in flat, (
            f"{name}: the view's session whitelist drifted from "
            f"intel.BROWSER_SESSION_EVENTS")

    # the offline report derives from the same constant at runtime
    import scripts.journey_report as jr
    assert intel.SESSION_FILTER_SQL in jr.SITE_SESSIONS_SQL
    jr_text = (root / "scripts" / "journey_report.py").read_text()
    assert ", sessions," not in jr_text, (
        "journey_report selects the view's raw sessions column again")


def test_the_view_fix_actually_reaches_an_existing_database():
    """A sentinel gate answers "does the object exist", never "is it
    current" — so a changed view body behind an existing sentinel is a
    silent no-op on exactly the databases that already run (the
    INTEL_SENTINEL lesson). ensure_schema must detect the stale view and
    re-apply it, on the fast path AND the slow path, and a failure to do so
    must never be reported as ok."""
    import inspect

    # the refresh DDL is the create-time view verbatim, plus the lockdown —
    # a fresh CREATE after a drop would otherwise inherit Supabase default
    # grants and expose named officials' reading behaviour to anon
    assert migrations.JOURNEY_VIEW_DDL.startswith("CREATE OR REPLACE VIEW")
    view_part = migrations.JOURNEY_VIEW_DDL[
        :migrations.JOURNEY_VIEW_DDL.index(";") + 1]
    assert view_part in migrations.VISITOR_TRACKING_DDL, (
        "the refresh DDL drifted from the create-time DDL")
    assert view_part.rstrip().endswith("r.sent_at;"), (
        "the slice truncated inside the view statement")
    assert ("REVOKE ALL ON public.v_recipient_journey FROM PUBLIC"
            in migrations.JOURNEY_VIEW_DDL)
    assert "'anon', 'authenticated', 'nlp_reader'" in migrations.JOURNEY_VIEW_DDL

    # the staleness marker must be a whitelist member that appears in the
    # deployed body, or every cold start re-applies the view forever
    cur = inspect.getsource(migrations._journey_view_current)
    assert '"followup" in body' in cur
    assert "followup" in intel.BROWSER_SESSION_EVENTS
    assert "'followup'" in migrations.JOURNEY_VIEW_DDL

    src = inspect.getsource(migrations.ensure_schema)
    assert src.count("_journey_view_current") >= 3, (
        "the view-currency check must guard the fast path, the slow path "
        "AND the raced-another-worker fallback — a failed refresh that "
        "lands in the fallback would otherwise report ok forever")
    assert src.count("JOURNEY_VIEW_DDL") >= 2, (
        "the corrected view is no longer applied on both boot paths")


def test_the_funnel_stage_is_computed_by_the_guarded_definition():
    """intel.engaged() is revert-guarded above, but the funnel is built in
    src/api.py — if that call site quietly goes back to the dwell-only
    expression, every test here stays green while the appliances rejoin the
    funnel. So the call site itself is pinned."""
    from pathlib import Path
    api = (Path(__file__).resolve().parent.parent / "src" / "api.py").read_text()
    assert "engaged = sum(1 for r in people if intel.engaged(r))" in api
    dwell_only = 'engaged = sum(1 for r in people if int(r.get("total_dwell_ms"'
    assert dwell_only not in api, "the dwell-only funnel stage is back"



