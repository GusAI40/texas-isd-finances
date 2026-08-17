"""Turn a reply from a superintendent into the one conversion this product has.

Everything else on the intelligence dashboard is behaviour a machine can
imitate. A mail-security appliance opens the message, follows the link and
loads the page; that is why the engagement score weights those lightly and why
the open rate is never quoted. A REPLY is a person typing to a person, and it
is the only outcome in the funnel worth the name.

Nothing wrote that event until this script existed, so `replied` read zero for
everyone — a funnel whose last stage is structurally empty, which is worse than
no funnel because it looks measured.

WHAT IT READS AND WHAT IT KEEPS
-------------------------------
It reads the inbox over IMAP, matches each sender against the addresses we
actually mailed, and writes ONE `reply` event per (recipient, message). It
keeps the FACT and the TIME. It does not keep the subject, the body, or a
quotation of any kind — `visitor_event` has nowhere to put them and it should
stay that way. What a superintendent wrote to us is correspondence, not
telemetry.

    python scripts/ingest_replies.py                 # dry run, prints matches
    python scripts/ingest_replies.py --write         # writes the events
    python scripts/ingest_replies.py --days 30       # look further back

Environment
-----------
    IMAP_USER, IMAP_PASSWORD   the mailbox (Gmail: an APP password, not the
                               account password; IMAP must be enabled)
    IMAP_HOST                  optional, defaults to imap.gmail.com
    SUPABASE_PAT               required for --write. Direct Postgres is blocked
                               from dev containers, so writes go through the
                               Management API like every other script here.

WHY SENDER MATCHING, NOT THREADING
----------------------------------
Threading on In-Reply-To would be more precise and is not worth it. A
superintendent we mailed who writes to this mailbox is the event we care about
whether or not their client threaded it — plenty of people compose a fresh
message instead of hitting reply, and Outlook drops References often enough to
matter. Matching on the sender is the same join the dashboard already uses
(email -> rid), and the false-positive risk is a person we mailed writing to us
about something else, which is still a reply from a person.
"""
from __future__ import annotations

import argparse
import email
import email.utils
import imaplib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT_REF = "zwhvabkvrexphlskubog"
OPTOUT_FILE = ROOT / "data" / "outreach_optout.txt"

# Phrases that mean "stop emailing me". Deliberately broad: the asymmetry is
# not close. Wrongly opting someone out costs one unsent email; missing a real
# request breaks a promise we made in writing to a public official, and the
# unsubscribe line is in every message we send.
_OPTOUT = re.compile(
    r"\b(unsubscribe|opt[\s-]?out|remove me|take me off|stop emailing|"
    r"do not (?:contact|email)|don't (?:contact|email)|no longer wish)\b",
    re.I)


def normalise(addr: str) -> str:
    """An address reduced to what two systems can agree on.

    Gmail's own display name, angle brackets and case all vary between the send
    log and the reply; the address itself does not.
    """
    _, parsed = email.utils.parseaddr(addr or "")
    return parsed.strip().lower()


def looks_like_optout(text: str) -> bool:
    return bool(_OPTOUT.search(text or ""))


def pick_rid(sends: list[dict], replied_at: datetime) -> str | None:
    """Which send is this a reply to?

    A district can appear in more than one wave, so an address can hold several
    tokens. The right one is the most recent send that PRECEDES the reply —
    attributing a reply to a wave that had not gone out yet would put a
    conversion before its own cause.
    """
    eligible = [s for s in sends if s["sent_at"] <= replied_at]
    if not eligible:
        return None
    return max(eligible, key=lambda s: s["sent_at"])["rid"]


