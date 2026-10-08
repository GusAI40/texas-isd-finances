"""Black-box and version-selection checks for the disposable PG17 runner."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts" / "run_finance_contract_tests.py"
PG17 = Path(
    r"C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128"
    r"\_audit_tools\pg17\pgsql\bin"
)
SPEC = importlib.util.spec_from_file_location("finance_contract_runner", RUNNER)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(runner)


def test_version_validation_rejects_mixed_and_unparseable_reports(monkeypatch, tmp_path):
    for name in ("postgres", "initdb", "pg_ctl", "psql"):
        (tmp_path / f"{name}.exe").touch()

    reports = iter(["postgres (PostgreSQL) 17.11", "initdb (PostgreSQL) 17.11",
                    "pg_ctl (PostgreSQL) 18.3", "psql (PostgreSQL) 17.11"])
    monkeypatch.setattr(runner, "version", lambda _path: next(reports))
    with pytest.raises(RuntimeError, match="majors disagree"):
        runner.validate_binaries(tmp_path, "17")

    monkeypatch.setattr(runner, "version", lambda _path: "unexpected version output")
    with pytest.raises(RuntimeError, match="could not parse"):
        runner.validate_binaries(tmp_path, "17")


def run_nested(target: Path, temp_parent: Path, *, expected_major: str = "17"):
    env = os.environ | {"PG_BIN": str(PG17)}
    return subprocess.run(
        [sys.executable, str(RUNNER), "--expected-major", expected_major,
         "--test-target", str(target), "--temp-parent", str(temp_parent),
         "--skip-runner-self-tests"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )


def test_actual_pg17_selection_rejects_wrong_requested_major(tmp_path):
    result = run_nested(Path("tests/test_finance_contract.py"), tmp_path, expected_major="18")
    assert result.returncode != 0
    assert "selected binaries report 17" in result.stderr
    assert not list(tmp_path.glob("txisd-finance-contract-*"))


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("def test_injected_failure():\n    assert False, 'injected runner failure'\n", "injected runner failure"),
        ("import pytest\npytestmark = pytest.mark.skip(reason='injected skip')\n"
         "def test_injected_skip():\n    pass\n", "selected integration tests were skipped"),
    ],
    ids=["test-failure", "test-skip"],
)
def test_failure_and_skip_are_nonzero_and_cleanup_owned_cluster(tmp_path, body, expected):
    target = tmp_path / "injected_test.py"
    target.write_text(body, encoding="utf-8", newline="\n")
    clusters = tmp_path / "clusters"
    result = run_nested(target, clusters)
    assert result.returncode != 0
    assert expected in result.stdout + result.stderr
    assert "finance contract teardown: owned cluster removed" in result.stdout
    assert not list(clusters.glob("txisd-finance-contract-*"))
