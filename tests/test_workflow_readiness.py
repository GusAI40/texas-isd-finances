"""Regression rails for scheduled-job and secret readiness visibility.

These checks are deliberately offline. They pin the workflow boundary that
previously let an unmonitored or unconfigured job look like a successful one,
without ever loading a secret value.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import check_cron_health as cron_health

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def test_monitor_names_every_vercel_cron_and_never_relies_on_api_default():
    """A bare /api/cron/runs request only observes isd-intelligence."""
    monitor = (WORKFLOWS / "monitor.yml").read_text()
    config = json.loads((ROOT / "vercel.json").read_text())
    jobs = {entry["path"].rsplit("/", 1)[-1] for entry in config["crons"]}

    assert jobs == {"isd-intelligence", "outreach-drain"}
    for job in jobs:
        assert re.search(rf"- job:\s*{re.escape(job)}\b", monitor), (
            f"Vercel cron {job!r} is not in the monitor matrix")
    assert 'scripts/check_cron_health.py' in monitor, (
        "monitor still relies on /api/cron/runs' isd-intelligence default")
    assert '--job "$CRON_JOB"' in monitor


def test_outreach_monitor_separates_empty_from_unarmed():
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    base = {
        "job": "outreach-drain",
        "available": True,
        "runs": [{
            "started_at": (now - timedelta(hours=22)).isoformat(),
            "status": "skipped",
            "rows_written": 0,
            "detail": "empty",
        }],
        "errors": 0,
    }
    assert cron_health.problems(base, "outreach-drain", "drain", now=now) == []

    unarmed = {**base, "runs": [{**base["runs"][0], "detail": "unarmed"}]}
    failures = cron_health.problems(
        unarmed, "outreach-drain", "drain", now=now
    )
    assert failures == ["outreach drain fired but is unarmed in Vercel"]


def test_cron_monitor_rejects_stale_wrong_empty_and_latest_failure():
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    latest = {
        "started_at": (now - timedelta(hours=37)).isoformat(),
        "status": "ok",
        "rows_written": 42,
        "detail": "private detail must not be copied",
    }
    payload = {
        "job": "isd-intelligence",
        "available": True,
        "runs": [latest],
        "gap_days": 0,
        "wrote_nothing": 0,
        "errors": 0,
    }
    failures = cron_health.problems(
        payload, "isd-intelligence", "productive", now=now
    )
    assert failures == ["latest firing is 37.0h old; daily cron is stale"]
    assert "private detail" not in " ".join(failures)

    assert cron_health.problems(
        {**payload, "job": "outreach-drain"},
        "isd-intelligence",
        "productive",
        now=now,
    ) == ["requested 'isd-intelligence', response described another job"]
    assert cron_health.problems(
        {**payload, "runs": []},
        "isd-intelligence",
        "productive",
        now=now,
    ) == ["no firing has ever been recorded"]
    failures = cron_health.problems(
        {
            **payload,
            "runs": [{
                **latest,
                "started_at": now.isoformat(),
                "status": "error",
            }],
            "errors": 1,
        },
        "isd-intelligence",
        "productive",
        now=now,
    )
    assert failures == [
        "latest intelligence outcome failed",
        "no successful run recorded at all",
    ]


def test_productive_monitor_does_not_keep_a_repaired_incident_red():
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    payload = {
        "job": "isd-intelligence",
        "available": True,
        "runs": [
            {
                "started_at": now.isoformat(),
                "status": "ok",
                "rows_written": 42,
            },
            {
                "started_at": (now - timedelta(days=1)).isoformat(),
                "status": "error",
                "rows_written": 0,
            },
        ],
        # These endpoint aggregates intentionally describe the whole window.
        "gap_days": 0,
        "wrote_nothing": 0,
        "errors": 1,
    }
    assert cron_health.problems(
        payload, "isd-intelligence", "productive", now=now
    ) == []


def test_productive_cron_must_write_and_drain_success_must_send():
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    latest = {"started_at": now.isoformat(), "status": "ok", "rows_written": 0}
    productive = {
        "job": "isd-intelligence",
        "available": True,
        "runs": [latest],
        "gap_days": 0,
        "wrote_nothing": 1,
        "errors": 0,
    }
    assert cron_health.problems(
        productive, "isd-intelligence", "productive", now=now
    ) == ["latest successful run wrote zero rows"]

    drain = {**productive, "job": "outreach-drain", "wrote_nothing": 0}
    assert cron_health.problems(
        drain, "outreach-drain", "drain", now=now
    ) == ["outreach drain reported success but sent zero rows"]


def test_secret_dependent_workflows_publish_explicit_readiness():
    expected = {
        "replies.yml": {"IMAP_USER", "IMAP_PASSWORD", "SUPABASE_PAT"},
        "outreach-kpi.yml": {"RESEND_API_KEY", "SUPABASE_PAT"},
    }
    for filename, secret_names in expected.items():
        workflow = (WORKFLOWS / filename).read_text()
        assert 'id: readiness' in workflow
        assert 'configured=false" >> "$GITHUB_OUTPUT"' in workflow
        assert 'configured=true" >> "$GITHUB_OUTPUT"' in workflow
        assert 'if: steps.readiness.outputs.configured == \'true\'' in workflow
        assert "::warning title=" in workflow
        assert "NOT CONFIGURED" in workflow
        assert "$GITHUB_STEP_SUMMARY" in workflow
        assert "exit 0" not in workflow
        for name in secret_names:
            assert f"missing+=({name})" in workflow


def test_scheduled_secret_monitors_fail_loudly_when_unconfigured():
    for filename in ("replies.yml", "outreach-kpi.yml", "llm-balance.yml"):
        workflow = (WORKFLOWS / filename).read_text()
        assert "github.event_name == 'schedule'" in workflow
        assert "exit 1" in workflow


def test_network_monitors_and_deploy_gate_require_reachability():
    monitor = (WORKFLOWS / "monitor.yml").read_text()
    deploy = (WORKFLOWS / "deploy.yml").read_text()
    assert "verify_live.py --with-query --require-network" in monitor
    assert monitor.count('--expect-revision "$GITHUB_SHA"') == 1
    assert 'h.get("tracking_schema") != "ready"' in monitor
    assert "check_freshness.py --require-network" in monitor
    assert "--require-network --expect-revision \"$GITHUB_SHA\"" in deploy
    assert "schema ready" in deploy


def test_live_verifier_rejects_an_old_or_missing_deployment_revision(monkeypatch):
    import scripts.verify_live as live

    monkeypatch.setattr(live, "CHECKS", [])
    monkeypatch.setattr(live, "TEXT_CHECKS", [])
    monkeypatch.setattr(live, "load_artifacts", lambda: {})
    monkeypatch.setattr(live, "check_headline_twin", lambda *args: ("SKIP", "test"))
    monkeypatch.setattr(live, "check_caching", lambda *args: ("SKIP", "test"))

    monkeypatch.setattr(live, "get", lambda url: ({"revision": "old-sha"}, None))
    monkeypatch.setattr(
        "sys.argv",
        ["verify_live.py", "--expect-revision", "expected-sha"],
    )
    assert live.main() == 1

    monkeypatch.setattr(live, "get", lambda url: ({}, None))
    assert live.main() == 1

    monkeypatch.setattr(
        live,
        "get",
        lambda url: ({
            "revision": "expected-sha",
            "status": "healthy",
            "database": "connected",
            "tracking_schema": "ready",
        }, None),
    )
    assert live.main() == 0

    monkeypatch.setattr(
        live,
        "get",
        lambda url: ({
            "revision": "expected-sha",
            "status": "healthy",
            "database": "connected",
            "tracking_schema": "unavailable",
        }, None),
    )
    assert live.main() == 1


def test_readiness_logs_names_not_secret_values():
    """No diagnostic command may print a secret-bearing environment value."""
    for filename in ("replies.yml", "outreach-kpi.yml"):
        workflow = (WORKFLOWS / filename).read_text()
        for line in workflow.splitlines():
            if "echo " not in line:
                continue
            assert not re.search(
                r"\$(IMAP_USER|IMAP_PASSWORD|SUPABASE_PAT|RESEND_API_KEY|"
                r"VERCEL_TOKEN|VERCEL_ORG_ID|VERCEL_PROJECT_ID)\b",
                line,
            ), f"{filename} could print a secret value: {line.strip()}"
