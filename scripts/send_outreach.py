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
import html
import json
import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import format as fmt  # noqa: E402
from src import tracking  # noqa: E402

SITE = "https://txisd.dev"
MERGE = ROOT / "data/outreach_merge.csv"
SENT_LOG = ROOT / "data/outreach_sent.csv"
# Journey tokens live in their own file rather than as a column on the sent
# log: that log already has 571 four-column rows from wave 1, and widening it
# in place would misalign every one of them.
RECIPIENTS = ROOT / "data/outreach_recipients.csv"
OPTOUT = ROOT / "data/outreach_optout.txt"
PREVIEW_DIR = ROOT / "data/outreach_preview"
API = "https://api.resend.com"

BLUE = "#2f4bd7"
INK = "#111318"
MUT = "#5a5f6b"


def render_email(row: dict, postal: str, unsubscribe: str,
                 rid: str = "", site: str = SITE) -> tuple[str, str]:
    """(html, text) for one district. Inline styles only — email clients strip
    <style> blocks. The three insights come from the merge file, which built
    them from the same artefacts the site serves: frame honesty travels.

    When `rid` is supplied the message carries this recipient's journey token:
    the link gets `&rid=…` so their click and everything after it is
    attributable, and an open pixel is appended. Without a rid the email is
    byte-identical to the untracked version, which is what --test sends.
    """
    e = html.escape
    name = row["district_name"]
    insights = [row[k] for k in ("insight_bonds", "insight_debt",
                                 "insight_trend") if row.get(k)]
    # The tracked link and the open pixel. Both are empty-safe: with no rid the
    # link is exactly what wave 1 sent, and the pixel is an empty string.
    link = f"{row['deep_link']}&src=email" + (f"&rid={rid}" if rid else "")
    pixel = (f'<img src="{site}/px/{rid}.gif" width="1" height="1" alt="" '
             f'style="display:block;border:0;" />') if rid else ""
    disclose = (f'This email carries a code unique to you, so we can see '
                f'whether it was opened and whether the report was useful. If '
                f'you&rsquo;d rather we didn&rsquo;t, don&rsquo;t click the '
                f'link &mdash; or reply and we&rsquo;ll delete the record. '
                f'<a href="{site}/about#privacy" style="color:{MUT};">'
                f'What we collect</a>.<br>') if rid else ""
    bullets = "".join(
        f'<tr><td style="padding:0 0 14px 0;vertical-align:top;width:18px;'
        f'color:{BLUE};font-weight:700;">&#8250;</td>'
        f'<td style="padding:0 0 14px 8px;color:{INK};font-size:15px;'
        f'line-height:1.55;">{e(s)}</td></tr>' for s in insights)

    body = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f4f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f2;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;background:#ffffff;border:1px solid #e4e4e0;">
  <tr><td style="padding:36px 40px 0;font-family:Georgia,'Times New Roman',serif;">
    <div style="font-size:12px;letter-spacing:2px;color:{MUT};font-family:Arial,sans-serif;">
      TAG AI &middot; TEXAS ISD FINANCIAL RESOURCE GUIDE</div>
    <h1 style="font-size:26px;line-height:1.3;color:{INK};margin:14px 0 0;">
      We built {e(name)}&rsquo;s report. It&rsquo;s yours.</h1>
  </td></tr>
  <tr><td style="padding:20px 40px 0;font-family:Arial,Helvetica,sans-serif;">
    <p style="font-size:15px;line-height:1.6;color:{INK};margin:0 0 16px;">
      Dear {e(row['greeting'])},</p>
    <p style="font-size:15px;line-height:1.6;color:{INK};margin:0 0 16px;">
      Congratulations on the start of the new school year. This week,
      campuses across Texas open their doors &mdash; we know it&rsquo;s the
      busiest week on your calendar, and we wish {e(name)}&rsquo;s students,
      teachers and staff a great 2026&ndash;27.</p>
    <p style="font-size:15px;line-height:1.6;color:{INK};margin:0 0 16px;">
      We&rsquo;re writing because we built something for you, and this felt
      like the right week to hand it over. Texas publishes every number about
      {e(name)} &mdash; finances, results, bonds, debt, boundaries &mdash; but
      across ten different state files that never talk to each other, which
      means the people your numbers describe can rarely see the whole
      picture. We believe transparency shouldn&rsquo;t take a records
      request. So we connected the files. This isn&rsquo;t a pitch;
      it&rsquo;s a gift: your district&rsquo;s complete public record,
      synthesized, on one page. A few things it already shows:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 8px;">{bullets}</table>
    <p style="font-size:13px;line-height:1.5;color:{MUT};margin:0 0 22px;">
      {e(row['hook'])}</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 26px;"><tr>
      <td style="background:{BLUE};border-radius:4px;">
        <a href="{e(link)}"
           style="display:inline-block;padding:13px 26px;color:#ffffff;
                  font-family:Arial,sans-serif;font-size:15px;font-weight:bold;
                  text-decoration:none;">See {e(name)}&rsquo;s full report &rarr;</a>
      </td></tr></table>
  </td></tr>
  <tr><td style="padding:0 40px;"><hr style="border:none;border-top:1px solid #e4e4e0;margin:0;"></td></tr>
  <tr><td style="padding:22px 40px 0;font-family:Arial,Helvetica,sans-serif;">
    <p style="font-size:14px;line-height:1.6;color:{INK};margin:0 0 12px;">
      <b>Who we are.</b> TAG ai works at the intelligence layer of data: we
      don&rsquo;t replace the systems you already have, we connect them and
      make them answer questions. This portal is our proof &mdash; 6.6 million
      public data points on all 1,310 districts, every figure linked to the
      state file it came from, and it refuses to guess.</p>
    <img src="{SITE}/static/tag-pipeline.png" width="520"
         alt="TAG ai: ten official state sources in, one intelligence layer,
              plain-English answers out"
         style="width:100%;max-width:520px;height:auto;margin:6px 0 16px;border:1px solid #e4e4e0;">
    <p style="font-size:14px;line-height:1.6;color:{INK};margin:0 0 22px;">
      If you&rsquo;d like a 20-minute walkthrough of {e(name)}&rsquo;s page
      &mdash; or to talk about what the same intelligence layer could do on
      your district&rsquo;s own data &mdash; just reply to this email. And if
      any figure looks wrong, tell us: we publish corrections with credit.</p>
    <p style="font-size:14px;line-height:1.7;color:{INK};margin:0 0 28px;">
      <b>Gus Sanchez</b><br>
      TAG ai<br>
      <a href="tel:+19092686875" style="color:{INK};text-decoration:none;">909-268-6875</a><br>
      <a href="mailto:gus@ubntag.com" style="color:{INK};">gus@ubntag.com</a></p>
  </td></tr>
  <tr><td style="padding:18px 40px 26px;background:#fafaf8;border-top:1px solid #e4e4e0;
               font-family:Arial,sans-serif;font-size:11.5px;line-height:1.6;color:{MUT};">
    All figures are derived from public records published by the State of
    Texas (TEA, Bond Review Board, Comptroller); sources and methods:
    <a href="{SITE}/sources" style="color:{MUT};">{SITE.replace('https://','')}/sources</a>.
    Your address comes from TEA&rsquo;s public district directory (AskTED).<br>
    Artificial intelligence was used in the preparation of this report and this
    email, orchestrated across our entire system. Figures carry a margin of
    error and are provided &ldquo;as&nbsp;is&rdquo; without warranty; verify
    independently before acting &mdash; use is at your own risk.
    <a href="{SITE}/transparency" style="color:{MUT};">How this was made, and
    the full terms</a>.<br>
    {disclose}This is a commercial message from TAG ai &middot; {e(postal)}<br>
    Don&rsquo;t want to hear from us? <a href="{e(unsubscribe)}"
    style="color:{MUT};">Unsubscribe</a> and we won&rsquo;t write again.
  </td></tr>
