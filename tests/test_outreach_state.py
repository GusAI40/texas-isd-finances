"""The outreach state must survive container loss — these tests hold the
durability layer to its contract, entirely offline.

The failure being defended against: data/outreach_sent.csv and
data/outreach_optout.txt live only in a disposable container. Container loss
plus a re-run would re-email everyone, including people who opted out — a
broken promise to named people. The state is therefore mirrored in Supabase
(sql/create_outreach_state.sql), pushed/pulled by
scripts/sync_outreach_state.py, and merged into send_outreach's skip-lists
before any real send. No test here touches the network: remote reads are
monkeypatched.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.send_outreach as so  # noqa: E402

SQL = (ROOT / "sql/create_outreach_state.sql").read_text()
SYNC = (ROOT / "scripts/sync_outreach_state.py").read_text()


# --- the schema and the sync script keep their contracts ----------------------

def test_sql_creates_both_tables_with_email_as_primary_key():
    assert "CREATE TABLE IF NOT EXISTS public.outreach_sent" in SQL
    assert "CREATE TABLE IF NOT EXISTS public.outreach_optout" in SQL
    # email PRIMARY KEY on both — the dedupe key ON CONFLICT relies on
    assert SQL.count("email") >= 2 and SQL.count("PRIMARY KEY") == 2
    for col in ("district_number", "message_id", "sent_at", "noted_at"):
        assert col in SQL, f"schema lost the {col} column"


def test_sql_explains_the_broken_promise_risk():
    """The comment header is load-bearing: the next agent must know WHY this
    state is durable before deciding to 'simplify' it away."""
    assert "promise" in SQL and "opt-out" in SQL.lower()


def test_sync_push_is_idempotent_by_construction():
    """Push must be INSERT ... ON CONFLICT DO NOTHING — re-running a sync can
    never overwrite or duplicate a remote row."""
    assert SYNC.count("ON CONFLICT (email) DO NOTHING") == 2  # sent + optout


def test_sync_pull_refuses_to_shrink_the_local_record():
    assert "refusing to pull" in SYNC


def test_send_outreach_still_imports_and_keeps_its_surface():
    """The durability layer was additive — every pre-existing entry point
    survives."""
    for name in ("render_email", "verify_targets", "load_sent", "load_optout",
                 "log_sent", "main"):
        assert callable(getattr(so, name))


def test_send_outreach_mirror_insert_is_conflict_safe():
    src = (ROOT / "scripts/send_outreach.py").read_text()
    assert "ON CONFLICT (email) DO NOTHING" in src


# --- the merge: local ∪ remote, remote wins by union --------------------------

@pytest.fixture()
def local_state(tmp_path, monkeypatch):
    """Point the module's file constants at a temp dir with known contents."""
    sent = tmp_path / "outreach_sent.csv"
    sent.write_text(
        "email,district_number,message_id,sent_at\n"
        "a@local.example,001902,mid-1,2026-08-11T17:34:24Z\n"
        "b@local.example,001903,mid-2,2026-08-11T17:34:26Z\n")
    opt = tmp_path / "outreach_optout.txt"
    opt.write_text("# a comment line\nStop@Local.example\n\n")
    monkeypatch.setattr(so, "SENT_LOG", sent)
    monkeypatch.setattr(so, "OPTOUT", opt)
    return sent, opt


def test_load_sent_unions_local_and_remote(local_state, monkeypatch):
    monkeypatch.setattr(
        so, "_remote_emails",
        lambda table: {"b@local.example", "c@remote.example"}
        if table == "outreach_sent" else set())
    assert so.load_sent() == {"a@local.example", "b@local.example",
                              "c@remote.example"}


def test_load_optout_unions_and_lowercases_both_sides(local_state, monkeypatch):
    monkeypatch.setattr(
        so, "_remote_emails",
        lambda table: {"Halt@Remote.example"}
        if table == "outreach_optout" else set())
    assert so.load_optout() == {"stop@local.example", "halt@remote.example"}


def test_without_pat_load_functions_are_local_only(local_state, monkeypatch):
    """No SUPABASE_PAT → pure local behavior, byte-for-byte what the script
    did before the durability layer. No network call is even attempted."""
    monkeypatch.delenv("SUPABASE_PAT", raising=False)
    monkeypatch.setattr(so, "_sb_sql",
                        lambda *a, **k: pytest.fail("network call attempted"))
    assert so.load_sent() == {"a@local.example", "b@local.example"}
    assert so.load_optout() == {"stop@local.example"}


def test_remote_read_failure_fails_closed(local_state, monkeypatch):
    """PAT set but Supabase unreachable → refuse, loudly. An empty remote
    answer would silently shrink the skip-list and re-email opt-outs."""
    monkeypatch.setenv("SUPABASE_PAT", "sbp_fake")
    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(so, "_sb_sql", boom)
    with pytest.raises(RuntimeError, match="opt-outs"):
        so.load_sent()


# --- the mirror write: best effort, loud on failure ---------------------------

ROW = {"email": "new@example.com", "district_number": "057905"}


