"""The outreach email is a published surface too — the same framing rules that
govern the site govern what lands in a superintendent's inbox, plus the rules
email adds: an unsubscribe that works, a postal address, and rails that make
the accidental mass-send impossible.

These run without a network and without the gitignored merge CSV: the renderer
is a pure function of a row, so the tests hand it rows.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_outreach_merge import greeting_from, hook, insight_bonds, insight_debt, insight_trend  # noqa: E402
from scripts.send_outreach import render_email  # noqa: E402

ROW = {
    "district_number": "061910",
    "district_name": "Argyle ISD",
    "greeting": "Dr. Carpenter",
    "email": "someone@argyleisd.com",
    "deep_link": "https://txisd.dev/?d=061910",
    "hook": hook("Argyle ISD", {"year": 2025, "enrollment": 6114,
                                "all_funds_per_student": 31704,
                                "operating_per_student": 10357,
                                "construction_debt_share_pct": 67}),
    "insight_bonds": "Voters in Argyle ISD have decided 14 bond propositions "
                     "since 1997 and approved 11 of them.",
    "insight_debt": "As of fiscal 2025, Argyle ISD owes $1.2B on bonds "
                    "already sold.",
    "insight_trend": "Instruction's share rose from 53.0% to 56.2%.",
    "subject": "Every number Texas publishes about Argyle ISD",
}
POSTAL = "123 Main St, Suite 1, Dallas TX 75201"
UNSUB = "mailto:gus@ubntag.com?subject=unsubscribe"


def _rendered():
    return render_email(ROW, POSTAL, UNSUB)


# --- frame honesty travels into the inbox -------------------------------------

def test_the_hook_never_gives_all_funds_without_operating():
    """The Argyle rule, applied to the email: at 67% construction share the
    all-funds figure must arrive chained to the operating figure."""
    h = ROW["hook"]
    assert "$31,704" in h and "$10,357" in h
    assert "building them" in h


def test_the_email_carries_the_hook_in_both_parts():
    body, text = _rendered()
    assert "$10,357" in body and "$10,357" in text


def test_low_construction_districts_get_the_operating_frame_only():
    h = hook("Elkhart ISD", {"year": 2025, "enrollment": 1100,
                             "all_funds_per_student": 13284,
                             "operating_per_student": 12000,
                             "construction_debt_share_pct": 10})
    assert "operations" in h and "all-funds" not in h


# --- the greeting never guesses a gendered title ------------------------------

def test_greeting_uses_published_honorific_or_neutral_title():
    assert greeting_from("DR JOE E SATTERWHITE III") == "Dr. Satterwhite"
    assert greeting_from("MR ROB BRIGGS") == "Mr. Briggs"
    assert greeting_from("KRISTIN COOK") == "Superintendent Cook"
    assert greeting_from("") == "Superintendent"


# --- what every email must contain --------------------------------------------

def test_email_contains_deep_link_greeting_and_gift_frame():
    body, text = _rendered()
    for part in (body, text):
        assert "https://txisd.dev/?d=061910" in part
        assert "Dr. Carpenter" in part
    assert "It&rsquo;s yours." in body        # gift first, pitch second
    assert "reply" in text.lower()            # the call invitation


def test_email_carries_unsubscribe_postal_address_and_source_disclosure():
    """CAN-SPAM: physical postal address + a working opt-out. And this project
    adds its own rule: say where the data AND the recipient's address came
    from."""
    body, text = _rendered()
    for part in (body, text):
        assert POSTAL in part
        assert UNSUB in part
    assert "AskTED" in body                   # how we got their address
    assert "/sources" in body                 # how we got the numbers
    for part in (body, text):                 # CAN-SPAM: identified as an ad
        assert "commercial message" in part


def test_email_is_signed_by_a_reachable_person():
    """The signoff is a person a superintendent can call back — name, phone
    and email — not an anonymous team."""
    body, text = _rendered()
    for part in (body, text):
        assert "Gus Sanchez" in part
        assert "909-268-6875" in part
        assert "gus@ubntag.com" in part


def test_email_never_uses_the_word_deficit():
    """The word the frame audit banned from mixed comparisons — the email
    doesn't compare frames at all, so it must not appear."""
    body, text = _rendered()
    assert "deficit" not in body.lower() and "deficit" not in text.lower()


