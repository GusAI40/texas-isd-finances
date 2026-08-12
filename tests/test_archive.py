"""Offline tests for the raw-data archive tooling.

The archive exists because the raw CSVs live only in a disposable container:
lose them and the provenance SHA in tests/fixtures/provenance.json can never
be re-verified. These tests run with no network and no data/ contents — they
check the manifest math, the exclusion of private outreach files, and that
the restore documentation exists and says what it must.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.archive_raw_data import build_manifest, is_raw_source, sha256_file  # noqa: E402

DOC = ROOT / "docs" / "RAW_DATA_ARCHIVE.md"


# --- manifest: the hashes are real hashes -----------------------------------

def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "sample.csv"
    payload = b"district_number,amount\n057905,123\n"
    p.write_bytes(payload)
    assert sha256_file(p) == hashlib.sha256(payload).hexdigest()


def test_build_manifest_records_name_bytes_and_sha(tmp_path):
    a = tmp_path / "b_second.csv"
    b = tmp_path / "a_first.csv"
    a.write_bytes(b"beta")
    b.write_bytes(b"alpha")
    manifest = build_manifest([a, b])
    assert [m["filename"] for m in manifest] == ["a_first.csv", "b_second.csv"]
    by_name = {m["filename"]: m for m in manifest}
    assert by_name["a_first.csv"]["bytes"] == 5
    assert by_name["a_first.csv"]["sha256"] == hashlib.sha256(b"alpha").hexdigest()
    assert by_name["b_second.csv"]["sha256"] == hashlib.sha256(b"beta").hexdigest()


# --- exclusion: outreach files (emails, send log) never enter the archive ---

def test_outreach_files_are_excluded(tmp_path):
    keep = tmp_path / "texas_finance_clean.csv"
    keep.write_bytes(b"x")
    for name in ("outreach_merge.csv", "outreach_sent.csv", "Outreach_extra.csv"):
        (tmp_path / name).write_bytes(b"private")
    (tmp_path / "notes.txt").write_bytes(b"not a csv")
    assert is_raw_source(keep)
    assert not any(is_raw_source(p) for p in tmp_path.iterdir() if p != keep)


# --- the restore doc exists and carries the verification vocabulary ---------

def test_doc_exists_and_mentions_sha256_and_release_location():
    text = DOC.read_text(encoding="utf-8")
    assert "sha256" in text.lower()
    assert "github.com/GusAI40" in text