def test_log_sent_writes_local_and_mirrors_remotely(local_state, monkeypatch):
    sent, _ = local_state
    monkeypatch.setenv("SUPABASE_PAT", "sbp_fake")
    calls = []
    monkeypatch.setattr(so, "_sb_sql", lambda q, pat: calls.append(q) or [])
    so.log_sent(ROW, "mid-9")
    assert "new@example.com" in sent.read_text()          # local first
    assert len(calls) == 1
    assert "INSERT INTO public.outreach_sent" in calls[0]
    assert "'new@example.com'" in calls[0] and "'057905'" in calls[0]


def test_log_sent_survives_remote_failure_with_loud_warning(
        local_state, monkeypatch, capsys):
    """The message is already SENT when the mirror fails — aborting would
    help nobody. But the warning must demand a manual sync."""
    sent, _ = local_state
    monkeypatch.setenv("SUPABASE_PAT", "sbp_fake")
    def boom(*a, **k):
        raise OSError("supabase down")
    monkeypatch.setattr(so, "_sb_sql", boom)
    so.log_sent(ROW, "mid-9")                             # must NOT raise
    assert "new@example.com" in sent.read_text()          # local log intact
    err = capsys.readouterr().err
    assert "WARNING" in err and "sync_outreach_state" in err


def test_log_sent_quotes_sql_literals():
    """An email with a quote must not break (or inject into) the mirror SQL."""
    assert so._sb_quote("o'brien@x.com") == "'o''brien@x.com'"


# --- the re-send footgun ------------------------------------------------------

def mod_floor():
    import importlib.util
    from pathlib import Path as _P
    sp = _P(__file__).resolve().parents[1] / "scripts" / "send_outreach.py"
    spec = importlib.util.spec_from_file_location("_wm", sp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.watermark_floor()


def test_watermark_is_committed_and_matches_the_waves():
    """data/outreach_sent.csv is gitignored and has never been committed, and
    _remote_emails() returns an empty set (not an error) when SUPABASE_PAT is
    unset. So a fresh clone with neither resolves an EMPTY skip-list. The
    watermark is the only send-state that survives that, which is why it is
    committed and why its total must equal the waves it lists."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "data" / "outreach_watermark.json"
    assert p.exists(), "the watermark must be committed — it is the re-send guard"
    d = json.loads(p.read_text())
    assert d["sent_total"] == sum(w["sent"] for w in d["waves"]), \
        "sent_total must equal the sum of the waves it lists"
    assert d["sent_total"] >= 571
    # The guard compares against unique_emails, so that is the number that must
    # track reality. It can never exceed the send count.
    assert d["unique_emails"] <= d["sent_total"]
    assert mod_floor() == d["unique_emails"]


def test_send_refuses_when_the_skiplist_shrank():
    """A skip-list cannot shrink: nobody un-receives an email. Smaller than the
    watermark means state was lost, and sending would re-mail people. This is
    the exact fresh-container shape: no local log, no PAT, skip-list of 0."""
    import importlib.util
    from pathlib import Path as _P
    sp = _P(__file__).resolve().parents[1] / "scripts" / "send_outreach.py"
    spec = importlib.util.spec_from_file_location("_send", sp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    floor = mod.watermark_floor()
    assert floor >= 571

    msg = mod.skiplist_shrank(0)           # fresh container: nothing known
    assert msg and "refusing" in msg
    assert "sync_outreach_state.py --pull" in msg, "must say how to recover"

    assert mod.skiplist_shrank(floor) == ""       # exactly the watermark: fine
    assert mod.skiplist_shrank(floor + 9) == ""   # grown since: fine
    assert mod.skiplist_shrank(floor - 1) != ""   # one short: refuse

    # and the refusal must come before anything is sent. The skip-list size is
    # read off the selection report rather than a local variable, so that the
    # dry run and the send can compute the wave the same way — but the ORDER is
    # the guarantee: refuse, then loop.
    src = sp.read_text()
    # The dry run calls skiplist_shrank too, but only to WARN — it sends
    # nothing, so matching that call would let the send's own rail be deleted
    # with the suite still green. Look for the guard INSIDE the send path:
    # between the real-send marker and the loop that hands messages to Resend.
    send_path = src[src.index("# ---- the real send"):
                    src.index("for i, row in enumerate(todo, 1)")]
    # Anchored to the guard's own block: searching for "return 1" anywhere
    # after the call passes on any LATER rail's return, so the guard could be
    # reduced to a print and the suite would stay green. Matched as a shape
    # rather than sliced at the first blank line, so a cosmetic newline or an
    # added comment cannot fail the build.
    import re as _re
    assert _re.search(
        r"skiplist_shrank\([^)]*\)\s*\n"
        r"\s*if refusal and not args\.ignore_watermark:\s*\n"
        r"(?:\s*(?:#.*)?\n|\s*print\(.*\n)*"
        r"\s*return 1\b", send_path), (
        "the send's watermark guard must ABORT — a fresh container with no "
        "state could otherwise re-email every superintendent already contacted")