def test_corrections_are_invited():
    body, _ = _rendered()
    assert "corrections with credit" in body


def test_email_discloses_ai_and_links_the_transparency_page():
    """The owner's rule: never shy away from it — every communication states
    that AI was used across the whole system, that figures carry a margin of
    error, and links the page that tells the full story."""
    body, text = _rendered()
    for part in (body, text):
        assert "https://txisd.dev/transparency" in part
        assert "margin of" in part
        assert "own risk" in part
    assert "Artificial intelligence" in body


# --- insight sentences state their frame --------------------------------------

def test_debt_insight_names_the_stock_frame():
    s = insight_debt("061910", "Argyle ISD",
                     {"061910": {"total": 1225125606, "per_student": 200380,
                                 "interest_share_pct": 45.3,
                                 "clears_in": 2056}})
    assert "bonds already sold" in s          # the stock, not the flow
    assert "interest not yet paid" in s       # names what the total includes


def test_absent_records_are_reported_as_absences_not_zeros():
    assert "no school bond election" in insight_bonds("999999", "Nowhere ISD", {})
    assert "no outstanding" in insight_debt("999999", "Nowhere ISD", {})
    assert insight_trend("999999", "Nowhere ISD", {},
                         {"instruction_share": {"first": 57.8, "last": 54.5}}) == ""


def test_trend_insight_gives_the_state_line_beside_the_district():
    s = insight_trend("061910", "Argyle ISD",
                      {"061910": {"change": {"instruction_share": {
                          "first": 53.0, "last": 56.2, "change": 3.2,
                          "first_year": 2009, "last_year": 2025}}}},
                      {"instruction_share": {"first": 57.8, "last": 54.5}})
    assert "53.0%" in s and "56.2%" in s      # the district
    assert "57.8%" in s and "54.5%" in s      # the state, for scale


# --- the graphic the email hot-links is really served -------------------------

def test_the_pipeline_graphic_exists_and_has_a_route():
    assert (ROOT / "static" / "tag_pipeline.png").exists()
    api = (ROOT / "src" / "api.py").read_text()
    assert "/static/tag-pipeline.png" in api


# --- every address we hand a superintendent must be a mailbox we read ---------

def test_no_unmonitored_address_can_reach_a_recipient():
    """gus@ubntag.com is the only mailbox anyone watches.

    The unsubscribe fallback was hello@txisd.dev — a domain that resolves and
    an inbox that does not exist. It sat behind two `or` clauses that always
    won, so it never actually shipped; that is luck, not design. A reply or an
    unsubscribe sent to an address nobody opens is indistinguishable from being
    ignored, and this campaign has already gone to 571 superintendents.

    Checked against the parsed string literals, not the file text: a comment
    explaining which address was retired would otherwise fail this test, which
    is a check firing on prose about the thing instead of the thing.
    """
    import ast
    tree = ast.parse((ROOT / "scripts" / "send_outreach.py").read_text())
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    joined = "\n".join(literals)
    for dead in ("hello@txisd.dev", "reports@txisd.dev", "noreply@"):
        assert dead not in joined, (
            f"{dead} is a live string in the sender — every address a "
            "recipient can reply to must be a mailbox someone reads")
    assert "gus@ubntag.com" in joined


# --- known-dead addresses are refused before the provider sees them -----------