</table>
</td></tr></table>{pixel}</body></html>"""

    text = (f"Dear {row['greeting']},\n\n"
            f"Congratulations on the start of the new school year — we wish "
            f"{name}'s students, teachers and staff a great 2026–27.\n\n"
            f"We're writing because we built something for you, and this felt "
            f"like the right week to hand it over. Texas publishes every "
            f"number about {name} — but across ten state files that never "
            f"talk to each other, so the people the numbers describe can "
            f"rarely see the whole picture. We believe transparency "
            f"shouldn't take a records request. So we connected the files. "
            f"Your district's complete public record, on one page:\n\n"
            + "".join(f"  • {s}\n" for s in insights) +
            f"\n{row['hook']}\n\n"
            f"See {name}'s full report: {link}\n\n"
            f"Who we are: TAG ai works at the intelligence layer of data — we "
            f"connect the systems you already have and make them answer "
            f"questions. Reply to this email for a 20-minute walkthrough, or "
            f"to talk about your own data. If any figure looks wrong, tell "
            f"us — we publish corrections with credit.\n\n"
            f"Gus Sanchez\n"
            f"TAG ai\n"
            f"909-268-6875\n"
            f"gus@ubntag.com\n\n"
            f"Sources and methods: {SITE}/sources\n"
            f"AI disclosure: artificial intelligence was used in the "
            f"preparation of this report and this email, orchestrated across "
            f"our entire system. Figures carry a margin of error and are "
            f"provided as-is without warranty; verify independently before "
            f"acting — use is at your own risk. How this was made and full "
            f"terms: {SITE}/transparency\n"
            + (f"This email carries a code unique to you, so we can see "
               f"whether it was opened and whether the report was useful. If "
               f"you'd rather we didn't, don't click the link — or reply and "
               f"we'll delete the record. {SITE}/about#privacy\n"
               if rid else "") +
            f"This is a commercial message from TAG ai · {postal}\n"
            f"Unsubscribe: {unsubscribe}\n")
    return body, text


def _req(path: str, key: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    # The User-Agent matters: api.resend.com sits behind Cloudflare, which
    # 403s Python's default urllib UA ("error 1010") while the same request
    # from curl succeeds. Same trap as the Supabase Management API — the 403
    # is NOT an auth failure, do not chase the key.
    r = urllib.request.Request(
        f"{API}{path}", data=data, method="POST" if data else "GET",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "User-Agent": "txisd-outreach/1.0 (+https://txisd.dev)"})
    with urllib.request.urlopen(r, timeout=30,
                                context=ssl.create_default_context()) as resp:
        return json.load(resp)


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


def domain_verified(key: str, from_addr: str) -> bool:
    """Refuse a mass send from an unverified domain — Resend would accept the
    call and every message would land in spam or bounce."""
    domain = from_addr.split("@")[-1].rstrip(">").strip()
    got = _req("/domains", key)
    for d in got.get("data", []):
        if d.get("name") == domain and d.get("status") == "verified":
            return True
    return False


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


def load_sent() -> set[str]:
    """Everyone already emailed: local CSV ∪ the Supabase mirror. Remote
    wins by union — an address in either place is never emailed again."""
    local = set()
    if SENT_LOG.exists():
        local = {r["email"] for r in csv.DictReader(SENT_LOG.open())}
    return local | _remote_emails("outreach_sent")


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
    unsub_addr = (os.environ.get("RESEND_REPLY_TO") or from_addr
                  or "hello@txisd.dev").split("<")[-1].rstrip(">")
    unsubscribe = f"mailto:{unsub_addr}?subject=unsubscribe"

    # ---- dry run (default): render previews, send nothing -------------------
    if not args.test and not args.send:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        for row in rows[:args.previews]:
            body, text = render_email(row, postal or "[postal address — set "
                                      "TAG_POSTAL_ADDRESS]", unsubscribe)
            stem = PREVIEW_DIR / row["district_number"]
            stem.with_suffix(".html").write_text(body)
            stem.with_suffix(".txt").write_text(text)
        print(f"dry run: wrote {min(args.previews, len(rows))} previews to "
              f"{PREVIEW_DIR.relative_to(ROOT)}/ — nothing sent.")
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
            sample = rows[:args.limit or 2]
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

    sent, optout = load_sent(), load_optout()
    todo = [r for r in rows if r["email"] not in sent
            and r["email"].lower() not in optout]
    skipped = len(rows) - len(todo)
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(rows)} districts in merge · {skipped} already sent/opted out "
          f"· sending {len(todo)} now")

    ok = fail = 0
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

    print(f"\ndone: {ok} sent, {fail} failed. Log: "
          f"{SENT_LOG.relative_to(ROOT)} (re-runs skip everyone already sent)")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
