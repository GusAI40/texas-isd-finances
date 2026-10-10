# Independent release verification

Read-only verification completed 2026-10-10 UTC against the approved Texas
ISD candidate and staged production deployment. No source, configuration,
deployment, or external state was changed.

## Verdict

R1 through R6 pass for the approved candidate and staged deployment.

| Criterion | Verdict | Evidence |
|---|---|---|
| R1 exact source/base/runtime scope | PASS | `isolated` is clean at `14326baf497f782db702f12427d6432af1df46be`, parent `73df1896ed0818020ec1c15c06f5ee823db7ec0f`; runtime diff is `static/index.html` and `static/ask.js`; normalized source SHA-256 values match the handoff. |
| R2 production target/project/commit/protection/alias boundary | PASS | `TXISD_STAGED_EXACT_DEPLOY_RESULT.json` identifies READY production deployment `dpl_9REP3jKBiDs4nkLyUPvNPkDaV1Dg` in project `prj_Q86h3ZufDMLk7bsyYOj7FP3S9Wqg`; `TXISD_STAGED_ASSETS.json` confirms revision `14326baf…`; the recorded public domain remains on the old revision and no intentional public alias switch is recorded. |
| R3 strict assets/runtime health | PASS | `TXISD_STAGED_ASSETS.json` records HTTP 200 for `/` and `/static/ask.js`, exact rendered hashes, healthy status, connected database, ready tracking schema, exact revision, and zero paid queries. `TXISD_STAGED_LIVE.json` records 39 passes, one expected cache-header skip, and zero drift/not-deployed/unreachable results. |
| R4 browser coverage | PASS | Newly completed staged-production `TXISD_STAGED_BROWSER.json` records 86 expected, 0 skipped, 0 unexpected, and 0 flaky across Chromium and Firefox at 320/390/430/1440 and required lifecycle/theme states. The staged evidence directory contains 56 screenshots. |
| R5 screenshot/library identity | PASS | 56 preview PNGs exist; the three pending library source files independently hash-match their manifest entries. Finalized receipt records three successful Library saves, full SHA-bearing filenames, IDs, and version 0. |
| R6 scope and safety boundaries | PASS | Handoff records backend/data/security/email/HOLD/credentials boundaries preserved; no paid/model-quality test was run; no secret values were read. |

## Material limitations

The strict 95% data-fill target remains unmet by the conservative metric and
independent-account ChatGPT/public-listing eligibility remains unverified, as
already documented in the final review. The staged browser receipt now passes
R4; `TXISD_STAGED_LIVE.json` retains one expected cache-header skip.

## Independent calculations

- `git status --porcelain`: clean.
- Normalized `static/index.html` SHA-256:
  `b4e4b5e59a0ef170b46614df02b21aad77c9cb0dfe83326f9f758ce10fe32636`.
- Normalized `static/ask.js` SHA-256:
  `c884583514709fe0e0c42e9648d3c5c4aca3c2b94a6cc12bb4347862d81676df`.
- Preview screenshot manifest checks: 3/3 source hashes match; 56 PNGs
  present; zero hash mismatches.
