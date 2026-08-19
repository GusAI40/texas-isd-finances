"""Make the outreach state durable: mirror data/outreach_sent.csv and
data/outreach_optout.txt into Supabase, and pull them back down.

Why: the local files are gitignored and live only in a disposable container.
Container loss + a re-run would email everyone again — including people who
opted out, which is a broken promise to named people. The tables
(sql/create_outreach_state.sql) outlive any container; this script is the
bridge in both directions.

    python scripts/sync_outreach_state.py            # push local files up
    python scripts/sync_outreach_state.py --pull     # write local files from
                                                     # the tables

Push is INSERT ... ON CONFLICT DO NOTHING, so it is idempotent and never
overwrites a remote row — the remote table only ever grows. Pull refuses to
run if a local file holds an email the table does not (push first), so a
pull can never silently shrink the local record.

Requires SUPABASE_PAT in the environment (a Supabase personal access token).
SQL travels over HTTPS via the Management API because direct Postgres
(5432/6543) is blocked from this container; the custom User-Agent matters —
Cloudflare 403s urllib's default agent ("error 1010", a bot block, not auth).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SENT_LOG = ROOT / "data/outreach_sent.csv"
RECIPIENTS = ROOT / "data/outreach_recipients.csv"
OPTOUT = ROOT / "data/outreach_optout.txt"

PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "zwhvabkvrexphlskubog")
API = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
USER_AGENT = "texas-isd-finances/1.0 (+https://txisd.dev)"

SENT_FIELDS = ["email", "district_number", "message_id", "sent_at"]


def run_sql(query: str, pat: str) -> list[dict]:
    req = urllib.request.Request(
        API, data=json.dumps({"query": query}).encode(), method="POST",
        headers={"Authorization": f"Bearer {pat}",
                 "Content-Type": "application/json",
                 "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
    return json.loads(raw) if raw else []


def q(s: str) -> str:
    """SQL string literal — single quotes doubled."""
    return "'" + s.replace("'", "''") + "'"


def _short(path: Path) -> str:
    """Repo-relative when the path is inside the repo, absolute otherwise —
    a progress line must never be the thing that raises, and a caller can
    legitimately pass a path outside ROOT (send_outreach.py does, in tests)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------
# push: local files → tables (idempotent, additive only)

def push(pat: str, *, sent_log: Path | None = None, recipients: Path | None = None,
         optout: Path | None = None) -> int:
    """Push local send state up to the durable mirror.

    The three paths default to this module's OWN files (the CLI usage:
    ``python scripts/sync_outreach_state.py``) — resolved at CALL time via a
    None sentinel, not baked into the signature, so the usual monkeypatch
    idiom (``monkeypatch.setattr(sync_outreach_state, "SENT_LOG", ...)``)
    still works for a caller that omits the keyword. send_outreach.py's own
    real-send loop calls this directly from its `finally` block to reconcile
    state automatically on exit — and it must reconcile the files IT wrote,
    which under a monkeypatched SENT_LOG/RECIPIENTS in a test (or a future
    --out flag) are not this module's own constants. Accepting them as
    parameters, rather than reading this module's globals unconditionally, is
    what keeps that call honest about which files it is actually syncing.
    """
    sent_log = SENT_LOG if sent_log is None else sent_log
    recipients = RECIPIENTS if recipients is None else recipients
    optout = OPTOUT if optout is None else optout
    if sent_log.exists():
        rows = list(csv.DictReader(sent_log.open()))
        if rows:
            values = ",".join(
                f"({q(r['email'])},{q(r['district_number'])},"
                f"{q(r['message_id'])},{q(r['sent_at'])}::timestamptz)"
                for r in rows)
            run_sql("INSERT INTO public.outreach_sent "
                    "(email, district_number, message_id, sent_at) "
                    f"VALUES {values} ON CONFLICT (email) DO NOTHING", pat)
        print(f"pushed {len(rows)} sent rows from {_short(sent_log)}")
    else:
        rows = []
        print("no local sent log — nothing to push there")

    # Journey tokens. These matter more than they look: visitor_event.rid is a
    # foreign key to outreach_recipient, so a token that never reached the
    # database silently drops every click that presents it. A wave sent with
    # SUPABASE_PAT unset is recoverable ONLY by pushing this file — and only
    # for recipients who have not clicked yet, so push it the same day.
    if recipients.exists():
        recips = list(csv.DictReader(recipients.open()))
        if recips:
            values = ",".join(
                f"({q(r['rid'])},{q(r['email'])},{q(r['district_number'])},"
                f"{q(r.get('campaign') or 'w2')},{q(r.get('message_id') or '')},"
                f"{q(r['sent_at'])}::timestamptz)" for r in recips)
            run_sql("INSERT INTO public.outreach_recipient "
                    "(rid, email, district_number, campaign, message_id, sent_at) "
                    f"VALUES {values} ON CONFLICT (rid) DO NOTHING", pat)
        print(f"pushed {len(recips)} journey tokens from {_short(recipients)}")
    else:
        print("no local journey tokens — nothing to push there")

    optouts = _local_optouts(optout)
    if optouts:
        values = ",".join(f"({q(e)})" for e in sorted(optouts))
        run_sql("INSERT INTO public.outreach_optout (email) "
                f"VALUES {values} ON CONFLICT (email) DO NOTHING", pat)
        print(f"pushed {len(optouts)} opt-outs from {_short(optout)}")
    else:
        print("no local opt-outs — nothing to push there")

    got = run_sql("SELECT (SELECT count(*) FROM public.outreach_sent) AS sent,"
                  "(SELECT count(*) FROM public.outreach_optout) AS optout",
                  pat)[0]
    print(f"remote now holds: {got['sent']} sent · {got['optout']} opt-outs "
          f"(local: {len(rows)} · {len(optouts)})")
    if got["sent"] < len(rows) or got["optout"] < len(optouts):
        print("ERROR: remote holds fewer rows than local after push",
              file=sys.stderr)
        return 1
    return 0