def test_the_suppression_list_is_committed_and_blocks_by_hash():
    """6 addresses hard-bounced and 5 were provider-suppressed in wave 1.
    Mailing them again reaches nobody and teaches every mail filter that this
    domain writes to dead addresses — which costs delivery to the live ones.

    The sent-log also covers them, but it is gitignored and container-only,
    and this repo has already once resolved a skip-list of ZERO in a fresh
    container. So the suppression is committed — as hashes, because contact
    data never is.
    """
    import json as _json

    from scripts.send_outreach import SUPPRESSION, _digest, load_suppressed

    assert SUPPRESSION.exists(), "data/outreach_suppression.json must be committed"
    data = _json.loads(SUPPRESSION.read_text())
    entries = data["entries"]
    assert len(entries) >= 11, "the 11 wave-1 failures must be recorded"
    for h, meta in entries.items():
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h), (
            "entries must be SHA-256 hex — never an address")
        assert "@" not in _json.dumps(meta), "no contact data in the metadata"
        assert meta["status"] in ("bounced", "suppressed", "complained")
    # and the loader actually reads them
    assert load_suppressed() == set(entries)
    # digest is over the canonicalised address, so case cannot dodge the block
    assert _digest("A@B.Com ") == _digest("a@b.com")


# --- the dry run must review the wave that would actually be sent -------------

def _rows(*nums):
    return [{"district_number": n, "district_name": f"District {n}",
             "email": f"super@{n}.org"} for n in nums]


def test_the_dry_run_previews_the_real_targets_not_the_top_of_the_file(monkeypatch):
    """The dry run IS the review step the runbook names, and it used to render
    ``rows[:previews]`` — the head of the merge file — while the send mailed a
    filtered list. From wave 2 onward those disagreed completely: the previews
    showed districts contacted months earlier that would never be mailed again.
    The send was never at risk (it filters, and the watermark stands behind
    it); what was broken is that the review reviewed the wrong emails, which is
    how a bad wave gets approved by someone doing everything right.
    """
    from scripts import send_outreach as so

    rows = _rows("001902", "001903", "163902", "163903")
    monkeypatch.setattr(so, "load_sent", lambda: {"super@001902.org",
                                                  "super@001903.org"})
    monkeypatch.setattr(so, "load_optout", lambda: set())
    monkeypatch.setattr(so, "load_suppressed", lambda: set())

    todo, report = so.select_targets(rows, limit=0)
    assert [r["district_number"] for r in todo] == ["163902", "163903"], (
        "an already-contacted district reached the review list")
    assert report["eligible"] == 2 and report["excluded"] == 2


def test_the_selection_is_reported_so_the_owner_can_see_it_is_deterministic(monkeypatch):
    """Counts alone cannot show WHICH 200. First and last district make the
    selection checkable by eye against a re-run."""
    from scripts import send_outreach as so

    monkeypatch.setattr(so, "load_sent", lambda: set())
    monkeypatch.setattr(so, "load_optout", lambda: set())
    monkeypatch.setattr(so, "load_suppressed", lambda: set())

    rows = _rows("001902", "163902", "220901")
    todo, report = so.select_targets(rows, limit=2)
    text = so.describe_selection(todo, report)
    assert "WOULD SEND                 : 2" in text
    assert "first : 001902" in text and "last  : 163902" in text
    assert "eligible, never contacted  : 3" in text, (
        "the limit must not be reported as the eligible pool")


def test_the_exclusion_counts_reconcile_even_when_the_reasons_overlap(monkeypatch):
    """The three reasons are not disjoint — in the real state file every
    opt-out and every dead address is ALSO in the skip-list, because you only
    bounce or unsubscribe after being mailed. So `excluded` must be their
    UNION; summing them would over-count and the printed figures would not
    subtract to the eligible pool. A fixture with empty sets passes for any
    definition, including the wrong one, so this one overlaps deliberately.
    """
    from scripts import send_outreach as so

    rows = _rows("001902", "001903", "163902")
    # 001902 is all three at once; 001903 is only opted out; 163902 is clean
    monkeypatch.setattr(so, "load_sent", lambda: {"super@001902.org"})
    monkeypatch.setattr(so, "load_optout",
                        lambda: {"super@001902.org", "super@001903.org"})
    monkeypatch.setattr(so, "load_suppressed",
                        lambda: {so._digest("super@001902.org")})

    todo, report = so.select_targets(rows, limit=0)
    assert (report["already_sent"], report["opted_out"], report["dead"]) == (1, 2, 1)
    # 2, not 4: summing the three reasons would count 001902 three times.
    # (in_merge - excluded == eligible is true by construction, so it is not
    # asserted here — it would pass for a wrong `eligible` too.)
    assert report["excluded"] == 2, "overlapping reasons were double-counted"
    assert report["eligible"] == 1
    assert [r["district_number"] for r in todo] == ["163902"]
    assert "excluded (any of the above): 2" in so.describe_selection(todo, report)


