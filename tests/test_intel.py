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
