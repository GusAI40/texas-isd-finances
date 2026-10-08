# Source refresh review — 2026-10-07

All 15 registered sources were reviewed against current publisher signals. The
[machine-readable ledger](evidence/source-refresh.json) distinguishes retrieval
dates, served vintages, compatible products, sampled content, and unfinished
rebuilds. No served artifact or vintage changed during this review.

| Source | Finding | Disposition and remaining work |
|---|---|---|
| TEA Snapshot | District 2025 detail obtained: 1,208 records, 136 columns; 43/44 existing mapped fields present. | Compatible refresh required. Preserve unavailable accountability_rating; download historical sources and validate dependent rebuilds. |
| District STAAR | Public 2026 signal identifies statewide PDFs; district CSV remains verification gated. | Unresolved. Obtain the authorized district product, then validate and rebuild equity; served 2025 remains stale. |
| Bond elections | Current 4,992 decided propositions and aggregate dollars/results equal served totals. | Unresolved. Compare every normalized proposition and district match; equal totals do not establish equal rows. |
| BRB debt | Issuer index changed; 1,039 ISD issuers. Dallas FY2025 sample agrees with the served debt artifact. | Unresolved. Reconcile all issuer series, identity matches, and historical/scheduled periods. |
| Census TIGER | Publisher 2026 ZIP passes archive integrity; 1,016 records with the same 15 DBF fields. | Compatible refresh required. Compare geometry and validate district/county crosswalks before rebuilding. |
| USAC FRNs | Texas row count changed to 91,921; Funded 41,867 requests total $2,361,216,998.29 commitments. | Compatible refresh required with entity file; retain Funded-only interpretation and independent aggregate checks. |
| USAC entities | Current Texas physical-state count 19,825; required matching fields exist. | Compatible refresh required with FRNs; refuse disagreements rather than guessing a district. |
| TEA PEIMS/property | Advertised latest covered periods still 2025. | No newer-release signal; complete raw rebuild unverified. Preserve served vintage. |
| TEA recapture/CCD | Recorded Last-Modified/ETag signals unchanged. | Metadata parity only; full row-content equality unverified. |
| Accountability 2026/F-33 FY2025/NPEFS FY2025 | Next-product probes do not establish a published compatible file. | Not published at review time; recheck before release. |
| BLS CPI | No stable automatic freshness signal; constant-dollar base 2024 deliberately pinned. | Unresolved automatic check. Verify the actual annual input before changing the base. |

Publisher downloads remain in an isolated local review directory, outside
authoritative data and static artifacts. The ledger records byte counts, SHA256
retrieval fingerprints, capture times, source URLs and follow-up requirements.
These fingerprints identify the reviewed files; they do not certify downstream
transformations. USAC entity/contact files are not included in public evidence.

Three existing documentation issues need a bounded source-specific follow-up:

- The TIGER source register describes 2024/1,005 while the served map and vintage
  register identify 2025/1,016.
- The source module says no source requires a login, while the current district
  STAAR bulk export requires email verification.
- Freshness JSON's `recorded: 2026-08-12` names the register date. It must not be
  presented as the date of the October 7 publisher check.

All raw rebuilds remain **UNVERIFIED** at this checkpoint. A source-specific
refresh must reconcile publisher rows, district identity, transformations and
artifact diffs before changing served data. The seven newer signals remain open;
local UI or plugin tests cannot close these freshness findings.
