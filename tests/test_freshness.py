"""The freshness watchdog, tested offline.

check_freshness.py is the only check that looks OUTWARD for data we have not
ingested, so its own failure modes matter: a vintage record that quietly stops
covering a source recreates the stale-bond-layer hole, and comparison logic
that never says NEWER is a watchdog that never barks. Everything here runs
with no network — the fetch function is faked.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import check_freshness as cf
from src import sources as S

ROOT = Path(__file__).resolve().parent.parent
MONITOR = ROOT / ".github" / "workflows" / "monitor.yml"


# ---------------------------------------------------------------- the record

def test_vintage_record_parses_and_declares_a_known_method_for_every_entry():
    rec = cf.load_vintages()
    assert rec["sources"], "vintage record has no sources"
    for sid, spec in rec["sources"].items():
        assert spec.get("method") in cf.CHECKERS, (
            f"{sid}: method {spec.get('method')!r} has no checker")
        assert spec.get("check_url", "").startswith("https://"), (
            f"{sid}: check_url must be HTTPS")
        assert spec.get("meaning"), (
            f"{sid}: every entry must say what its vintage means")


def test_each_method_carries_the_fields_its_checker_reads():
    rec = cf.load_vintages()
    for sid, spec in rec["sources"].items():
        m = spec["method"]
        if m == "socrata":
            # must parse as a timestamp or the comparison silently breaks
            from datetime import datetime
            datetime.fromisoformat(spec["vintage_utc"].replace("Z", "+00:00"))
        elif m == "page_year":
            assert isinstance(spec["vintage_year"], int)
            pat = re.compile(spec["pattern"], re.IGNORECASE)
            # the pattern must be anchored on a release label, not a bare year:
            # every TEA page carries a 2026 copyright and nav noise
            assert pat.pattern != r"20\d{2}", f"{sid}: pattern is a bare year"
        elif m == "next_url":
            assert isinstance(spec["vintage_year"], int)
        elif m == "etag":
            assert spec.get("etag") or spec.get("last_modified"), (
                f"{sid}: etag method with nothing recorded to compare")


def test_every_register_source_is_covered_or_explicitly_unverifiable():
    """The coverage guarantee. A source in src/sources.py with no entry here is
    an unwatched source, which is the exact hole the watchdog exists to close.
    'Unverifiable' is allowed, but only said out loud."""
    rec = cf.load_vintages()
    missing = set(S.SOURCES) - set(rec["sources"])
    assert not missing, f"register sources with no vintage entry: {sorted(missing)}"
    stale = set(rec["sources"]) - set(S.SOURCES)
    assert not stale, f"vintage entries for sources no longer registered: {sorted(stale)}"


# ------------------------------------------------------- the comparison logic

def fake_fetch(status=200, body=b"", headers=None, error=None):
    def _fetch(url, **kw):
        r = {"status": status, "body": body, "headers": headers or {}}
        if error:
            r["error"] = error
        return r
    return _fetch


def test_socrata_flags_an_upstream_update_after_our_vintage():
    spec = {"check_url": "https://x", "vintage_utc": "2026-08-11T00:00:00Z"}
    # 2026-08-20 12:00 UTC, after our vintage
    meta = json.dumps({"rowsUpdatedAt": 1787227200}).encode()
    out = cf.check_socrata(spec, fake_fetch(body=meta))
    assert out["state"] == cf.NEWER
    assert "2026-08-20" in out["detail"]


def test_socrata_passes_when_upstream_is_on_or_before_our_vintage():
    spec = {"check_url": "https://x", "vintage_utc": "2026-08-11T00:00:00Z"}
    meta = json.dumps({"rowsUpdatedAt": 1782878578,        # 2026-07-01
                       "viewLastModified": 1593214940}).encode()
    assert cf.check_socrata(spec, fake_fetch(body=meta))["state"] == cf.OK


def test_socrata_reports_network_failure_as_error_not_staleness():
    spec = {"check_url": "https://x", "vintage_utc": "2026-08-11T00:00:00Z"}
    assert cf.check_socrata(spec, fake_fetch(status=0, error="timed out"))["state"] == cf.ERROR
    assert cf.check_socrata(spec, fake_fetch(status=503))["state"] == cf.ERROR


def test_page_year_flags_a_release_year_past_our_vintage():
    spec = {"check_url": "https://x", "pattern": r"Snapshot\s*(20\d{2})",
            "vintage_year": 2024}
    html = b"<a>Snapshot 2023</a> <a>Snapshot 2024</a> <a>Snapshot 2025</a>"
    out = cf.check_page_year(spec, fake_fetch(body=html))
    assert out["state"] == cf.NEWER
    assert "2025" in out["detail"]


def test_page_year_passes_when_the_latest_advertised_release_is_ours():
    spec = {"check_url": "https://x", "pattern": r"Snapshot\s*(20\d{2})",
            "vintage_year": 2024}
    html = b"<a>Snapshot 2024</a> and a 2026 copyright line the pattern ignores"
    assert cf.check_page_year(spec, fake_fetch(body=html))["state"] == cf.OK


def test_page_year_says_so_when_the_pattern_stops_matching():
    """A redesigned page must not read as fresh — the signal vanished."""
    spec = {"check_url": "https://x", "pattern": r"Snapshot\s*(20\d{2})",
            "vintage_year": 2024}
    out = cf.check_page_year(spec, fake_fetch(body=b"<html>new CMS, no labels</html>"))
    assert out["state"] == cf.UNVERIFIABLE


def test_next_url_flags_a_published_next_release_and_passes_a_404():
    spec = {"check_url": "https://x/tl_2025_48_unsd.zip", "vintage_year": 2024}
    shipped = fake_fetch(status=200, headers={"Content-Type": "application/zip"})
    assert cf.check_next_url(spec, shipped)["state"] == cf.NEWER
    assert cf.check_next_url(spec, fake_fetch(status=404))["state"] == cf.OK


def test_next_url_treats_a_200_html_answer_as_a_soft_error_not_a_release():
    spec = {"check_url": "https://x/2026.xlsx", "vintage_year": 2025}
    soft = fake_fetch(status=200, headers={"Content-Type": "text/html; charset=utf-8"})
    assert cf.check_next_url(spec, soft)["state"] == cf.UNVERIFIABLE


def test_etag_flags_change_and_passes_the_recorded_value():
    spec = {"check_url": "https://x", "etag": "abc123"}
    same = fake_fetch(headers={"ETag": '"abc123"'})
    moved = fake_fetch(headers={"ETag": '"def456"'})
    assert cf.check_etag(spec, same)["state"] == cf.OK
    assert cf.check_etag(spec, moved)["state"] == cf.NEWER


def test_etag_falls_back_to_last_modified_then_admits_defeat():
    spec = {"check_url": "https://x", "last_modified": "Tue, 11 Aug 2026 06:07:28 GMT"}
    same = fake_fetch(headers={"Last-Modified": "Tue, 11 Aug 2026 06:07:28 GMT"})
    moved = fake_fetch(headers={"Last-Modified": "Wed, 12 Aug 2026 06:07:28 GMT"})
    naked = fake_fetch(headers={})
    assert cf.check_etag(spec, same)["state"] == cf.OK
    assert cf.check_etag(spec, moved)["state"] == cf.NEWER
    assert cf.check_etag(spec, naked)["state"] == cf.UNVERIFIABLE


def test_evaluate_fails_a_register_source_with_no_vintage_entry():
    register = {"covered": {}, "orphan": {}}
    vintages = {"sources": {"covered": {
        "method": "unverifiable", "check_url": "https://x", "meaning": "none"}}}
    rows = {r["id"]: r for r in cf.evaluate(register, vintages, fake_fetch())}
    assert rows["orphan"]["state"] == cf.UNCOVERED
    assert rows["covered"]["state"] == cf.UNVERIFIABLE


def test_main_exit_codes_fail_on_newer_or_uncovered_and_nothing_else(monkeypatch, capsys):
    def run(rows):
        monkeypatch.setattr(cf, "load_vintages", lambda: {"sources": {}, "recorded": "t"})
        monkeypatch.setattr(cf, "evaluate", lambda *a, **k: rows)
        code = cf.main([])
        capsys.readouterr()
        return code

    row = {"id": "x", "method": "m", "detail": "d"}
    assert run([{**row, "state": cf.OK}]) == 0
    assert run([{**row, "state": cf.UNVERIFIABLE}]) == 0
    assert run([{**row, "state": cf.ERROR}]) == 0        # no egress != stale
    assert run([{**row, "state": cf.NEWER}]) == 1
    assert run([{**row, "state": cf.UNCOVERED}]) == 1


# ----------------------------------------------------------------- the wiring

def test_monitor_workflow_exists_and_runs_every_watchdog():
    """The audit finding was not that the checks were missing — it was that
    nothing RAN them. This pins the wiring."""
    assert MONITOR.exists(), "monitor workflow is gone — nothing watches production"
    y = MONITOR.read_text()
    assert "schedule" in y and re.search(r"cron:\s*'0 12 \* \* \*'", y), \
        "monitor must run on a daily schedule"
    assert "workflow_dispatch" in y, "monitor must be runnable by hand"
    for needle in ("https://txisd.dev/health",
                   "https://txisd.dev/api/cron/runs",
                   "scripts/verify_live.py",
                   "scripts/check_freshness.py"):
        assert needle in y, f"monitor no longer runs {needle}"
    for signal in ("gap_days", "wrote_nothing", "database"):
        assert signal in y, f"monitor no longer reads {signal}"


def test_monitor_workflow_needs_no_secrets():
    """Every endpoint the monitor hits is public by design; a secret reference
    appearing here would mean that stopped being true."""
    assert "secrets." not in MONITOR.read_text()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# --- is the check watching the right product? ---------------------------------
# A year on a page proves nothing. tea_staar_district matched "2025-2026 STAAR"
# and was right that a release existed — but it matched a statewide PDF, not the
# district file this site ingests. Right by coincidence is one page redesign
# away from wrong in silence.

def _spec(**kw):
    base = {"method": "page_year", "check_url": "https://example.invalid/x",
            "pattern": r"(20\d{2})-(20\d{2})\s+Widget", "vintage_year": 2024}
    base.update(kw)
    return base


def _page(body: bytes):
    def fetch(url, **kw):
        return {"status": 200, "body": body, "headers": {}}
    return fetch


def test_product_proof_beside_the_match_passes():
    from scripts.check_freshness import check_page_year
    page = b"<p>2024-2025 Widget &mdash; Summarized Thing Data (Excel)</p>"
    r = check_page_year(_spec(vintage_year=2025,
                              product_proof="Summarized Thing Data"), _page(page))
    assert r["state"] == "OK", r


def test_year_found_but_product_absent_is_unverifiable_not_ok():
    """The STAAR shape exactly: the label is on the page, but it belongs to a
    different product. That must not read as a clean OK or a confident NEWER."""
    from scripts.check_freshness import UNVERIFIABLE, check_page_year
    page = b"<p>2026-2027 Widget &mdash; All Results Analysis (PDF)</p>"
    r = check_page_year(_spec(product_proof="Summarized Thing Data"), _page(page))
    assert r["state"] == UNVERIFIABLE, r
    assert "different product" in r["detail"]


def test_a_source_without_a_proof_still_works():
    """Opting out is allowed — tea_staar_district does, deliberately — but it
    must be a choice, not an accident, so behaviour is unchanged without one."""
    from scripts.check_freshness import check_page_year
    page = b"<p>2026-2027 Widget</p>"
    r = check_page_year(_spec(), _page(page))
    assert r["state"] == "NEWER", r


def test_every_page_year_source_either_proves_itself_or_says_why():
    """No silent gaps: a page_year check with no product_proof must explain in
    its own meaning field why it cannot have one."""
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).resolve().parents[1] / "scripts"
                    / "freshness_vintages.json").read_text())
    for name, spec in d["sources"].items():
        if spec.get("method") != "page_year":
            continue
        if not spec.get("product_proof"):
            assert "coincidence" in spec.get("meaning", "").lower(), (
                f"{name} has no product_proof and does not say why")


# --- the question box runs on a prepaid balance -------------------------------

def test_no_key_is_not_a_failure(monkeypatch):
    """A monitor that fails for a credential the runner was never given is a
    monitor people switch off."""
    import importlib.util
    from pathlib import Path as _P
    sp = _P(__file__).resolve().parents[1] / "scripts" / "check_llm_balance.py"
    spec = importlib.util.spec_from_file_location("_bal", sp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["check_llm_balance.py"])
    assert m.main() == 0


def test_an_unreachable_provider_is_never_reported_as_empty():
    """'Could not tell' and 'zero dollars' must never be the same answer."""
    import importlib.util
    from pathlib import Path as _P
    sp = _P(__file__).resolve().parents[1] / "scripts" / "check_llm_balance.py"
    spec = importlib.util.spec_from_file_location("_bal2", sp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    def boom(url, **kw):
        raise OSError("network down")
    m.urllib.request.urlopen = boom
    balance, detail = m.fetch_balance("sk-whatever")
    assert balance is None, "an outage must not read as an empty account"
    assert "reach" in detail


def test_the_balance_check_has_its_own_workflow():
    """Deliberately NOT in monitor.yml. That workflow references no secrets so
    it always runs and can never silently skip; this check needs the provider
    key, and adding it there would have left monitor.yml green while one step
    quietly did nothing — the exact failure the KPI job had been having every
    Monday. Its own file states the dependency at the top."""
    from pathlib import Path as _P
    wf_dir = _P(__file__).resolve().parents[1] / ".github" / "workflows"
    own = (wf_dir / "llm-balance.yml").read_text()
    assert "check_llm_balance.py" in own
    assert "DEEPSEEK_API_KEY" in own
    assert "INERT until the secret exists" in own, \
        "a workflow that no-ops without a secret must say so where it is read"
    assert "check_llm_balance" not in (wf_dir / "monitor.yml").read_text(), \
        "monitor.yml must stay secret-free"
