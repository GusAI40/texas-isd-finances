"""Outreach KPI snapshot: pull every sent email's fate and make it durable.

Resend is the only system that knows whether an email was opened or bounced,
and that knowledge lives on their servers under their retention rules. This
script copies it home: for every row in data/outreach_sent.csv it asks Resend
for the message's last event, writes a human-readable roster
(data/outreach_kpi_report.csv, openers first), and — when SUPABASE_PAT is set
— upserts every status into public.outreach_status so the engagement history
survives this container, the Resend account, and time.

Usage
-----
    RESEND_API_KEY=... SUPABASE_PAT=... python scripts/outreach_kpi.py

Environment
-----------
    RESEND_API_KEY   required — read-only use of GET /emails/{id}
    SUPABASE_PAT     optional — without it the roster CSV is still written,
                     but nothing durable is recorded and the run says so
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SENT_LOG = ROOT / "data" / "outreach_sent.csv"
CROSSWALK = ROOT / "data" / "district_crosswalk.csv"
REPORT = ROOT / "data" / "outreach_kpi_report.csv"
PROJECT_REF = "zwhvabkvrexphlskubog"

# openers surface first: the roster doubles as a follow-up worklist
_ORDER = {"clicked": 0, "opened": 0, "delivered": 1, "sent": 2,
          "bounced": 3, "suppressed": 4}


def _resend_status(message_id: str, key: str) -> str:
    req = urllib.request.Request(
        f"https://api.resend.com/emails/{message_id}",
        headers={"Authorization": f"Bearer {key}",
                 "User-Agent": "txisd-outreach/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp).get("last_event") or "unknown"
    except Exception:
        return "api-error"


def _district_names() -> dict[str, str]:
    with CROSSWALK.open() as f:
        return {r["district_number"]: r.get("district_name", "")
                for r in csv.DictReader(f)}


def _upsert_supabase(rows: list[dict], pat: str) -> None:
    def esc(s: str) -> str:
        return s.replace("'", "''")
    values = ",".join(
        f"('{esc(r['message_id'])}','{esc(r['district_number'])}',"
        f"'{esc(r['email'])}','{esc(r['status'])}')" for r in rows)
    query = (
        "INSERT INTO public.outreach_status "
        "(message_id, district_number, email, status) VALUES " + values +
        " ON CONFLICT (message_id) DO UPDATE SET "
        "status = EXCLUDED.status, checked_at = now()")
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"Bearer {pat}",
                 "User-Agent": "txisd-outreach/1.0",
                 "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=120).read()


def _remote_sent(pat: str) -> list[dict]:
    """The sent log from Supabase — so this runs on a fresh clone with no
    local files at all (containers die; the database is the memory)."""
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query":
            "SELECT email, district_number, message_id, sent_at::text "
            "FROM public.outreach_sent ORDER BY sent_at"}).encode(),
        headers={"Authorization": f"Bearer {pat}",
                 "User-Agent": "txisd-outreach/1.0",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> int:
    key = os.environ.get("RESEND_API_KEY", "").strip()
    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if not key:
        print("RESEND_API_KEY is not set — cannot read email statuses.")
        return 1

    names = _district_names()
    if SENT_LOG.exists():
        sent = list(csv.DictReader(SENT_LOG.open()))
    elif pat:
        sent = _remote_sent(pat)
        print(f"local sent log absent — using {len(sent)} rows from Supabase")
    else:
        print(f"{SENT_LOG.relative_to(ROOT)} not found and SUPABASE_PAT "
              "unset — no sent log to check.")
        return 1
    print(f"checking {len(sent)} sent emails against Resend…")

    tally: Counter[str] = Counter()
    rows: list[dict] = []
    for r in sent:
        status = _resend_status(r["message_id"], key)
        tally[status] += 1
        rows.append({
            "district": names.get(r["district_number"], r["district_number"]),
            "district_number": r["district_number"], "email": r["email"],
            "sent_at": r["sent_at"][:16], "status": status,
            "message_id": r["message_id"]})
        time.sleep(0.09)          # stay far inside Resend's rate limit

    rows.sort(key=lambda x: (_ORDER.get(x["status"], 9), x["district"]))
    with REPORT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "district", "district_number", "email", "sent_at", "status"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})

    for status, n in tally.most_common():
        print(f"  {status:12} {n}")
    print(f"roster: {REPORT.relative_to(ROOT)} (openers first)")

    pat = os.environ.get("SUPABASE_PAT", "").strip()
    if pat:
        _upsert_supabase(rows, pat)
        print(f"durable: {len(rows)} statuses upserted to "
              "public.outreach_status")
    else:
        print("SUPABASE_PAT not set — statuses NOT recorded durably "
              "(the roster above dies with this machine).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
