"""The server-side outreach machine — every rail, held without a network.

What is at risk here is mass email to named public officials, fired from a
public website's own endpoints. The rails are therefore tested structurally:
the schema copies cannot drift, the endpoints answer 404 to the wrong token,
enqueue refuses without the literal GO, the eligibility SQL carries every
skip-list, and a claimed-but-crashed message is quarantined rather than
retried into a duplicate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import migrations, outreach_email, outreach_runner

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "sql" / "create_outreach_queue.sql"

_OBJECT_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|VIEW|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([A-Za-z_.]+)", re.I)


def _objects(sql: str) -> set[tuple[str, str]]:
    return {(kind.upper(), name.lower().replace("public.", ""))
            for kind, name in _OBJECT_RE.findall(sql)}


# --- the schema: two copies, one truth ---------------------------------------

def test_embedded_ddl_and_sql_file_create_the_same_objects():
    assert _objects(migrations.OUTREACH_DDL) == _objects(SQL_FILE.read_text())


def test_the_sentinel_is_the_object_created_last():
    """Same rule that moved INTEL_SENTINEL to site_feedback: the sentinel must
    be the newest object, or existing databases fast-path past new DDL."""
    assert migrations.OUTREACH_SENTINEL == "public.outreach_queue"
    ddl = migrations.OUTREACH_DDL
    assert ddl.index("public.outreach_contact") < ddl.index("public.outreach_queue")


def test_ensure_schema_checks_the_outreach_sentinel_everywhere():
    import inspect
    src = inspect.getsource(migrations.ensure_schema)
    assert src.count("OUTREACH_SENTINEL") >= 3, (
        "the outreach sentinel must gate the fast path, the slow path AND "
        "the raced-another-worker fallback")


def test_the_queue_ddl_is_additive_and_idempotent():
    ddl = migrations.OUTREACH_DDL.upper()
    for forbidden in ("DROP TABLE", "DROP VIEW", "DROP COLUMN", "TRUNCATE",
                      "DELETE FROM", "ALTER COLUMN"):
        assert forbidden not in ddl
    for match in re.finditer(r"CREATE\s+(TABLE|INDEX)\s+(.{0,20})",
                             migrations.OUTREACH_DDL, re.I):
        assert match.group(2).upper().startswith("IF NOT EXISTS"), match.group(0)


def test_contact_data_is_locked_down_like_visitor_event():
    """outreach_contact holds named officials' addresses; a prompt injection
    that reached nlp_reader must not be able to read a contact list."""
    for ddl in (migrations.OUTREACH_DDL, SQL_FILE.read_text()):
        assert "ENABLE ROW LEVEL SECURITY" in ddl
        assert "REVOKE ALL ON public.outreach_contact FROM PUBLIC" in ddl
        assert "'nlp_reader'" in ddl


def test_double_enqueue_is_structurally_impossible():
    """UNIQUE(email) plus ON CONFLICT DO NOTHING: an address is queued at
    most once, ever — the one-touch doctrine as a constraint, not a habit."""
    assert "email           text        NOT NULL UNIQUE" in migrations.OUTREACH_DDL
    import inspect
    src = inspect.getsource(outreach_runner.enqueue)
    assert "ON CONFLICT (email) DO NOTHING" in src


# --- eligibility: every skip-list, in the database ---------------------------

def test_eligibility_excludes_sent_optout_and_already_queued():
    sql = outreach_runner.ELIGIBLE_SQL
    assert "NOT IN (SELECT email FROM public.outreach_sent)" in sql
    assert "lower(email) FROM public.outreach_optout" in sql
    assert "NOT IN (SELECT email FROM public.outreach_queue)" in sql
    assert "ORDER BY c.district_number" in sql, (
        "selection must be deterministic, not a sample")


def test_enqueue_guards_the_watermark_before_writing_anything():
    """On the production database the sent table IS the durable record, so a
    count below the committed floor means the WRONG database — a fork, a
    fresh project — and enqueueing there would re-email everyone."""
    import inspect
    src = inspect.getsource(outreach_runner.enqueue)
    assert src.index("watermark_floor()") < src.index("ELIGIBLE_SQL"), (
        "the floor check must come before selection")
    assert src.index("watermark_floor()") < src.index("INSERT INTO"), (
        "the floor check must come before any write")
    assert '"refused"' in src


def test_enqueue_runs_the_identity_gate_before_queueing():
    import inspect
    src = inspect.getsource(outreach_runner.enqueue)
    assert src.index("identity_problems") < src.index("INSERT INTO")


def test_the_suppression_hashes_still_block_by_digest():
    assert outreach_runner._digest("A@B.Com ") == outreach_runner._digest("a@b.com")
    assert len(outreach_runner.suppressed_digests()) >= 11, (
        "the committed wave-1 failures must be loaded")


def test_identity_gate_catches_a_crossed_wire():
    """A row whose insights or link belong to another district must be
    refused. Checked against the committed fallback index so a wrong NAME for
    a real number is caught too."""
    import json
    fb = json.loads((ROOT / "static" / "fallback_index.json").read_text())
    real = fb["districts"][0]
    num, name = real["district_number"], real["district_name"]
    good = {"district_number": num, "district_name": name,
            "email": "x@y.org", "greeting": "Superintendent",
            "subject": f"Every number Texas publishes about {name}",
            "deep_link": f"https://txisd.dev/?d={num}",
            "hook": f"{name} spent money.", "insight_bonds": f"{name} bonds.",
            "insight_debt": "", "insight_trend": ""}
    assert outreach_runner.identity_problems([good]) == []

    crossed = dict(good, deep_link="https://txisd.dev/?d=999999")
    assert outreach_runner.identity_problems([crossed])

    wrong_name = dict(good, district_name="Nowhere ISD",
                      subject="Every number Texas publishes about Nowhere ISD",
                      hook="Nowhere ISD spent money.",
                      insight_bonds="Nowhere ISD bonds.")
    assert outreach_runner.identity_problems([wrong_name]), (
        "a real number wearing another district's name passed the gate")


# --- the drain: safe to fire any number of times -----------------------------

def test_two_racing_drains_claim_disjoint_rows():
    """The property that stops a superintendent getting two copies.

    Vercel can run several instances of one cron, and a manual kick can land
    while the scheduled firing is mid-batch. SKIP LOCKED makes the second
    worker skip rows the first holds rather than wait for them, so two drains
    take disjoint sets.

    Asserted against the SQL because a real two-connection race needs a live
    Postgres, which CI does not have. What CI CAN prove is that the clause
    making the race safe has not been dropped — a plain SELECT ... LIMIT here
    would read as correct in review and double-send under load.
    """
    assert "FOR UPDATE SKIP LOCKED" in outreach_runner.CLAIM_SQL
    assert "status = 'queued'" in outreach_runner.CLAIM_SQL
    assert "'sending'" in outreach_runner.CLAIM_SQL, (
        "a claimed row must leave 'queued' in the same statement, or a third "
        "worker selects it before the first has marked it")


def test_the_sent_log_is_written_the_moment_resend_accepts():
    """A crash between the send and the queue-row update must not re-send:
    the outreach_sent insert (the skip-list) comes first, conflict-safe."""
    import inspect
    src = inspect.getsource(outreach_runner.drain)
    assert src.index("INSERT INTO public.outreach_sent") < \
        src.index("SET status = 'sent'")
    assert "ON CONFLICT (email) DO NOTHING" in src
    assert "ON CONFLICT (rid) DO NOTHING" in src


def test_an_optout_recorded_after_enqueue_is_still_honoured():
    import inspect
    src = inspect.getsource(outreach_runner.drain)
    assert "outreach_optout" in src
    assert "opted out after enqueue" in src


def test_a_crashed_message_is_quarantined_never_retried():
    """A 'sending' row means the message MAY have left; auto-retry is how a
    named official gets the same email twice. Humans decide, with Resend's
    record in front of them."""
    import inspect
    src = inspect.getsource(outreach_runner.drain)
    assert "'queued'" not in src.split("except Exception")[1].split(
        "await asyncio.sleep")[0], (
        "the failure path must not silently re-queue")
    st = outreach_runner.status
    assert "stale_sending" in inspect.getsource(st)
    assert "never auto-retried" in inspect.getsource(st)


def test_unarmed_drain_touches_nothing_and_says_what_is_missing():
    """No RESEND_API_KEY / postal address in Vercel → the drain reports
    'unarmed' and leaves the queue alone, exactly like the workflows that
    skip harmlessly until their secrets exist."""
    import asyncio
    import os
    old = {k: os.environ.pop(k, None)
           for k in ("RESEND_API_KEY", "TAG_POSTAL_ADDRESS")}
    try:
        code, payload = asyncio.run(outreach_runner.drain(pool=None))
        assert code == 200 and payload["status"] == "unarmed"
        assert set(payload["missing"]) == {"RESEND_API_KEY",
                                           "TAG_POSTAL_ADDRESS"}
    finally:
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v


def test_the_throttle_respects_resends_rate_limit():
    assert outreach_runner.THROTTLE_S >= 1.0
    assert outreach_runner.BATCH * outreach_runner.THROTTLE_S <= 45, (
        "a batch must fit one serverless invocation with room to spare")


# --- the endpoints: invisible without the right token ------------------------

@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.api import app
    monkeypatch.setenv("OUTREACH_TOKEN", "test-token-outreach")
    with TestClient(app) as c:
        yield c


def test_wrong_or_missing_token_is_a_404_not_a_403(client):
    """A 403 confirms the route exists; these trigger mass email and must be
    indistinguishable from nothing."""
    for path in ("/api/outreach/status", "/api/cron/outreach-drain"):
        assert client.get(path).status_code == 404
        assert client.get(path, headers={"x-outreach-token": "wrong"}
                          ).status_code == 404
    r = client.post("/api/outreach/enqueue",
                    json={"campaign": "wave3", "confirm": "GO"})
    assert r.status_code == 404


def test_enqueue_refuses_without_the_literal_go(client):
    r = client.post("/api/outreach/enqueue",
                    headers={"x-outreach-token": "test-token-outreach"},
                    json={"campaign": "wave3", "confirm": "yes"})
    assert r.status_code == 400
    assert "GO" in r.json()["refused"]


def test_authorised_calls_without_a_database_degrade_to_503(client):
    h = {"x-outreach-token": "test-token-outreach"}
    assert client.get("/api/outreach/status", headers=h).status_code == 503
    r = client.post("/api/outreach/enqueue", headers=h,
                    json={"campaign": "wave3", "confirm": "GO"})
    assert r.status_code == 503


def test_the_drain_accepts_the_cron_secret_too(client, monkeypatch):
    """Vercel Cron authenticates with CRON_SECRET; a manual kick uses the
    outreach token. Either must work, neither may leak the route's existence
    when wrong."""
    monkeypatch.setenv("CRON_SECRET", "cron-secret-test")
    r = client.get("/api/cron/outreach-drain",
                   headers={"authorization": "Bearer cron-secret-test"})
    assert r.status_code == 503          # authorised; no DB in tests
    r = client.get("/api/cron/outreach-drain",
                   headers={"authorization": "Bearer wrong"})
    assert r.status_code == 404


def test_the_admin_token_is_not_the_ops_token():
    """OPS_TOKEN has already transited a chat transcript. The token that can
    trigger mass email must never share fate with it."""
    src = (ROOT / "src" / "api.py").read_text()
    gate = src[src.index("def _outreach_ok"):src.index("class EnqueueRequest")]
    assert "OUTREACH_TOKEN" in gate
    assert "OPS_TOKEN" not in gate


# --- the deployment carries what the runner needs ----------------------------

def test_the_drain_cron_is_scheduled_and_no_rewrites_appeared():
    import json
    d = json.loads((ROOT / "vercel.json").read_text())
    assert "rewrites" not in d, "rewrites break ALL routing — see CLAUDE.md"
    paths = [c["path"] for c in d["crons"]]
    assert "/api/cron/outreach-drain" in paths
    assert len(paths) <= 2, "Vercel Hobby allows two cron jobs"


def test_the_laptop_script_and_the_server_render_the_same_email():
    """One renderer. scripts/send_outreach.py must import src/outreach_email's
    objects, not carry a second copy that drifts like the money formatters
    once did."""
    script = (ROOT / "scripts" / "send_outreach.py").read_text()
    assert "from src.outreach_email import" in script
    assert "def render_email" not in script
    assert script.count("api.resend.com") == 0, (
        "the Resend client lives in src/outreach_email now")
    import scripts.send_outreach as so
    assert so.render_email is outreach_email.render_email


# --- the second review's findings, pinned ------------------------------------

def test_one_touch_per_district_not_only_per_address():
    """A roster refresh gives a district with a new superintendent a NEW
    address that sails past an address-only skip-list. The skill said this in
    prose; the WHERE clause says it structurally."""
    sql = outreach_runner.ELIGIBLE_SQL
    assert "district_number FROM public.outreach_sent" in sql
    assert "district_number FROM public.outreach_queue" in sql


def test_enqueue_has_a_preview_that_writes_nothing():
    """The laptop flow made reviewing the selection mandatory before any
    send; an HTTP enqueue must not lose that step. confirm=PREVIEW returns
    the exact districts a GO would queue, and inserts nothing."""
    import inspect
    src = inspect.getsource(outreach_runner.enqueue)
    assert "if not write:" in src
    assert src.index("if not write:") < src.index("INSERT INTO"), (
        "the preview branch must return before any write")
    api = (ROOT / "src" / "api.py").read_text()
    assert '"PREVIEW"' in api and 'write=body.confirm == "GO"' in api


def test_every_per_recipient_rail_is_reheld_at_send_time():
    """The queue can sit for weeks while the contact table, the opt-out list
    and the suppression file all move. Enqueue-time checks are stale checks;
    the drain re-holds each one against the row it actually renders."""
    import inspect
    src = inspect.getsource(outreach_runner.drain)
    for marker in ("opted out after enqueue", "suppressed after enqueue",
                   "contact address changed since enqueue",
                   "identity gate failed"):
        assert marker in src, f"send-time rail missing: {marker}"
    # and the gate runs against the CURRENT contact row, pre-render
    assert src.index("identity_problems") < src.index("render_email")


def test_a_delivered_message_can_never_be_marked_error():
    """Once Resend accepts, the message exists in the world. A DB failure
    after that point is bookkeeping — marking the row 'error' invites an
    operator to retry a delivery, which re-emails a named official."""
    import inspect
    src = inspect.getsource(outreach_runner.drain)
    accepted = src[src.index("# Resend ACCEPTED"):]
    assert "status = 'error'" not in accepted, (
        "a post-acceptance failure path can mark a delivered message error")
    assert "sent; log write failed" in accepted
    assert "sent += 1" in accepted.split("try:")[0], (
        "the sent counter must reflect acceptance, not bookkeeping success")


def test_provably_unsent_rows_are_released_not_quarantined():
    """Before the first /emails call nothing has left, so a failure there
    (domain check down, invocation budget hit) releases the claim; after a
    send is attempted the row must NEVER silently return to 'queued'."""
    import inspect
    src = inspect.getsource(outreach_runner.drain)
    assert "released: domain check unavailable" in src
    assert "released: invocation budget" in src
    # the resend-failure branch marks error, never re-queues
    resend_fail = src.split("resend_request", 1)[1]
    resend_fail = resend_fail[:resend_fail.index("# Resend ACCEPTED")]
    assert "status = 'error'" in resend_fail
    assert "'queued'" not in resend_fail


def test_the_wall_clock_guard_fits_the_configured_duration():
    """The platform kills the invocation at maxDuration; rows claimed but
    never attempted would be stranded. The guard stops early — and it must
    actually fit inside what vercel.json configures."""
    import json
    assert outreach_runner.WALL_BUDGET_S < 60
    d = json.loads((ROOT / "vercel.json").read_text())
    assert d["functions"]["api/index.py"]["maxDuration"] == 60
    assert "rewrites" not in d


def test_the_cron_handler_records_runs_with_monotonic_time():
    """_record_cron_run subtracts time.monotonic(); a time.time() start
    yields a negative trillion-ms duration that overflows the integer column
    and the run row silently never writes — a permanent gap in the exact
    watchdog built after the intel cron failed silently for four days."""
    api = (ROOT / "src" / "api.py").read_text()
    fn = api[api.index("async def cron_outreach_drain"):
             api.index("async def outreach_status")]
    assert "started = time.monotonic()" in fn
    assert "started = time.time()" not in fn


def test_the_status_page_survives_a_dead_drain():
    """stale_sending rows carry datetimes; without jsonable_encoder the page
    500s exactly when a drain has died and the operator most needs it."""
    api = (ROOT / "src" / "api.py").read_text()
    fn = api[api.index("async def outreach_status"):]
    fn = fn[:fn.index("@app.")]
    assert "jsonable_encoder" in fn


def test_the_cron_secret_comparison_cannot_500_on_weird_bytes():
    """compare_digest raises TypeError on a non-ASCII str; an unhandled
    exception answers 500 and confirms the hidden route exists — the exact
    defect _ops_ok documents. Both sides are encoded, inside a try."""
    api = (ROOT / "src" / "api.py").read_text()
    fn = api[api.index("async def cron_outreach_drain"):
             api.index("async def outreach_status")]
    assert 'encode("utf-8")' in fn
    assert "except Exception" in fn.split("cron_ok")[1].split("if not")[0]


# --- the third review's findings, pinned -------------------------------------

def test_an_all_suppressed_tail_answers_instead_of_crashing():
    """The campaign tail can be entirely suppressed addresses; reading
    take[0] off the post-filter selection was a 500 to the operator instead
    of 'nobody eligible'. One emptiness guard, after EVERY filter."""
    import inspect
    src = inspect.getsource(outreach_runner.enqueue)
    assert src.index("suppressed_digests()") < src.index("if not rows:"), (
        "the emptiness guard must come after the suppression filter")


def test_a_fresh_database_gets_every_table_the_runner_touches():
    """The self-applying doctrine: no hand steps. The runner reads AND writes
    outreach_sent/outreach_optout, which were born in a hand-applied SQL
    file — a fresh or forked database (the exact scenario this whole feature
    answers) must get them from ensure_schema, or enqueue 500s and a drain
    strands its claimed batch."""
    for name in ("public.outreach_sent", "public.outreach_optout"):
        assert f"CREATE TABLE IF NOT EXISTS {name}" in migrations.OUTREACH_DDL
    # shapes mirror the original file exactly — three copies is two too many,
    # so at least hold them identical
    state = (ROOT / "sql" / "create_outreach_state.sql").read_text()
    for col in ("email           text PRIMARY KEY", "district_number text",
                "message_id      text", "noted_at timestamptz DEFAULT now()"):
        assert col in state and col in migrations.OUTREACH_DDL, col


def test_the_wall_budget_accounts_for_an_in_flight_resend_call():
    """40s of budget plus a 30s laptop-default timeout overruns the 60s
    maxDuration — the tail message hangs, the platform kills the invocation,
    and the unattempted remainder is stranded. The drain passes its own
    shorter timeout, and budget + timeout must stay under the cap."""
    import inspect
    assert outreach_runner.WALL_BUDGET_S + outreach_runner.RESEND_TIMEOUT_S < 60
    src = inspect.getsource(outreach_runner.drain)
    assert "RESEND_TIMEOUT_S" in src.split("resend_request", 1)[1].split(")")[0]
    import scripts.send_outreach  # noqa: F401 — laptop path keeps the 30s default
    from src.outreach_email import resend_request
    assert resend_request.__defaults__[-1] == 30


def test_a_mid_batch_abort_releases_what_provably_never_left():
    """A pooler drop during a bookkeeping UPDATE used to propagate and strand
    every not-yet-attempted row in quarantine. The loop is guarded whole; the
    one ambiguous row (its Resend call had started) is never released, and
    everything after it is."""
    import inspect
    src = inspect.getsource(outreach_runner.drain)
    assert "released: drain aborted mid-batch" in src
    assert "claimed[i + 1:] if attempted else claimed[i:]" in src
    assert "attempted = True" in src
    assert src.index("attempted = True") < src.index("resend_request"), (
        "the attempt flag must be set BEFORE the send starts, or a crash "
        "inside the call releases a message that may have left")


def test_a_failed_drain_keeps_its_reason_in_the_cron_log():
    """A 503 drain outcome carries only an 'error' key; recording
    detail=None showed the watchdog a failing job with no stated cause."""
    api = (ROOT / "src" / "api.py").read_text()
    fn = api[api.index("async def cron_outreach_drain"):
             api.index("async def outreach_status")]
    assert 'payload.get("error")' in fn


def test_provider_and_legacy_error_text_is_never_returned_verbatim():
    sentinel = "delivery failed for recipient@example.org?token=sk-secret"
    assert outreach_runner._safe_queue_error_detail(sentinel) == (
        "failure detail redacted"
    )
    assert outreach_runner._safe_queue_error_detail(
        "delivery attempt failed") == "delivery attempt failed"
    src = __import__("inspect").getsource(outreach_runner.drain)
    assert "str(exc)" not in src
    assert "drain aborted mid-batch ({exc})" not in src


def test_the_identity_gates_name_map_is_read_once_not_per_message():
    import inspect
    assert hasattr(outreach_runner._site_names, "cache_info"), (
        "_site_names lost its cache — 15 blocking 82KB JSON parses per drain")
    src = inspect.getsource(outreach_runner.identity_problems)
    assert "_site_names()" in src


# --- concurrency -------------------------------------------------------------

def test_the_claim_runs_inside_a_transaction():
    """SKIP LOCKED only holds a lock for the life of its transaction. Outside
    one, the lock is released the moment the statement ends and the guarantee
    is gone."""
    src = (ROOT / "src" / "outreach_runner.py").read_text()
    body = src.split("async def drain(")[1]
    claim_at = body.index("CLAIM_SQL, BATCH")
    window = body[max(0, claim_at - 220): claim_at]
    assert "async with conn.transaction():" in window, (
        "the claim must be inside an explicit transaction")


def test_the_batch_cannot_outrun_the_function_timeout():
    """maxDuration is 60s in vercel.json. A batch that can spend longer than
    that is killed mid-send, and a kill after Resend accepts is exactly the
    ambiguity the failure policy exists to avoid."""
    import json as _json
    vercel = _json.loads((ROOT / "vercel.json").read_text())
    limit = vercel["functions"]["api/index.py"]["maxDuration"]
    worst = outreach_runner.WALL_BUDGET_S + outreach_runner.RESEND_TIMEOUT_S
    assert worst < limit, (
        f"worst case {worst}s against a {limit}s function limit — the wall "
        f"budget plus one full Resend timeout must finish inside it")


def test_a_stale_claim_is_recoverable():
    """A worker killed mid-batch leaves rows in 'sending' with nothing coming
    back for them. Without a recovery window those rows are stranded forever
    and the wave silently stops short."""
    assert outreach_runner.STALE_SENDING_S > 0
    src = (ROOT / "src" / "outreach_runner.py").read_text()
    assert "STALE_SENDING_S" in src.split("async def status(")[1], (
        "the status endpoint must surface stale claims, or a stranded row is "
        "invisible to the person who would fix it")
