#!/usr/bin/env python3
"""How much money is left for the question box, and how fast is it going?

Why this exists
---------------
The /query ceilings bound CALLS, not DOLLARS: QUERY_DAILY_LIMIT caps how many
questions the agent will answer in a day, not what they cost. For a long time
the honest note in CLAUDE.md was "only a provider-side cap does that, and it is
still owed."

It turns out one already exists, by accident of billing: the DeepSeek account is
prepaid, so the balance IS the cap and the failure is safe — when it runs out
the question box stops and every other page keeps working. That is a fine
design. What it is not is VISIBLE. A prepaid balance draining is indistinguishable
from nothing happening until the day it hits zero, and then the site's most
distinctive feature is quietly dead with no error anywhere.

So this reads the balance and says it out loud, on the same schedule as every
other watchdog.

The ratio worth watching
------------------------
The default daily ceiling is 5,000 questions. Total questions ever asked, as of
2026-08-16, is 18. A ceiling ~278x above observed demand means an abusive or
looping client can drain a small prepaid balance in a day or two — so this warns
on the RATIO as well as the absolute number, because "balance still positive" is
not the same as "configured to survive a bad afternoon".

    export DEEPSEEK_API_KEY=sk-...
    python scripts/check_llm_balance.py
    python scripts/check_llm_balance.py --min 2.00   # fail below $2

Exit 0: balance healthy, or no key configured (nothing to check — this must
never fail a monitor for a credential the runner was not given).
Exit 1: balance below the floor.
Network failures are reported, never fatal: an unreachable provider is not an
empty account, and a watchdog that cries wolf gets ignored.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BALANCE_URL = "https://api.deepseek.com/user/balance"
UA = "txisd-balance-check/1.0 (+https://txisd.dev)"
TIMEOUT = 30


def fetch_balance(key: str) -> tuple[float | None, str]:
    """(usd_balance, detail). None means 'could not tell', never 'zero'."""
    req = urllib.request.Request(BALANCE_URL, headers={
        "Authorization": f"Bearer {key}", "Accept": "application/json",
        "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        # 401 is a real finding — the key the site runs on stopped working.
        return None, f"provider returned HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 — DNS/TLS/timeout are not an outage here
        return None, f"could not reach the provider ({type(e).__name__})"

    for info in body.get("balance_infos", []):
        if (info.get("currency") or "").upper() == "USD":
            try:
                return float(info.get("total_balance")), "ok"
            except (TypeError, ValueError):
                break
    if not body.get("is_available", True):
        return 0.0, "provider reports the account is not available"
    return None, "no USD balance in the response"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min", type=float, default=2.00,
                    help="fail below this USD balance (default 2.00)")
    ap.add_argument("--daily-limit", type=int,
                    default=int(os.getenv("QUERY_DAILY_LIMIT", "5000")),
                    help="the configured questions/day ceiling, for the ratio warning")
    args = ap.parse_args()

    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        print("DEEPSEEK_API_KEY not set — nothing to check, not a failure.")
        return 0

    balance, detail = fetch_balance(key)
    if balance is None:
        print(f"UNVERIFIABLE  {detail}")
        print("  Reported, not failed: an unreachable provider is not an empty "
              "account.")
        return 0

    print(f"question-box balance: ${balance:,.2f}")

    # A ceiling far above real demand is how a small prepaid balance disappears
    # in an afternoon. Warn on the shape, not just the number.
    for price in (0.0005, 0.001, 0.005):
        days = balance / (args.daily_limit * price)
        if days < 7:
            print(f"  WARNING: at {args.daily_limit:,} questions/day and "
                  f"${price:.4f} each, this balance lasts {days:.1f} day(s).")
            print("  Consider lowering QUERY_DAILY_LIMIT — observed demand has "
                  "never exceeded ~10 questions/day.")
            break

    if balance < args.min:
        print(f"LOW: below the ${args.min:,.2f} floor. The question box will "
              f"stop answering when this reaches zero; every other page keeps "
              f"working.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