def test_a_local_only_skip_list_says_so_where_the_owner_will_read_it(monkeypatch):
    """_remote_emails() returns an EMPTY set when SUPABASE_PAT is unset —
    supported offline mode, not an error — so the skip-list can be silently
    partial. The line that shows the number must show its provenance."""
    from scripts import send_outreach as so

    monkeypatch.setattr(so, "load_sent", lambda: {"super@001902.org"})
    monkeypatch.setattr(so, "load_optout", lambda: set())
    monkeypatch.setattr(so, "load_suppressed", lambda: set())

    monkeypatch.delenv("SUPABASE_PAT", raising=False)
    _, report = so.select_targets(_rows("001902", "163902"), limit=0)
    assert "LOCAL ONLY" in so.describe_selection([], report)

    monkeypatch.setenv("SUPABASE_PAT", "sbp_test")
    _, report = so.select_targets(_rows("001902", "163902"), limit=0)
    assert "Supabase mirror" in so.describe_selection([], report)


def _dry_run(monkeypatch, tmp_path, rows, sent=(), extra_argv=()):
    """Run the real dry-run path of main() against a temporary merge file."""
    import csv as _csv

    from scripts import send_outreach as so

    merge = tmp_path / "merge.csv"
    with merge.open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    monkeypatch.setattr(so, "MERGE", merge)
    monkeypatch.setattr(so, "PREVIEW_DIR", tmp_path / "preview")
    if sent is not None:                 # None: leave load_sent as the caller set it
        monkeypatch.setattr(so, "load_sent", lambda: set(sent))
    monkeypatch.setattr(so, "load_optout", lambda: set())
    monkeypatch.setattr(so, "load_suppressed", lambda: set())
    monkeypatch.setattr(sys, "argv", ["send_outreach.py", *extra_argv])
    return so.main(), tmp_path / "preview"


def _full_row(num, name):
    r = dict(ROW)
    r.update(district_number=num, district_name=name,
             email=f"super@{num}.org",
             deep_link=f"https://txisd.dev/?d={num}",
             subject=f"Every number Texas publishes about {name}",
             hook=f"{name} spent money.", insight_bonds=f"{name} bonds.",
             insight_debt=f"{name} debt.", insight_trend=f"{name} trend.")
    return r


def test_the_dry_run_warns_when_a_send_would_refuse_the_selection(
        monkeypatch, tmp_path, capsys):
    """A dry run cannot refuse — it sends nothing — but showing a wave the
    watermark guard would reject, without saying so, invites the owner to
    approve a send that then dies at the rail. This runs the real path."""
    rows = [_full_row("163902", "D'Hanis ISD"), _full_row("163903", "Natalia ISD")]
    code, _ = _dry_run(monkeypatch, tmp_path, rows, sent=[],
                       extra_argv=["--previews", "0"])
    out = capsys.readouterr().out
    assert code == 0
    # the committed watermark is non-zero, so a skip-list of zero must warn
    assert "a real send would REFUSE" in out
    assert "refusing:" in out


