# Texas ISD redesign publication receipt

Published [txisd.dev](https://txisd.dev) on 2026-10-10 UTC.

- Approved source: `14326baf497f782db702f12427d6432af1df46be`, [PR84](https://github.com/GusAI40/texas-isd-finances/pull/84).
- Production deployment: `dpl_9REP3jKBiDs4nkLyUPvNPkDaV1Dg`, TAG-ai project `prj_Q86h3ZufDMLk7bsyYOj7FP3S9Wqg`.
- Public health: healthy; database connected; tracking schema ready; exact revision.
- Public assets: rendered landing and ask.js byte hashes match approved source.
- Public data/provenance: 40/40 PASS. Public browsers:86/86PASS, no skipped/unexpected/flaky.
- Chromium/Firefox:320/390/430/1440, light/dark, accessibility, empty/loading/error, Stop/Retry/timeout, safe malformed-answer handling.
-56public screenshots in `release-public-evidence`; chat responses mocked,0paidqueries.
-3review images saved to Library; filenames include the full approved SHA. IDs and original screenshot hashes are in the Library receipts.
-Only2runtime files changed; backend/data/config/security/CI untouched. PR82/83 unmerged. District emails and scheduling remain HOLD; no Michelle work.

Vercel promoted the already-tested production build. The source commit was preserved;
master remains73df1896 and PR84 remains draft/open. A future master deployment
can replace this promotion. Reconcile only PR84 through normal review before a
later production push; do not merge stacked PR82/83.

Limits: strict95%data-fill metric remains unmet; independent-account ChatGPT
installation/public listing remains unverified; no paid/model-quality query test;
Python3.11/LinuxCI not run. Local Windows Library xattrs are unsupported, but all
three Library saves are confirmed and their IDs/versions are retained.

Automatic approval review rejected a broad production-secret download and direct
master push. Neither ran. Existing production settings were validated through
runtime checks, and publication completed via authorized Vercel promotion.

See TXISD_PUBLICATION_RECEIPT.json, TXISD_PUBLISHED_MAPPING.json,
TXISD_PUBLIC_ASSETS.json, TXISD_PUBLIC_LIVE.json, TXISD_PUBLIC_BROWSER.json,
PR84_LIBRARY_FINALIZED_IMAGES.json and the independent reviews for evidence.
