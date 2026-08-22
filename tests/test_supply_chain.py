"""Regression rails for reproducible builds and immutable CI dependencies."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def test_every_external_action_is_pinned_to_a_full_commit():
    mutable = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(workflow.read_text().splitlines(), 1):
            match = re.search(r"\buses:\s*([^\s#]+)", line)
            if not match or match.group(1).startswith("./"):
                continue
            reference = match.group(1).rsplit("@", 1)[-1]
            if not re.fullmatch(r"[0-9a-f]{40}", reference):
                mutable.append(f"{workflow.name}:{number}: {match.group(1)}")
            assert "# v" in line, (
                f"{workflow.name}:{number} needs a same-line version comment "
                "so Dependabot can preserve the human-readable release"
            )
    assert mutable == [], "mutable Action references: " + ", ".join(mutable)


def test_production_deploy_path_has_no_duplicate_cli_or_deploy_secrets():
    workflow = (WORKFLOWS / "deploy.yml").read_text()
    assert "Git integration" in workflow
    assert "scripts/verify_live.py" in workflow
    assert '--require-network --expect-revision "$GITHUB_SHA"' in workflow
    assert "npm " not in workflow
    assert "vercel deploy" not in workflow
    assert "secrets." not in workflow
    assert "VERCEL_TOKEN" not in workflow


def test_workflows_use_read_only_permissions_and_drop_checkout_credentials():
    for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = workflow_path.read_text()
        assert re.search(r"(?m)^permissions:\n  contents: read$", workflow), (
            f"{workflow_path.name} lacks a read-only default token")
        if "actions/checkout@" in workflow:
            assert workflow.count("persist-credentials: false") == workflow.count(
                "actions/checkout@"
            ), f"{workflow_path.name} retains GitHub credentials after checkout"


def test_one_uv_lock_covers_every_python_build_path():
    lock = (ROOT / "uv.lock").read_text()
    assert 'name = "texas-isd-finances"' in lock
    assert 'name = "numpy"' in lock
    assert 'name = "pillow"' in lock
    assert 'name = "uvicorn"' in lock
    assert 'name = "pytest"' in lock
    assert 'name = "sqlglot"' in lock
    assert "langchain-community" not in lock

    ci = (WORKFLOWS / "ci.yml").read_text()
    docker = (ROOT / "Dockerfile").read_text()
    render = (ROOT / "render.yaml").read_text()
    assert "uv lock --check" in ci
    assert "uv sync --locked --all-extras --group dev" in ci
    assert "uv sync --locked --no-dev --extra server" in docker
    assert "uv sync --locked --no-dev --extra server" in render
    assert "COPY pyproject.toml uv.lock" in docker


def test_container_base_is_immutable_and_bootstraps_are_not_mutable_latest():
    docker = (ROOT / "Dockerfile").read_text()
    assert re.search(
        r"(?m)^FROM python:\d+\.\d+\.\d+-slim-bookworm@sha256:[0-9a-f]{64}$",
        docker,
    )
    for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = workflow_path.read_text()
        assert "pip install --upgrade pip" not in workflow
        assert "npm install --global" not in workflow
        assert "@latest" not in workflow


def test_direct_offline_imports_are_declared():
    requirements = (ROOT / "requirements.txt").read_text()
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r"(?mi)^numpy\s*[<=>]", requirements)
    assert re.search(r"(?mi)^Pillow\s*[<=>]", requirements)
    assert '"numpy>=1.26.0,<3.0.0"' in pyproject
    assert '"Pillow>=10.0.0,<13.0.0"' in pyproject


def test_update_process_covers_locked_ecosystems():
    config = (ROOT / ".github" / "dependabot.yml").read_text()
    for ecosystem in ("uv", "github-actions", "docker"):
        assert f"package-ecosystem: {ecosystem}" in config
