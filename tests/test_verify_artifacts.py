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
    assert verify.is_known_missing_raw_input("missing data\\raw.csv")
    assert verify.is_known_missing_raw_input("not found: data/input.csv")
    assert verify.is_known_missing_raw_input("data/input.csv is absent")
    assert verify.is_known_missing_raw_input(f"missing input: {verify.ROOT / 'data' / 'input.csv'}")
    assert not verify.is_known_missing_raw_input("input not present; run scripts/build.py")
    assert not verify.is_known_missing_raw_input("missing static/output.json")
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
    code = run_one(
        monkeypatch, tmp_path,
        SimpleNamespace(returncode=1, stdout="", stderr="Traceback: assertion failed"),
    )
    assert code == 1
    assert "build failed" in capsys.readouterr().out


def test_missing_raw_data_is_reported_unverified(monkeypatch, tmp_path, capsys):
    code = run_one(
        monkeypatch, tmp_path,
        SimpleNamespace(returncode=1, stdout="", stderr="FileNotFoundError: data\\source.csv"),
    )
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
    monkeypatch.setattr(
        verify.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    monkeypatch.setattr("sys.argv", ["verify_artifacts.py", "--update"])
    assert verify.main() == 1
    assert "boom" in capsys.readouterr().err


def test_known_dependency_cascade_is_unverified(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    static = repo / "static"
    static.mkdir(parents=True)
    for name in ("upstream.json", "downstream.json"):
        (static / name).write_text('{"meta": {}}', encoding="utf-8")
    monkeypatch.setattr(verify, "ROOT", repo)
    monkeypatch.setattr(verify, "CHAIN", [
        ("upstream.json", "upstream.py", []),
        ("downstream.json", "downstream.py", []),
    ])

    def build(command, **_kwargs):
        if command[1].endswith("upstream.py"):
            return SimpleNamespace(returncode=1, stdout="", stderr="missing data\\raw.csv")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=f"FileNotFoundError: {command[3].replace('downstream.json', 'upstream.json')}",
        )

    monkeypatch.setattr(verify.subprocess, "run", build)
    monkeypatch.setattr("sys.argv", ["verify_artifacts.py"])
    assert verify.main() == 0
    output = capsys.readouterr().out
    assert "upstream.json" in output and "downstream.json" in output
    assert "NOTHING WAS VERIFIED" in output


@pytest.mark.parametrize("parent_utf8", [None, "1"], ids=["windows-default", "inherited-utf8"])
def test_zero_verified_result_and_child_encoding_are_explicit(
    monkeypatch, tmp_path, capsys, parent_utf8
):
    repo = tmp_path / "repo"
    static = repo / "static"
    static.mkdir(parents=True)
    (static / "one.json").write_text('{"meta": {}}', encoding="utf-8")
    monkeypatch.setattr(verify, "ROOT", repo)
    monkeypatch.setattr(verify, "CHAIN", [("one.json", "fake.py", [])])
    if parent_utf8 is None:
        monkeypatch.delenv("PYTHONUTF8", raising=False)
    else:
        monkeypatch.setenv("PYTHONUTF8", parent_utf8)

    def build(*_args, **kwargs):
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "backslashreplace"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        return SimpleNamespace(returncode=1, stdout="", stderr="missing data/source.csv")

    monkeypatch.setattr(verify.subprocess, "run", build)
    monkeypatch.setattr("sys.argv", ["verify_artifacts.py"])
    assert verify.main() == 0
    assert "NOTHING WAS VERIFIED" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("body", "expected_code", "expected_text"),
    [
        ("import sys\nsys.stderr.write('missing data\\\\raw.csv\\n')\nraise SystemExit(1)\n", 0, "UNVERIFIED"),
        ("raise RuntimeError('real builder failure')\n", 1, "DRIFT"),
    ],
    ids=["real-missing-source", "real-traceback"],
)
def test_real_builder_process_classification(monkeypatch, tmp_path, capsys, body, expected_code, expected_text):
    repo = tmp_path / "repo"
    (repo / "static").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "static" / "one.json").write_text('{"meta": {}}', encoding="utf-8")
    (repo / "scripts" / "fake.py").write_text(body, encoding="utf-8", newline="\n")
    monkeypatch.setattr(verify, "ROOT", repo)
    monkeypatch.setattr(verify, "CHAIN", [("one.json", "fake.py", [])])
    monkeypatch.setattr("sys.argv", ["verify_artifacts.py"])
    assert verify.main() == expected_code
    captured = capsys.readouterr()
    assert expected_text in captured.out
