# Texas ISD visual redesign review candidate

This candidate rebuilds the landing story and polishes the existing shared
website chat. It is ready for review, **not approved for production**. The
literal 95% meaningful graphic-area gate remains unmet on every measured
surface. No merge or production deployment is authorized by this task.

## Verified baseline and scope

The live source is `14326baf497f782db702f12427d6432af1df46be`, deployment
`dpl_9REP3jKBiDs4nkLyUPvNPkDaV1Dg`, in the TAG-ai project
`prj_Q86h3ZufDMLk7bsyYOj7FP3S9Wqg`, team
`team_hLW8yrUTYNGt9CiRY4IMMSet`. The custom domain is https://txisd.dev.
Public health was healthy/database connected/tracking schema ready on
2026-10-10, with that exact revision. Forty read-only public checks passed.
This is baseline evidence, not candidate deployment evidence.

PR #84 is still draft/open and `master` remains
`73df1896ed0818020ec1c15c06f5ee823db7ec0f`; production was previously
promoted from PR #84. Older project notes calling master the live revision
are historical. PRs #82/#83 remain stacked and must not be merged for this
design. This branch, `feat/txisd-visual95-20261010`, starts directly from
the actual published source. The original checkout's zero tracked changes
and 389 unrelated untracked files were preserved.

Only `static/index.html` and `static/ask.js` change at runtime. Scoped tests,
recorded health fixture, screenshots, receipts and memory notes accompany
them. Backend/data artifacts, SQL, providers, dependencies, credentials,
security settings, CI, hosting configuration and outreach are unchanged.

## Result and provenance

The first journey identifies a free tool by Gus at TAG, historical public
school records, and use with ChatGPT or the independent website chat. A
Dallas spending picture leads into the actual question, separate TEA record
groups, district `057905`, and a sourced answer. The statewide district
finder, dollar picture and recorded 2009–2025 trend carry the next part of
the story; methods and supporting details use accessible disclosures.

Dallas FY2025 all-funds total is $3,319,208,715: classroom $1,092,607,589
(functions 11/12/13), construction $766,316,261 (object 6600), debt
$500,174,938 (object 6500), and other combined $960,109,927. The mobile
100-cell picture uses largest-remainder allocation 33/23/15/29 and says
each square is about 1%. Exact figures and definitions remain accessible.
Source: TEA PEIMS; recorded source freshness August 12, 2026. Historical
finance ends at FY2025. The statewide operating-spending trend is separately
labeled; it is not Dallas's all-funds share. No savings are invented.

Supported chat answers lead with conservative max-scaled dollar comparisons,
not invented totals or arbitrary pie shares. Complete tables, source/date
context, limitations and follow-ups remain available. Loading, errors,
unsupported answers, Stop, manual Retry, timeout, stale-response protection,
IME input and focus handling retain the shared service contract.

ChatGPT setup preserves the owner-verified https://chatgpt.com/plugins
custom-server route and https://txisd.dev/mcp, no authentication, Personal
installation and app selection. The visible guide says custom setup is
required and availability depends on account/workspace. Illustrations are
labeled concepts. Independent-account availability and a public listing
remain unverified; there is no public store, universal-plan or one-click
installation claim, and no OpenAI endorsement.

## Verification and limits

- Python 3.10 and 3.12: each 1,169 passed, 31 skipped, three warnings.
- Locked Chromium/Firefox: 106 passed, zero skips/failures/flaky cases.
- WCAG AA: 64 surfaces across 320/390/430/1440, light/dark, landing,
  selected district, disclosures, empty/answer/expanded/error chat. Zero
  automated violations, page/reflow overflow, undersized controls or text.
  Half-size CSS viewports model 200% reflow; native browser zoom was not
  independently certified.
- Ruff, 14/14 static JavaScript page parses, ask.js syntax, offline uv lock
  check (91 packages), and Git whitespace checks pass. There is no separate
  TypeScript/typecheck target for this static JavaScript application.
- One old typography assertion counted `!important` and inline HTML as
  distinct font sizes. Its parsing was corrected; the six-size bound stays
  unchanged. Browser readability checks cover the actual rendered floor.
- Complete matching captures: 444 baseline + 437 candidate, plus 32
  light/dark disclosure images and three cover-the-words images. Zero capture
  failures, horizontal overflow or page errors. Landing heights before →
  after: 320px 7898→7204; 390px 6812→6090; 430px 6449→5952;
  desktop 4309→3842. Shared report/map chat states are included.
- Every `/query` was mocked or held; other mutations were blocked. No paid
  provider call or model-quality test, no district email. Python 3.11/Linux
  CI was unavailable; GitHub Actions remains disabled.

The fixed semantic checklist scores N=20/20, separately from area coverage.
The frozen area measure C=G/(G+T) is below 95% on **all 437** measured surfaces.
Full landing C is approximately 37.7/43.4/46.9/62.7%; selected district
28.8/33.2/35.6/55.6%. Text-only unsupported/error states have C=0. Generic
containers, icons, controls, padding and whitespace are excluded from G.
Generated CSS prose is omitted from the text inventory, so true C can only
be lower. P is a separate CSS-mark rectangle estimate excluding SVG paint,
not a certified painted share. These figures must not be called a completed
95% redesign. Resolving or revising the release gate requires explicit
design direction; truthful readable notices and failure states remain.

Evidence is in [evidence/visual95-final](evidence/visual95-final), including
every full/tile/state ledger, exact runtime hashes, measurements, tests,
representative screenshots and the independent criterion review. The complete
pixel archive is retained in the delegated task workspace. Canonical LF
runtime SHA256: index `6ad59e4b4452e79e9eae09d31f557fff5c4572a8fa2366a89ae0c1fbbc1bacd3`;
ask `f88eb476c20e3a4cd046a5a22ec37174248281a74d5dff16e6544aaea3641b75`.
The external handoff receipt records the final commit/diff identities and
preview; an exact commit cannot refer to its own SHA inside its contents.

## Release approval boundary

Return the protected preview and draft PR for Gus's design approval. Do not
merge, create a production-target build, assign the custom domain, or promote
this preview during this task. If explicitly approved later, build production
from that exact reviewed source with domain assignment skipped, verify the
exact immutable build using read-only checks and mocked browser queries,
then promote only that verified build. Reconcile approved changes through
normal protected PR review before any future master deployment; do not merge
the unrelated stacked PRs. Preserve deployment protection and existing
authentication throughout.
