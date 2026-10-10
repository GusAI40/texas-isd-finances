# Landing and website chat candidate based on production

This review candidate starts from production `master` at
`73df1896ed0818020ec1c15c06f5ee823db7ec0f`. It contains the reviewed landing
and website chat design from `96cf3122d44046eeb59c2771fbea34be09f4c02e`
without taking the PR #82 stack. Publication to `https://txisd.dev` remains
subject to separate, explicit approval.

## Runtime scope

Exactly two runtime files change: `static/index.html` and `static/ask.js`.
All backend, SQL, data artifacts, shared stylesheets, dependencies, hosting
configuration and workflows remain byte-identical to production.

The index applies eight landing/chat hunks from the reviewed PR #83 delta.
Its welcome replacement uses production's original two-line heading as the
old context. The PR #82-only finder-reordering deletion and both
`applyVisualLedger` changes are omitted because those functions do not exist
in production. No visual-components script, plugin, MCP resource route or
portal rewrite is carried over.

Fresh production-style screenshots exposed one contextual difference: the
legacy explanation is a direct `.pipeline` child in production, while PR #82
wrapped it in a hidden `.welcome-method` disclosure. Two additional rules
inside the landing's inline CSS hide only `#welcome > .pipeline` and stretch
only its question button on screens up to 600px. The original pipeline markup
is preserved. These scoped rules restore the reviewed example -> purpose ->
setup composition without importing PR #82's shared portal styles.

Expected normalized runtime identities:

| File | Git blob SHA-1 | LF SHA-256 |
| --- | --- | --- |
| `static/index.html` | `efc2adeaa9aa283606da72f4eac837e86aed3b57` | `b4e4b5e59a0ef170b46614df02b21aad77c9cb0dfe83326f9f758ce10fe32636` |
| `static/ask.js` | `a267582c51e73e51fef4b9a49b5d71e13ce650eb` | `c884583514709fe0e0c42e9648d3c5c4aca3c2b94a6cc12bb4347862d81676df` |

The earlier eight-hunk index blob `2b5babe...` and runtime-only tree
`d9f821...` are superseded by the two compatibility rules. The final runtime-only
projection tree is `54e64fe4570adcf45565b0d21428d88806853a8c`. The full Git tree
also includes the scoped tests, screenshots and review documentation. Exact
commit, runtime-only tree and preview identity are supplied in the evidence,
draft PR and handoff.

## What visitors receive

The first screen asks how school money was spent and shows Dallas ISD's real
FY2025 all-funds record. The desktop treemap becomes proportionate bars on a
phone. The source, period and snapshot remain visible; exact figures and
definitions are available in a disclosure. Highlighting classroom spending
uses the recorded example locally and makes no model request.

The total is $3,319,208,715. Classroom spending is $1,092,607,589;
construction is $766,316,261; debt payments are $500,174,938; and the
combined remaining categories are $960,109,927. The snapshot is August 12,
2026. These are historical actual records, not a current budget, projected
savings or causal claim. See [the recorded receipt](evidence/landing/dallas-example.json).

Gus at TAG remains the creator. The ChatGPT setup guide states before its
first external action: "Custom setup is required. Availability depends on
your ChatGPT account and workspace." Its illustration is schematic. The
owner-account custom setup route was verified separately; independent-account
installation and public directory availability remain unverified. No public
app-store listing, universal plan eligibility, one-click install or OpenAI
endorsement is claimed.

The existing website chat leads with a concise answer, a chart when its
supplied data qualifies, and visible district/year/source/scope context.
Complete supplied prose, exact tables and figure lineage remain available.
Missing, negative, malformed, mixed-currency or ambiguous-unit data remain
readable tables. Stop, manual Retry, timeout, stale-response protection,
close/reopen, keyboard focus and the inline fallback preserve the production
request contracts. Stopping the browser request does not promise cancellation
of an already-running server-side model call.

## Verification boundaries

The scoped browser harness uses recorded public GET fixtures and mocked
`/query` responses. It blocks external, telemetry and mutating requests.
Screenshots of answers illustrate the interface using recorded Dallas figures;
they are not actual ChatGPT responses or evidence of model answer quality.
The local test server runs with database and model credentials cleared.

The dependency authority is unchanged `pyproject.toml` and `uv.lock`.
Fresh Windows Python 3.10.11 and 3.12.14 environments were installed with
`uv 0.11.33`, `--locked --all-extras --group dev`. Python 3.11 and the
configured Ubuntu CI matrix are unavailable locally. GitHub Actions were
observed disabled and remain unchanged; a Vercel READY state is not CI proof.
There is no separate TypeScript or frontend compilation pipeline.

The default Windows CP1252 test run encounters existing UTF-8 source files;
acceptance runs use `PYTHONUTF8=1`, consistent with Ubuntu's UTF-8 locale.
Windows CRLF checkout inflated the dictionary's byte-size totals. Four
unchanged JSON artifacts were restored locally to their exact committed LF
bytes; their Git blob identities and the committed dictionary remain unchanged.
Normal sandbox execution also denied browser-worker spawning and pytest temp
directories; the offline test runs used approved process/file permissions.

The conservative painted-area measurement falls below the strict 95/5 target:
initial-viewport visual shares are 3.1%, 2.5%, 2.7% and 54.3% at
320/390/430/1440px. It counts only actual data-bearing fills against text,
excludes decorative card backgrounds, and is not a perceptual design score.
See [the observation](evidence/landing/painted-data-observation.json). The parent
accepted composition review without treating this metric as a technical
delivery blocker. No 95% success is claimed. Automated accessibility
checks do not replace human screen-reader or participant testing.

Final check counts, screenshot hashes, source scope and independent review
are recorded in [verification evidence](evidence/landing/verification.json)
and [the independent review](evidence/landing/independent-review.md).

Final local checks passed: 1,169 tests passed, 31 skipped and 3 warnings on
each Python version; 86/86 Playwright cases passed without skips, retries or
flaky results. The 56 PNGs cover both browsers, all four viewport widths,
light/dark mode and loading/empty/error/stopped states. Ruff, the lock check,
all 14 static-page JavaScript parses, ask.js syntax and a disposable npm ci
also passed. The final browser run started at 2026-10-10T03:43:52.944Z.


## Release and rollback boundary

Verified production is TAG-ai / `tag-ai-projects`, Vercel project
`texas-isd-finances` (`prj_Q86h3ZufDMLk7bsyYOj7FP3S9Wqg`), domain
`https://txisd.dev`. Production was healthy with database connected and
tracking schema ready at the base revision. Preview creation does not
authorize a production merge, alias change or promotion.

The documented production path is Vercel Git integration from `master`.
The retained healthy production deployment is
`dpl_C9cCgpLNiRhqk5R4uBFKC3Wanc4t`, revision `73df1896...`.
A normal reviewed Git revert produces a new SHA, which must be verified as
the deployed revision. Emergency restoration of the retained deployment
requires rollback authority and subsequent Git reconciliation. Do not race
CLI publication with the Git integration. This candidate needs no schema
rollback.

No paid query, outreach, credential change, security setting change, production
merge or production promotion is included in this work.
