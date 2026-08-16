"""Where the outreach actually landed, on a map of Texas.

One dot per district in the mailing list, coloured by how far that district got
through the funnel: sent -> arrived -> opened -> clicked through to their own
report. It answers the question no table answers well — *which parts of the
state are we reaching, and which are we not?*

Why this is not on the public site
----------------------------------
Every dot is a named superintendent and whether they opened an email. That is
behavioural data about identifiable people, and the rest of txisd.dev is
deliberately anonymous. So this lives behind its own token on /ops/*, the
public site is untouched, and the payload is assembled per request from the
database rather than committed anywhere.

Six states, not four, and the extra two are the honest ones
-----------------------------------------------------------
The obvious design is sent / opened / clicked. It would misreport, twice:

  UNKNOWN   We have sent 571 emails but only checked 271 against the provider.
            Painting the other 300 as "not opened" asserts a measurement we
            have not made. Same error as calling an unrated campus a failing
            one — so they render hollow, and the legend says how many.

  BOUNCED   An address that never arrived is not a superintendent ignoring us.
            Folding it into "not opened" would quietly overstate disinterest
            and hide a list-quality problem that is worth fixing.

CLICKED will read zero for wave 1 no matter how many people clicked, because
click tracking was a disabled toggle during those sends and the links are
already delivered. That is a real limit of the data, not a bug here, and the
payload says so in `limits` so the caveat travels with the numbers.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "static" / "district_geo.json"
CROSSWALK = ROOT / "data" / "district_crosswalk.csv"

# Order matters: a district is coloured by the FURTHEST point it reached.
FUNNEL = ["not_sent", "unknown", "bounced", "delivered", "opened", "clicked"]


def _geography() -> dict[str, dict]:
    """district_number -> {name, lon, lat}. From the committed boundary payload,
    so the map works with no database and no third-party tiles."""
    d = json.loads(GEO.read_text())["d"]
    return {num: {"name": rec["n"], "lon": rec["c"][0], "lat": rec["c"][1]}
            for num, rec in d.items()}


def _names() -> dict[str, str]:
    with CROSSWALK.open() as fh:
        return {r["district_number"]: r["district_name"]
                for r in csv.DictReader(fh)}


async def _rows(conn, sql: str) -> list[dict]:
    """Query tolerantly: a table that has not been created yet is a migration
    that has not run, not an outage, and must not blank the whole map."""
    try:
        return [dict(r) for r in await conn.fetch(sql)]
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        print(f"outreach_map: skipping ({exc})")
        return []


async def build(pool, mailing_list: set[str] | None = None) -> dict[str, Any]:
    """Assemble the map payload. `pool` may be None (returns geography only)."""
    geo, names = _geography(), _names()
    sent: dict[str, dict] = {}
    status: dict[str, str] = {}
    journey: dict[str, dict] = {}

    if pool is not None:
        async with pool.acquire() as conn:
            # These tables hold one row per address / per message / per rid, so
            # a district mailed in two campaigns has SEVERAL rows. Taking
            # whichever arrived last would let an untouched second send erase a
            # real click from the first — the map would quietly downgrade
            # someone who did engage. So: keep the earliest send, and keep the
            # FURTHEST progress rather than the most recent row.
            for r in await _rows(conn,
                                 "SELECT district_number, sent_at FROM public.outreach_sent"):
                num = r.get("district_number")
                if not num:
                    continue
                prev = sent.get(num)
                if prev is None or (r.get("sent_at") and prev.get("sent_at")
                                    and r["sent_at"] < prev["sent_at"]):
                    sent[num] = r

            # Rank so a weaker later row cannot overwrite a stronger earlier one.
            RANK = {"opened": 3, "delivered": 2, "bounced": 1, "suppressed": 1}
            for r in await _rows(conn,
                                 "SELECT district_number, status FROM public.outreach_status"):
                num = r.get("district_number")
                if not num:
                    continue
                st = (r.get("status") or "").lower()
                if RANK.get(st, 0) >= RANK.get(status.get(num, ""), 0):
                    status[num] = st

            for r in await _rows(conn, """
                    SELECT district_number, first_open_at, opens, first_click_at,
                           pageviews, distinct_pages, total_dwell_ms, last_seen_at
                      FROM public.v_recipient_journey"""):
                num = r.get("district_number")
                if not num:
                    continue
                prev = journey.get(num)
                if prev is None:
                    journey[num] = dict(r)
                    continue
                # Merge: any click, any open, and the sums, survive.
                for k in ("first_open_at", "first_click_at"):
                    if r.get(k) and (not prev.get(k) or r[k] < prev[k]):
                        prev[k] = r[k]
                for k in ("opens", "pageviews", "distinct_pages", "total_dwell_ms"):
                    prev[k] = (prev.get(k) or 0) + (r.get(k) or 0)
                if r.get("last_seen_at") and (not prev.get("last_seen_at")
                                              or r["last_seen_at"] > prev["last_seen_at"]):
                    prev["last_seen_at"] = r["last_seen_at"]

    # The map is about outreach, so the universe is the mailing list plus
    # anyone already emailed — NOT all 1,310 districts. Nearly 300 have no
    # contact address at all; drawing them as "not sent yet" would read as a
    # choice we made rather than a district we cannot reach, and would bury the
    # 3 real gaps among 294 charters. They are counted, not plotted.
    universe = set(mailing_list or set()) | set(sent)
    if not universe:
        universe = set(names)
    no_contact = len(set(names) - universe)
    out, counts = {}, dict.fromkeys(FUNNEL, 0)

    for num in sorted(universe):
        g = geo.get(num)
        s, st, j = sent.get(num), status.get(num), journey.get(num) or {}

        if not s:
            state = "not_sent"
        elif j.get("first_click_at") or (j.get("pageviews") or 0) > 0:
            state = "clicked"
        elif j.get("first_open_at") or st == "opened":
            state = "opened"
        elif st in ("bounced", "suppressed"):
            state = "bounced"
        elif st:                      # delivered, complained, anything measured
            state = "delivered"
        else:
            state = "unknown"         # sent, never checked — NOT "not opened"

        counts[state] += 1
        rec: dict[str, Any] = {
            "n": names.get(num) or (g or {}).get("name") or num,
            "s": state,
        }
        if g:
            rec["c"] = [round(g["lon"], 4), round(g["lat"], 4)]
        if s and s.get("sent_at"):
            rec["sent"] = str(s["sent_at"])[:19] + "Z"
        if j.get("first_open_at"):
            rec["opened"] = str(j["first_open_at"])[:19] + "Z"
        if j.get("first_click_at"):
            rec["clicked"] = str(j["first_click_at"])[:19] + "Z"
        for src, dst in (("pageviews", "pv"), ("distinct_pages", "pages"),
                         ("opens", "opens")):
            if j.get(src):
                rec[dst] = int(j[src])
        if j.get("total_dwell_ms"):
            rec["dwell_s"] = round(int(j["total_dwell_ms"]) / 1000)
        out[num] = rec

    plotted = sum(1 for r in out.values() if "c" in r)
    return {
        "meta": {
            "districts": len(out),
            "plotted": plotted,
            "no_boundary": len(out) - plotted,
            "counts": counts,
            "sent_total": len(sent),
            "no_contact": no_contact,
            "limits": [
                "A hollow dot means SENT BUT NEVER CHECKED against the email "
                "provider — not 'did not open'. Run scripts/outreach_kpi.py to "
                "resolve them.",
                "Bounced is shown separately from unopened: an address that "
                "never arrived is not a person ignoring us.",
                "Clicks only exist for campaigns sent AFTER per-recipient "
                "tracking went live. Wave 1's links are already delivered and "
                "cannot be retrofitted, so those districts can never turn "
                "green however many people visited.",
                "Charter districts have no geographic boundary and cannot be "
                "plotted; they are counted in `no_boundary`, not dropped.",
                "`no_contact` districts are absent from the map entirely: we "
                "hold no address for them, which is a coverage gap to fix, not "
                "a district we chose to skip.",
            ],
        },
        "d": out,
    }