def sql(query: str, pat: str) -> list[dict]:
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": query}).encode(),
        # Cloudflare 403s a bare urllib with error 1010. It is a User-Agent
        # block, never an auth failure — this scar is shared with every other
        # script in this directory.
        headers={"Authorization": f"Bearer {pat}",
                 "User-Agent": "txisd-replies/1.0",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def fetch_sends(pat: str) -> dict[str, list[dict]]:
    """Every address we mailed, with its tokens and send times."""
    rows = sql("SELECT rid, lower(email) AS email, campaign, sent_at "
               "FROM public.outreach_recipient", pat)
    out: dict[str, list[dict]] = {}
    for r in rows:
        stamp = r["sent_at"]
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        out.setdefault(r["email"], []).append(
            {"rid": r["rid"], "campaign": r["campaign"], "sent_at": when})
    return out


def read_inbox(days: int) -> list[dict]:
    """Messages received in the window, as {from, at, id, text}.

    stdlib imaplib on purpose: a mail SDK would be a new dependency in a
    project whose Vercel bundle is already near its cap, for one IMAP SEARCH.
    """
    user = os.environ.get("IMAP_USER", "").strip()
    password = os.environ.get("IMAP_PASSWORD", "").strip()
    if not (user and password):
        raise SystemExit(
            "IMAP_USER and IMAP_PASSWORD are required.\n"
            "For Gmail this must be an APP PASSWORD (Google Account -> "
            "Security -> 2-Step Verification -> App passwords), not the "
            "account password, and IMAP must be enabled in Gmail settings.")

    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    out: list[dict] = []
    box = imaplib.IMAP4_SSL(host)
    try:
        box.login(user, password)
        box.select("INBOX", readonly=True)          # never mark anything read
        status, data = box.search(None, f'(SINCE "{since}")')
        if status != "OK":
            return out
        for num in data[0].split():
            status, raw = box.fetch(num, "(RFC822)")
            if status != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            when = email.utils.parsedate_to_datetime(msg.get("Date", "")) \
                if msg.get("Date") else None
            if when and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            out.append({
                "from": normalise(msg.get("From", "")),
                "at": when,
                "id": (msg.get("Message-ID") or f"imap-{num.decode()}").strip("<> "),
                # Kept ONLY long enough to test for an unsubscribe request, and
                # never written anywhere.
                "text": _plain_text(msg),
            })
    finally:
        try:
            box.logout()
        except Exception:                           # noqa: BLE001
            pass
    return out


def _plain_text(msg) -> str:
    if not msg.is_multipart():
        try:
            return msg.get_payload(decode=True).decode("utf-8", "replace")
        except Exception:                           # noqa: BLE001
            return ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            try:
                return part.get_payload(decode=True).decode("utf-8", "replace")
            except Exception:                       # noqa: BLE001
                continue
    return ""


def match(messages: list[dict], sends: dict[str, list[dict]]) -> list[dict]:
    """Replies from people we actually mailed. Everything else is just mail."""
    out = []
    for m in messages:
        # Normalised HERE, not only at read time. read_inbox() already does it,
        # so relying on that would work until the day something else feeds this
        # function a raw `Dr. Jane Doe <Super@ArgyleISD.example>` header — and
        # then it would silently match nothing rather than fail. The guarantee
        # belongs where the comparison happens.
        who = normalise(m.get("from", ""))
        if not who or who not in sends or not m.get("at"):
            continue
        rid = pick_rid(sends[who], m["at"])
        if not rid:
            continue                                # reply predates the send
        out.append({"rid": rid, "email": who, "at": m["at"], "id": m["id"],
                    "optout": looks_like_optout(m.get("text", ""))})
    return out


def write_events(matches: list[dict], pat: str) -> int:
    """One `reply` event each, idempotent on the message id.

    A cron that runs daily re-reads the same fortnight every day. Without the
    key, one reply becomes fourteen conversions and the funnel inverts.
    """
    if not matches:
        return 0
    values = ",".join(
        f"({_q(m['rid'])}, {_q('reply-' + m['rid'][:8])}, "
        f"{_q('reply-' + m['id'][:12])}, 'reply', {_q('replied')}, "
        f"{_q(m['at'].isoformat())}, {_q('reply:' + m['rid'] + ':' + m['id'])})"
        for m in matches)
    sql(
        "INSERT INTO public.visitor_event "
        "(rid, visitor_id, session_id, event, detail, occurred_at, event_key) "
        f"VALUES {values} ON CONFLICT DO NOTHING", pat)
    rows = sql("SELECT count(*) AS n FROM public.visitor_event "
               "WHERE event = 'reply'", pat)
    return int(rows[0]["n"]) if rows else 0


def honour_optouts(matches: list[dict]) -> list[str]:
    """Add anyone who asked to stop to the opt-out list.

    Done here rather than left for a human because the list is checked before
    every send and a request sitting unread in an inbox is not honoured. The
    detector is deliberately broad; see the note on _OPTOUT.
    """
    asked = sorted({m["email"] for m in matches if m["optout"]})
    if not asked:
        return []
    existing = set()
    if OPTOUT_FILE.exists():
        existing = {ln.strip().lower() for ln in
                    OPTOUT_FILE.read_text().splitlines() if ln.strip()}
    new = [a for a in asked if a not in existing]
    if new:
        OPTOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OPTOUT_FILE.open("a") as fh:
            for a in new:
                fh.write(a + "\n")
    return new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=21,
                    help="how far back to read the inbox (default 21)")
    ap.add_argument("--write", action="store_true",
                    help="actually record the events; otherwise dry run")
    args = ap.parse_args()

    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not pat:
        print("SUPABASE_PAT is not set — cannot read who was mailed.")
        return 1

    sends = fetch_sends(pat)
    print(f"  mailed addresses on record: {len(sends):,}")

    messages = read_inbox(args.days)
    print(f"  messages in the last {args.days} days: {len(messages):,}")

    matches = match(messages, sends)
    if not matches:
        # A real answer, and the expected one for a while. Saying "no replies"
        # is not the same as failing, and the difference has to be visible or
        # the next person assumes the pipe is broken.
        print("\n  No replies from anyone we mailed in this window.")
        print("  That is a finding, not a failure: the funnel's last stage is")
        print("  honestly empty until a superintendent writes back.")
        return 0

    print(f"\n  REPLIES FROM PEOPLE WE MAILED ({len(matches)})\n")
    for m in sorted(matches, key=lambda x: x["at"]):
        flag = "  ** ASKED TO BE REMOVED **" if m["optout"] else ""
        print(f"  {m['at']:%Y-%m-%d %H:%M}  {m['email']:<44}{flag}")

    if not args.write:
        print("\n  Dry run. Re-run with --write to record these.")
        return 0

    total = write_events(matches, pat)
    print(f"\n  recorded. reply events now in the database: {total}")
    removed = honour_optouts(matches)
    if removed:
        print(f"  added to {OPTOUT_FILE.name}: {', '.join(removed)}")
        print("  COMMIT that file and mirror it with sync_outreach_state.py "
              "before the next wave.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
