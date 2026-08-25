"""The dictionary must describe everything, and must not be hand-maintained.

A data dictionary is trusted more than it is checked, so a wrong one is worse
than none. Two properties keep this one honest: it covers every published file,
and it is generated from those files rather than typed.
"""
import ast
import json
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
    src = (ROOT / "scripts" / "build_data_dictionary.py").read_text()
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


def test_the_committed_dictionary_matches_a_fresh_run():
    """A dictionary that drifted from the files it describes is the failure
    mode this whole file exists to prevent."""
    if not (ROOT / "docs" / "DATA_DICTIONARY.md").exists():
        pytest.skip("dictionary not built")
    r = subprocess.run(
        [sys.executable, "scripts/build_data_dictionary.py",
         "--json", "/tmp/dd_check.json", "--markdown", "/tmp/dd_check.md"],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    fresh = Path("/tmp/dd_check.md").read_text()
    committed = (ROOT / "docs" / "DATA_DICTIONARY.md").read_text()
    assert fresh == committed, (
        "docs/DATA_DICTIONARY.md is stale. Re-run "
        "scripts/build_data_dictionary.py and commit the result.")


def test_the_field_counts_are_real():
    """Guards against a dictionary that lists files but describes nothing."""
    p = ROOT / "data" / "data_dictionary.json"
    if not p.exists():
        pytest.skip("dictionary not built")
    d = json.loads(p.read_text())
    assert d["totals"]["fields_documented"] > 300
    assert len(d["routes"]) > 40
    for a in d["artifacts"]:
        assert a["title"], f"{a['file']} has no title"
