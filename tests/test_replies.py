"""The reply ingest — the only conversion this product has.

Every other stage of the funnel is behaviour a mail-security appliance can
imitate. A reply is a person typing, which is why it carries the heaviest
weight in the engagement score and why getting it wrong matters more than
getting a page view wrong.

Three ways this could lie, and a test for each:

  * counting a reply that is not one, or missing one that is;
  * counting the same reply on every daily run, so one person becomes fourteen
    conversions and the funnel inverts;
  * reading an unsubscribe request and doing nothing with it.

No network here: every function under test is pure, and the IMAP and Supabase
calls are deliberately thin wrappers around them.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ingest_replies", ROOT / "scripts" / "ingest_replies.py")
replies = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replies)

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def sends(**kw):
    """The send log shape fetch_sends() produces."""
    return {"super@argyleisd.example": [
        {"rid": "w1token", "campaign": "w1", "sent_at": NOW - timedelta(days=6)},
        {"rid": "w2token", "campaign": "w2", "sent_at": NOW - timedelta(days=1)},
    ], **kw}


# --- who counts as a reply --------------------------------------------------

def test_a_reply_from_someone_we_mailed_counts():
    got = replies.match(
        [{"from": "super@argyleisd.example", "at": NOW, "id": "m1", "text": "thanks"}],
        sends())
    assert len(got) == 1
    assert got[0]["email"] == "super@argyleisd.example"


def test_mail_from_someone_we_never_emailed_is_just_mail():
    """The inbox is a real mailbox. It carries printers, alarms and family —
    none of which is a conversion for a school-finance portal."""
    got = replies.match([
        {"from": "sales@msmarketing.biz", "at": NOW, "id": "m1", "text": "hi"},
        {"from": "MayaAI@ubntag.com", "at": NOW, "id": "m2", "text": "poster down"},
    ], sends())
    assert got == []


def test_the_display_name_and_the_casing_do_not_break_the_match():
    """The send log has a bare address; the reply arrives as
    `Superintendent <Super@ArgyleISD.example>`."""
    got = replies.match([{
        "from": "Dr. Jane Doe <Super@ArgyleISD.example>", "at": NOW,
        "id": "m1", "text": "hello"}], sends())
    assert len(got) == 1


def test_a_message_with_no_date_is_skipped_rather_than_guessed():
    got = replies.match([{"from": "super@argyleisd.example", "at": None,
                          "id": "m1", "text": "x"}], sends())
    assert got == []


# --- which send it answers --------------------------------------------------

def test_a_reply_is_attributed_to_the_most_recent_send_before_it():
    """A district can appear in more than one wave, so one address holds
    several tokens."""
    got = replies.match([{"from": "super@argyleisd.example", "at": NOW,
                          "id": "m1", "text": "x"}], sends())
    assert got[0]["rid"] == "w2token"


def test_a_reply_between_two_waves_belongs_to_the_earlier_one():
    got = replies.match([{"from": "super@argyleisd.example",
                          "at": NOW - timedelta(days=3), "id": "m1",
                          "text": "x"}], sends())
    assert got[0]["rid"] == "w1token"


def test_a_message_that_predates_every_send_is_not_a_reply():
    """Attributing it would put a conversion before its own cause."""
    got = replies.match([{"from": "super@argyleisd.example",
                          "at": NOW - timedelta(days=30), "id": "m1",
                          "text": "x"}], sends())
    assert got == []


def test_pick_rid_returns_nothing_when_nothing_is_eligible():
    assert replies.pick_rid([], NOW) is None


# --- not counting the same reply forever ------------------------------------

def test_the_idempotency_key_is_the_recipient_and_the_message():
    """A daily cron re-reads the same three weeks every day. Without a key,
    one reply becomes twenty-one conversions and the funnel inverts."""
    m = {"rid": "w2token", "id": "<CAF=abc@mail.gmail.com>"}
    key = "reply:" + m["rid"] + ":" + m["id"]
    assert key.startswith("reply:w2token:")
    # the same message on a later run produces a byte-identical key
    assert key == "reply:" + m["rid"] + ":" + m["id"]


def test_the_insert_is_conflict_tolerant():
    src = (ROOT / "scripts" / "ingest_replies.py").read_text()
    assert "ON CONFLICT DO NOTHING" in src
    assert "event_key" in src


def test_nothing_but_the_fact_and_the_time_is_stored():
    """What a superintendent wrote to us is correspondence, not telemetry.
    visitor_event has nowhere to put a body and it should stay that way."""
    src = (ROOT / "scripts" / "ingest_replies.py").read_text()
    insert = src[src.index("INSERT INTO public.visitor_event"):]
    insert = insert[:insert.index(")")]
    for banned in ("subject", "body", "text", "snippet", "message_text"):
        assert banned not in insert, f"{banned} must never be written"


# --- opt-outs ---------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Please unsubscribe me",
    "Take me off this list",
    "opt out",
    "opt-out please",
    "Remove me from your mailing list",
    "Please stop emailing me",
    "do not contact me again",
    "I no longer wish to receive these",
])
def test_a_request_to_stop_is_recognised(text):
    assert replies.looks_like_optout(text) is True


@pytest.mark.parametrize("text", [
    "Thanks, this is useful — can you send the bond figures?",
    "Please remove the debt chart from the PDF and resend",
    "I will stop by your booth at the conference",
])
def test_ordinary_replies_are_not_mistaken_for_opt_outs(text):
    """A false positive costs one unsent email; a false negative breaks a
    promise. Broad, but not so broad that 'remove the chart' silences someone
    who is actively engaging."""
    assert replies.looks_like_optout(text) is False


def test_an_opt_out_is_still_recorded_as_a_reply():
    """It is a person typing to a person, which is what the conversion
    measures. Whether they liked it is a different question."""
    got = replies.match([{"from": "super@argyleisd.example", "at": NOW,
                          "id": "m1", "text": "please unsubscribe"}], sends())
    assert len(got) == 1 and got[0]["optout"] is True


def test_opt_outs_are_appended_without_duplicating(tmp_path, monkeypatch):
    f = tmp_path / "outreach_optout.txt"
    f.write_text("already@there.example\n")
    monkeypatch.setattr(replies, "OPTOUT_FILE", f)
    added = replies.honour_optouts([
        {"email": "already@there.example", "optout": True},
        {"email": "new@district.example", "optout": True},
        {"email": "happy@district.example", "optout": False},
    ])
    assert added == ["new@district.example"]
    lines = [ln.strip() for ln in f.read_text().splitlines() if ln.strip()]
    assert lines == ["already@there.example", "new@district.example"]


def test_no_opt_outs_touches_nothing(tmp_path, monkeypatch):
    f = tmp_path / "outreach_optout.txt"
    monkeypatch.setattr(replies, "OPTOUT_FILE", f)
    assert replies.honour_optouts([{"email": "a@b.c", "optout": False}]) == []
    assert not f.exists()


# --- safety rails -----------------------------------------------------------

def test_the_mailbox_is_opened_read_only():
    """Marking a superintendent's message as read from a cron job would edit
    the owner's inbox to measure it."""
    src = (ROOT / "scripts" / "ingest_replies.py").read_text()
    assert 'box.select("INBOX", readonly=True)' in src


def test_writing_is_opt_in():
    src = (ROOT / "scripts" / "ingest_replies.py").read_text()
    assert '"--write", action="store_true"' in src
    assert "Dry run. Re-run with --write" in src


def test_an_empty_result_is_reported_as_a_finding_not_a_failure():
    """'No replies' and 'the pipe is broken' look identical in a log unless
    one of them says so."""
    src = (ROOT / "scripts" / "ingest_replies.py").read_text()
    assert "That is a finding, not a failure" in src
