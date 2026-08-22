#!/usr/bin/env python3
"""Fail when a configured Vercel cron is stale, broken, or unready.

The public cron history endpoint defaults to ``isd-intelligence``. This
watchdog always supplies a job name so adding a second cron cannot silently
leave it unwatched. It prints aggregate readiness only, never run detail.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

RUNS_URL = "https://txisd.dev/api/cron/runs"
MAX_AGE_HOURS = 36


def fetch(job: str, base_url: str = RUNS_URL) -> dict[str, Any]:
    url = f"{base_url}?{urlencode({'job': job})}"
    request = Request(url, headers={"User-Agent": "txisd-cron-monitor/1.0"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed HTTPS host
        return json.load(response)


def _age_hours(value: Any, now: datetime) -> float:
    if not isinstance(value, str):
        raise ValueError("timestamp is not text")
    fired = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if fired.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return (now - fired).total_seconds() / 3600


def problems(
    payload: dict[str, Any],
    job: str,
    policy: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Return sanitized readiness failures for one cron-history response."""
    found: list[str] = []
    if payload.get("job") != job:
        return [f"requested {job!r}, response described another job"]
    if not payload.get("available"):
        return ["cron history unavailable; firing cannot be proven"]

    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        return ["no firing has ever been recorded"]
    latest = runs[0]
    if not isinstance(latest, dict):
        return ["latest firing is malformed"]

    clock = now or datetime.now(timezone.utc)
    try:
        age = _age_hours(latest.get("started_at"), clock)
    except (TypeError, ValueError):
        found.append("latest firing has no parseable timezone-aware timestamp")
    else:
        if age < -1:
            found.append(f"latest firing is {abs(age):.1f}h in the future")
        elif age > MAX_AGE_HOURS:
            found.append(f"latest firing is {age:.1f}h old; daily cron is stale")

    if policy == "drain":
        status = latest.get("status")
        detail = latest.get("detail")
        if status == "skipped" and detail == "unarmed":
            found.append("outreach drain fired but is unarmed in Vercel")
        elif status == "skipped" and detail == "empty":
            pass  # legitimate idle state: cron fired, queue had no work
        elif status == "ok":
            rows_written = latest.get("rows_written")
            if (
                not isinstance(rows_written, int)
                or isinstance(rows_written, bool)
                or rows_written <= 0
            ):
                found.append("outreach drain reported success but sent zero rows")
        else:
            # Do not include detail: the endpoint is public today, but a
            # future exception string must not be copied into Actions logs.
            found.append(f"latest outreach outcome is status={status!r}")
    elif policy == "productive":
        # The endpoint's aggregate error/zero-write counts cover its whole
        # 30-run window. Failing on those would keep a repaired incident red
        # for roughly a month. Readiness is instead the newest firing plus the
        # newest successful, productive run; older failures remain available
        # in history without becoming permanent false alarms.
        status = latest.get("status")
        if status == "error":
            found.append("latest intelligence outcome failed")
        elif status not in {"ok", "skipped"}:
            found.append(f"latest intelligence outcome is status={status!r}")

        latest_ok = next(
            (
                run
                for run in runs
                if isinstance(run, dict) and run.get("status") == "ok"
            ),
            None,
        )
        if latest_ok is None:
            found.append("no successful run recorded at all")
        else:
            # The common latest-firing check already covers this timestamp
            # when the newest firing itself succeeded. Re-check only when a
            # later idempotent skip could otherwise hide a stale last success.
            if latest_ok is not latest:
                try:
                    success_age = _age_hours(latest_ok.get("started_at"), clock)
                except (TypeError, ValueError):
                    found.append("latest successful run has no parseable timestamp")
                else:
                    if success_age < -1:
                        found.append(
                            "latest successful run is "
                            f"{abs(success_age):.1f}h in the future"
                        )
                    elif success_age > MAX_AGE_HOURS:
                        found.append(
                            "latest successful run is "
                            f"{success_age:.1f}h old; job is stale"
                        )
            rows_written = latest_ok.get("rows_written")
            if (
                not isinstance(rows_written, int)
                or isinstance(rows_written, bool)
                or rows_written <= 0
            ):
                found.append("latest successful run wrote zero rows")
    else:
        found.append(f"unknown monitor policy {policy!r}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", choices=(RUNS_URL,), default=RUNS_URL)
    parser.add_argument("--job", required=True)
    parser.add_argument("--policy", choices=("productive", "drain"), required=True)
    args = parser.parse_args(argv)

    try:
        payload = fetch(args.job, args.url)
    except Exception as exc:  # noqa: BLE001 -- one actionable watchdog failure
        print(
            f"CRON MONITOR FAILED ({args.job}): could not read run history "
            f"({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1

    failures = problems(payload, args.job, args.policy)
    if failures:
        print(
            f"SILENT FAILURE ({args.job}): " + "; ".join(failures),
            file=sys.stderr,
        )
        return 1
    print(f"cron {args.job!r} is current and ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