def test_the_dry_run_renders_the_selected_districts_and_clears_stale_ones(
        monkeypatch, tmp_path, capsys):
    """Previews are keyed by district number, so last wave's files would
    otherwise sit in the directory the runbook says to read — the same
    reviewed-the-wrong-emails failure, moved onto disk."""
    rows = [_full_row("163902", "D'Hanis ISD"), _full_row("163903", "Natalia ISD")]
    _dry_run(monkeypatch, tmp_path, rows, sent=["super@163902.org"],
             extra_argv=["--previews", "5"])
    pv = tmp_path / "preview"
    stale = pv / "001902.html"
    stale.write_text("last wave")
    # a second run must leave only the current wave behind
    _dry_run(monkeypatch, tmp_path, rows, sent=["super@163902.org"],
             extra_argv=["--previews", "5"])
    assert not stale.exists(), "a previous wave's preview survived"
    assert {p.stem for p in pv.glob("*.html")} == {"163903"}, (
        "the previews are not the districts that would be sent")


def test_the_dry_run_does_not_call_a_bypassed_guard_a_refusal(
        monkeypatch, tmp_path, capsys):
    """--ignore-watermark makes the send proceed. A dry run that still says
    "a real send would REFUSE" is wrong in the one direction that matters: it
    makes the bypass look inert, so the next person passes it again believing
    it does nothing."""
    rows = [_full_row("163902", "D'Hanis ISD")]
    _dry_run(monkeypatch, tmp_path, rows, sent=[],
             extra_argv=["--previews", "0", "--ignore-watermark"])
    out = capsys.readouterr().out
    assert "WOULD OVERRIDE IT" in out
    assert "a real send would REFUSE" not in out


def test_the_preview_directory_always_reflects_the_last_dry_run(monkeypatch, tmp_path):
    """Two bad outcomes were possible and they are not equally bad. Leaving the
    reviewer with NOTHING is a nuisance; leaving them the PREVIOUS wave's
    emails, in the directory the runbook tells them to open, is the
    reviewed-the-wrong-emails failure itself. So the directory always reflects
    the last dry run — including when that run had nothing to show.
    """
    rows = [_full_row("163902", "D'Hanis ISD")]
    pv = tmp_path / "preview"
    _dry_run(monkeypatch, tmp_path, rows, sent=[], extra_argv=["--previews", "1"])
    assert (pv / "163902.html").exists()

    # asked for the selection only — the stale email must not survive
    _dry_run(monkeypatch, tmp_path, rows, sent=[], extra_argv=["--previews", "0"])
    assert not (pv / "163902.html").exists()

    # a wave of zero districts must not leave the last wave standing either
    _dry_run(monkeypatch, tmp_path, rows, sent=[], extra_argv=["--previews", "3"])
    assert (pv / "163902.html").exists()
    _dry_run(monkeypatch, tmp_path, rows, sent=["super@163902.org"],
             extra_argv=["--previews", "3"])
    assert list(pv.glob("*.html")) == [], (
        "an empty wave left the previous wave's previews on disk")


def test_a_failed_render_leaves_the_previous_previews_intact(monkeypatch, tmp_path):
    """The clear and the write are not one operation, so the wave is rendered
    into a staging directory and swapped in. A crash before the swap must not
    cost the reviewer what they already had."""
    from scripts import send_outreach as so

    rows = [_full_row("163902", "D'Hanis ISD")]
    pv = tmp_path / "preview"
    _dry_run(monkeypatch, tmp_path, rows, sent=[], extra_argv=["--previews", "1"])
    assert (pv / "163902.html").exists()

    def boom(*a, **k):
        raise ValueError("template blew up")

    monkeypatch.setattr(so, "render_email", boom)
    with pytest.raises(ValueError):
        _dry_run(monkeypatch, tmp_path, rows, sent=[], extra_argv=["--previews", "1"])
    assert (pv / "163902.html").exists(), (
        "a failed render destroyed the previews it could not replace")


