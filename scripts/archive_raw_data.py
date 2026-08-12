"""Archive the raw source data to a public GitHub release.

Why this exists
---------------
The ~43 MB of raw source CSVs in `data/` (TEA PEIMS finance, TEA Snapshot,
STAAR, property values, BRB debt outstanding, bond elections, accountability)
are gitignored and live only in a disposable dev container. Every committed
artifact — and the provenance fixture's SHA-256 of the source — derives from
them. If they are lost and TEA restates a single row, the SHA in
`tests/fixtures/provenance.json` can never be re-verified and every artifact
becomes unreproducible. All of these files are public State of Texas records,
so a public mirror is appropriate and strengthens the provenance chain for
everyone, not just us.

What it does
------------
1. Builds a manifest (filename, bytes, sha256) of every raw CSV/JSON in
   `data/` — EXCLUDING the `outreach_*` files, which carry superintendent
   email addresses and a send log and are NOT public state records. They must
   never appear in a public release.
2. Writes `manifest.json` and tars/gzips the set into
   `raw-data-YYYYMMDD.tar.gz` OUTSIDE the repo (scratchpad/tmp).
3. If `GITHUB_TOKEN` is set, publishes the archive as a release asset on
   GusAI40/texas-isd-finances (tag `raw-data-YYYY-MM-DD`). Idempotent: an
   existing release is reused, an existing asset is skipped.

The token is read from the environment only and is never written anywhere.

    python scripts/archive_raw_data.py            # build archive only
    GITHUB_TOKEN=... python scripts/archive_raw_data.py   # build + upload

Cut a new release (new date, new tag) whenever a new TEA/BRB vintage is
ingested — see docs/RAW_DATA_ARCHIVE.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPO = "GusAI40/texas-isd-finances"
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"

# Raw public-record inputs only. The outreach files carry superintendent
# email addresses and a send log — private working data, never published.
INCLUDE_GLOBS = ("*.csv", "*.json")
EXCLUDE_PREFIXES = ("outreach",)


def is_raw_source(path: Path) -> bool:
    """True for a top-level data file that belongs in the public archive."""
    if not path.is_file():
        return False
    if not any(path.match(g) for g in INCLUDE_GLOBS):
        return False
    return not path.name.lower().startswith(EXCLUDE_PREFIXES)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(paths: list[Path]) -> list[dict]:
    """Manifest rows (filename, bytes, sha256) for the given files, sorted by name."""
    return [
        {"filename": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        for p in sorted(paths, key=lambda p: p.name)
    ]


def build_archive(out_dir: Path, stamp: str | None = None) -> tuple[Path, list[dict]]:
    """Write manifest.json + raw-data-YYYYMMDD.tar.gz into out_dir; return (archive, manifest)."""
    stamp = stamp or date.today().strftime("%Y%m%d")
    files = [p for p in sorted(DATA.iterdir()) if is_raw_source(p)]
    if not files:
        raise SystemExit(f"no raw source files found in {DATA}")
    manifest = build_manifest(files)

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    archive = out_dir / f"raw-data-{stamp}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(manifest_path, arcname="manifest.json")
        for p in files:
            tar.add(p, arcname=p.name)
    return archive, manifest


# --- GitHub release upload (curl subprocess; token from env only) -----------

def _curl(token: str, args: list[str]) -> str:
    cmd = ["curl", "-sS", "-H", f"Authorization: token {token}",
           "-H", "Accept: application/vnd.github+json"] + args
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout


def _get_release(token: str, tag: str) -> dict | None:
    out = _curl(token, [f"{API}/repos/{REPO}/releases/tags/{tag}"])
    data = json.loads(out)
    return data if "id" in data else None


def ensure_release(token: str, tag: str, manifest: list[dict]) -> dict:
    existing = _get_release(token, tag)
    if existing:
        print(f"release {tag} already exists — reusing (id {existing['id']})")
        return existing
    day = tag.removeprefix("raw-data-")
    sha_lines = "\n".join(
        f"| `{m['filename']}` | {m['bytes']:,} | `{m['sha256']}` |" for m in manifest
    )
    body = (
        f"Raw source data vintage {day} for txisd.dev / texas-isd-finances.\n\n"
        "Every file in this archive is a public State of Texas record (TEA PEIMS "
        "actual financial data, TEA District Snapshot, STAAR district results, "
        "TEA property values, Bond Review Board debt outstanding and bond "
        "elections, TEA accountability ratings) or a small derived registry "
        "built from them. They are the gitignored inputs from which every "
        "committed artifact and the provenance fixture's source SHA-256 derive. "
        "This mirror exists so the provenance chain stays verifiable even if "
        "the state restates or removes a file.\n\n"
        "Restore: download, verify each SHA-256 against `manifest.json` inside "
        "the archive (and the table below), then place the files in `data/`. "
        "See docs/RAW_DATA_ARCHIVE.md.\n\n"
        "| file | bytes | sha256 |\n|---|---|---|\n" + sha_lines + "\n"
    )
    payload = json.dumps({
        "tag_name": tag,
        "name": f"Raw source data vintage {day}",
        "body": body,
        "draft": False,
        "prerelease": False,
    })
    out = _curl(token, ["-X", "POST", f"{API}/repos/{REPO}/releases",
                        "-H", "Content-Type: application/json", "-d", payload])
    data = json.loads(out)
    if "id" not in data:
        raise SystemExit(f"release creation failed: {out[:500]}")
    print(f"created release {tag} (id {data['id']})")
    return data


def upload_asset(token: str, release: dict, archive: Path) -> dict:
    for asset in release.get("assets", []):
        if asset["name"] == archive.name:
            print(f"asset {archive.name} already on release — skipping upload")
            return asset
    url = f"{UPLOADS}/repos/{REPO}/releases/{release['id']}/assets?name={archive.name}"
    out = _curl(token, ["-X", "POST", url, "-H", "Content-Type: application/gzip",
                        "--data-binary", f"@{archive}"])
    data = json.loads(out)
    if data.get("state") != "uploaded":
        raise SystemExit(f"asset upload failed: {out[:500]}")
    print(f"uploaded {archive.name} ({data['size']:,} bytes)")
    return data


def verify_release(token: str, tag: str, archive: Path) -> dict:
    release = _get_release(token, tag)
    if not release:
        raise SystemExit(f"verification failed: release {tag} not found")
    names = {a["name"]: a for a in release.get("assets", [])}
    if archive.name not in names:
        raise SystemExit(f"verification failed: asset {archive.name} not on release {tag}")
    asset = names[archive.name]
    if asset["size"] != archive.stat().st_size:
        raise SystemExit(
            f"verification failed: asset size {asset['size']} != local {archive.stat().st_size}")
    print(f"verified: {release['html_url']} serves {archive.name} ({asset['size']:,} bytes)")
    return release


def main() -> int:
    out_dir = Path(os.environ.get("ARCHIVE_OUT_DIR", tempfile.gettempdir())) / "raw-data-archive"
    archive, manifest = build_archive(out_dir)
    total = sum(m["bytes"] for m in manifest)
    print(f"archive: {archive}")
    print(f"archive size: {archive.stat().st_size:,} bytes "
          f"({len(manifest)} files, {total:,} bytes uncompressed)")
    for m in manifest:
        print(f"  {m['sha256']}  {m['bytes']:>12,}  {m['filename']}")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN not set — skipping GitHub release upload")
        return 0
    tag = f"raw-data-{date.today().isoformat()}"
    release = ensure_release(token, tag, manifest)
    upload_asset(token, release, archive)
    release = verify_release(token, tag, archive)
    print(f"release URL: {release['html_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
