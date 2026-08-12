# Raw Data Archive

## Why this exists

The raw source files in `data/` (~48 MB of CSVs) are gitignored and normally
live only in a disposable dev container. Every committed artifact in
`static/`, and the SHA-256 of the source recorded in
`tests/fixtures/provenance.json`, derive from them. If they are lost and TEA
restates even one row, that SHA can never be re-verified and every artifact
becomes unreproducible — the provenance chain would dead-end at a hash with
nothing to check it against.

All of these files are public State of Texas records (TEA PEIMS finance, TEA
District Snapshot, STAAR district results, TEA property values, Bond Review
Board debt outstanding and bond elections, TEA accountability ratings), so a
public mirror is appropriate and strengthens the provenance chain for anyone
who wants to re-derive the site's numbers — not just us.

**Excluded on purpose:** the `outreach_*` files (superintendent email
addresses and a send log) are private working data, not state records, and
must never appear in a public release. `scripts/archive_raw_data.py` excludes
them by name prefix.

## Where it lives

Each vintage is a GitHub **release asset** on the project repo — never a
commit (the files are large, binary and gitignored by design):

- Releases: <https://github.com/GusAI40/texas-isd-finances/releases>
- Tag scheme: `raw-data-YYYY-MM-DD`, asset `raw-data-YYYYMMDD.tar.gz`
  (the tarball contains the CSVs flat, plus `manifest.json`).

> **Status of vintage 2026-08-12:** the archive was built and its manifest is
> recorded below, but the sandboxed session that built it was not permitted to
> create GitHub releases (organization egress policy: "Creating, editing, or
> deleting releases is not permitted for this session type"). Publish it by
> running the script below from any environment with normal GitHub access
> while the container holding `data/` is still alive, or after restoring
> `data/` and confirming the SHAs match this table.

## How to publish a vintage

```bash
GITHUB_TOKEN=<a GusAI40 token with repo scope> python scripts/archive_raw_data.py
```

The script is idempotent: it reuses an existing release for today's tag and
skips an asset that is already uploaded. The token is read from the
environment only and is never written to disk.

## How to restore

1. Download `raw-data-YYYYMMDD.tar.gz` from the release.
2. Extract and verify every file against the bundled manifest:

   ```bash
   tar -xzf raw-data-YYYYMMDD.tar.gz -C /tmp/raw
   cd /tmp/raw
   python - <<'EOF'
   import hashlib, json
   for m in json.load(open("manifest.json")):
       h = hashlib.sha256(open(m["filename"], "rb").read()).hexdigest()
       assert h == m["sha256"], f"MISMATCH: {m['filename']}"
   print("all sha256 verified")
   EOF
   ```

3. Move the CSVs into `data/` in the repo checkout. The provenance suite
   (`tests/test_provenance.py`) will then re-verify the source hash and every
   headline against them.

## When to cut a new release

Cut a **new** vintage (new date, new tag) whenever a new TEA/BRB file is
ingested — after `ingest_tea_snapshot.py`, `ingest_brb_debt.py`,
`ingest_bond_elections.py`, `ingest_tea_accountability.py`,
`ingest_tea_property.py`, `ingest_staar_district.py` or a new PEIMS finance
download. Old vintages are never overwritten: a restated state file is
exactly the event this archive exists to make detectable, so both the before
and after must stay downloadable.

## Manifest — vintage 2026-08-12

Archive `raw-data-20260812.tar.gz`, 13,754,956 bytes compressed;
11 files, 48,823,043 bytes uncompressed.

| file | bytes | sha256 |
|---|---:|---|
| `brb_debt_outstanding.csv` | 2,655,159 | `e91939c49f782ea07ca03fe7eac043828c287d82c98753dd8a703c2b5f8ef88d` |
| `data_dictionary.csv` | 8,725 | `8b00207c439445ced636a9b2af1d0e08586afa73afcc94fcb46f60e35e7ae3f8` |
| `district_crosswalk.csv` | 85,025 | `e09ffe0b48fe5b34d15405b09bc342ff5ed04e0e65d61fff158bbb0dbfe407c1` |
| `snapshot_all.csv` | 4,387,714 | `3de817ae9d009c15fd8f77c88a87058278dcf59b722bc8a293da4d51f5911871` |
| `staar_district_2024.csv` | 3,232,272 | `e87a0125473a18ca8915a808aeba48c360db12845d157739c497a6ba0df4ac87` |
| `staar_district_2025.csv` | 3,370,041 | `0c5c59fd8edad1c33abb68230936519d14bc0dd4769088933d85eba165857080` |
| `staar_district_long.csv` | 11,015,115 | `485ca6de577a0f071dde722c74bab64c0f611c6ecddf4f54693a390244d67696` |
| `tea_accountability.csv` | 1,661,451 | `ac2689ade5e5d068f99725b86009731adb19b356a42b7a11caa8f028de0bcc58` |
| `tea_property.csv` | 3,092,475 | `b5352cd931220d00d81d6be076bdaaa4a62d596f421925f9576c170976c0c24b` |
| `texas_bond_elections.csv` | 456,005 | `674302d4195961c5d48a96c818be20243ed6f9a757ef5a1790bbf75014687282` |
| `texas_finance_clean.csv` | 18,859,061 | `60aa06351ee4d4e0df1f61190801439556c43e9a5dfab16c8b32b79dddb4447a` |

(`district_crosswalk.csv` and `data_dictionary.csv` are also committed to the
repo; they ride along so the archive is self-sufficient. `tea_property_raw/`
xlsx originals and generated outreach previews are outside the archive's
scope.)