def _test_send(monkeypatch, tmp_path, rows, sent=(), extra_argv=()):
    """Drive the --test path with the Resend call stubbed, returning the rows
    that would really have been rendered into a message."""
    import csv as _csv

    from scripts import send_outreach as so

    merge = tmp_path / "merge.csv"
    with merge.open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    seen = []
    monkeypatch.setattr(so, "MERGE", merge)
    monkeypatch.setattr(so, "load_sent", lambda: set(sent))
    monkeypatch.setattr(so, "load_optout", lambda: set())
    monkeypatch.setattr(so, "load_suppressed", lambda: set())
    monkeypatch.setattr(so, "_req",
                        lambda path, key, payload: seen.append(payload) or {"id": "x"})
    monkeypatch.setattr(so.time, "sleep", lambda *_: None)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setattr(sys, "argv",
                        ["send_outreach.py", "--test", "owner@example.com",
                         *extra_argv])
    so.main()
    return seen


def test_the_real_inbox_check_samples_the_wave_not_the_merge_file(
        monkeypatch, tmp_path):
    """--test is the other half of the same review. Sampling rows[:2] meant the
    owner inspected an email for a district contacted months ago — the same
    defect the dry run had, in the channel that actually reaches an inbox."""
    rows = [_full_row("001902", "Cayuga ISD"), _full_row("163902", "D'Hanis ISD"),
            _full_row("163903", "Natalia ISD")]
    seen = _test_send(monkeypatch, tmp_path, rows,
                      sent=["super@001902.org"], extra_argv=["--limit", "2"])
    subjects = " ".join(p["subject"] for p in seen)
    assert "Cayuga" not in subjects, (
        "an already-contacted district was put in front of the owner")
    assert "D'Hanis" in subjects and "Natalia" in subjects


def test_naming_a_district_still_shows_it_even_if_already_contacted(
        monkeypatch, tmp_path):
    """--only is an explicit request to see one district's email. Filtering it
    the way the wave is filtered would make it impossible to re-check a message
    that has already gone out — which is exactly when you want to look."""
    rows = [_full_row("001902", "Cayuga ISD"), _full_row("163902", "D'Hanis ISD")]
    seen = _test_send(monkeypatch, tmp_path, rows, sent=["super@001902.org"],
                      extra_argv=["--only", "001902"])
    assert len(seen) == 1 and "Cayuga" in seen[0]["subject"]


def test_an_empty_skiplist_warns_before_the_owner_trusts_the_sample(
        monkeypatch, tmp_path, capsys):
    """A skip-list that resolves EMPTY does not raise — offline is supported —
    so --test would quietly sample the head of the merge file, which is where
    the already-contacted districts live. It must say so."""
    rows = [_full_row("001902", "Cayuga ISD"), _full_row("163902", "D'Hanis ISD")]
    _test_send(monkeypatch, tmp_path, rows, sent=[], extra_argv=["--limit", "1"])
    out = capsys.readouterr().out
    assert "may be districts already contacted" in out
    assert "would refuse until the state is recovered" in out


def test_a_dry_run_that_cannot_resolve_the_skiplist_refuses_to_preview(
        monkeypatch, tmp_path, capsys):
    """_remote_emails() RAISES when Supabase is set but unreachable, precisely
    so a partial skip-list never passes as a whole one. The dry run must not
    turn that into previews: the wave it would show is larger than the truth,
    in the direction that re-emails people."""
    from scripts import send_outreach as so

    def boom():
        raise RuntimeError("could not read public.outreach_sent from Supabase")

    monkeypatch.setattr(so, "load_sent", boom)
    code, pv = _dry_run(monkeypatch, tmp_path,
                        [_full_row("163902", "D'Hanis ISD")], sent=None,
                        extra_argv=["--previews", "3"])
    err = capsys.readouterr().err
    assert code == 1, "a dry run with an unresolvable skip-list must not pass"
    assert "cannot show the wave" in err
    assert "No previews written" in err
    assert not pv.exists() or not list(pv.glob("*.html")), (
        "previews were written from a skip-list that could not be resolved")