def _local_optouts(optout: Path | None = None) -> set[str]:
    optout = OPTOUT if optout is None else optout
    if not optout.exists():
        return set()
    return {ln.strip().lower() for ln in optout.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")}


# --------------------------------------------------------------------------
# pull: tables → local files (refuses to shrink the local record)

def pull(pat: str) -> int:
    sent = run_sql(
        "SELECT email, district_number, message_id,"
        " to_char(sent_at AT TIME ZONE 'utc',"
        " 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') AS sent_at"
        " FROM public.outreach_sent ORDER BY sent_at, email", pat)
    optout = run_sql(
        "SELECT email FROM public.outreach_optout ORDER BY email", pat)

    # A pull must never lose a local row the remote lacks — that would
    # recreate the exact failure the tables exist to prevent.
    if SENT_LOG.exists():
        local = {r["email"] for r in csv.DictReader(SENT_LOG.open())}
        missing = local - {r["email"] for r in sent}
        if missing:
            print(f"refusing to pull: {len(missing)} local sent rows are not "
                  f"in the table (e.g. {sorted(missing)[:3]}). Push first.",
                  file=sys.stderr)
            return 1
    local_opt = _local_optouts() - {r["email"].lower() for r in optout}
    if local_opt:
        print(f"refusing to pull: {len(local_opt)} local opt-outs are not in "
              f"the table ({sorted(local_opt)[:3]}). Push first.",
              file=sys.stderr)
        return 1

    SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SENT_LOG.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SENT_FIELDS)
        w.writeheader()
        for r in sent:
            w.writerow({k: r[k] or "" for k in SENT_FIELDS})
    print(f"wrote {len(sent)} sent rows to {SENT_LOG.relative_to(ROOT)}")

    if optout or OPTOUT.exists():
        OPTOUT.write_text("".join(f"{r['email']}\n" for r in optout))
        print(f"wrote {len(optout)} opt-outs to {OPTOUT.relative_to(ROOT)}")
    else:
        print("no opt-outs remotely and no local file — nothing written")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pull", action="store_true",
                    help="write the local files FROM the tables "
                         "(default is push: local files → tables)")
    args = ap.parse_args()

    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not pat:
        print("SUPABASE_PAT is not set — export a Supabase personal access "
              "token first. Never pass it as an argument.", file=sys.stderr)
        return 2
    return pull(pat) if args.pull else push(pat)


if __name__ == "__main__":
    sys.exit(main())
