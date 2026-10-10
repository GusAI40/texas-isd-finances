# Independent final landing and chat review

Read-only review by a different agent from the original auditor. The review
checked the frozen source, screenshots, test receipts and the agreed criteria.
The reviewer made no edits. Source hashes are in [verification.json](verification.json).

| Criterion | Result | Evidence |
| --- | --- | --- |
| Responsive evidence | PASS | Fresh Chromium/Firefox landing, full welcome, setup and chat captures at 320/390/430/1440; 78 browser tests pass. |
| Strict 95% visual / 5% text | FAIL | Full closed landing shares 31.62%, 39.75%, 46.00%, 51.78%; best case is 43.22 points short. Whitespace and decorative backgrounds do not count. |
| Plain-language purpose | PASS | Free tool for ChatGPT, built by Gus at TAG; visible Dallas example and useful website answer. Independent ChatGPT access remains unverified. |
| Honest real data | PASS | Dallas 057905 FY2025 all-funds total $3,319,208,715; 139,776 students; exact four group amounts and proportions; source/date and historical limitations. |
| ChatGPT setup | PASS with boundary | Verified custom setup labels, URL, no authentication, Personal install, app selection, account/workspace caveat and schematic disclaimer. Independent-account installation/public access remains unverified. |
| Accessible responsive controls | PASS for automated scope | 320px one-column setup, no horizontal document overflow, light/dark, readable chart/chat, focus trap, Escape, reduced motion and scoped WCAG AA checks pass. |
| Existing navigation/context | PASS | Dallas example sends once with six-digit district context and restores focus; welcome/setup ordering, hashes, returning reader flows and assets pass. |
| Chat states and safety | PASS | Structured/plain/source/lineage rendering, follow-up attribution, literal hostile text, 429/5xx/network/timeout, Stop/Retry, stale-response suppression, close/reopen and inline fallback. No skeleton remains after Stop/close. |
| Boundaries and repository checks | PASS | Mocked requests; Python 1,227 passed / 60 skipped / 3 warnings; Ruff, static parsing and Node checks pass. No paid provider call, merge, deployment or outreach. |

The draft remains a working design review. Functional checks passing do not
satisfy the failed visual criterion or prove external ChatGPT installation.
