"""Send each Texas superintendent THEIR district's report — the gift, then the
introduction. Powered by the Resend API (https://resend.com).

The email is reverse-engineered from what TAG ai actually did: it opens with
the recipient's own numbers (three insights drawn from the same committed
artefacts the site serves, so an email can never disagree with the page it
links to), a button to their district's page, then — only then — who built it
and an invitation to talk. Value first, pitch second.

Modes (safe by default)
-----------------------
    python scripts/send_outreach.py                       # dry run: writes
        previews to data/outreach_preview/ and sends NOTHING
    python scripts/send_outreach.py --test you@you.com    # sends 2 real
        emails to YOUR address so you can see them in a real inbox
    python scripts/send_outreach.py --send --confirm GO   # the real thing
    python scripts/send_outreach.py --send --confirm GO --limit 50

Rails that hold even when excited
---------------------------------
- `--send` refuses to run without `--confirm GO`, a RESEND_API_KEY, a
  verified sending domain (checked against Resend's /domains API before the
  first message), and TAG_POSTAL_ADDRESS set — CAN-SPAM requires a physical
  postal address in every commercial email, no address, no send.
- Every delivery is recorded in data/outreach_sent.csv (gitignored) and
  re-runs skip anyone already sent — a crash halfway cannot double-email.
- data/outreach_optout.txt (one email per line) is honoured before anything
  leaves, and every email carries a List-Unsubscribe header plus a visible
  unsubscribe line. An opt-out is a promise; the file is the memory of it.
- The sent log and opt-out list are ALSO mirrored in Supabase
  (sql/create_outreach_state.sql, scripts/sync_outreach_state.py): the local
  files live in a disposable container, and container loss + a re-run would
  re-email everyone including opt-outs. When SUPABASE_PAT is set, a real
  send unions the remote tables into both skip-lists first and mirrors each
  delivery up as it happens (best effort — a mirror failure never aborts the
  send, it warns loudly instead).
- Throttled to ~1 message/second (Resend's public rate limit is 2/s).

Environment
-----------
    RESEND_API_KEY       required for --test/--send
    RESEND_FROM          defaults to 'Gus Sanchez <gus@ubntag.com>' — the
                         domain must be verified in Resend first (DNS records)
    RESEND_REPLY_TO      optional, defaults to the from address
    TAG_BCC              defaults to gus@ubntag.com — every real send is
                         BCC'd here so the owner holds a copy; "" disables
    TAG_POSTAL_ADDRESS   required for --send (CAN-SPAM physical address)
    SUPABASE_PAT         optional; when set, sent/opt-out state is merged
                         from and mirrored to Supabase (durable across
                         container loss)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import ssl
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import sync_outreach_state  # noqa: E402
from src import format as fmt  # noqa: E402
from src import tracking  # noqa: E402

# The renderer and Resend client moved to deployed code (src/outreach_email)
# so the SITE can send without a container; this script keeps working and
# renders byte-identical messages because it imports the same objects.
from src.outreach_email import SITE, domain_verified, render_email  # noqa: E402,F401  (re-exported names)
from src.outreach_email import resend_request as _req  # noqa: E402

MERGE = ROOT / "data/outreach_merge.csv"
SENT_LOG = ROOT / "data/outreach_sent.csv"
WATERMARK = ROOT / "data" / "outreach_watermark.json"
# Journey tokens live in their own file rather than as a column on the sent
# log: that log already has 571 four-column rows from wave 1, and widening it
# in place would misalign every one of them.
RECIPIENTS = ROOT / "data/outreach_recipients.csv"
OPTOUT = ROOT / "data/outreach_optout.txt"
PREVIEW_DIR = ROOT / "data/outreach_preview"
def verify_targets(rows: list[dict]) -> list[str]:
    """THE critical property: every superintendent gets THEIR report, not
    someone else's. Returns a list of violations; the caller refuses to send
    if there are any. Runs before every real send, not once at build time —
    a stale or hand-edited merge file must fail here, not in an inbox.

    Three independent checks per row:
      1. The deep link's ?d= number IS the row's own district number.
      2. The site will greet that number with the SAME district name the
         email uses — checked against the committed fallback index, which is
         what the page's headline falls back to and derives from the same
         registry as the live database.
      3. Every insight sentence names the row's own district — a crossed
         wire between rows cannot survive this, because the insights were
         built keyed by number and each carries its name in the text.
    """
    problems = []
    fb = json.loads((ROOT / "static/fallback_index.json").read_text())
    site_name = {d["district_number"]: fmt.district_name(d["district_name"])
                 for d in fb["districts"]}
    for row in rows:
        num, name = row["district_number"], row["district_name"]
        if not row["deep_link"].endswith(f"?d={num}"):
            problems.append(f"{num} {name}: deep link points elsewhere "
                            f"({row['deep_link']})")
        page = site_name.get(num)
        if page is not None and page.casefold() != name.casefold():
            # casefold: 'McDade' vs 'Mcdade' is typography; a crossed wire is
            # a DIFFERENT name, which no capitalisation can hide.
            problems.append(f"{num}: email says {name!r} but the site page "
                            f"for that number says {page!r}")
        for k in ("insight_bonds", "insight_debt", "insight_trend", "hook"):
            if row.get(k) and name not in row[k]:
                problems.append(f"{num} {name}: {k} names a different "
                                f"district: {row[k][:80]!r}")
        if name not in row["subject"]:
            problems.append(f"{num} {name}: subject lacks the district name")
    return problems


SB_REF = os.getenv("SUPABASE_PROJECT_REF", "zwhvabkvrexphlskubog")
SB_QUERY_API = f"https://api.supabase.com/v1/projects/{SB_REF}/database/query"


def _sb_sql(query: str, pat: str) -> list[dict]:
    """SQL over the Supabase Management API — direct Postgres (5432/6543) is
    blocked from dev containers. Same Cloudflare UA trap as _req above."""
    r = urllib.request.Request(
        SB_QUERY_API, data=json.dumps({"query": query}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {pat}",
                 "Content-Type": "application/json",
                 "User-Agent": "txisd-outreach/1.0 (+https://txisd.dev)"})
    with urllib.request.urlopen(r, timeout=60,
                                context=ssl.create_default_context()) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else []


def _sb_quote(s: str) -> str:
    """SQL string literal — single quotes doubled."""
    return "'" + s.replace("'", "''") + "'"


def _remote_emails(table: str) -> set[str]:
    """Emails in the durable Supabase mirror (sql/create_outreach_state.sql),
    or an empty set when SUPABASE_PAT is unset (offline: local files only).

    A remote FAILURE raises instead of returning empty on purpose: this feeds
    the skip-lists, and an empty answer would silently shrink them. If the
    local files are stale (fresh container), that means re-emailing people —
    including opt-outs, a promise broken. Fail closed; nothing has been sent
    yet when this runs. Unset SUPABASE_PAT to explicitly accept local-only
    state."""
    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not pat:
        return set()
    if table not in ("outreach_sent", "outreach_optout"):
        raise ValueError(f"unknown outreach state table {table!r}")
    try:
        rows = _sb_sql(f"SELECT email FROM public.{table}", pat)
    except Exception as ex:
        raise RuntimeError(
            f"could not read public.{table} from Supabase ({ex}). Refusing "
            f"to trust the local files alone — if they are stale, a send "
            f"would re-email people, including opt-outs. Fix the connection, "
            f"or unset SUPABASE_PAT to accept local-only state.") from ex
    return {r["email"] for r in rows}


def watermark_floor() -> int:
    """How many addresses we KNOW have been emailed, from committed state."""
    if not WATERMARK.exists():
        return 0
    d = json.loads(WATERMARK.read_text())
    # Compare like with like. The skip-list is a SET OF ADDRESSES; sent_total
    # counts SENDS. Two districts sharing one address would make sends exceed
    # addresses forever, tripping the refusal with no way out but a flag.
    return int(d.get("unique_emails", d.get("sent_total", 0)))


def skiplist_shrank(resolved: int) -> str:
    """Return a refusal message when the skip-list is smaller than the
    committed watermark, else "".

    A skip-list can only ever GROW: nobody un-receives an email. Smaller than
    the watermark therefore does not mean fewer people were mailed, it means
    send state was LOST — and the way that happens is mundane.
    data/outreach_sent.csv is gitignored and has never been committed, and
    _remote_emails() returns an empty set (not an error) when SUPABASE_PAT is
    unset, because offline is a supported mode. A fresh clone with neither
    resolves a skip-list of zero and would cheerfully re-email every
    superintendent already contacted.
    """
    floor = watermark_floor()
    if resolved >= floor:
        return ""
    return (
        f"refusing: the skip-list resolved to {resolved} addresses but "
        f"{WATERMARK.name} records {floor} already sent. A skip-list cannot "
        f"shrink — nobody un-receives an email — so send state was lost, and "
        f"sending now would re-email people who have already heard from us.\n"
        f"  Recover state first, in this order:\n"
        f"    1. export SUPABASE_PAT=...   (the durable mirror is the truth)\n"
        f"    2. python scripts/sync_outreach_state.py --pull\n"
        f"    3. re-run this command\n"
        f"  If the watermark itself is wrong, fix it in a commit rather than "
        f"passing --ignore-watermark.")


# Same helper as sync_outreach_state._short (same repo root, same job) —
# reused rather than redefined, so a change to the rule can't diverge between
# the two files the way this project's money/name formatters once did (see
# src/format.py's own docstring for that history).
_short = sync_outreach_state._short


def select_targets(rows: list[dict], limit: int) -> tuple[list[dict], dict]:
    """The wave, exactly as the send would compute it, plus a report of how it
    got there.

    This exists as one function because the dry run used to preview
    ``rows[:previews]`` — the HEAD OF THE MERGE FILE — while the send mailed a
    filtered list. The two disagreed from the first wave onward, so the review
    step showed districts that had already been contacted months earlier and
    would never be mailed again. That is not a near miss with a duplicate send
    (the send filters correctly, and the watermark stands behind it); it is
    worse in a quieter way: it made the ONE step the runbook calls "the real
    review" a review of the wrong emails. Both paths now call this.
    """
    sent, optout = load_sent(), load_optout()
    suppressed = load_suppressed()
    todo = [r for r in rows if r["email"] not in sent
            and r["email"].lower() not in optout
            and _digest(r["email"]) not in suppressed]
    eligible = len(todo)
    if limit:
        todo = todo[:limit]
    # Every count below is scoped to THIS merge file, because a report that
    # mixes "671 addresses we have ever mailed" with "11 rows here are dead"
    # cannot be added up by the person reading it — and a selection report
    # whose numbers do not reconcile is a report nobody checks. The three
    # reasons can overlap (a dead address can also be in the skip-list), so
    # `excluded` is their UNION and is the only figure that subtracts.
    return todo, {
        "in_merge": len(rows),
        "already_sent": sum(1 for r in rows if r["email"] in sent),
        "opted_out": sum(1 for r in rows if r["email"].lower() in optout),
        "dead": sum(1 for r in rows if _digest(r["email"]) in suppressed),
        "excluded": len(rows) - eligible,
        "eligible": eligible,
        "skiplist": len(sent),
        "remote": bool(os.environ.get("SUPABASE_PAT", "").strip()),
    }


def describe_selection(todo: list[dict], report: dict) -> str:
    """The selection, in the terms the runbook asks to see before a send: how
    many, from what, and which district is first and last — so the owner can
    confirm the choice is deterministic rather than a sample."""
    source = ("local + Supabase mirror" if report["remote"]
              else "LOCAL ONLY — SUPABASE_PAT unset")
    lines = [
        f"  in the merge file          : {report['in_merge']:,}",
        f"    already contacted        : {report['already_sent']:,}"
        f"   (skip-list holds {report['skiplist']:,} addresses; {source})",
        f"    opted out                : {report['opted_out']:,}",
        f"    known-dead address       : {report['dead']:,}",
        f"  excluded (any of the above): {report['excluded']:,}",
        f"  eligible, never contacted  : {report['eligible']:,}",
        f"  WOULD SEND                 : {len(todo):,}",
    ]
    if todo:
        first, last = todo[0], todo[-1]
        lines += [
            f"    first : {first['district_number']} {first['district_name']}",
            f"    last  : {last['district_number']} {last['district_name']}",
        ]
    return "\n".join(lines)


def load_sent() -> set[str]:
    """Everyone already emailed: local CSV ∪ the Supabase mirror. Remote
    wins by union — an address in either place is never emailed again."""
    local = set()
    if SENT_LOG.exists():
        local = {r["email"] for r in csv.DictReader(SENT_LOG.open())}
    return local | _remote_emails("outreach_sent")


SUPPRESSION = ROOT / "data" / "outreach_suppression.json"


def load_suppressed() -> set[str]:
    """SHA-256 hashes of addresses that must never be mailed again.

    Hard bounces, provider suppressions, complaints — recorded by
    scripts/prune_bad_addresses.py and COMMITTED, because the sent-log that
    also covers these addresses is gitignored and container-only. Mailing a
    dead address reaches nobody and teaches every mail filter that this domain
    writes to dead addresses, which costs delivery to the live ones.

    Hashes rather than addresses: the file is public and contact data is not.
    """
    if not SUPPRESSION.exists():
        return set()
    return set(json.loads(SUPPRESSION.read_text()).get("entries", {}))


def _digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def load_optout() -> set[str]:
    """Everyone who asked us to stop: local file ∪ the Supabase mirror,
    lower-cased (the caller compares lower-cased)."""
    local = set()
    if OPTOUT.exists():
        local = {ln.strip().lower() for ln in OPTOUT.read_text().splitlines()
                 if ln.strip() and not ln.startswith("#")}
    return local | {e.lower() for e in _remote_emails("outreach_optout")}


def log_recipient(row: dict, rid: str, message_id: str, campaign: str) -> None:
    """Record the journey token so a later click can be traced to a person.

    This row is what the ?rid= foreign key points at: if it is missing when the
    recipient clicks, the event is dropped and the click is lost. Written
    immediately after the send returns, which is comfortably before any human
    can open a mail client — but it means a Supabase mirror failure is a real
    loss of attribution, hence the loud warning rather than a silent pass.
    """
    sent_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    new = not RECIPIENTS.exists()
    with RECIPIENTS.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["rid", "email", "district_number",
                                           "campaign", "message_id", "sent_at"])
        if new:
            w.writeheader()
        w.writerow({"rid": rid, "email": row["email"],
                    "district_number": row["district_number"],
                    "campaign": campaign, "message_id": message_id,
                    "sent_at": sent_at})
    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not pat:
        print("  WARNING: SUPABASE_PAT unset — journey token is local only, "
              "so this recipient's clicks will not be attributable.")
        return
    try:
        _sb_sql(
            "INSERT INTO public.outreach_recipient "
            "(rid, email, district_number, campaign, message_id) VALUES ("
            f"{_sb_quote(rid)}, {_sb_quote(row['email'])}, "
            f"{_sb_quote(row['district_number'])}, "
            f"{_sb_quote(campaign)}, {_sb_quote(message_id)}) "
            "ON CONFLICT (rid) DO NOTHING",
            pat)
    except Exception as ex:                      # noqa: BLE001
        print(f"  WARNING: journey token not mirrored to Supabase ({ex}). "
              f"Clicks from {row['email']} will not resolve to a person.")


def log_sent(row: dict, message_id: str) -> None:
    sent_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    new = not SENT_LOG.exists()
    with SENT_LOG.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["email", "district_number",
                                           "message_id", "sent_at"])
        if new:
            w.writeheader()
        w.writerow({"email": row["email"],
                    "district_number": row["district_number"],
                    "message_id": message_id,
                    "sent_at": sent_at})
    # Mirror the row to Supabase so the record survives this container.
    # Best effort: the message is already SENT — failing the run here would
    # only stop the local log from growing, not un-send anything — but the
    # warning must be loud enough to act on before the container dies.
    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not pat:
        return
    try:
        _sb_sql(
            "INSERT INTO public.outreach_sent "
            "(email, district_number, message_id, sent_at) VALUES "
            f"({_sb_quote(row['email'])},{_sb_quote(row['district_number'])},"
            f"{_sb_quote(message_id)},{_sb_quote(sent_at)}::timestamptz) "
            "ON CONFLICT (email) DO NOTHING", pat)
    except Exception as ex:  # noqa: BLE001 — a mirror failure must not abort the send
        print(f"  WARNING: {row['email']} logged LOCALLY ONLY — the Supabase "
              f"mirror insert failed ({ex}). The local CSV is now ahead of "
              f"the durable table: run scripts/sync_outreach_state.py before "
              f"this container is lost.", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", metavar="EMAIL",
                    help="send 2 sample districts to THIS address instead")
    ap.add_argument("--send", action="store_true",
                    help="send for real, to the superintendents in the merge file")
    ap.add_argument("--confirm", default="",
                    help="must be the literal word GO for --send")
    ap.add_argument("--ignore-watermark", action="store_true",
                    help="send even if the skip-list is smaller than the "
                         "committed watermark. Almost always the wrong "
                         "answer: recover state instead.")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N sends (0 = all); use for a pilot wave. "
                         "With --test: how many samples to send (default 2)")
    ap.add_argument("--only", default="",
                    help="comma-separated district numbers; with --test, send "
                         "exactly these districts' emails as the samples")
    ap.add_argument("--previews", type=int, default=5,
                    help="dry run: how many HTML previews to write")
    ap.add_argument("--campaign", default="w2",
                    help="campaign label stored with each journey token, so a "
                         "wave's behaviour can be reported — or deleted — on "
                         "its own (default: w2; wave 1 was sent untracked)")
    args = ap.parse_args()
    campaign = args.campaign.strip() or "w2"

    rows = list(csv.DictReader(MERGE.open()))
    if not rows:
        print("merge file is empty — run scripts/build_outreach_merge.py first")
        return 1

    postal = os.environ.get("TAG_POSTAL_ADDRESS", "").strip()
    from_addr = (os.environ.get("RESEND_FROM", "").strip()
                 or "Gus Sanchez <gus@ubntag.com>")
    # every real client send is BCC'd here so the owner holds a copy of
    # exactly what each superintendent received; TAG_BCC="" disables it
    bcc_addr = os.environ.get("TAG_BCC", "gus@ubntag.com").strip()
    key = os.environ.get("RESEND_API_KEY", "").strip()
    # The last resort must be a mailbox someone actually reads. This used to
    # fall back to hello@txisd.dev, which nobody monitors — an unsubscribe
    # request sent there would have vanished, and an unsubscribe that goes
    # nowhere is worse than no unsubscribe link at all.
    unsub_addr = (os.environ.get("RESEND_REPLY_TO") or from_addr
                  or "gus@ubntag.com").split("<")[-1].rstrip(">")
    unsubscribe = f"mailto:{unsub_addr}?subject=unsubscribe"

    # ---- dry run (default): render previews, send nothing -------------------
    if not args.test and not args.send:
        # The skip-list is what makes this a review rather than a rendering.
        # If it cannot be resolved, the wave shown would be WRONG — larger than
        # the truth, in the direction that re-emails people — so say so and
        # stop, rather than writing previews that look authoritative.
        try:
            todo, report = select_targets(rows, args.limit)
        except RuntimeError as ex:
            print(f"cannot show the wave: {ex}", file=sys.stderr)
            print("\nNo previews written. A dry run that cannot resolve the "
                  "skip-list would show more districts than are really "
                  "eligible. To render the email copy alone, with no "
                  "selection, unset SUPABASE_PAT and re-run.", file=sys.stderr)
            return 1
        print("dry run — this is the wave the same flags would SEND:")
        print(describe_selection(todo, report))
        refusal = skiplist_shrank(report["skiplist"])
        if refusal and not args.ignore_watermark:
            print("\nWARNING — a real send would REFUSE this selection:")
            print(refusal)
        elif refusal:
            # Saying "a send would refuse" under --ignore-watermark would be
            # false in the one direction that matters: it makes the bypass look
            # inert, so the next person passes it again believing it does
            # nothing. The send honours the flag; say what it will really do.
            print("\nWARNING — the watermark guard would normally REFUSE this "
                  "selection, and --ignore-watermark WOULD OVERRIDE IT:")
            print(refusal)

        # Previews are keyed by district number, so last wave's files must not
        # linger in the directory the runbook says to read — that is the same
        # reviewed-the-wrong-emails failure, moved onto disk. But clearing
        # first means an exception mid-render leaves the reviewer with nothing.
        # So build the whole wave into a temporary directory and swap it in;
        # a failure anywhere before the swap leaves the old previews intact.
        #
        # `--previews 0` is a real request — show me the selection, not the
        # emails — and so is a wave of zero districts. Both must still clear,
        # or the directory keeps asserting a wave that is not this one.
        if args.previews:
            staging = PREVIEW_DIR.with_name(PREVIEW_DIR.name + ".staging")
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            for row in todo[:args.previews]:
                body, text = render_email(row, postal or "[postal address — "
                                          "set TAG_POSTAL_ADDRESS]", unsubscribe)
                stem = staging / row["district_number"]
                stem.with_suffix(".html").write_text(body)
                stem.with_suffix(".txt").write_text(text)
            if PREVIEW_DIR.exists():
                shutil.rmtree(PREVIEW_DIR)
            staging.rename(PREVIEW_DIR)
        elif PREVIEW_DIR.exists():
            shutil.rmtree(PREVIEW_DIR)
        print(f"\nwrote {min(args.previews, len(todo))} previews to "
              f"{_short(PREVIEW_DIR)}/ — from the list above, not "
              f"the top of the merge file — nothing sent.")
        print("next: --test you@you.com for a real-inbox look, then "
              "--send --confirm GO")
        return 0

    # ---- anything real needs the key and the from address -------------------
    if not key:
        print("RESEND_API_KEY is not set — get one at resend.com, then retry.")
        return 1

    if args.test:
        if args.only:
            wanted = {n.strip() for n in args.only.split(",")}
            sample = [r for r in rows if r["district_number"] in wanted]
            missing = wanted - {r["district_number"] for r in sample}
            if missing:
                print(f"not in the merge file: {sorted(missing)}")
        else:
            # The head of the merge file is NOT the wave. --test is the
            # real-inbox half of the same review the dry run does on disk, so
            # it must show the same districts; sampling rows[:2] meant the
            # owner checked an email for a district contacted months ago.
            # (--only stays unfiltered on purpose: naming a district is an
            # explicit request to see that one, including an already-mailed
            # one.) A failure to resolve the skip-list falls back to the head
            # rather than aborting — nothing here reaches a superintendent, so
            # a partial list costs a less representative sample, not a send.
            try:
                sample, rep = select_targets(rows, args.limit or 2)
            except RuntimeError as ex:
                print(f"WARNING: could not resolve the skip-list ({ex}) — "
                      f"sampling the merge file instead, so these may be "
                      f"districts already contacted.")
                sample, rep = rows[:args.limit or 2], None
            # A skip-list that resolves EMPTY does not raise — it is the
            # supported offline mode — so the sample above would silently be
            # the head of the merge file, which is where the already-contacted
            # districts are. Nothing here reaches a superintendent, so this
            # warns rather than refusing; but it must not stay quiet, or the
            # owner approves the wave having inspected the wrong email.
            if rep is not None and skiplist_shrank(rep["skiplist"]):
                print(f"WARNING: the skip-list resolved to only "
                      f"{rep['skiplist']} addresses against a watermark of "
                      f"{watermark_floor()} — these samples may be districts "
                      f"already contacted. A real send would refuse until the "
                      f"state is recovered.")
        for row in sample:
            body, text = render_email(row, postal or "[postal address — set "
                                      "TAG_POSTAL_ADDRESS]", unsubscribe)
            got = _req("/emails", key, {
                "from": from_addr, "to": [args.test],
                "subject": f"[TEST] {row['subject']}",
                "html": body, "text": text})
            print(f"test sent to {args.test}: {row['district_name']} "
                  f"(id {got.get('id')})")
            time.sleep(1)
        return 0

    # ---- the real send ------------------------------------------------------
    if args.confirm != "GO":
        print("refusing: --send requires --confirm GO (the literal word).")
        return 1
    if not postal:
        print("refusing: TAG_POSTAL_ADDRESS is not set. CAN-SPAM requires a "
              "physical postal address in every commercial email.")
        return 1
    if not domain_verified(key, from_addr):
        print(f"refusing: the sending domain of {from_addr!r} is not verified "
              f"in Resend. Verify its DNS records first, or every message "
              f"bounces or lands in spam.")
        return 1
    problems = verify_targets(rows)
    if problems:
        print(f"refusing: {len(problems)} rows would send someone else's "
              f"report. Nothing was sent. First few:")
        for p in problems[:10]:
            print(f"  {p}")
        return 1
    print(f"target identity verified: all {len(rows):,} rows deep-link to "
          f"their own district and every sentence names it")

    todo, report = select_targets(rows, args.limit)

    # The skip-list can only ever GROW: nobody un-receives an email. So a
    # skip-list smaller than the committed watermark does not mean fewer people
    # were mailed, it means state was LOST — and the way that happens is
    # mundane: data/outreach_sent.csv is gitignored and has never been
    # committed, and _remote_emails() returns an empty set (not an error) when
    # SUPABASE_PAT is unset. A fresh clone with neither therefore resolves a
    # skip-list of zero and would cheerfully re-email all 571 superintendents
    # already contacted. Refuse instead, and say exactly how to recover.
    refusal = skiplist_shrank(report["skiplist"])
    if refusal and not args.ignore_watermark:
        print(refusal)
        return 1

    print("sending this wave:")
    print(describe_selection(todo, report))

    ok = fail = 0
    reconcile_failed = False
    try:
        for i, row in enumerate(todo, 1):
            rid = tracking.new_rid()
            body, text = render_email(row, postal, unsubscribe, rid=rid)
            try:
                payload = {
                    "from": from_addr, "to": [row["email"]],
                    "reply_to": os.environ.get("RESEND_REPLY_TO", from_addr),
                    "subject": row["subject"], "html": body, "text": text,
                    "headers": {"List-Unsubscribe": f"<{unsubscribe}>"}}
                if bcc_addr:
                    payload["bcc"] = [bcc_addr]
                got = _req("/emails", key, payload)
                log_sent(row, got.get("id", ""))
                log_recipient(row, rid, got.get("id", ""), campaign)
                ok += 1
                print(f"  [{i}/{len(todo)}] {row['district_name']:<32} "
                      f"{row['email']}")
            except Exception as ex:  # noqa: BLE001 — a bounce must not kill the run
                fail += 1
                print(f"  [{i}/{len(todo)}] FAILED {row['email']}: {ex}")
            time.sleep(1.1)
    finally:
        # This is the manual-recovery step the audit called out: a crash here
        # used to mean the ONLY durable record was whatever log_sent() managed
        # to mirror per-message, and a human had to notice and run
        # sync_outreach_state.py by hand — which has already happened at least
        # once. Reconciling here makes that automatic instead of remembered.
        # It still cannot help against a hard container kill (SIGKILL, an OOM
        # kill) that never lets Python run a finally block at all — that risk
        # is why every message is ALSO mirrored individually in log_sent(),
        # not only here at the end.
        pat = os.environ.get("SUPABASE_PAT", "").strip()
        if pat:
            print("\nreconciling local state with the durable mirror...")
            try:
                # Pass THIS module's own SENT_LOG/RECIPIENTS/OPTOUT explicitly
                # — sync_outreach_state.py has its own copies of those same
                # constants, independent of these. They agree today only
                # because nothing enforces it; reading this module's own
                # (possibly monkeypatched-in-tests, or future --out-directed)
                # paths is what keeps this reconciling the files THIS run
                # actually wrote, not whatever sync_outreach_state.py's
                # defaults happen to point at.
                reconcile_failed = sync_outreach_state.push(
                    pat, sent_log=SENT_LOG, recipients=RECIPIENTS,
                    optout=OPTOUT) != 0
            except Exception as ex:  # noqa: BLE001 — report, don't mask the send's own result
                reconcile_failed = True
                print(f"  RECONCILE FAILED: {ex}", file=sys.stderr)
            if reconcile_failed:
                print("  STATE MAY NOT SURVIVE CONTAINER LOSS. Before this "
                      "container is discarded, run:\n"
                      "    python scripts/sync_outreach_state.py",
                      file=sys.stderr)
        else:
            print("\nSUPABASE_PAT was not set for this run — every send above "
                  "exists ONLY in local, gitignored files. Before this "
                  "container is discarded, run:\n"
                  "    export SUPABASE_PAT=...\n"
                  "    python scripts/sync_outreach_state.py", file=sys.stderr)

    print(f"\ndone: {ok} sent, {fail} failed. Log: "
          f"{_short(SENT_LOG)} (re-runs skip everyone already sent)")
    # Durability outranks a per-message bounce: a failed send is visible in
    # this line and was likely already a suppression/opt-out/bounce the next
    # run will route around on its own, while state that failed to reconcile
    # is exactly the failure mode that has already re-required a human to
    # notice and recover BY HAND — so it gets its own code (3) even when sends
    # also failed (1), rather than one silently swallowing the other. Both
    # facts are still in the line above regardless of which code wins.
    if reconcile_failed:
        return 3
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
