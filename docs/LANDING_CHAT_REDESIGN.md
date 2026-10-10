# Landing and website chat review - 2026-10-10

This is an isolated, unpublished review of the Texas ISD Finances landing and
existing website question tool. TAG remains the creator. No production merge
or deployment is authorized by this review. The strict 95/5 visual target
remains unmet; this draft is available for design review, not release approval.

## Repository and release mapping

- BeastMode source checkout: `C:\Users\gsanc\.codex\.chatgpt-projects\g-p-6aa23b54aca481919d6bea38fe3e3128\texas-isd-finances`.
- Remote: `https://github.com/GusAI40/texas-isd-finances.git`.
- Isolated worktree: `C:\Users\gsanc\Documents\Codex\2026-10-09\task-5\redesign`.
- Review branch: `feat/txisd-visual-landing-chat-20261010`.
- Source branch: `feat/visual-public-portal-plugin-20261007` (existing draft PR #82).
- Base SHA: `da1721a5ea40b60b76e9e3f9efe69fe67305daee`.
- Production domain: `https://txisd.dev`; Vercel team `TAG-ai` / `tag-ai-projects`, project `texas-isd-finances`.
- Recorded production revision: `73df1896ed0818020ec1c15c06f5ee823db7ec0f`.

The source checkout's unrelated untracked work was preserved. This change is
stacked on the existing public-portal work; its review diff must be compared
with the source branch, not with production. The baseline screenshot is from
that source checkout, not a claimed new capture of production.

## Design and data

The landing uses a real Dallas ISD spending example to show the useful answer
to a plain-language question. Its period is **FY2025** and its scope is
**recorded all-funds spending**, including construction and debt payments.
The recorded source snapshot is **August 12, 2026**; this is not a statement
that a current budget is live or that the data was reverified on that date.

The total is `$3,319,208,715`, with `139,776` students. Classroom teaching is
`$1,092,607,589`; construction is `$766,316,261`; debt payments are
`$500,174,938`; combined other spending is `$960,109,927`. The combined-other
group is the residual after those three featured categories, not the source's
individual "other" category. Exact amounts determine graphic proportions.
See [the data receipt](evidence/landing/dallas-example.json).

## ChatGPT setup boundary

The access action opens this site's setup guide. The verified route is
`https://chatgpt.com/plugins` → `+ Add custom MCP server` → name `Texas ISD
Finances`, server URL `https://txisd.dev/mcp`, `No authentication` → review
warning → `Create as a plugin` → `Personal` + install → new chat, `@` select.
Exact technical words appear only as required setup UI labels.

The guide says that custom setup is required and availability depends on the
visitor's account and workspace. It links current official documentation:
[custom servers](https://developers.openai.com/api/docs/guides/custom-mcp-server)
and [plugins](https://learn.chatgpt.com/docs/plugins). The illustration is
schematic, not a captured ChatGPT screen or an installation receipt.

Development registration and owner-account tool calls are recorded elsewhere
in this repository. Independent-account installation, public directory
approval, native visual reports, and complete package installation remain
unverified. The guide's production anchor does not exist until an approved
release. No universal-plan eligibility, public app-store listing, one-click
install, or OpenAI endorsement is claimed.

## Website chat

The existing shared drawer remains the website's question tool. Inline
questions use it once; the original inline fallback works if the drawer script
is unavailable. Responses preserve the existing structured renderer, source
links, figure lineage, conversation and turn fields, six-digit district
context, follow-up attribution, and literal safe text rendering.

Stop aborts a pending browser request; Retry is manual and retains the original
question/context. A 45-second timeout exposes Retry. Request tokens suppress
stale responses. Closing cancels pending work and restores focus; reopening
retains the thread. Focus trapping uses visible enabled controls. Stopping a
browser request does not promise server-side provider cancellation.

## Verification evidence

All browser question responses are mocked. Recorded public GET fixtures drive
reports and maps; external, telemetry, and mutating requests are blocked by
the fixture harness. Mock answer screenshots use the real Dallas amounts above
and are not presented as actual ChatGPT answers or a provider-quality test.

The source is FastAPI with static HTML/JavaScript. There is no separate frontend
compiler or TypeScript project; the repository's JavaScript parse check covers
all 15 HTML pages, and Node parses `static/ask.js`. Python dependencies and the
universal lock are unchanged. The final `uv lock --check` passed with uv 0.12.15.

Final checks on the frozen frontend:

- Python: **1,227 passed, 60 skipped, 3 warnings**.
- Chromium/Firefox: **78 passed**, including 320/390/430/1440, setup, existing
  reports/maps, mocked chat states, manual retry, cancellation and accessibility.
- Repository Ruff, JavaScript parsing **15/15 pages**, Node syntax, existing
  visual-component unit test and `git diff --check`: **passed**.
- Dependency lock: **passed**; no frontend TypeScript/build pipeline exists.

See [the source hashes, screenshot manifest and receipts](evidence/landing/verification.json)
and [the independent final review](evidence/landing/independent-review.md).

Screenshots under `docs/evidence/landing/` include 320/390/430/1440-pixel first
viewports, full welcome sections, setup, sourced answer, dark theme, loading,
empty, error, and stopped chat states in Chromium and Firefox. Automated WCAG
AA checks cover the new landing, setup, and chat; keyboard and reduced-motion
flows are also exercised. Automated checks do not replace human screen-reader
or participant testing.

Windows required the original Python 3.12 virtual environment. New literal
smart quotes were removed because existing default-encoding tests read HTML
without specifying UTF-8. Git's CRLF checkout also changed byte-sensitive
plugin schema/skill files; they were restored locally to the same committed LF
contents without altering their Git blobs or package behavior.

## Approval and remaining gates

The strict 95% visual / 5% text criterion **fails** in the fresh landing
observation. Earlier report measurements do not certify this page.

| Width | First viewport visual share | Full closed landing visual share |
| --- | ---: | ---: |
| 320px | 29.49% | 31.62% |
| 390px | 44.72% | 39.75% |
| 430px | 51.42% | 46.00% |
| 1440px | 51.78% | 51.78% |

[The reproducible observation](evidence/landing/painted-data-observation.json)
counts actual data-encoded treemap fills, subtracts overlapping labels, and
counts every visible heading, label, button and instruction as text. It
excludes whitespace, card backgrounds, decorative outlines and closed setup
content. The measured region is welcome plus the closed setup summary; the
global masthead and following finder/reports are outside this observation.
Run `node tests/browser/capture-landing.cjs` against the local preview to repeat
it with the recorded public fixtures. This is a conservative observation,
not a whole-page 95/5 certificate. Required readable context and natural page
dimensions were preserved rather than shrinking labels or enlarging graphics
to change the score. Passing functional tests do not satisfy this design gate.

Production publication, the independent-account ChatGPT access test, and the
human accessibility review remain separate gates. No credentials, security
settings, subscriptions, billing, contacts, outreach automation, or backend
contracts changed. No paid query or district email was sent.
