"""Evidence classification for the artifact verifier stays deliberately narrow."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("verify_artifacts", ROOT / "scripts" / "verify_artifacts.py")
verify = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(verify)


def test_only_explicit_data_path_os_errors_are_unverified():
    assert verify.is_known_missing_raw_input("FileNotFoundError: data\\raw.csv")
    assert verify.is_known_missing_raw_input("No such file or directory: data/input.csv")
    assert not verify.is_known_missing_raw_input("input not present; run scripts/build.py")
    assert not verify.is_known_missing_raw_input("FileNotFoundError: C:\\temp\\missing.json")
    assert not verify.is_known_missing_raw_input("Traceback (most recent call last): boom")


def run_one(monkeypatch, tmp_path, result):
    repo = tmp_path / "repo"
    static = repo / "static"
    static.mkdir(parents=True)
    (static / "one.json").write_text('{"meta": {}}', encoding="utf-8")
    monkeypatch.setattr(verify, "ROOT", repo)
    monkeypatch.setattr(verify, "CHAIN", [("one.json", "fake.py", [])])
    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **k: result)
    monkeypatch.setattr("sys.argv", ["verify_artifacts.py"])
    return verify.main()


def test_genuine_builder_failure_is_not_fabricated_unverified(monkeypatch, tmp_path, capsys):
    code = run_one(monkeypatch, tmp_path, SimpleNamespace(returncode=1, stdout="", stderr="Traceback: assertion failed"))
    assert code == 1
    assert "build failed" in capsys.readouterr().out


def test_missing_raw_data_is_reported_unverified(monkeypatch, tmp_path, capsys):
    code = run_one(monkeypatch, tmp_path, SimpleNamespace(returncode=1, stdout="", stderr="FileNotFoundError: data\\source.csv"))
    assert code == 0
    assert "NOTHING WAS VERIFIED" in capsys.readouterr().out


def test_successful_rebuild_with_different_bytes_fails(monkeypatch, tmp_path, capsys):
    def build(command, **kwargs):
        Path(command[3]).write_text('{"meta": {"districts": 2}}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    repo = tmp_path / "repo"
    static = repo / "static"
    static.mkdir(parents=True)
    (static / "one.json").write_text('{"meta": {"districts": 1}}', encoding="utf-8")
    monkeypatch.setattr(verify, "ROOT", repo)
    monkeypatch.setattr(verify, "CHAIN", [("one.json", "fake.py", [])])
    monkeypatch.setattr(verify.subprocess, "run", build)
    monkeypatch.setattr("sys.argv", ["verify_artifacts.py"])
    assert verify.main() == 1
    assert "DRIFT" in capsys.readouterr().out


def test_update_keeps_builder_failure_nonzero(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    (repo / "static").mkdir(parents=True)
    monkeypatch.setattr(verify, "ROOT", repo)
    monkeypatch.setattr(verify, "CHAIN", [("one.json", "fake.py", [])])
    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"))
    monkeypatch.setattr("sys.argv", ["verify_artifacts.py", "--update"])
    assert verify.main() == 1
    assert "boom" in capsys.readouterr().err
