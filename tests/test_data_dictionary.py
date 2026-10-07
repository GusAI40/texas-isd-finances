"""The dictionary must describe everything, and must not be hand-maintained.

A data dictionary is trusted more than it is checked, so a wrong one is worse
than none. Two properties keep this one honest: it covers every published file,
and it is generated from those files rather than typed.
"""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_every_published_file_has_a_plain_english_entry():
    """The builder's own docstring promises this. A layer added without a
    sentence explaining it would appear in the dictionary as a bare filename,
    which is exactly the confusion the dictionary exists to end."""
    from build_data_dictionary import PURPOSE

    published = {p.name for p in (ROOT / "static").glob("*.json")}
    missing = sorted(published - set(PURPOSE))
    assert not missing, (
        f"no plain-English entry for {missing}. Add one to PURPOSE in "
        f"scripts/build_data_dictionary.py — a file nobody can describe in a "
        f"sentence is a file nobody can use.")


def test_every_published_file_is_placed_in_a_group():
    """Grouping is by the QUESTION a file answers. An ungrouped file falls into
    a bucket that tells a reader nothing."""
    from build_data_dictionary import GROUPS

    published = {p.name for p in (ROOT / "static").glob("*.json")}
    placed = {f for _t, _b, files in GROUPS for f in files}
    missing = sorted(published - placed)
    assert not missing, (
        f"{missing} not placed in GROUPS. Decide which question each answers.")


def test_the_dictionary_is_generated_and_not_typed():
    """Parsed with ast, because grepping for 'open(' matches the docstring's
    own explanation of why it is generated."""
    src = (ROOT / "scripts" / "build_data_dictionary.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    reads = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "attr", getattr(f, "id", ""))
            if name in ("read_text", "open", "glob", "parse"):
                reads.add(name)
    assert {"read_text", "glob"} <= reads, (
        "the builder must read the real files; if it stops doing so it has "
        "become a hand-written document wearing a script's name")


def test_the_committed_dictionary_matches_a_fresh_run(tmp_path):
    """A dictionary that drifted from the files it describes is the failure
    mode this whole file exists to prevent."""
    if not (ROOT / "docs" / "DATA_DICTIONARY.md").exists():
        pytest.skip("dictionary not built")
    env = os.environ | {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    r = subprocess.run(
        [sys.executable, "scripts/build_data_dictionary.py",
         "--json", str(tmp_path / "dd_check.json"), "--markdown", str(tmp_path / "dd_check.md")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=300, env=env)
    assert r.returncode == 0, r.stderr
    fresh = (tmp_path / "dd_check.md").read_text(encoding="utf-8")
    committed = (ROOT / "docs" / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    assert fresh == committed, (
        "docs/DATA_DICTIONARY.md is stale. Re-run "
        "scripts/build_data_dictionary.py and commit the result.")


def test_the_field_counts_are_real():
    """Guards against a dictionary that lists files but describes nothing."""
    p = ROOT / "data" / "data_dictionary.json"
    if not p.exists():
        pytest.skip("dictionary not built")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["totals"]["fields_documented"] > 300
    assert len(d["routes"]) > 40
    for a in d["artifacts"]:
        assert a["title"], f"{a['file']} has no title"


def test_dictionary_artifact_metadata_is_utf8_and_line_ending_canonical(tmp_path):
    from build_data_dictionary import describe_artifact

    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    payload = '{\n  "meta": {"source": "Peña"},\n  "districts": {"057905": {"name": "Münster"}}\n}\n'
    lf.write_text(payload, encoding="utf-8", newline="\n")
    crlf.write_text(payload, encoding="utf-8", newline="\r\n")
    left, right = describe_artifact(lf), describe_artifact(crlf)
    assert left["source"] == "Peña"
    assert left["fields"] == right["fields"]
    assert left["bytes"] == right["bytes"]


def test_dictionary_reads_current_working_file_and_rejects_invalid_utf8(tmp_path):
    from build_data_dictionary import describe_artifact

    path = tmp_path / "working.json"
    path.write_text('{"meta":{"source":"one"},"districts":{}}\n', encoding="utf-8", newline="\n")
    first = describe_artifact(path)
    path.write_text('{"meta":{"source":"two"},"districts":{}}\n', encoding="utf-8", newline="\n")
    second = describe_artifact(path)
    assert first["source"] == "one" and second["source"] == "two"
    path.write_bytes(b'{"meta":"\xff"}')
    with pytest.raises(UnicodeDecodeError):
        describe_artifact(path)


def test_mini_dictionary_generation_is_utf8_lf_canonical_and_uses_working_files(tmp_path, monkeypatch):
    import build_data_dictionary as builder

    root = tmp_path / "mini"
    static = root / "static"
    static.mkdir(parents=True)
    (root / "src").mkdir()
    (root / "sql").mkdir()
    (root / "src" / "api.py").write_text("", encoding="utf-8", newline="\n")
    (root / "sql" / "create_tables.sql").write_text("", encoding="utf-8", newline="\n")
    payload = '{\r\n  "meta": {"source": "Peña"},\r\n  "districts": {}\r\n}\r\n'
    artifact = static / "sample.json"
    artifact.write_text(payload, encoding="utf-8", newline="")
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "STATIC", static)
    first = builder.build()
    first_markdown = builder.markdown(first).encode("utf-8")
    artifact.write_text(payload.replace("\r\n", "\n"), encoding="utf-8", newline="")
    second = builder.build()
    second_markdown = builder.markdown(second).encode("utf-8")
    assert first == second and first_markdown == second_markdown
    assert b"\r" not in first_markdown and "Peña" in first_markdown.decode("utf-8")
    artifact.write_text('{"meta":{"source":"changed"},"districts":{}}\n', encoding="utf-8", newline="\n")
    assert builder.build()["artifacts"][0]["source"] == "changed"
