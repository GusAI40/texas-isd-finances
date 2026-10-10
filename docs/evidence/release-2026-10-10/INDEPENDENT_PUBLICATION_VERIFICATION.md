# Independent post-publication verification

Read-only verification completed after publication of the approved Texas ISD
candidate. No source, settings, deployment, query, or external state was
changed during this review.

## Verdict

P1 through P4 pass for the published public domain.

| Criterion | Verdict | Evidence |
|---|---|---|
| P1 exact public mapping and source | PASS | `TXISD_PUBLISHED_MAPPING.json` records `txisd.dev` mapped to READY deployment `dpl_9REP3jKBiDs4nkLyUPvNPkDaV1Dg` in the expected project, with truthful commit SHA `14326baf497f782db702f12427d6432af1df46be`; public assets return 200 and exact reviewed hashes. |
| P2 public health and data | PASS | `TXISD_PUBLIC_ASSETS.json` reports healthy status, connected database, ready schema, and exact revision. `TXISD_PUBLIC_LIVE.json` records 40/40 checks passing with zero skips, drift, not-deployed, or unreachable results. |
| P3 unauthenticated browser and visual evidence | PASS | `TXISD_PUBLIC_BROWSER.json` records 86 expected, 0 skipped, 0 unexpected, 0 flaky in a public browser context with no storage state or credentials. `release-public-evidence/browser-verification.json` contains 56 records; independent hash verification found 56/56 present and matching. The publication receipt records the three previously finalized Library artifacts and IDs. |
| P4 source, Git, and boundary handling | PASS | Candidate checkout remains clean at `14326baf...`; master remains `73df189...`; PR84 is draft/open and PR82/PR83 remain unmerged. Backend/data/security/email/HOLD/credentials boundaries are preserved. Direct master push was auto-review rejected as bypassing normal branch workflow and was never executed; supported Vercel promotion of the tested deployment was used. |

## Remaining operational note

The public deployment is an intentional promotion of the tested candidate
while Git master remains on the prior revision. A future master deployment
could supersede this promoted build; reconcile PR84 through the normal reviewed
branch workflow before a later production push. No paid query or model-quality
test was run, and the documented strict 95% data-fill and independent-account
ChatGPT listing limitations remain.

## Independent calculations

- Public asset receipts: `/` and `/static/ask.js` exact rendered SHA-256
  matches; paid query count 0.
- Public screenshot manifest: 56/56 files present, 0 hash mismatches.
- Public browser stats: 86 expected, 0 skipped/unexpected/flaky.
