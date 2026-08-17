# Engineering Log — Texas ISD Finances

Append-only session memory. **Newest entries at the top.** Written for an
engineer (human or AI) with zero prior context. Maintained by the `/ariba`
skill — see `.claude/skills/ariba/SKILL.md`. Never put secrets here.

Entry template:

```
## YYYY-MM-DD — <one-line headline>
**What changed:** facts — files, deployments, data.
**Why:** the reasoning git can't record.
**Gotchas:** anything that cost real time to figure out.
**Open items:** carried forward + new.
**Notes:** (quick /ariba note additions land here)
```

---

## 2026-08-17 (later still) — The E-Rate layer: federal money TEA's books never see

**What changed.** PR #29 merged: `/erate/texas` + `/district/{n}/erate` +
the "Federal internet money" econ card, from `static/erate_data.json`
(884 KB, no DB). First-party from USAC's open-data portal (Socrata, like
the bond layer): FRN Status `qdmp-ygft` + Supplemental Entity Information
`7i5i-83qf`, 91,332 TX FRN rows + 19,796 entities ingested by
`scripts/ingest_erate.py`, built by `scripts/build_erate_data.py`.
**$2.2B Funded to Texas FY2017–2026 (~$220–300M/yr); closed years drawn
86–94%; Internal Connections $1.00B edges Internet Access $893M; Dallas
$60M committed.** USAC pays most discounts straight to vendors, so this
money appears in no PEIMS file — the card says so, and the artifact's
limits forbid mixing it with TEA figures.

**CORRECTION to this morning's log entry (append-only rule).** The
scoping note said FY2018's "committed $657M vs $284M disbursed" was
"worth investigating". It is not a finding — it is a category error I
caught while building: `funding_commitment_request` on a PENDING row is
the amount the applicant ASKED, and the dataset carries one row per FORM
VERSION, so most funded requests also have a superseded Pending row.
Funded-only FY2018 is $301M committed / $284M disbursed = **94% drawn, a
non-story**. The builder enforces Funded-only; ingest verifies no FRN
carries two Funded rows; a test asserts the all-status sum still dwarfs
the Funded sum so the refusal stays load-bearing. **A scandal-shaped
number from a mis-read status column is exactly what this project exists
to not publish.**

**The join** (BEN→TEA, `data/erate_district_match.csv`): three roads,
disagreement refused — (1) `state_lea_code` verified against the
crosswalk; (2) unanimous 6-digit campus-code prefix of the BEN's child
schools, unanimity judged BEFORE the crosswalk filter and ≥2 coded
children required when alone (one coded child with a typo'd code handed
Orenda's money to Inspire Academies in testing); (3) name+county through
the shared resolver, with a USAC suffix normaliser ("Indep School
District"→ISD) whose spelling fixups are RETRY-only (a blanket Fort→Ft
broke Fort Bend while fixing Ft Sam Houston), and the prefix road gated
on charter flags agreeing (unqualified it matched Houston Gateway
Academy, a charter, to Houston ISD). **1,077/1,118 BENs, 97.4% of
district-applicant dollars.** The one conflict on record is the two
Dawson ISDs — the entity's own code says Dawson County, its own campuses
say Navarro — refused, never guessed. Charter networks (Harmony $23M,
Great Hearts, ResponsiveEd) spanning many TEA districts under one BEN sit
in the unresolved bucket, test-locked against ever landing on one
district. Consortium money ($299M) is counted statewide and deliberately
never split to members.

**Second review pass: 8 findings, the worst a false published claim.**
USAC writes "Wilbarger County" where the crosswalk writes "WILBARGER", so
both county-verified roads never fired — the Wilbarger **Northside ISD**
(a documented twin name) sat unmatched with the absence sentence denying
its $183k of funded requests. Trailing " County" stripped; five districts
gained. Also fixed: absence wording claims only what the artifact holds
("no FUNDED request" — districts with Pending/Denied filings exist); the
national+E-Rate cards now render for the 10 districts outside the
economics dataset (renderEconomics used to hide the whole section over
them); Socrata paging orders by the verified-unique (frn, status)
composite; the charter-network guard test asserts presence so an
upstream rename fails loudly; first_year has one home (the payload).

**Gotchas.**
- `dt.date.today()` in a builder breaks verify_artifacts' byte-diff at
  midnight. The open-year clock reads the recorded ingest vintage from
  `freshness_vintages.json`; re-ingesting IS how the clock advances.
- USAC socrata `rowsUpdatedAt` moves continuously (FRNs churn through
  review) — the freshness entry says re-ingest on cadence, not per fire.
- `armCounters` arms every `.econ-big` at $0 until scrolled into view — a
  headless read of a fresh page sees "$0 million" and it is NOT a bug;
  scroll and wait before reading.
- Per-district totals are the SUM OF THE ROUNDED year rows (round once,
  derive), or a reader adding the column catches a ±3 mismatch.

**Open items:** owner list unchanged. Next fountains: TAPR campus files
(SAS broker CGI mapped, needs a session), NPEFS history, SAIPE. E-Rate
follow-ups if wanted: an MCP tool, and the C2 budget dataset.

**Notes:**

---

## 2026-08-17 (later) — The press brief, tool eleven, and the strip that ate a phone screen

**What changed.** Three PRs (#26, #27, #28), all merged and live.

**The owner's screenshot was right and the last wave's review "fix" was
wrong.** The District News strip shipped reading
`/static/isd_briefing.json` — but this site deliberately has NO blanket
static mount (one asset, one route), so that path 404s in production, and
an author `display:flex` on `.ticker` beats the UA's
`[hidden]{display:none}`, so the failed strip rendered as an empty VISIBLE
bar. The fetch was swapped in during review AFTER the browser test had
run. **A fix can be its own regression, invisibly — the browser check must
be the LAST thing that touches a front-end change, not the middle.** Now:
the strip reads `/briefing` (server-side fallback to the committed
snapshot; one hour of shared cache, guard identical to the caching
middleware — never set while SITE_PASSWORD locks the site), and
`.ticker[hidden]{display:none !important}` makes hidden mean hidden. On
Vercel, `s-maxage` is consumed by the edge and STRIPPED from the response
— `cache-control: public` + `x-vercel-cache: HIT` is what success looks
like from outside, not the header you set.

**The brand is HOME now.** Owner asked twice where clicking "Texas ISD /
Financial Resource Guide" takes them; the honest answer was "nowhere you
can see". It now never carries `?d` (excluded from parse-time decoration
AND the click-time resolver on all 10 pages), so from a district report it
lands on the statewide landing; on bare `/` it scrolls to top. And on
≤620px screens the news strip wraps — tag + Feed link on the top row,
headline full-width below (owner's phone screenshot showed ten lines of
one word each; now 98px tall, browser-measured).

**The HISD press brief exists in two forms**:
`docs/HISD_TAKEOVER_BRIEF.md` (committed) and a designed shareable page
(claude.ai artifact 6dd06bc0…, private until shared). Every figure from
`takeover_data.json`; the two DIFFERENT windows (headline: mean 2024-25
minus 2023; by-group: 2024→2025) stated so they cannot be conflated; the
special-education regression given equal billing; limits quoted as part of
the result.

**`district_national` is MCP tool eleven.** Figures read from the artifact
at call time; charter absences reuse `src/absences.py`'s sentences (one
wording, two surfaces); verified live (Dallas answers with every caveat).
Review-caught before merge: 20 artifact rows carry only the NCES id (no
positive spending in the Census file) and the first cut crashed with a
bare KeyError on them — now an explained absence, test-locked. The
`docs/MCP.md` count-pin test caught the stale "ten" in the intro:
the pin worked.

**Two fountains scoped, not built:**
- **TAPR campus files** (teacher certification): reachable first-party via
  TEA's SAS broker CGI (`/cgi/sas/broker`, form POST, no login) — needs a
  session to map form parameters. The old DownloadData.html path is gone.
- **USAC E-Rate** (owner-suggested, opendata.usac.org `qdmp-ygft`,
  Socrata like the bond layer): FRN-level, FY2017–2026, **~$500–650M/yr
  committed to ~1,373 Texas applicants**, and committed-vs-disbursed gaps
  (2018: $657M committed, $284M disbursed) worth investigating —
  disbursement lags invoicing, so recent-year gaps are NOT findings.
  Join path: BEN → USAC supplemental entity dataset (carries NCES ids) →
  the CCD bridge already in the repo.

**Open items:** unchanged owner list. New: build E-Rate or TAPR next (in
that order — E-Rate composes with existing bridges and speaks Socrata,
which the freshness watchdog already knows how to watch).

**Notes:**

---

## 2026-08-17 — Texas against the other 49; the More menu was a clipped dropdown, not a dead link

**What changed.** PR #25 merged and verified live (`verify_live.py` **31/31**,
was 26). Three things shipped in one wave:

**1. The national layer — the first fountain, ingested.** Census F-33 fiscal
2024 district file (`elsec24t.xlsx`, released 2026-05-07, owner-uploaded) +
NCES NPEFS state file (committed at `data/npefs_state_2024.txt`, 57 rows,
pulled first-party from nces.ed.gov and cross-checked against the owner's
paste) + CCD LEA Directory SY 2024-25 as the join bridge.
`scripts/build_national_data.py` → `static/national_data.json` (100 KB) →
`/national/texas` + `/district/{n}/national` (DB-free) → an "Against the
whole country" card in the econ section + a did-you-know sentence.
Headlines: **Texas ranks 44th of 51** (50 states + DC) at $13,642 per
student in average daily attendance; the median ranked Texas district
spends $13,197 in current spending vs the national median $15,770; Dallas
ISD sits at the 43rd percentile of the 9,294 U.S. districts with 500+
students. Robustness shipped in the artifact: ranking by fall membership
instead of ADA moves Texas only 44→45.

**Why the join is safe.** NCES ids are NOT derivable from TEA numbers
(Dallas is 4816230, not 48+057905 — an early assumption that measurement
killed). The CCD directory's `ST_LEAID` column ('TX-057905') is the only
published bridge, keyed by NUMBER, so the eleven twin district names that
once put five districts on the wrong map cannot cross-match here. All
1,048 Texas F-33 rows resolve; the build refuses to write if the
accounting doesn't balance; `TX-057905 → 4816230` is asserted in the
builder AND re-checked from the raw file in `tests/test_national.py`.

**Why PPCSTOT is published, not recomputed.** It is NOT
`TCURSPND×1000/ENROLL` (~1% off, varying per district, up to 7×). The
Census's documentation says why, and the artifact quotes it verbatim: per
pupil excludes non-elementary-secondary programs and "spending by a school
system for students not included in its fall membership counts." A
homemade division would have been confidently wrong; a formula you can't
verify doesn't get published.

**Structural absence, stated.** 175 of 1,202 econ districts have no F-33
row — 174 charters + UT Austin's lab school — because the Census surveys
GOVERNMENTS and Texas charters aren't independent governments. Charters
(open AND closed — the closed ones live only in the crosswalk) get a
`not_applicable` absence, never "missing information." Percentile is
floor, not round, so "more per student than X%" is always literally true.

**2. The header — owner-reported, browser-diagnosed.** Verdicts from
clicking every element in driven Chromium, not from reading the code:
- **"More" was never a dead link — it was a clipped dropdown.** The
  `<details>` lived inside `.m-tabs`, whose `overflow-x:auto` clips an
  absolutely-positioned child; `elementFromPoint` at every menu item's
  midpoint hit the section nav instead. Moved outside the strip on all 10
  pages; all six items hit-test clean from any scroll position.
- **Brand/active-tab clicks looked dead**: same-URL navigation restores
  scroll. Same destination now scrolls to top. And the ?d decoration moved
  from parse time to CLICK time — review caught that a district switched
  in-page navigated masthead links to the PREVIOUS district. Modified
  clicks (ctrl/cmd) keep native behaviour.
- Both locked by tests (`test_the_more_menu_is_not_inside_the_scrolling_
  tab_strip`, `test_clicking_the_tab_for_the_current_page_scrolls_to_top`).

**3. District news on the front page** — a second strip under Live
Figures rotating the Feed's stories, one WHOLE headline at a time (the
crawling marquee was rejected on this site once already and stays
rejected), escaped before innerHTML, reduced-motion gets a static strip.
It reads the COMMITTED `static/isd_briefing.json`, not `/briefing` — zero
new DB round trips on the front page, and it renders with Supabase
paused. Both strips share ONE rotator (`rotateStrip`) after review flagged
the copy — the `_usd`-formatter lesson, applied before the drift.

**Review before merge: 9 findings, all applied.** The two that mattered
most: the stale-district navigation above, and closed charters getting the
wrong absence kind. Also: verify_live had no national checks (a deploy
dropping the artifact would have been invisible — the .vercelignore class
of failure); live-derived counts (44th, 9,294, 1,048, 14,077) sat in
docstrings/register/og prose that no test holds to the artifact — all
de-numberized, counts live in the payload only; `/sources` eyebrow said
"Seven public sources" while the register held ten (pre-existing drift!) —
now digits, test-pinned to `len(SOURCES)`/`len(MEASURES)`; the released
date parse accepted any cell starting "20"; round() percentile could
render the logically-false "more than 100%".

**Gotchas.**
- The NPEFS per-pupil figure `PPE15` divides by **ADA**, not membership
  (`NCE13/ADA` matches exactly for every state; `NCE13/MEMBR23` does
  not). Texas counts attendance, so per-ADA reads higher than per-member.
  The page says which count the denominator is.
- Census F-33 `STATE` column is NOT FIPS — filter on `FIPST=='48'` or you
  get Washington.
- Sources page counts and MEASURES: every SOURCES entry must be used by a
  measure and mirrored by hand on `static/sources.html` (title + URL +
  label are test-enforced), and the register now requires a vintage entry
  per source — three new files = 3 source entries + 3 measures + 3
  vintage entries + 3 page cards + 3 table rows, or the suite fails.
- `pkill` in a compound Bash command still exits 144 (noted last session,
  hit again) — start a new port.

**Open items:** unchanged from 2026-08-16 (credential rotation ×7 with the
owner, DeepSeek monthly cap, STAAR SY2026 human download, wave-2 outreach
GO, raw-data release publish). New: the F-33 layer stops at fiscal 2024 by
construction — the `census_f33`/`nces_npefs` vintage probes watch the
predictable fiscal-2025 URLs; the CCD directory ships at an unpredictable
versioned URL, so its etag only catches restatement (a human finds the new
SY on nces.ed.gov/ccd/files.asp). NPEFS `_2a/_3a` same-year revisions
deliberately don't fire the probe. Optional next fountains, in order:
NPEFS detail for state comparisons over time, TAPR campus file (teacher
certification), Census SAIPE, MSRB EMMA.

**Notes:**

---

## 2026-08-16 — The invisible half: a browser audit, three blockers, all fixed

**What happened.** A corner-to-corner visual audit — 13 pages rendered in
Chromium at 1440px and 390px against live production — found that the site's
biggest defects were ones no existing check could see, because none of them
rendered a page. Then all three blockers were fixed, verified in a browser, and
pushed, along with the outreach repairs from the KPI report.

**Blocker 1 — eight of sixteen sections never painted.** On the district report,
`.reveal` set `opacity:0` from CSS alone and eight sections waited on an
IntersectionObserver that never fired — full height, full content, blank.
Lost: trends, peers, where the money goes, payroll vs contracts, who the money
serves, anomalies, insights, and the question box. Confirmed by experiment:
`prefers-reduced-motion: reduce` (which makes `wireReveals()` bail) showed 0
invisible vs 8, same URL back to back. **Fix: the hidden state now requires
`.armed`, added only in the same statement that hands the section to the
observer — CSS alone can never hide content again.** A narrow rescue sweep
reveals only sections the reader has reached and warns to console. Verified:
0 invisible, animation intact (observer does the work, watchdog silent).

**Blocker 2 — /docs was a blank page.** HTTP 200, zero pixels,
`SwaggerUIBundle is not defined`: FastAPI's Swagger loads from cdn.jsdelivr.net
and our CSP is `script-src 'self'`. They had been fighting since the header
shipped. Fix: built-ins off; `/docs` is server-rendered from the app's own
OpenAPI schema — 40 endpoints, zero external requests, works with JS disabled.
Building it surfaced the `/district-geo` docstring citing TIGER 2024 for 2025
boundaries (fixed), and the geomap eyebrow now names BOTH vintages.

**Blocker 3 — the AI disclosure named the wrong vendor** ("OpenAI gpt-4o-mini",
nine days after the DeepSeek switch). Now read from `/health` at load; neutral
wording if the call fails. Same class as the MCP "4,588 bond elections" bug:
derive it, don't repeat it.

**The new rung: `tests/test_render.py`.** Boots the app, renders the report in
Chromium, scrolls like a reader, fails on any section laid out at full height
and painting nothing; plus a static CSS guard **verified to FAIL with the bug
reintroduced**. Honest limit, stated in the file: without a database the
browser test cannot see this exact bug (the affected sections are DB-backed and
correctly `display:none`), so the static guard is the regression test.

**Gotcha that mattered: the sandbox proxy ate localhost.** Under the full suite
the render tests silently SKIPPED — `HTTP(S)_PROXY` sent the fixture's
`127.0.0.1` health probe to the proxy, which refused, and the fixture read that
as "app did not start". Fixed with an explicit no-proxy opener, and the fixture
now FAILS with the server log instead of skipping. A skip that hides a working
check is the same disease as a check aimed at the wrong file.

**Outreach (the KPI report's list, every item doable without keys):**
- **Every reply-able address is now gus@ubntag.com.** The unsubscribe fallback
  was `hello@txisd.dev` — an inbox that does not exist. It never actually
  shipped (two `or` clauses always won), but that was luck. Test-enforced via
  parsed string literals — a text grep failed on its own comment, again.
- **The 11 undeliverable addresses are committed** in
  `data/outreach_suppression.json` as SHA-256 hashes (contact data never lands
  in git); `send_outreach` refuses them before any other check.
  `scripts/prune_bad_addresses.py` rebuilds it from the KPI report.
- **`usage_report.py` now leads with the first-party email click-through**
  (`src:email` by day) — counted since 2026-08-12 12:50, never read. Still
  needs SUPABASE_PAT to run; not present in this container.
- `KNOWN_SOURCES` gains `email-w2/w3/w4` — wave tokens, identical within a
  wave, so waves compare without identifying anyone.

**Still owner-only:** Resend click/open tracking toggles for ubntag.com;
running `usage_report.py` / `outreach_kpi.py` (needs RESEND_API_KEY +
SUPABASE_PAT); checking gus@ubntag.com for replies (no connected mailbox sees
it); repo secrets for the Monday KPI workflow.

**Verified.** ruff clean; 763 tests pass; verify_live 26/26 against a local
build; JS parse clean; the fixed page re-rendered in Chromium (0 invisible
sections, both motion preferences).

---

## 2026-08-16 — The trust question asked out loud, and one pixel for grandma

**What changed** (PR #24, live). Readability and trust, both MEASURED first.
Flesch-Kincaid on the real page text showed the core path already reads at
grade 5–7, with three spikes: the AI disclosure (9.2), the outcomes explainer
(9.8), the balance explainer (8.3). All three rewritten and re-measured: 5.5,
6.4, 5.6. Body base moved **15px → 16px** (one token, `--fs-base`) — the
accessibility floor for older readers; re-rendered both viewports, 0 overflow.

**New section: "Can I trust these numbers?"** — the question asked in the
reader's own words, linked from the hero's AI strip, measured at a
**grade-3.4** read. Five answers: where numbers come from (download the same
state file), how we check (a second program redoes the math; on disagreement
the site will not publish), what happens when we're wrong (**the Wills Point
correction, named** — a real mistake owned in public is the strongest trust
evidence the site has), what the AI did and did not do, and check-one-yourself
(click any revenue figure). Static HTML on purpose: the trust answer must not
depend on the database being awake. Test-locked including the Wills Point
receipt.

**Insight worth keeping**: the trust machinery all existed — /sources,
/provenance, /transparency, lineage — but was an Easter-egg hunt across four
pages. Evidence nobody can find is evidence that doesn't work. The question
had to be asked ON the page, in the reader's words.

**Next fountain decided: NCES/Census F-33** (national context — "Texas vs the
other 49"). Sources verified live: nces.ed.gov/ccd/f33agency.asp (district
fiscal files) and census.gov/programs-surveys/school-finances.html (the Census
side; same joint collection). Join key: NCES LEAID carries the TEA district
number for Texas (state 48 prefix) — verify against the crosswalk on ingest,
never join on name.

773 tests pass; verify_live green after deploy.

---

## 2026-08-16 — Three insights that carry their own receipts

**What changed** (PR #23, live). Three reader-facing features from data already
ingested, each printing its working in place — the answer to "is every number
traceable?" is designed in, not bolted on.

1. **The money clock** (hero): $109.4B/yr ÷ 31,536,000s = **$3,471/second**,
   counting up with the reader's time on page. The `?` opens the numerator,
   divisor, fiscal year and source, led by the honesty sentence: *"This is an
   average, not a meter."* Static under reduced motion. The tick touches only
   `#clock-amt.textContent` — rebuilding innerHTML each second destroyed the
   `?` button under keyboard focus.
2. **Your house, your share** (What you pay): reader types a taxable value →
   bill with the arithmetic beside it (`$500,000 ÷ 100 × 1.0138 = $5,069`),
   scaled recapture share, and *"your household funds ~1.1 minutes of Dallas
   ISD's year"* — denominator named as operations+debt, construction excluded.
   Fully client-side. ⚠️ **The decimal guard matters**: `'250,000.00'` (every
   appraisal site's format) inflated 100× when non-digits were stripped
   naively; the point is truncated FIRST, and a test locks the guard.
3. **The starkest borders** (map): top-6 same-boundary spending gaps from the
   existing adjacency + the map's own PEIMS measure. Today's sharpest:
   **Cotulla ISD $23,636 vs United ISD $12,679 — $10,957/student across one
   line.** Click → pins the line. Rules, all stated on the section and
   test-enforced: under-500-student districts excluded (site ranking rule);
   pairs must share ≥2 quantised vertices (**one vertex can be a corner
   touch**, and a tail-of-the-distribution list is exactly where such
   artifacts surface); the gap is the difference of the ROUNDED figures shown,
   so the reader's own subtraction checks out.

**Review caught seven defects pre-merge** (decimal inflation, focus-destroying
tick, corner-touch adjacency, unrounded gap, unnamed denominator, smooth
scroll ignoring reduced motion, zero tests). `tests/test_wow.py` (9 tests)
holds each published claim to its code — divisor to its stated value,
exclusion rule to its prose.

**Traceability state, stated precisely**: the four revenue figures have full
clickable lineage with gate verdicts; the three new features print numerator/
divisor/source in place; everything else traces via /sources + the provenance
tests but is not yet click-openable (builders would need to emit numerators —
the lineage backlog).

772 tests pass; verified in a driven browser with arithmetic re-checked by
hand; verify_live green after deploy.

---

## 2026-08-16 — A+ close-out: the zoom that already existed, and the last of the ledger

**What changed** (PR #22, live and verified). The map's "no zoom" finding
dissolved on inspection: wheel, pinch and drag all existed and read as absent,
because nothing on desktop announced them and zoom flew away from the cursor.
Now **anchored on the pointer** (`zoomAt` reuses `unproject()`/`project()` —
change scale, see where the anchor lands, pan the difference away; verified:
the same district stays under the cursor through a 2× zoom), pinch anchors on
the finger midpoint, **+/− buttons** + a desktop hint, double-click zoom that
**defers click-to-pin 280ms and cancels it** (both mouseups used to pin, the
second against an already-flown view — it could pin a NEIGHBOUR). The side
panel rests on a statewide read of the current metric with clickable extremes.
Toolbar down to two button styles (filled = primary/active, outline = idle).

On the report: the **Tutorial/Disclaimer/Print bar is retired** into the
masthead's More menu (`#mm-*` buttons; `.m-menu button` styled in design.css);
the credential line no longer repeats the proof row; the picker chips carry a
`.chip-sep` seam between district jumps and page exits; percentiles are
grammatical (`ordSuf`: 91st/22nd/43rd — every one said "th" before, in display
type).

**Gotchas.**
- **"Missing feature" is often "unannounced feature."** Grade discoverability
  before granting the feature request.
- **An unanchored zoom is indistinguishable from a broken one.** Anchor on the
  pointer or don't ship the wheel handler.
- **`design.css` changes need the `?v=` bump on all ten pages** (v3→v4 this
  time) — max-age=3600 means an unbumped change serves naked UA styling to
  returning visitors for up to an hour. Second time this has bitten.
- **dblclick and click-to-pin share mouseups**; any double-click gesture on a
  click-target surface needs the deferred-click pattern.
- `zoomAt` must no-op before the geo fetch resolves — the review caught it
  throwing on every wheel tick over a still-loading map.

**The audit is closed at A+**: C− → B+ → A− → A+ across four waves (PRs #19–
#22), every re-inspection measured in Chromium against production, artifact
updated in place. Left open by stated choice: the 28-screen page length (the
long-form design is the page's own promise; all its mitigations now function).

---

## 2026-08-16 — The bond chart, and the claim the data walked away from

**What changed** (PR #21). Beat 2 of the bond story redesigned per the audit,
plus a factual correction found on the way in: the title said "Stadiums, fewer
than half" while `bond_data.json` now carries **stadium pass_rate 50.3%** — the
Board's 2026 refresh moved the number and the prose gloss went stale on the
live site. Beat 4 had the same defect one screen down ("a coin flip" over a
card rendering 56%). **Both beats now derive their headline numbers from the
data at render time** — the same rule the MCP `instructions` learned when they
kept claiming 4,588 bond elections: prose that summarises a number must be
recomputed with it.

Design changes, each tied to an audit finding: athletics was warning-orange
while arts venues, tied at 58%, sat grey — the discussed row is now
**accent-blue against neutral grey** (a pointer, not a verdict); "100%
approved" gets a real axis line plus a 50% "half pass" reference; all
`.econ-fig` SVGs are **capped at 720px** because viewBox scaling inflated 11px
chart labels to ~19px — larger than the section heading (measured after:
12.8px vs 16px); the duplicate giant stat is gone; "over 66 years" is computed
(68); both title figures share one guarded failure mode (numberless title, not
"classrooms NaN%" and not a blanked section).

**Gotchas.**
- **The design system defends itself**: `scripts/design_audit.py` failed the
  build on the first attempt's `▸` marker. Emphasis devices must come from the
  typographic system — colour, weight, opacity — never a glyph.
- **Opacity is not an emphasis device on dark grounds**: 55%-alpha over
  `#101216` measured ~2.1:1, under WCAG's 3:1 for graphics. `BOND_C` is a JS
  constant no theme token can rescue — use solid hexes that hold in both
  themes.
- **A hardcoded prose gloss of a computed number is a time bomb.** Two went
  off in one section. Grep candidates: any headline containing a quantity word
  ("half", "coin flip", "most", "double") near a rendered figure.

**Verified live** after merge: "Stadium-specific asks, 50%" serving on
production, verify_live green. 763 tests pass, ruff clean.

---

## 2026-08-16 — The A+ pass: five audit gaps, ten review catches, two PRs

**What changed.** The visual audit's five named gaps between B+ and A are
closed and live (PR #19 + #20): tap targets (the "?" buttons 18→24px, zero
controls under 24px, was fourteen under 32); scroll-shadow affordance on the
masthead and section nav (pure CSS, `background-attachment: local`, themed via
a new `--scroll-shadow` token); the ticker rebuilt from marquee to
one-whole-item rotation (pauses on hover/focus/tap; reduced motion gets a
static all-items strip — no self-updating content for readers who opted out);
the penny palette's four greys cut to two meaningful ones (admin → burgundy
#9c4f63, buildings → brown #8d6b4a, plus a neutral hairline inset so
near-black construction survives the dark theme); and the orphaned cells fixed
(proof stats a real 4-up/2×2 grid, drivers 4+3 at full width). Also: "Deficit"
in the alarm colour, `fmtMoneyShort` for ten-digit prose, value–unit nowrap,
the "Start anywhere" panel defaults to the largest penny INSIDE `focusCat` so
grid/bars/text agree, placeholders unclipped, and the district hero's penny
legend restored (the statewide render always had one; personalising dropped it).

**The review before the merge caught ten defects in the first attempt**, and
the three sharpest were regressions in the fixes themselves, all dark-theme or
accessibility: the scroll shadow was hard-coded black on a dark surface —
invisible to exactly the readers it was added for; the darkened construction
penny vanished into the dark ground; and the new ticker auto-rotated under
prefers-reduced-motion where the old marquee froze completely. Plus a real
interval/timeout leak that could write district A's figure into district B's
strip, a "$1000.0M" formatter boundary (branch on the value AS DISPLAYED —
`toFixed(1)` rounds at 50k, so the B threshold is 999.95e6), and the geomap
placeholder trim that had deleted "press Enter" — the only instruction for the
only trigger.

**Gotchas.**
- **A fix can be its own regression, invisibly.** Everything looked right in
  the light theme where I was testing. The review's dark-theme pass is what
  caught two of the three worst items. Check both themes for any colour that
  is not a token.
- **Scroll shadows via `background-attachment: local` need themed colours** —
  the technique is CSS-only and appears/disappears correctly at the ends, but
  the shadow colour must come from a token or it dies in dark mode.
- **Seven is prime**: no column count divides the drivers grid evenly; 4+3 at
  full width is the best obtainable and the comment now says honestly where it
  holds. Don't chase the mid-width orphan with span tricks.
- **Reduced motion is not "gentler motion".** Rotating content is still
  self-updating content; the compliant fallback is everything-at-once, reader-
  scrolled.
- Foreground `sleep`-then-check is blocked in this harness; use
  `run_in_background` with an `until` loop for deploy waits.

**Verified live** after both merges: `verify_live.py` green, `--scroll-shadow`
resolves to `rgba(255,255,255,0.28)` under `data-theme=dark` on production,
reduced-motion strip static with 14 items, ticker rotating and pausing,
palette hexes live, no JS errors. 763 tests pass; ruff clean.

**Open items.** Unchanged (owner queue: mailbox, Resend toggles, keys as repo
secrets, credential rotation, DeepSeek cap, STAAR download). Audit items left
open by choice, not oversight: the bond chart's label hierarchy and colour
implication (C+, needs a design decision), map zoom (feature), page length,
the utility row, the repeated credential line.

---

## 2026-08-16 — Clickable lineage: why is this number this number

**What changed.** A reader can now click a published per-student revenue figure
on a district page and see the working: numerator, denominator, **which student
count the denominator is**, the formula, the fiscal year, the publisher, a link
to the original file, and the verdict of a publication gate. New:
`src/lineage.py` (the Evidence object + `gate()`), `scripts/recompute_revenue.py`
(a second, independent re-derivation), `GET /district/{n}/lineage/{metric}`,
a tenth MCP tool `district_lineage`, `tests/test_lineage.py` (34 tests), and the
panel itself in `static/index.html`. `scripts/build_economics_data.py` emits the
evidence; `src/sources.py` gained `freshness_and_aim()` and `recorded_on()`.

**Why a gate and not a validation flag.** "Deterministic" is not "true". Every
reader-visible error this project has shipped came from deterministic code with
a green suite behind it — the bond layer two years stale, five districts drawn
on another district's land, a test comparing an artefact to a column generated
from that artefact. So VERIFIED requires four separate questions to pass, and
each has one of those failures behind it: **computability** (can it be computed,
and does a per-unit figure name its denominator — "per student" is not a
definition, this site publishes per-student figures on different denominators
that legitimately disagree), **arithmetic**, **correctness** (does an
independent re-read agree), **freshness**, **aim**. `gate()` refuses to return
VERIFIED when `recomputed_from` names the artefact being checked, and a figure
nobody recomputed is **UNVERIFIED**, not VERIFIED — a badge nobody earned is
worse than no badge.

**The second road.** `scripts/recompute_revenue.py` re-derives all four figures
with the standard-library `csv` module — no pandas, no helper shared with the
builder — and the build **refuses to write the artefact** if any of the 4,808
figures disagree. A test parses its imports (via `ast`, not grep — the first
draft failed on its own docstring) so it cannot quietly become a wrapper around
the builder. `meta.lineage_recomputation` records that the check ran and found
zero, because a check that ran and found nothing must not look like a check that
never ran.

**Six bugs found by reviewing BEFORE the merge.** All mine, from the commit
before the fix.
1. **`.vercelignore` drops all of `scripts/`**, and `src/sources.py` reads
   `scripts/freshness_vintages.json` at request time. In a deploy-shaped tree
   every verdict fell to UNVERIFIED — correct behaviour and a broken deploy at
   once, invisible unless someone clicked a number, with tests green because the
   repo checkout has the file. Re-included; reproduced both the failure and the
   fix in a tree built to the ignore file's own rules.
2. **The second road overclaimed.** It reads `prepare_data.py`'s cleaned CSV,
   not TEA's workbook, and names the same 60-char-truncated columns as the
   builder — so a wrong TEA-to-CSV mapping would be reproduced by both roads and
   still publish VERIFIED under the words "an independent re-read of the
   publisher's own file". Prose corrected in three places.
3. **`fresh=True` was inferred from the ABSENCE of a hand-typed flag** and shown
   as "Is this the publisher's latest? yes". The daily watchdog asks the
   publishers but never writes back, so that claim was unearned. Label is now
   "Source current, as last recorded?" and the panel states the record's date.
4. `verify_artifacts.py` added economics to the chain but left the downstream
   builders reading `static/`, so drift would surface only on a second run.
5. Two docstrings claimed `/query` uses the Evidence object. It does not.
6. The arithmetic tolerance had zero headroom — 278,038 / 212 is exactly 1311.5
   and passed on floating-point luck.

**Gotchas.**
- **`.vercelignore` is a silent third environment.** Tests and local runs both
  see the full checkout; only the deploy sees the filtered tree. Anything under
  `src/` that opens a file outside `src/`, `static/` or `api/` needs a
  re-include AND a test asserting it, or it behaves differently in production
  from everywhere it was checked.
- **Store only what varies.** The first draft emitted the formula, unit and
  denominator name per district and nearly doubled the artefact (2.4 MB) for no
  new fact. Constants now live once in `meta.lineage_templates`: 1,202 copies of
  "the formula" is 1,202 chances for one to differ. Cost with four metrics:
  +320 KB raw, ~286 KB gzipped.
- **`economics_data.json` was never in `verify_artifacts.py`'s rebuild chain**,
  despite being what the forensic and trend layers read. It rebuilds
  byte-identically, so there was no reason for the exemption. Added.
- **The three revenue PERCENTAGES deliberately get no lineage.** `federal_pct`
  is 100 minus the other two so the bar's labels add to 100 — a subtraction, not
  a division. A numerator for it would describe a calculation that never
  happened.
- **`tea_staar_district` now carries `known_stale: true`.** Being a release
  behind was recorded only in a JSON comment, where no reader would ever find
  it; it is now machine-readable and reaches the lineage panel.
- `verify_live.py` covers the endpoint: 21 checks to **26**, including the
  verdict itself and that the recomputation never derives from the artefact it
  validates. Confirmed it exits 1 against a deploy missing the vintage file.

**Verified.** ruff clean; 754 tests pass; `verify_artifacts` byte-identical on
all four artefacts; `verify_live` 26/26 against a local build; and the panel
rendered in Chromium — four clickable figures, full working, Escape closes, no
JS errors. Dallas ISD: $2,383,669,437 / 139,776 = $17,053, VERIFIED.

**Open items.** Unchanged from the previous entry, plus: lineage covers the four
revenue figures only — spending, debt and outcome figures still publish
result-only and cannot be opened up until their builders emit numerators. The
`/query` path does not use the Evidence object yet.

---

## 2026-08-16 — Fifteen bugs, two reviews, and a test that validated itself

**What happened.** Asked for `/code-review` over the week's work. First pass on
the caching change found 6; second pass over the previously unreviewed changes
found 9. All fifteen were mine, all in code I had already reported as working,
all with a green suite behind them.

**The one worth remembering.** `tests/test_geo_boundaries.py` checked
`district_geo.json` against the crosswalk's `has_boundary` column — which
`build_district_crosswalk.py` GENERATES from that same payload. Reintroduce the
twin-collapse bug, rebuild both artefacts, and the tests stay green while five
districts are drawn on another district's land. It was circular from the day I
wrote it, in the same commit where I claimed it "fails against the old payload
and passes against the new" — true then, meaningless as a guard. Replaced with
a fact no rebuild can launder: a TEA number's first three digits ARE its county
code, so each twin's centroid must fall in the county its own number encodes.

**Two were user-facing.** The map credited TIGER/Line 2024 in four places while
serving 2025 boundaries — the exact class of defect (fresh data, stale label)
this week was spent eliminating elsewhere. And `/ops/*` returned 500 rather
than 404 for a non-ASCII token, because `secrets.compare_digest` raises on
non-ASCII `str`; the crash confirmed the private route exists, defeating the
whole "404 not 403" design. Both fixed, deployed, verified live.

**Two more had real blast radius.** `/feed.xml` got a 24-hour cache despite
being rebuilt daily by cron with no deploy. And CDN caching could have bypassed
`SITE_PASSWORD` entirely — the gate is middleware and a cached response never
runs middleware. Root cause was placement: cache rules in static `vercel.json`,
the gate a runtime switch, so they could never coordinate. Moved into the app
beside the gate.

**The rule, now in CLAUDE.md:** run the review BEFORE the merge. A passing
suite is evidence about the tests, not about the code.

---

## 2026-08-14 (evening) — The outreach map: seeing the campaign on the state

**What changed.** A private map of where the outreach actually landed:
`/ops/outreach` + `/ops/outreach-data`, `src/outreach_map.py`,
`static/opsmap.html`, `tests/test_outreach_map.py` (13). One dot per district
in the mailing list, coloured by how far it got through the funnel. Hover gives
sent/opened/clicked dates plus pages and dwell; double-click opens that
district's own report.

**Why not Mapbox** (it was the original request). `/geomap` already renders
1,016 real TIGER2025 boundaries in our own canvas code with no API key. A
basemap vendor would have added a token, a third-party script to the CSP, and
an external dependency the build leans on — to draw a worse version of a map we
already own. Same engine, new colouring, far smaller build.

**Why SIX states and not the four asked for.** Four would misreport twice:
- **UNKNOWN** — 571 sent, only 271 ever checked against the provider. Painting
  the other 300 "not opened" asserts a measurement nobody made. Same error as
  counting an unrated campus as failing. They render hollow.
- **BOUNCED** — an address that never arrived is not a person ignoring us.
  Folding it into "unopened" overstates disinterest and hides a list problem.

**CLICKED reads zero for wave 1 and always will.** Click tracking was a
disabled toggle during those sends and the links are already delivered. The
payload states this in `meta.limits` so the caveat travels with the numbers.

**Why it is not on the public site.** Every dot is a named superintendent and
whether they opened an email; the rest of txisd.dev is deliberately anonymous.
So: own `OPS_TOKEN` (constant-time compare), **404 not 403** when absent or
unset (403 confirms there is something to find), noindex + no-store, linked
from nowhere, and deliberately NOT reusing `SITE_PASSWORD` — that would couple
taking this private to taking the whole portal private. A test asserts no email
address can reach the payload at all.

**Gotchas.**
- Districts with no contact address (291) are counted, never drawn. Showing
  them as "not sent yet" reads as a choice rather than a coverage gap, and
  would bury the 3 real gaps among 294 charters.
- The public design-system tests glob `static/*.html`, so a private page
  failed 7 of them (masthead, AI disclosure, tokens). Fixed by scoping those to
  `PAGES` and excluding private pages BY NAME — but the JavaScript parse check
  still runs over `ALL_PAGES`, because a syntax error breaks a private page
  exactly as badly as a public one. A test enforces that split.
- The payload is assembled per request from the database; nothing with personal
  data is committed.

**Open items.** `OPS_TOKEN` must be set for the route to exist at all.
`RESEND_API_KEY` turns the ~300 hollow dots into real red/yellow.
`SUPABASE_PAT` at send time is what lets wave 2 ever show green.

---

## 2026-08-14 (later) — The A+ pass: one live data error, three checks watching the wrong thing

The pattern, stated plainly, because it is now four for four: **every serious
defect this project has had was a check looking slightly to the left of the
thing that mattered.** Not a missing check. A mis-aimed one.

  the bond layer ran two years stale       with a green suite
  verify_sources passed the wrong publisher because the link was alive
  the freshness monitor fired on a PDF     instead of the district file
  the map printed "unmatched: 0"           while overwriting eleven districts

**The live error.** Eleven Texas district names belong to two districts each.
`build_district_geo.py` keyed a plain dict by name, so both twins resolved to
one TEA number — one district drawn with the other's land, one absent. Five
were already live: Highland Park ISD (Potter) as **Dallas's**, Northside ISD
(Wilbarger) as **San Antonio's**, plus Chapel Hill, Valley View, Hubbard. A
parent using "find my district" in Dallas's Highland Park saw Potter County's
finances. TIGER2025 made it worse-looking-better: Census now ships the second
twin of all eleven pairs, so the join overwrote eleven times and reported
`unmatched polygons: 0`, an apparent improvement on 2024's 1.

Fixed by county — the polygon's own location decides, the same name+county key
the bond layer uses — plus a hard accounting assert, and the vintage read off
the filename instead of a hardcoded "2024". 1,016 districts, 0 unmatched, all
22 twins verified.

**Three checks re-aimed.** `tea_recapture` was a false alarm (watched a landing
page for a product we never ingest). `tea_staar_district` was right by
coincidence (matched a statewide PDF). `verify_live` never touched `/query` at
all. Each page_year source now carries a `product_proof` that must sit beside
the matched year; STAAR deliberately has none, because none is honest.

**Two footguns closed.** `/query` degraded (5/min) instead of failing open when
metering dies — it bounds calls, not dollars. And a committed
`outreach_watermark.json` refuses a send whenever the skip-list is smaller than
571, which a fresh container with no PAT would otherwise resolve to zero.

**One thing I got wrong mid-session** and want recorded: I suspected the bond
dataset's moved timestamp was a metadata touch. It was a real correction — the
Board backfilled vote tallies for Crowell ISD and Como-Pickton CISD. The check
was right; my scepticism was not.

**Still not A+, and not by me:** equity is a release behind because TEA put the
file behind a login and the portal gates bulk export on email verification;
seven credentials need rotating; and the only hard dollar ceiling is a
provider-side cap. The equity headline is now at least dated rather than
silently ageing.

---

## 2026-08-14 — Deployed: the migration applied itself in production, and /health can now prove it

**What changed:**
- PR **#11** (journey tracking, self-applying schema, doc corrections) and PR
  **#12** (`/health` reports `tracking_schema`) merged to master and deployed.
- Production confirms the whole loop:
  `{"status":"healthy","database":"connected","tracking_schema":"ok: tracking schema already present"}`
- `verify_live.py` **21/21**. `/px/{rid}.gif` returns a real 43-byte GIF89a,
  `/static/track.js` 200, and **an anonymous visitor still receives no
  `set-cookie`** — the privacy guarantee holds in production, not just in tests.
- The new disclosure is live on `/about`; the old false sentence
  ("We measure the site, never the visitor: no cookies…") greps **0** times.

**Why "already present" is the result that matters:** on the PR #12 boot the
tables were reported as ALREADY existing, which means an earlier boot — PR #11's
deploy — created them. The self-applying migration worked unattended against
production. No dashboard step was ever taken, and none is needed again.

**Gotchas:**
- **master is branch-protected**: `git push origin HEAD:master` is rejected
  ("push declined due to repository rule violations"). A PR is the only route
  to production; that is how #7–#12 all shipped.
- Vercel's **Git integration** builds production on merge to master. The tell
  that it is connected at all is the existence of the
  `texas-isd-finances-git-master-…vercel.app` domain. `deploy.yml` is a
  separate, still-inert path (needs VERCEL_TOKEN/ORG_ID/PROJECT_ID secrets).
- A freshly deployed route can still 404 at the edge for ~a minute. Append a
  cache-busting query before concluding a deploy failed — that briefly looked
  like a broken deploy and was not.
- No Supabase credential exists in the dev container, the Vercel CLI is
  unauthenticated, the Vercel MCP can only create NEW projects, and
  `workflow_dispatch` returns 403 (the GitHub App token has no
  `actions: write`). Every path to "just run the SQL" was closed — which is
  what forced the better answer of having the app do it.

**Open items:**
- `SUPABASE_PAT` still required at send time for journey tokens to reach the
  database; recoverable same-day via `scripts/sync_outreach_state.py --push`.
- Wave 1's 571 sends remain untracked and unretrofittable. Next wave uses
  `--campaign w2`.
- `data/outreach_sent.csv` (571 rows) is still gitignored and container-only
  unless mirrored; verify `SELECT count(*) FROM public.outreach_sent` = 571
  before any wave.
- The seven pasted credentials still need rotating.

---

## 2026-08-13 — 500 more sends, the KPI read that found two instrument failures, and per-recipient journey tracking

**What changed:**
- **Outreach wave continued: 150 sent 08-12, 350 sent 08-13** (71 on 08-11),
  total **571 to 571 unique districts** — 43.6% of Texas, zero duplicates.
  ~448 of the 1,019 merge rows remain unsent.
- **`scripts/outreach_kpi.py` + `.github/workflows/outreach-kpi.yml`** (Mondays
  12:30 UTC): pulls each message's last event from Resend, writes
  `data/outreach_kpi_report.csv`, upserts `outreach_status` so engagement
  outlives Resend's retention. Skips harmlessly until both secrets exist.
- **Per-recipient journey tracking**: `sql/create_visitor_tracking.sql`,
  `src/tracking.py`, `/px/{rid}.gif` open pixel, `/e` dwell beacon,
  `static/track.js`, `scripts/journey_report.py`, `docs/TRACKING_SETUP.md`.
  Sender mints a rid per recipient, logs it to `data/outreach_recipients.csv`
  and Supabase. 666 tests green.
- **Privacy disclosure rewritten** on `static/index.html` and
  `static/about.html#privacy`, plus both halves of the tracked email.

**Why:**
- The KPI read exists because opens/clicks live on Resend's servers under
  Resend's retention. A campaign whose only record is someone else's database
  is a campaign you will eventually not be able to report on.
- Tracking is per-recipient because "did the superintendent read it" is the
  question the whole outreach exists to answer, and campaign-level counters
  cannot answer it. The **entry condition is the design**: only a minted
  `?rid=` opens the identified path, so anonymous visitors keep the old
  guarantee exactly.
- The disclosure shipped WITH the feature because the old sentence — "We
  measure the site, never the visitor: no cookies, no IP addresses, no visitor
  IDs" — became false the moment the first cookie was set. On a transparency
  project that is the one bug that discredits every other number.

**Gotchas:**
- **Zero opens from the 08-11 batch is not behaviour, it is an off switch.**
  68 delivered, 0 opened, against 40.3% the next day: p ≈ 6e-16. Resend
  toggles open tracking PER DOMAIN, and that send predates the
  `gus@ubntag.com` default (added 08-12 04:38); the tests bracketing it went
  from `reports@txisd.dev`. Those 71 districts are UNMEASURED, not cold — do
  not re-target them as non-responders.
- **0 clicks across all 571 is also a switch**, not a verdict: 0 of 58 openers
  clicked, p ≈ 1/450. Click tracking is off. Campaign-level click-through IS
  already counted first-party as `src:email` in `site_visits` since 08-12
  12:50 and **has never been read**.
- `Success. No rows returned` in the Supabase SQL editor is printed BOTH by a
  migration that worked and by a SELECT that found nothing — it cannot tell
  you which. Verify DDL with `to_regclass(...) IS NOT NULL`, which always
  returns one row of true/false.
- The open pixel read `app.state.db_pool` directly and raised AttributeError
  when the lifespan had not run; that renders as a broken image inside a
  superintendent's inbox. All tracking paths now use `_pool_or_none()`.
- `tests/test_static_pages.py` resolved a script `src` against `static/`
  without stripping a `/static/` prefix, so the project's own asset
  convention failed its own guard.

**Open items:**
- 🔴 **`sql/create_visitor_tracking.sql` is NOT yet applied to production**
  (checked 08-13: all three objects absent). Until it is, every click is
  dropped — `visitor_event.rid` is a FK to `outreach_recipient`.
- 🔴 **`data/outreach_sent.csv` (571 rows) has never been committed and is
  gitignored.** It survives only in this container and in Supabase
  `outreach_sent` IF each send ran with SUPABASE_PAT. `_remote_emails()`
  returns an EMPTY set when the PAT is unset, so a fresh container with no
  local log and no PAT has an empty skip-list and **would re-email all 571**
  (571 of the 1,019 merge rows overlap). Verify
  `SELECT count(*) FROM public.outreach_sent` = 571 before any wave.
- 🔴 Same exposure for `data/outreach_kpi_report.csv` (271 status rows) —
  container-only unless that run had a PAT.
- Wave 1's 571 sends can never be journey-tracked; links are already
  delivered. Tracking starts with `--campaign w2`.
- Master is 3 commits behind this branch (PRs #7–#10 merged the rest).

---

## 2026-08-11 (deployed) — Production finally serves what the repo says

**What changed:** deployed to Vercel production (`dpl_3LcfZUbZbHTMXeA5NYfDpsmtfN1G`,
READY) and applied `sql/create_nlp_usage.sql` + `sql/create_cron_runs.sql` to
Supabase.

**Verified, not assumed:**
- `verify_live.py` **21/21 green** — was 8 DRIFT / 7 NOT DEPLOYED.
- **Wills Point ISD and Louise ISD are off the false-claim list** (93 flagged,
  was 102). Wills Point's live bond record now reads 6 propositions, 1 carried,
  2004-2025, with the $70M 2025-11-04 win present.
- `/debt/texas`, `/campuses/texas` 200. `/forensics` HTML carries both new
  sections. MCP serves 9 tools.
- `/query` answered a real question AND incremented `nlp_usage`, so the global
  call ceiling is enforced across instances rather than per-process.
- `/api/cron/runs` returns `available:true` with an empty run list — correct, the
  cron has not fired since the table was created.
- `vercel.json` unchanged by the CLI and `git status` clean.

**Gotchas:**
- **The Supabase Management API 403s urllib with `error code 1010`** — that is a
  Cloudflare user-agent block, NOT an auth failure. The same PAT and the same
  body work through curl. Diagnosing it as a bad token would have wasted the
  session; check with a GET first.
- The Vercel CLI printed a clean READY JSON this time (no `deploy_failed` noise),
  but `vercel.json` was still worth re-reading afterwards — the CLI rewrites it
  when it decides to re-link.

**Open items:**
- 🔴 **Rotate the Vercel, Supabase and GitHub PATs plus the DeepSeek key.** The
  first three were pasted into chat a second time on 2026-08-11 and used for
  this deploy. They are live in Vercel env vars, so rotating means updating them
  there too.
- 🔴 Set a DeepSeek monthly spend cap. The SQL bounds CALLS, not dollars.
- `master` is still ~130 commits behind the work branch.
- No alerting. `/api/cron/runs` now makes a silent cron failure visible, but
  nothing watches it.

---

## 2026-08-11 (campus) — The district rating hides 138,664 students

**What changed:** `scripts/ingest_tea_accountability.py` +
`scripts/build_campus_data.py` -> `static/campus_data.json`.
`/campuses/texas`, `/district/{n}/campuses`, a `district_campuses` MCP tool
(nine now), a "What the district rating hides" section on `/forensics`,
`tests/test_campuses.py` (14). 549 tests pass.

**The finding:** 138,664 students attend a campus Texas rates D or F inside a
district Texas rates A or B — 221 campuses, 73 districts, 21,415 of them at a
campus rated F. And the spread is the rule: 779 of the 890 districts with more
than one rated campus contain campuses at different letter grades; 196 span
three or more.

**Why:** every other layer stops at the district, because that is where money is
reported. It is the wrong unit for the question a family asks. A child goes to a
campus, not to an average.

**Gotchas:**
- **TEA's accountability download is a multi-step SAS form** (`_service=marykay`,
  `prgopt=.../dd_pick_columns.sas`). Not worth automating: the Enhanced
  Statewide Summary workbook is one 16 MB xlsx with every district AND campus
  for the year plus demographics, and a longitudinal sheet back to 2011.
- **"Not Rated" is not a bad rating.** 525 campuses. Counting them would have
  manufactured 525 failing schools out of missing data.
- **Alternative-education campuses are rated on a different scale.** Checked
  before publishing: only 2 of the 223 raw matches carry the flag, so the
  finding does not depend on excluding them — but both figures ship so the
  choice is visible rather than trusted.
- **The best/worst labels shipped inverted.** The campus list is sorted
  worst-first and `GRADE.get(rating, 9)` sorts unrated campuses PAST an A, so
  `rows[0]`/`rows[-1]` both read backwards and could report "Not Rated" as a
  district's best campus. Houston ISD printed `worst=A`. Derive from the grades.
- **The refusal that matters most:** no campus is ranked against a campus in
  another district. A statewide campus league table would rank a school serving
  newly arrived students against a wealthy suburb and call the gap quality.
  `test_no_campus_is_ranked_against_another_district` fails the build if a
  campus number ever appears in a statewide list.

**Open items:** unchanged — deploy blocked on the user, five credentials, three
SQL migrations. Provenance tests still do not cover equity, outcomes, bonds,
debt or campuses.

---

## 2026-08-11 (end) — Asked whether districts should get a UUID; built a crosswalk instead

**What changed:** `scripts/build_district_crosswalk.py` -> `data/district_crosswalk.csv`
(1,310 rows, committed, `.gitignore` whitelisted). `tests/test_crosswalk.py` (11).
533 tests pass.

**Why a UUID is the wrong answer**, checked against our own 20,587 district-years:
- 103 districts changed NAME and kept their number (004901 Aransas County ->
  Rockport-Fulton). That is the one job an identifier has, already done.
- Zero numbers ever reused for a different entity.
- It would not touch the hard step: the Bond Review Board sends a NAME, so
  name+county resolution is needed either way.
- It would break "check it yourself" — 057905 is verifiable at TEA; a minted id
  is verifiable against nobody but us, making us the authority instead of Texas.
- 057905 carries its county in the first three digits, which is exactly what
  fixed the bond join and caught the Highland Park double-count.
- tryopendata's `texas-isd/registry` is this idea already, and its `tea_number`
  column is filled for **3 of 1,029 rows**. The schema is easy; the mapping is
  the work.

**What was actually missing:** somewhere to WRITE DOWN the reconciliation, which
was recomputed on every run and discarded. 37 aliases now captured (including
the `ISDa`/`ISDb` disambiguator suffixes whose loss silently dropped 147
propositions the first time), 103 former names, 967 brb_ids, 1,005 boundaries.

**Gotchas:**
- 4 districts have no county — all charters first appearing in 2025, not yet in
  TEA's Snapshot. A test asserts that a county-less district is ALWAYS new, so a
  future county-join failure cannot hide among them.
- 279 charters, 0 with a Census boundary. Asserted: a boundary on a charter
  would mean TIGER attached somebody else's polygon.
- `test_the_bond_review_id_maps_one_to_one` is the double-count guard: the
  Board serves one id under two contradictory county labels.

**Open items:** unchanged. Deploy still blocked on the user; five credentials to
rotate; three SQL migrations to apply.

---

## 2026-08-11 (later still) — MCP 2026-07-28 shipped final; we conform, and MRTR found a use

**What changed:**
- Audited `src/mcp_protocol.py` against the final release point by point:
  version string, no handshake (SEP-2575), no `Mcp-Session-Id` (SEP-2567),
  `Mcp-Method`/`Mcp-Name` routing with -32020 (SEP-2243), `ttlMs`+`cacheScope`
  on list results (SEP-2549), `_meta` requirements, -32022, 404+-32601,
  `resultType` on every result. **12/12 pass, no code change needed.**
- **MRTR implemented (SEP-2322)** for ambiguous district names.
  `NeedsInput` in `src/mcp_tools.py`; `resultType: "input_required"` with an
  `inputRequests` / `elicitation/create` form; retry via `inputResponses`.
  7 new tests. 522 pass.
- **`instructions` now derives its figures from the artefact.**

**Why:**
The final release shipped what the RC described, so conformance was a
verification job, not a migration. MRTR is the one genuinely new mechanism
worth adopting here, and it maps exactly onto this project's oldest hazard:
thirteen Texas district names belong to two districts each. Previously an
ambiguous name returned prose telling the model to disambiguate — which works
only if the model reads and obeys the prose. Now the call does not complete.
That is the same instinct as everything else in this repo: make the system
refuse rather than guess.

**Gotchas:**
- **The blog announcement is not the spec.** It confirmed conformance but says
  nothing about `isError` vs protocol errors, the `tools` capability
  declaration, `x-mcp-header` constraints, or the exact MRTR wire shape.
  Reading `/specification/2026-07-28/server/tools` gave the real
  `inputRequests` / `elicitation/create` / `inputResponses` structure. Building
  MRTR from the summary would have shipped a non-conforming guess.
- **My first probe of `find_district` "failed" because I passed `query`; the
  schema says `name`.** The tool was fine. Worth remembering before reporting a
  bug from a red result.
- **`instructions` said "4,588 bond elections" and had for weeks** — hardcoded,
  never updated by the refresh, and going into the context of every assistant
  that connects. Stale numbers in server instructions are our stale numbers
  repeated in somebody else's model. Now read from `bond_data.json`, with a
  test.
- **No `requestState` is minted.** The spec has clients echo it only if the
  server provides one; the arguments are re-sent, so there is nothing to
  remember. Minting one would have added an opaque token to validate for no
  gain, in a server whose whole point is statelessness.
- A name matching NOTHING stays `isError` rather than becoming a question. A
  typo is self-correctable; only a real ambiguity — where both answers exist —
  earns a round trip.
- `compare_districts` catches `(ToolError, NeedsInput)`: one ambiguous name in
  a list of six must skip that district, not abort the comparison.

**Open items:** unchanged — deploy still blocked on the user, five credentials
still to rotate, three SQL migrations still to apply.

---

## 2026-08-11 (later) — Nothing was checking the live site

**What changed:**
- `scripts/verify_live.py` (NEW) — fetches production and diffs 16 headline
  figures plus 2 attribution claims against the committed artefacts. Run now:
  **7 DRIFT, 5 NOT DEPLOYED**. Against a local server built from this tree:
  all green. `docs/live_check.json`.
- `sql/create_cron_runs.sql` + `/api/cron/runs` (NEW) — one row per firing,
  with `status`/`duration_ms`/`rows_written`. The cron handler now records
  `skipped`, `ok` and — new — `error`, before re-raising.
- `src/format.py` (NEW) — one `usd`, one `big`, one `district_name`.
  `src/mcp_tools.py`, `src/api.py` and `scripts/isd_intel.py` all point at it.
- `tests/test_cron_log.py` (10), `tests/test_format.py` (13). 514 pass.

**Why:**
Asked whether the app was "god-mode". It is not, and the reason is not
analytical: the live site was publicly wrong about a named school district
while every check in the repo was green. Every guard ran inward from the
deployed site. None of them had any idea what was on the internet.

**Gotchas:**
- **A 404 is not a network failure.** The first cut of verify_live classified
  `/debt/texas -> 404` as UNREACHABLE, which is exactly the wrong answer: the
  site answered, and it said it does not have that endpoint. Only transport
  failures are unreachable now; an HTTP status is always a finding. Getting
  this backwards would let a whole missing layer hide behind "no egress".
- **`_usd` meant two different things in two modules.** `mcp_tools._usd` is
  exact; `isd_intel._usd` abbreviated, rendering **$1,500,000 as "$2M"** and
  $1,234 as "$1K" in emailed output — a third of the value gone. Any code moved
  between the two silently changed precision. `isd_intel` also still had the
  `$-354` sign bug fixed in `mcp_tools` months before and never propagated.
- **All three name formatters had the same two bugs**, independently:
  `D'hanis ISD` (plain `.capitalize()` after an apostrophe) and `S And S CISD`
  — the latter being a real Grayson County district, and one of the two names
  behind the original bond mis-attribution.
- `_RecordingConn` in `tests/test_api.py` kept only the LAST `execute`, so
  adding a second INSERT broke `test_cron_binds_a_date_not_a_string` on
  position. It records every statement now and selects by SQL text.
- `format.district_name` must NOT re-case input that is already mixed case:
  TEA shouts, the Bond Review Board does not, and blindly title-casing turns
  "Rio Grande City Grulla ISD" into "... Isd".

**Open items:**
- 🔴 **Deploy is blocked on the user.** No `VERCEL_TOKEN` in this container and
  the Vercel MCP needs interactive approval. Production is still wrong about
  Wills Point ISD and Louise ISD.
- 🔴 Rotate the five credentials; apply `sql/create_nlp_usage.sql` and
  `sql/create_cron_runs.sql`; set a DeepSeek monthly cap.
- Wire `verify_live.py` into CI as a scheduled job once deployed.

---

## 2026-08-11 — The bond data was the wrong publisher's copy, and the balance sheet was missing

**What changed:**
- `scripts/ingest_bond_elections.py` (NEW) pulls school bond elections from the
  **Texas Bond Review Board** on `data.texas.gov/resource/kbmc-qmvg.json`,
  replacing a municipal-advisory vendor's Excel export. Refreshed layer:
  **4,992 decided propositions 1958–2026, 952 districts, 100% matched**,
  $327.6B asked (was 4,588 / 943 / $291.5B).
- `src/sources.py` bond entry repointed. It had credited the file to
  "compiled county election returns (Texas Secretary of State)" and asserted
  that no single agency publishes school bond elections statewide.
- `scripts/verify_sources.py` now checks **attribution**, not just liveness.
  Every source declares `proves_it`; two declare an `attribution_url`.
- `scripts/ingest_brb_debt.py` + `scripts/build_debt_data.py` (NEW) →
  `static/debt_data.json`. `/debt/texas`, `/district/{n}/debt`, a "What is
  still owed" section on `/forensics`, and a `district_debt` MCP tool (eight
  now). `tests/test_debt.py` (21 tests). 489 tests pass.
- `scripts/district_match.py`: `&` is expanded to `AND` before punctuation is
  stripped. `scripts/build_bond_data.py`: `matched_pct` no longer rounds up
  to 100.
- `src/absences.py`: `no_debt_outstanding` — owing nothing is a finding.

**Why:**
Two questions from the user, one day apart, produced this. The first pointed at
a `data.texas.gov` endpoint; checking it revealed our bond file was the same
data, two years stale, from the wrong publisher. The second was an aggregator
(tryopendata.ai) carrying BRB debt-outstanding data — which we did **not**
ingest from there. The whole provenance chain is "publisher file → hashed copy
→ committed fixture → diffed artefact → tested page", and a re-publisher breaks
it at link one. The aggregator was used to *discover* the source; both
endpoints we actually read belong to the Board.

**Gotchas:**
- **A live link is not a right link.** `verify_sources.py` passed the wrong
  bond publisher every single run: the SoS page returns 200 and its host
  matched the publisher we had wrongly named. Liveness and host-match are both
  satisfiable by a completely wrong citation. This is the failure mode that
  hides longest, because it looks checked.
- **The vendor file was two years stale and nothing could tell.** It matched
  the state's own file exactly through 2023, so it looked complete. 404 decided
  propositions were missing, every one of them recent.
- **Two published claims were wrong.** Wills Point ISD was on `/forensics` as
  having no voter-approved bond; it carried $69.9M on 2025-11-04 after five
  straight defeats over 21 years. Louise ISD carried $9M on 2026-05-02. Checked
  the 25 named districts on that list first, before anything else — 13 appeared
  in the live file but 11 of those were *defeated* bonds, so the claim held for
  them and the absence layer was never implicated.
- **The CAB repayment ratio is an artifact on a current balance.** As principal
  retires the denominator shrinks while accreted interest does not. Leander ISD
  reads 4.5x in 2014, 20.1x in 2025, 396x in 2030, 698x in 2040 — describing no
  change in any deal. Publishing the current-year figure would have put a
  fabricated 20x on a named district. Ratios are taken at peak only, and two
  further guards were needed after that: a **gap** in the reported years
  disqualifies a district (Ysleta reports 2005–2012 then 2020+, and its largest
  reported total postdates the 2015 4:1 cap, so no such deal could have been
  signed), and a series that opens already declining does too (La Joya, 90.5x
  in 2005). 63 ratios published, 1.22x–10.84x; 106 districts keep their
  deferred interest with no ratio.
- **`data.brb.texas.gov` returns 403, not 404, for a key that does not exist.**
  Verified by hand (Allison ISD's own page carries no CSV reference; twenty
  rapid requests for a key that exists all returned 200). Conflating forbidden
  with absent is normally dangerous, so `MAX_ABSENT_PCT` refuses the run if it
  starts happening at scale — a host-wide 403 would otherwise publish as Texas
  having paid off its schools.
- **The Board's index lists three issuers under two names each**, including one
  id serving byte-identical data as both "Highland Park ISD (Dallas)" and
  "Highland Park ISD [Amarillo]" — contradictory county labels, one of them
  simply wrong upstream. Deduplicating by name would have added $406.5M to the
  statewide total twice. Dedupe by id.
- **Sands CISD really does owe $601,490 per student.** 229 students in the
  Permian Basin with enough oil-and-gas value to service $138M. Not a bad
  join — and worth guarding, since "Sands CISD" and "S and S CISD" were the
  original name-collision bug.
- Rows after fiscal 2025 are the **amortisation schedule**, not history. Summed
  together they would show Texas owing roughly twice what it owes.
- `static/sources.html` is hand-maintained against the register and
  `tests/test_sources.py` enforces that they agree — changing `src/sources.py`
  alone fails the suite.

**Open items:**
- 🔴 **Rotate five credentials pasted into chat**: Vercel PAT, Supabase PAT,
  GitHub PAT, DeepSeek key, and now `od_live_…` (tryopendata.ai, 2026-08-11).
  All live in Vercel env vars; rotating means updating them there too.
- 🔴 **This branch is not deployed.** Production still serves the vendor bond
  file, still shows Wills Point and Louise ISD as having no voter-approved
  bond, and has no `/debt/*` endpoints.
- Apply `sql/create_nlp_usage.sql` to production.
- Provenance tests still do not cover equity, outcomes, bonds or debt.
- Still no cron run log — the one silent-failure path left in production.
- Worth taking later from the same aggregator's catalogue, first-party:
  **TEA campus accountability** (81,117 rows, 9,989 campuses, 2017-18→2024-25 —
  the campus file already on the NEXT list) and **Census district population**
  (tax burden per resident, not per student). Their `entity-tax-rates` is
  broken upstream; `audit-fund-financials` covers 15 districts.

---

## 2026-08-10 — txisd speaks MCP 2026-07-28, and the caveats travel with the numbers

**What changed:** commit `5708370`, live on https://txisd.dev/mcp. 388 tests
(was 351). `docs/MCP.md` is the reference.

`POST /mcp` implements Model Context Protocol **2026-07-28** (final; the RC
window closed on schedule and all four Tier 1 SDKs speak it). Seven read-only
tools over committed JSON: `find_district`, `district_money`,
`district_forensics`, `district_trends`, `district_bonds`, `texas_overview`,
`compare_districts`.

**Why this, and why now.** People increasingly ask an assistant where their
school tax goes, and those answers are ungrounded. The point is not the tools —
it is that **every result returns the payload's own `limits` array**, and the
headline caveat is in the text a model reads most closely. "Suggestive, not
settled" now travels with the bond finding into someone else's chat instead of
sitting on a page nobody scrolled.

**Why it was cheap.** Earlier MCP revisions established a connection-scoped
session with an `initialize` handshake and an `Mcp-Session-Id` header. This app
is Vercel serverless behind a round-robin with no sticky routing and no shared
session store — the same reason `/query`'s call ceiling had to be counted in
the database rather than in a process. An MCP server here would have needed
affinity the architecture does not have. 2026-07-28 removed the handshake
(SEP-2575) and the session (SEP-2567) and moved version, identity and
capabilities into `_meta` on every request, so the server is just another
stateless POST handler.

### Hand-written, not the SDK

Vercel builds this function from the `[project]` table under a 500 MB cap, and
a dependency that fails to resolve fails **every** deploy, not just this
feature. The surface actually needed — three methods, no sampling, no
elicitation, no subscriptions, no resources — is small enough that the standard
library is the smaller risk. `src/mcp_protocol.py` is the wire format,
`src/mcp_tools.py` is the content. **No new dependency was added.**

Implemented: `server/discover` / `tools/list` / `tools/call`; required `_meta`
validated; `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` mirrored **and
validated against the body** including the `=?base64?…?=` sentinel (−32020 —
that error code exists because a gateway routing on the header while the server
executes the body is a real hole); `x-mcp-header` mirrors `district_number`
into `Mcp-Param-District`; unknown method → **404** with a JSON-RPC body (lets
a client tell a modern server from a legacy one with no MCP endpoint); unknown
tool → −32602; bad version → −32022 with the supported list; notifications →
202; GET/DELETE → 405; a legacy `initialize` is told what this server speaks,
because legacy clients cannot fall forward; `Origin` checked when present.
`ttlMs` one day, `cacheScope` public — the data changes once a year at a TEA
release.

### 🔒 `/query` is deliberately NOT exposed — keep it that way

It is the single path with a prompt-injection history (closed 2026-07-31 via
`nlp_reader`), it spends DeepSeek tokens against a global ceiling, and exposing
it would let arbitrary text in any chat reach a SQL agent. Every tool here is a
deterministic read of a committed artefact: nothing to inject, nothing to
spend, and **no database**, so a paused Supabase free tier cannot take the
endpoint down. Tests assert all of it, including every tool still answering
with `db_pool` set to `None`, and that the string "sql" appears nowhere in the
tool surface.

**Gotchas:**
- Results **MUST** carry `resultType` in this revision, and `server/discover`
  returns `supportedVersions` (plural) — not `protocolVersion`. Reading the
  blog summary alone would have produced a subtly wrong server; the spec pages
  were worth fetching.
- Python 3.11 f-strings cannot contain a backslash or reuse the outer quote
  inside the expression. A nested `f"{x:+.1f}"` inside an f-string is a
  SyntaxError, not a style issue — extract a helper.
- `src/api.py` imports `mcp_tools`, so `mcp_tools` must import `api` **inside**
  the function, not at module level. That also avoids a second in-memory copy
  of a 2.8 MB artefact.
- There was no parsed loader for `fallback_index.json` — `/fallback-index`
  streams the file with `FileResponse`, deliberately. Added `_fallback_index()`
  alongside it rather than making every visitor pay to parse it.
- Reading the actual tool OUTPUT caught three things the tests did not: an
  operating balance rendering as `$-649`, statewide sums running to twelve
  digits (`$291,455,942,461`) which invites a model to transcribe them wrong,
  and `find_district("wylie")` returning two rows both reading "Wylie ISD" with
  nothing to choose between them. It now carries enrolment — 19,334 in Collin
  vs 5,595 in Taylor. **Print what the model will read; the tests will not tell
  you it is unusable.**

**Verified:** ruff clean, 388 tests, and a conforming client
(`/tmp/mcp_client.py`, reproduced in `docs/MCP.md`) run against LIVE production
over HTTPS: discovery, listing, all seven tools with their limits, the
fragility label surviving the trip, and every spec-named error — header
mismatch −32020, bad version −32022 with the supported list, unknown method
404/−32601, unknown tool −32602, bad argument as `isError` rather than a
protocol error, and GET → 405. All pass.

**Open items:** unchanged — the four pasted credentials still need rotating,
`sql/create_nlp_usage.sql` still needs applying, Supabase is still on the free
tier. New: consider the **MCP Apps** extension (SEP-1865) later — the eight
pages here are already self-contained with a strict CSP and no external
scripts, which is close to what it wants, but it is an extension rather than
core and can wait.

**Notes:**

## 2026-08-09 (later) — The forensic file becomes a trajectory, and one revenue column nearly published a 30-point error

**What changed:** commit `9222f76`, live on https://txisd.dev. 351 tests (was 332).

New `/trends/texas`, `/district/{n}/trends`, and a "Seventeen years, and which
way it is moving" section on `/forensics`, from `static/trend_data.json`
(`scripts/build_trend_data.py`), no database. Six measures per district,
fiscal 2009–2025, constant 2024 dollars, each drawn against the state's own
line. The portal's Trends section links into a district's trajectory
(`/forensics?d=…#trajectory`) and the forensic file links back.

**Why:** every view on the site reported one year. That tells a board where it
stands and not which way it is going, and the direction is the part still open
to a decision. The user asked whether the data could be seen per year and
whether the trends told a story for leadership; it does, and it is one story.

### The statewide squeeze, all six measures

| | 2009 | 2025 |
|---|---|---|
| instruction's share of the operating dollar | 57.8% | **54.5%** |
| instruction per student (real) | $7,249 | **$6,880** |
| security & monitoring per student | $96 | **$232 (2.4×)** |
| debt service per student | $1,507 | **$2,441 (1.6×)** |
| federal revenue per student | $1,452 | $1,432 (peak **$2,798** in 2022) |
| operating revenue − operating spend | +$0.15B | **−$1.58B** |

Total spending per student rose ~$1,010 real, but a shrinking share reaches a
classroom because debt service and security absorbed it; the federal money
that masked it for three years is gone; and enrolment growth fell from ~68,900
a year through the 2010s to 12,807. Library/media fell $79/student (−42%) over
the same window — the second-largest cut after instruction.

### ⚠️ The column that nearly published a 30-point error

An operating deficit was first computed against
`all_funds_total_operating_revenue_and_other_revenue_and_reca`, giving **12%**
of districts short in 2025. Against `all_funds_total_operating_revenue` it is
**44.4%**. The difference is `all_funds_other_revenue`, and that column tracks
debt service almost exactly year by year — $5.3B vs $4.9B in 2009 through
$14.3B vs $13.9B in 2025. **It is the I&S debt tax levy.** Counting it as
operating revenue while excluding debt service from operating cost understates
deficits badly. The measure now excludes debt from BOTH sides, which is also
what stops a routine construction year reading as a crisis. An intermediate
answer of "3.4% → 12.1%" was given to the user before this was caught and has
been corrected to them in writing.

The finding that survives is stronger than the one that was nearly published:
in this seventeen-year window Texas districts had **never** collectively spent
more on operations than operating revenue covered. 2025 is the first time
(+$3.0B in 2022 → −$1.6B), 44.4% of districts are short against a previous
worst of 27.1%, and they enrol 67.7% of students.

### Guards

- **Balanced panel.** Every headline re-derived on only the 1,142 districts
  present in both end years: instruction's share falls 3.2 points there vs 3.3
  across all reporting districts. The check ships in the payload and the page
  quotes it, because a trend that only exists because the roster changed is not
  a trend.
- **Findings are generated from the series**, so tests re-derive each headline
  from the data it came from — the share figures, the federal peak YEAR, the
  deficit percentages, and the claim of a "first" against every earlier year's
  margin.
- **Direction is per measure.** A rise in debt and a fall in instruction are
  both bad news; `fall_is_worrying` carries that per measure, and a test asserts
  `steeper_than_state` respects it on 1,000+ comparisons. A single sign test
  would have inverted half of them.
- Districts under 500 students keep their series but are flagged and excluded
  from rankings. Districts with fewer than 8 reported years 404 by design.

**Gotchas:**
- `json.dumps` writes bare `NaN`, which strict parsers reject. Missing years
  must be `None`. The test loads the artefact with `parse_constant` so this
  can never ship.
- `.tcard svg { height:110px }` also matched the arrow icon `apply_design.py`
  injects in place of a text "→", rendering it 110px tall. Scope chart CSS to
  a class (`svg.tline`), never to the element.
- `usd(-354)` renders `$-354`, which reads as a typo. Operating balance is the
  one measure routinely negative — the sign goes before the currency mark.
- Two `scrollIntoView` calls raced: the district file scrolled itself in, then
  the trajectory did. If the reader followed a `#trajectory` link the file must
  stand down, and the anchor must wait until the district's own lines are in.
- The portal's Trends section only renders when the database answers, so the
  cross-link is invisible with `SUPABASE_DB_URL` unset. Verify it by replaying
  a real production `/summary` response through `page.route()`.
- The Vercel CLI again exited non-zero with a JSON "deploy_failed" blob while
  the deployment succeeded. `vercel ls --prod` is the source of truth.

**Open items:** unchanged from the entry below — the four pasted credentials
still need rotating, `sql/create_nlp_usage.sql` still needs applying, and
Supabase is still on the free tier.

**Notes:**

## 2026-08-09 — The bond join was wrong in both directions; fixing it moved a published finding, and the forensic file was built on the corrected base

**What changed:** commit `55ac58a`, live on https://txisd.dev. 332 tests (was 313).

### 1. The bond-to-district join was broken, and one failure mode was publishing to the wrong district

The bond layer is the only one joined on a NAME rather than a TEA district
number. It matched by squashing names to uppercase A-Z. That failed twice:

- **147 propositions were silently dropped.** The source disambiguates Texas's
  thirteen colliding district names with a trailing lowercase letter — "Wylie
  ISDa" (Collin) vs "Wylie ISDb" (Taylor) — which squashes to `WYLIEISDA`, not
  `WYLIEISD`. Wylie ISD's district page showed **none** of its twenty
  propositions. Also lost: 11 Chapel Hill, 9 Northside, 7 Highland Park. A
  second class of miss was pure spelling — TEA writes `STEPHENVILLE` with no
  "ISD" at all, `PEWITT CISD` vs the source's "Pewitt ISD", `IRION COUNTY` vs
  "Irion Co", and renames like Roscoe → Roscoe Collegiate.
- **7 propositions were attached to a district that did not hold the election.**
  "S and S CISD" (Grayson) and "Sands CISD" (Dawson) are different districts
  that squash to the same `SANDSCISD`, and `drop_duplicates` kept whichever
  sorted first. That is the worst failure this project can have: a published
  claim on the wrong district.

**Fix:** a TEA district number already carries its county in the first three
digits (057 = Dallas), and the bond file records each election's county. New
`scripts/district_match.py` resolves in order — name+county (exact), then a
name unique statewide, then a prefix relation *inside the right county* for
districts that renamed themselves — and **refuses rather than guesses**
otherwise. New `scripts/audit_bond_match.py` prints the entire join
(collisions, unmatched, weak) and **exits non-zero if a shared name was ever
resolved without the county agreeing**. Result: **100% matched** (was 96.8%),
**943 districts** (was 911), **0 risky**, 12 rename matches — both of them
correct (Rio Grande City Grulla, West Rusk County).

### 2. Correcting the join moved a published finding, so the wording moved with it

The bond→outcome test was published as **p=0.061, not distinguishable from
zero**. With the recovered elections it is **+1.31 points, CI +0.07 to +2.55,
p=0.038** (310 bonds, 153 districts). It crossed the conventional line on a
**3% change in sample**, which is exactly what a borderline result does.
Rather than promote it to a finding, the payload now carries a `fragile` flag
and a confidence interval, and the district page reads **"suggestive, not
settled — read it as a lead, not a finding."** Do not let anyone quote this as
proof that bonds raise test scores.

### 3. The forensic file — built only after the base was trustworthy

New `/forensics` page + `/forensics/texas` + `/district/{n}/forensics`, served
from `static/forensic_data.json` (`scripts/build_forensic_data.py`), no
database. It composes four questions Texas publishes in four incompatible
files:

1. **What sits OUTSIDE TEA's operating total** — $13.9B/yr statewide in debt
   service, median $1,538/student, 90th pct $4,490. Composed with the
   operating figure, never subtracted from it (a test asserts
   `total == operating + debt` across 1,000+ districts).
2. **Who pays** — from GROSS local collections, not TEA's net-of-recapture
   figure, which makes property-funded districts look state-funded.
3. **What the ballot promised** — the only public itemisation of school
   facilities that exists.
4. **Where it landed** — against what each district's own need predicts.

**Deliberately no combined score** and **no per-district causal claim.** Flags
are descriptions carrying their own number against a threshold published
beside them. 1,013 of 1,202 districts carry at least one flag; the most common
are beats/below prediction (461/425), locally funded (244), recapture (224).

**Why:** the user asked for forensic-intelligence treatment of the ISD system.
The honest version of that is not a risk score — it is finding the places
where the official reporting structurally hides a number, and putting those
numbers side by side. A composite ranking would have implied wrongdoing from
four unrelated inputs, so tests now forbid a composite field, accusatory
language, and any named individual in the payload.

**Gotchas:**
- `itertuples()` silently renames columns starting with `_` to positional
  `_1`, `_2` — `r._county` raises AttributeError. Name assign() columns
  without a leading underscore.
- `.note` in `design.css` is a **callout component** (accent bar + tinted
  well), not a caption class. Six captions in a row as callouts is visual
  noise; the page uses `.sub-note` for captions and keeps `.note` for the one
  disclaimer that earns the emphasis.
- `grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))` gives **three**
  columns inside `--page-max`, so a four-card set renders 3 + an orphan.
  Explicit `1fr 1fr` above 800px is what makes "four questions" read as 2×2.
- The Vercel CLI printed `"deploy_failed" / "fetch failed"` and a non-zero
  exit **while the deployment succeeded** — `vercel ls --prod` showed three
  Ready production deploys from the "failed" runs. Check `ls` before retrying;
  retrying just stacks duplicate deploys.
- `curl` to `127.0.0.1` fails with code 000 in this container unless
  `NO_PROXY='*'` is set — the agent proxy intercepts loopback.

**Open items:**
- 🔴 **Still open:** rotate the four credentials pasted into chat (DeepSeek,
  Vercel, Supabase, GitHub PATs) and update them in Vercel env vars. DeepSeek
  first — it has a live billable balance.
- Set a monthly spend cap on DeepSeek.
- Supabase free tier still pauses after ~7 days idle; the site now survives it
  but the NLP path does not.
- `sql/create_nlp_usage.sql` still needs applying to production to activate the
  cross-instance `/query` ceiling.
- Optional: PR from `claude/audit-public-launch-ocd7ra` to `master` (production
  deploys from the working tree, so master is behind).

**Notes:**

## 2026-07-27 (later) — Three accuracy fixes, two new layers, and a green deploy that served a dead site

**What changed:** commits `06f694c` → `f797b0c`, all live on https://txisd.dev.
55 tests.

### The accuracy work (do this before features — the user was right to insist)

1. **We were reporting the wrong STAAR bar.** TEA publishes three. Statewide
   SY 2024-25: **74.2% reach Approaches, 46.5% reach Meets, 17.6% Masters.**
   The portal reported Approaches — the lowest — and a parent told "74%" hears
   "at grade level". Everything now reports **Meets**, with all three shipped
   as context.
   **This was not a relabel.** Scoring districts on Approaches vs Meets moves
   **35 of the top 100** "reliably beats expectations" districts, so modelling
   one bar while displaying another would have named outperformers on a measure
   nobody sees. Meets starts in 2018 (costing 5 years of span), costs nothing
   in reliability (split-half **0.913** vs 0.910), and the need model fits
   BETTER on it (**50.1%** vs 42.3% of the spread).
   **The lever ranking changed with the bar:** teacher pay +$5,000 is now the
   largest identifiable effect (**+0.86**, CI +0.48/+1.23); class size −2 is
   +0.37 (+0.20/+0.55); **turnover −10 drops to +0.30 and its CI now crosses
   zero**; spending +$2,000 stays at +0.15, still zero. The headline holds;
   the ranking under it did not.
2. **A flipped confidence interval.** Scaling for display — "cut turnover by
   10" multiplies per-unit by −10 — **flips the interval**, so `ci_low` becomes
   the upper bound. The crosses-zero test silently failed and turnover was
   drawn as solid when it spans zero. Fixed with `Math.min/max`; test pins it.
3. **An overstated credential.** The hero claimed "67 years of records". True
   of ONE source (bond elections, 1958-2024); finance is 2009-2025. Now "17
   years of budgets", pinned to `/stats` by a test.

### New layers

- **Equity** (`/district/{id}/equity`, `/equity/texas`) from TEA District STAAR
  2024+2025, 99.8% join. Headlines **how a district's low-income students do**
  and their percentile among poor students statewide.
  **The trap deliberately avoided:** ranking on the poor/non-poor GAP. It
  correlates **−0.02** with how well poor students actually do; the 30
  narrowest-gap districts average 40.2% against 39.0% statewide, so gap-ranking
  surfaces the merely average. A gap narrows as easily when the top falls as
  when the bottom rises. Austin ISD: **28% for low-income students (14th
  percentile), 75% for everyone else.**
- **HISD takeover** (`/takeover/houston`). Difference-in-differences against 13
  districts matched on PRE-takeover size and poverty. **Houston +5.5 vs +0.0,
  first of 14.** Pre-trends parallel (−0.30 vs −0.53/yr). Placebo across all
  1,166 districts: 50th overall, **1st of 30 large districts**. Enrolment fell
  3.0% vs 1.3% but poverty held (79.5→79.6), so composition is reduced not
  excluded. Gains broad — low income +4 vs +1.7, EB +3 vs −1.0, Black +5 vs
  +2.1, Hispanic +5 vs +1.8 — **except special education, −1.0 vs +0.8**,
  reported in the caption with a test asserting a negative group still ships.
  No p-value, and the payload says why.

### Presentation

Scroll-triggered count-up on headline figures (IntersectionObserver + eased
tween, once only, `prefers-reduced-motion` honoured, real value in `aria-label`).
Progress rail + sticky section nav with J/K keys. Hero rewritten to answer what
this is / what you are looking at / why you should care, with **6.6 million data
points** — counted, breakdown on hover. Prose cut hard: bond section 800 → 454
words.

**Gotchas — the expensive ones:**

- 🔴 **A READY deploy served a 404 on every route.** Vercel changed
  backend-framework routing so an internal rewrite passes the DESTINATION path
  to the app. Our `/(.*) → /api/index` rewrite handed FastAPI the literal
  `/api/index` for every request. Portal, `/health`, `/docs` — all 404 while
  the build log said READY. The only signal was one warning line in the build
  log. **Pinning the CLI to 57 did NOT help — the change is platform-side,
  keyed on the framework setting.** Fix: delete the rewrite; the `fastapi`
  preset already routes to `api/index.py`. Now an invariant in CLAUDE.md plus
  a test asserting `vercel.json` has no `rewrites`.
- **A counter that never fires shows a confident zero.** Pre-zeroing every
  count-up meant elements the reader never scrolled to sat at "0%". Fixed:
  already-visible figures play immediately, and anything un-fired after 6s
  snaps to the real value.
- **`loadDashboard()` swallows render exceptions**, and it bit again — the
  section nav sat behind fourteen render calls inside the try block and
  silently never built. Anything that must run belongs AFTER `renderAll()`,
  not inside it.
- **CSS `.chk b` styled every bold in the body** as a block uppercase label.
  Scope decorative rules to `:first-child`.
- Claims drift as filters change: the "narrow gaps mean nobody does well" line
  was true unfiltered and false once thin cells were excluded (40.2 vs 39.0).
  Re-read your own prose after changing a threshold.

**Open items:**
- 🔴 **Rotate the three PATs** (Vercel/Supabase/GitHub) — pasted twice, used
  for ~8 deploys, shredded after each.
- ⏭️ Write the HISD finding up for a reporter (offered, not started).
- ⏭️ TAPR campus file — teacher certification, and the 77% of district
  performance invisible above campus level.
- 🟡 Read-only DB role for NLP; 1.6 MB `economics_data.json`; 518 KB `/geomap`.

---

## 2026-07-27 — The bond story shipped, and the question it forced: does any of this buy results?

**What changed:** commit `ca1c943`, deployed and verified live on
https://txisd.dev.

- `scripts/build_bond_data.py` -> `static/bond_data.json` (981 KB, committed).
  4,588 decided propositions 1958-2024, 911 districts, 96.8% name-matched to
  TEA numbers. Source: a user-supplied export of Texas ISD bond election
  results, staged as `data/texas_bond_elections.csv` (gitignored; the script
  rebuilds from it).
- `/district/{id}/bonds` and `/bonds/texas`, both serving with no database.
- A four-beat narrative section on the district page, built to
  storytelling-with-data discipline rather than as a chart dump: every chart
  title states the FINDING, grey carries context and one accent carries the
  argument, and the pass/fail read never depends on colour alone (filled vs
  dashed outline). Interactive timeline — hover or tap any circle for that
  ballot's purpose, amount and vote.
- 47 tests.

**Why this data matters more than its size suggests:** we had documented, in
`docs/DATA_ROADMAP.md` and in the economics payload's own limits, that TEA does
not itemise facilities and therefore a stadium cannot be separated from a roof
without district bond documents. **The ballot closes that gap.** Every dollar
of Texas school debt passed through an election with a stated purpose and a
recorded vote. It is the only public record of what school debt was FOR.

**The findings (all live on the page):**
- Texans approve classrooms 74% of the time. Athletics is the only category
  they reject more often than they approve; the 145 propositions naming a
  **stadium** specifically pass just **48%** of the time.
- **Bundling works.** Athletics alone passes 54.2%; bundled with classrooms,
  63.8% — and the typical ask goes from **$6M to $22M**. A voter who wants
  classrooms often cannot vote for them without also voting for the field house.
- **The demand side of the debt rise we already measured:** districts asked for
  **$120.5B in 2020-24**, more than in all of the 2010s ($89.2B), while approval
  fell from 86.8% (1958-99) to **63.2%** — a 66-year low. That is the other half
  of the +72% I&S rate rise in the economics layer.

**The analysis that closes the loop (run, NOT yet on the page):** does passing
the bond change results? 710 bonds, 484 districts, each district compared to
ITSELF — the residual-vs-need 2-4 years after the vote against the 3 years
before. Passed: **-0.32 pts**. Rejected: **+0.24 pts**. Difference **-0.57,
p=0.214** — indistinguishable from zero. Large bonds (>$20k/student): -0.34.
Athletics bonds that passed: -0.19. Buildings do not move test scores. The
caveat that must ship with it: a bond in a growing district buys SEATS, not
scores, and safety and roofs are real goods STAAR cannot see.

Taken with the economics layer, every money lever we can measure now lands in
the same place: spending +0.08 (CI crosses zero), buildings -0.57 (crosses
zero), teacher pay +0.48. What is large is the 20.2-point persistent
between-district effect that is **77% unexplained** by anything TEA publishes
at district level.

**Gotchas:**
- **21.5% of bond records carry a vote tally under 20** — a $40M bond recorded
  as "1 for, 0 against". Those are placeholders, not turnout. Printing them
  would have put an obviously false number in front of a reader. Fixed at the
  SOURCE (`MIN_PLAUSIBLE_VOTES = 20`, tally suppressed, `votes_reported` flag,
  limit stated in the payload); the carried/defeated result is unaffected and
  is kept. A test pins it.
- **Propositions bundle**, so athletics dollars include classrooms sold
  alongside. Both the bundled and athletics-alone figures ship; a test asserts
  the payload says "upper bound".
- `df.itertuples()` cannot expose columns whose names contain spaces
  ("Votes For"), which fails at runtime, not at import. Use `iterrows()` or
  rename first.
- **`loadDashboard()` swallows every render exception** in its outer
  `catch {}`, so a broken render leaves the section silently hidden with no
  page error. When a section will not appear, call its render function directly
  from the console before assuming the data is missing — the data was fine both
  times this happened.
- The local design harness proxies DB endpoints to the live site and is flaky
  on a cold start; a run showing everything empty is often just that. Re-run
  before debugging.

**Do not ingest the two companion bond files.** They carry a vendor's CRM —
17 named sales representatives, per-district revenue, commission percentages.
The bond and TEA columns in them are public; the commercial columns must never
reach an MIT-licensed public repo. Only `..._Bond_Results_All.csv` is used.

**Open items:**
- 🔴 **Rotate the three PATs** (Vercel/Supabase/GitHub) — pasted in chat twice
  now, 2026-07-22 and 2026-07-25. The Vercel one was used for two deploys this
  session and shredded after each; `.vercel/` and `.env.local` removed.
- ⏭️ **Bake outcomes in as the spine, not a section.** Every money fact should
  terminate in what it bought, with an error bar. First build: put the
  bond→outcome test on the district page under the timeline.
- ⏭️ **The HISD board-of-managers test** — did the 2023 TEA takeover change
  outcomes, against matched districts? Biggest education story in Texas,
  directly testable with data already loaded, and unpublished.
- ⏭️ **TAPR campus file** — teacher certification status is the sharpest test
  of our own finding that stability beats pay, and 77% of what makes a district
  work is invisible above campus level.
- 🟡 Read-only DB role for NLP; 1.6 MB `economics_data.json`; 518 KB `/geomap`.

---

## 2026-07-26 — Deployed. And the two Vercel traps that nearly sent it to the wrong place

**What changed:** everything from `fc294cd` through `c6be292` is now LIVE on
https://txisd.dev. Verified: `/economics/texas`, `/district/{id}/economics`,
`/outcomes`, `/geomap`, `/map` all 200; all five security headers present on
`/`; `/docs` still 200 with no CSP; the economics section rendered in a real
browser against production with 3 macro series, 5 lever intervals, 6 peer rows,
a 17-row table twin, zero page errors, and the turnover correction in place.

**Gotchas — both would have looked like success:**

1. **There are TWO Vercel teams and TWO projects named `texas-isd-finances`.**
   `vercel link --project texas-isd-finances` without the right scope resolved
   to team **GOAT-UIX** and *created a brand-new project there*, which deployed
   green and served nothing. `txisd.dev` is attached to the **TAG-ai** team
   (`tag-ai-projects`, `team_hLW8yrUTYNGt9CiRY4IMMSet`), project
   `prj_Q86h3ZufDMLk7bsyYOj7FP3S9Wqg`. The confusion is real: the Supabase org
   is called GOAT-UIX while the Vercel account is TAG-ai. **A deployment
   reporting "ready" proves nothing — check the project's domain list.** The
   stray project was deleted.
2. **`vercel link` REWRITES `vercel.json`.** CLI 57 detected "services" and
   injected a `services` block with `buildCommand: pip install -r
   requirements.txt`. That is the full local dev set — pandas, matplotlib,
   statsmodels — and would have blown the 500 MB bundle cap that
   `requirements-vercel.txt` and the `[project]` table exist to avoid. It also
   flipped the PROJECT's framework setting server-side to `services`, which
   then failed every deploy with "no services are declared" until it was PATCHed
   back to `fastapi` via the REST API. Always `cat vercel.json` after linking.

Also removed the now-redundant top-level `functions` block from `vercel.json`:
CLI 57 rejects it alongside service detection, and every path its `excludeFiles`
listed is already covered by `.vercelignore`.

**Open items:**
- 🔴 **Rotate the three PATs pasted in chat** (Vercel/Supabase/GitHub, both
  2026-07-22 and 2026-07-25). The Vercel one was used for this deploy and then
  shredded; `.vercel/` and `.env.local` were removed.
- ⏭️ Bond election data analysed but NOT built in — the per-district bond
  history section is the next feature.
- 🟡 Read-only DB role for NLP; 1.6 MB `economics_data.json`; 518 KB `/geomap`.

---

## 2026-07-26 — The economics layer, and the bond data that closes the stadium question

**What changed:** commits `325e9f9` and `5c05564` (pushed, **still not deployed**).

- `scripts/ingest_tea_property.py` — certified property values (tax years
  2015-2025), adopted M&O/I&S rates (2005-06 to 2023-24), recapture paid by
  district (fiscal 1994-2026). TEA has no finance API; these are spreadsheets,
  older ones under `/sites/default/files` with underscores where newer ones use
  hyphens. The URL table records both.
- `scripts/build_economics_data.py` -> `static/economics_data.json` (1.6 MB,
  committed, served sliced per request). Within-district first differences for
  the lever effects; an 11-year reliability score; matched outperformers.
- `/district/{id}/economics` and `/economics/texas`; a district-page section
  with inline-SVG charts, a validated categorical palette, and a table twin.
- Corrected the published turnover claim (see below). 44 tests.

**Why:** the portal could say where money went and how students did, but not
what a taxpayer pays, what it buys, or who does better — which is every
question an actual reader has.

**Gotchas — three that would have shipped wrong numbers:**
- **TEA reports local M&O revenue NET of recapture.** Any per-student figure
  built on that column understates property-wealthy districts badly (Austin
  reads as a $93B tax base instead of $184B). Add recapture back for gross
  collections.
- **Debt service sits OUTSIDE `total_operate_expend_by_function`.** Subtracting
  it to get a residual yields a NEGATIVE "everything else" for any district
  with real debt. Compose the parts; do not carve them out.
- **Charters are not data-quality failures.** 188 districts have no tax rate
  because they levy no property tax. Counting them as "withheld for QA" would
  have reported our error rate as 188 when it is 0. Now counted separately and
  pinned by a test.
- Playwright needs `executable_path="/opt/pw-browsers/chromium"`; the local
  design harness must be a `ThreadingHTTPServer` or the browser's parallel
  fetches deadlock it and `networkidle` never fires.

**The correction we owed:** the published lever chart (turnover 10.12% of
variance vs spending 0.01%) is CROSS-SECTIONAL and was being read as leverage.
Within districts over three years (5,887 windows, 1,210 districts, year effects,
clustered SEs): $2,000/student more buys **+0.08 STAAR points, CI -0.21 to
+0.37** — indistinguishable from zero; cutting turnover 10 points buys +0.43;
cutting class size by 2 buys +0.59. The ranking survives, the magnitude does
not. What IS large is the persistent between-district difference: split-half
r = **+0.91**, a 20.2-point spread top-to-bottom decile, of which only **23%**
is explained by every staffing and money variable TEA publishes. The chart now
says it describes rather than forecasts, and links to the within-district
effects. Same correction inline in `docs/WHAT_A_DOLLAR_BUYS.md`.

**Bond election data (analysed, NOT yet built in).** A user-supplied CSV of
4,588 decided Texas school bond propositions, 1958-2024, $291B asked / $232B
approved, with an explicit purpose field — it joins to our districts at 97%
(912 districts). This closes the gap we had documented as unclosable: TEA does
not itemise facilities, but the ballot does. Athletics: 637 props, 57% pass
rate vs 74% for school buildings; stadiums named specifically: 145 props, 48%
pass — the only category voters reject more than approve. Bundling athletics
with classrooms lifts the pass rate from 54.7% to 62.3% and takes the median
ask from $6M to $24M. Voter willingness is collapsing as the asks grow:
86.8% pass on $9.8B (1958-99) -> **63.2% pass on $120.5B (2020-24)**, which is
the demand side of the +72% I&S rate rise we already measured.

**Do not ingest the other two bond files.** They carry a company's CRM —
17 named sales reps, per-district revenue, commission percentages. Public bond
and TEA columns are fine; the commercial columns must never reach an
MIT-licensed public repo. Rebuild that analysis from the clean file instead.

**Open items:**
- 🔴 **Nothing since `439e82f` is deployed.** No Vercel token in this session
  and the Vercel MCP needs an interactive approval. Production still 404s on
  `/economics/*` and serves no CSP header.
- 🔴 Rotate the credentials pasted into chat (2026-07-22 and 2026-07-25).
- 🟡 `economics_data.json` is 1.6 MB — fine sliced server-side, needs trimming
  before any client-side use.
- 🟡 Read-only DB role for the NLP path; 518 KB `/geomap` payload.
- ⏭️ Next: the per-district bond history section from the clean CSV.

---

## 2026-07-26 — Hardening pass: security headers, a bounded /query, and a table twin for both maps

**What changed:** Commit `fc294cd` on `claude/audit-public-launch-ocd7ra`
(pushed, **not yet deployed — no Vercel token in this session**).

- `src/api.py`: a `security_headers` middleware setting CSP
  (`default-src 'self'`, `frame-ancestors 'self'`, `script-src`/`style-src`
  `'self' 'unsafe-inline'` because the pages inline their script and styles),
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a
  `Permissions-Policy` allowing geolocation only for `self` (the "find my
  district" path needs it). `/docs`, `/redoc` and `/openapi.json` return
  before the headers are set.
- `src/api.py`: `/query` now runs the LangChain agent through
  `run_in_threadpool` under `asyncio.wait_for` (`QUERY_TIMEOUT_SECONDS`,
  default 45) and returns 504 instead of hanging. A global ceiling
  (`QUERY_GLOBAL_LIMIT`, default 60 per window, `_global_hits`) sits behind
  the per-IP bucket.
- `static/geomap.html` and `static/map.html`: a `<details class="a11y">`
  table twin publishing the same numbers as the canvas — 1,005 rows sorted by
  teacher turnover on `/geomap`, 1,202 sorted by spending per student on
  `/map`, every row linking to `/?d=<number>`.
- `tests/test_api.py`: 41 tests now — added `test_security_headers_present`,
  `test_query_has_a_global_spend_ceiling`, `test_maps_ship_a_table_twin`.

**Why:** These were the findings graded but not fixed in the previous audit.
The canvas maps are the centrepiece of the site and were completely
unreachable by keyboard or screen reader; bolting fake focus onto pixels
would have been theatre, so the honest fix is to publish the same data as a
real table. On `/query`, the per-IP limit alone could not bound cost —
`X-Forwarded-For` is caller-supplied — and the synchronous agent was being
awaited inline, so one slow question stalled every other request on the
worker.

**Gotchas:**
- **`map.html` had the a11y CSS but never the markup or the function.** The
  styles shipped and looked like the feature was there. `test_maps_ship_a_table_twin`
  now asserts markup + function + call site on both pages.
- **Writing `<caption>` before `table.innerHTML` silently wipes it** — the
  caption is a child of the table. Both pages now emit the caption as part of
  the same innerHTML string. Only caught by reading the rendered DOM; the
  source grepped fine and the page threw no error.
- The local design harness routes are `/map` and `/geomap`, **not**
  `/map.html` — pointing Playwright at the `.html` paths silently serves
  `index.html`, and every selector comes back "not found" with no error.
- Playwright in this container needs
  `executable_path="/opt/pw-browsers/chromium"`; the bundled headless-shell
  version it looks for is not installed, and `playwright install` is banned.

**Open items:**
- 🔴 Rotate the credentials pasted into chat (2026-07-22 and 2026-07-25).
- ⏳ **Deploy `fc294cd`** — needs a Vercel token; the staged one was shredded
  after the last deploy and the Vercel MCP server requires approval this
  session. Verify after: security headers present on `/`, absent on `/docs`,
  and both `<details>` tables render with 1,005 / 1,202 rows.
- 🟡 Read-only DB role for the NLP path — the last unfixed hardening finding.
- 🟡 518 KB `/geomap` payload on mobile.
- 🟡 Intel gap to close first: **revenue composition** (24 unused columns —
  "who pays"), then General Fund vs All Funds (67 column pairs).

---

## 2026-07-26 — Audit: the AI was stating falsehoods, and nothing was findable

**Graded the whole system, then fixed the two failing areas.** Data work
graded A; **AI accuracy D, distribution D.**

🔴 **The answer box was confidently wrong.** Asked "how many districts are
in the data" it replied *"There are a total of 100 distinct school
districts."* Truth: 1,310. Asked again in other words: 1,310, correct.
**Non-deterministic, which is worse — you cannot warn users precisely.**

**Cause was our own system prompt**, which said "Limit results to prevent
overload (default LIMIT 100)". The agent put `LIMIT 100` on a
`SELECT DISTINCT` and reported the row count as the total. Replaced with an
explicit *counting is not limiting* rule (never LIMIT an aggregate; use
`COUNT(DISTINCT …)`; never present returned-row-count as a total; flag
possibly-truncated listings) plus the ground truth (1,310 / 20,587 /
2009–2025) so a contradicting answer is caught before a reader sees it.
**Verified fixed: same question 5× on production, 1,310 every time.**

**Distribution (why nobody had found it):**
- **Shared links now work.** `/?d=043905` opens that district on a device
  that has never seen the site. Before this, every link posted anywhere
  opened on the *reader's own* saved district — it would have silently
  broken an entire campaign.
- `og:`/`twitter:` tags on report and map; shares were bare blue links.
- `robots.txt` + sitemap of all 1,205 district pages (district views render
  client-side from `?d=`, so crawlers had no way in). `/query` disallowed —
  no crawl budget on the paid path.
- Vercel Web Analytics (no cookies). We had zero usage visibility.
- **txisd.dev** swept through pages, docs and citations, replacing the
  vercel.app prototype URL. *That domain existed the whole time and was in
  neither CLAUDE.md nor this log* — every link handed over for days pointed
  at the prototype. **Custom domains belong in the boot file.**

**Gotchas:**
- **`/districts?limit=500` returns the first 500 ALPHABETICALLY.** The first
  shared-link implementation looked names up there: worked for Frisco (F),
  silently failed for Pittsburg (P) and ~800 others, which announced
  themselves as "032902". Now resolved from the `summary` payload
  `loadDashboard()` already fetches. **A limit is a filter — testing one case
  inside it proves nothing about cases outside it.**
- Local harness passed; production caught it. Test across the *range*, not
  one sample.

**Still open (graded, not fixed):** map keyboard/screen-reader path (C−),
`/query` threadpool + timeout, read-only DB role, spoofable rate limit,
no CSP/X-Frame headers, 518 KB geomap payload on mobile.

**Intel still missing, ranked:** revenue composition (24 unused columns —
answers "who pays", needs no new data) · General Fund vs All Funds (67 unused
pairs) · campus-level TAPR (parents attend schools, not districts) · teacher
salary by experience band (likely the mechanism behind the turnover finding)
· bond schedules · multi-year turnover averages · vendor registers.

---

## 2026-07-26 — "One child": the report at human scale

**What changed:** A card at the top of the outcomes section that divides the
same figures down to one student, one classroom, one childhood. Plus
`border_keeps_teachers_better` in `scripts/build_outcomes_data.py`.

**The three beats:**
- **"$163 a day"** — spending per student over a 180-day year. Billions move
  nobody; a daily figure for one child does.
- **"2 of 10 teachers"** — of ten teachers present when a child starts
  kindergarten, how many would still be there when they leave fifth grade at
  today's turnover rate, beside the same figure for similar districts.
  **Nobody has ever handed a parent that number.**
- **"6 of 10 classmates"** — student poverty as a classroom, not a percentage.

Then the closer: the bordering district teaching similar students that keeps
its teachers. Rockport-Fulton loses 30.4%; Calhoun County next door, 66.5%
student poverty vs 60.9%, loses 10.7%.

**Gotchas:**
- The ten-teacher figure compounds `(1 - turnover)^5`. That **overstates**
  churn among veterans, because leavers skew new. The caveat is **in the
  card, not a footnote** — stating it is what makes the number quotable
  instead of attackable. Do not remove it to tighten the layout.
- `border_keeps_teachers_better` uses TIGER adjacency (shared boundary
  vertices), similar poverty within 8 pts, turnover better by >=4 pts.
  **373 of 1,205** districts have one. Needs `--shapefile` on the outcomes
  build; without it the field is simply absent and the card degrades.
- Rebuild order still matters: `build_outcomes_data.py --shapefile ...` then
  `build_district_geo.py` (which merges the measures).
- When spot-checking a district in the browser, **use a real district number** —
  the page trusts the number for data and the stored name for display, so an
  invented pair renders the wrong name against real figures. Cost me one
  confusing test.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted 2026-07-25.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, keyboard/SR path for
both maps, PR #2 review.

---

## 2026-07-26 — Named the report, surfaced the map, credited the collaboration

**What changed:** Three things, all live.

1. **The map was live but unfindable.** "Map of Texas" sat in a row of quiet
   text links beside Print; the owner shipped it and could not find it. It is
   now the one filled button in the header. **Shipping and surfacing are
   different jobs** — doing the first is not doing the second.
2. **Named the work.** Hero eyebrow: "Storytelling with data · a story of
   Texas ISD", plus a credential band — 17 years of state records, 1,310
   districts, 20,587 financial records, the annual total, "every number
   traceable to the State of Texas". **Every figure reads from live data at
   load**, so it cannot drift when TEA publishes again. First pass got this
   wrong twice: hardcoded a record count, and fetched the 518 KB boundary
   file on the landing page purely to count districts. Both removed.
3. **Collaboration credit** — TAG ai with Michelle Sanchez, Realtor,
   Coldwell Banker Realty.

**Gotchas / judgement calls on the credit:**
- Her details came from the `michelle-sanchez-brand` skill, not from chat.
  Correct form is **"Realtor | Coldwell Banker Realty"** (not "Coldwell
  Banker Realtor"), and **TREC License #0724260** is included because Texas
  license holders' public-facing material should carry it.
- **No unverifiable claims.** The copy states the shared goal that was given;
  it invents no client anecdote.
- **Added an independence statement unprompted.** A school-data guide
  credited to a realtor invites the question "are these numbers picked to
  sell houses?" Silence leaves it open. Stating that figures are TEA's
  loaded unchanged, that nothing is ranked or recommended, and that no party
  influenced any number or method, closes it. Disclosure is what makes the
  collaboration an asset.
- **Deliberately did NOT apply her brand chrome** (black header bar, gold
  accents, CB badge, headshot). Correct for a listing presentation; in a
  public data report it would read as real estate marketing and spend the
  exact credibility this report cannot afford. The report keeps its
  white-minimalist design. Revisit only if she wants a co-branded PDF, which
  is a different artifact.

**Positioning settled** (for future sessions): TAG ai's angle is *nobody
trusts a capability deck, everybody trusts a thing they already used.* The
guide is the demonstration; the footer credit is enough. Leading with TAG
turns it into vendor content districts will not cite in a board meeting.

**Open items:** 🔴 **rotate the Vercel / Supabase / GitHub PATs pasted
2026-07-25** — still outstanding, the Vercel one deploys to production.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, keyboard/SR path for
both maps, PR #2 review. Product idea with the strongest case: the
one-paragraph plain-English verdict-free "should I worry?" sentence,
generated for all 1,205 districts — it serves parents, teachers, taxpayers
and reporters at once.

---

## 2026-07-26 — The real map of Texas is live (and it needed no Mapbox)

**What changed:** `/geomap` — 1,005 actual school-district boundaries,
colourable by teacher turnover, spending, student poverty, or how far a
district beats what its demographics predict. Plus
`scripts/build_district_geo.py`, `scripts/simulate_map_value.py`,
`docs/MAP_VALUE_SIMULATION.md`, and routes `/geomap` + `/district-geo`.

**Asked before building.** The Monte Carlo (100k visitors placed by real
enrolment, adjacency from 2,863 real shared borders) had to be able to say
"no". It said: **100%** of visitors see a bordering district that is not
among their statistical peers; **64.7%** share no overlap at all; median
overlap between neighbours and k-NN peers is **0**. The map is a different
question, not a prettier answer.

**No Mapbox, on purpose.** Polygons are Census TIGER 2024 (public domain),
the renderer is our own canvas code, and "find my district" is
point-in-polygon **in the browser** — location never leaves the device, no
API key, no per-load billing, nothing to lock into. Mapbox remains optional
later for street-address geocoding and a basemap; neither is needed here.
Free tier if we ever do: 50k map loads and 100k geocodes a month.

**Gotchas:**
- Census keys on NCES codes, we key on TEA numbers. **Join by normalised
  name: 1,005 of 1,006.** The ten mismatches are an explicit alias table
  checked by hand (`Ft Davis` vs `Fort Davis`, `Hamlin Collegiate`,
  `LaPoynor`…). `Spring Creek ISD` is genuinely absent from TEA 2024 — left
  unmatched rather than forced.
- **Douglas-Peucker must be iterative here.** Texas rings run to tens of
  thousands of vertices; the recursive form blows the stack.
- 27 MB shapefile → **518 KB**: quantise to 1e-4 deg (~11 m), delta-encode
  along each ring, drop sub-threshold islands. 1,660,525 vertices → 48,760
  (2.9%). Measures are merged into the same file so the map is one fetch.
- **Charters have no boundary** — the map covers ~92% of Texas students and
  says so on its face. Never let a map imply those children do not exist.
- Rebuild after any TEA release: `build_outcomes_data.py` first (its output
  is merged in), then `build_district_geo.py`.

**What it shows.** Coloured by turnover, Texas renders as a **patchwork, not
regions** — the visual form of the finding that neighbouring districts differ
in turnover 87% as much as random ones, while salary (a labour-market
quantity) is only 63%. Pin Wharton ISD and the page says it plainly: loses
33% of its teachers; El Campo next door, 73.8% vs 78.1% student poverty,
loses 12.7%.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted 2026-07-25.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, keyboard/SR path for
both maps, PR #2 review.

---

## 2026-07-26 — Live-figures ticker, and the hero flash (a real bug) fixed

**What changed:** A scrolling ticker under the header, and the end of the
"hero appears then vanishes" flash a user reported.

🔴 **The flash was worse than it looked.** `boot()` did
`await loadStatewide()` **before** reading `localStorage` for a saved
district, so a returning visitor saw the entire hero — headline, subtitle,
statewide penny grid — for the length of two API round-trips, then watched
it disappear when `.compact` was applied. Anything that appears and then
vanishes reads as broken.

**Fix — do it before first paint, never in `boot()`:** a tiny inline script
in `<head>` sets `html.has-district` from `localStorage`, and CSS keyed off
that class hides the hero from frame one. The `Find your district` /
`Look up a different district` label swap moved out of JS into the same
class for the same reason. The statewide fetch no longer blocks the district
load. Verified by sampling the DOM 16 times during load against
**production**: hero visible in **0 frames** for a returning visitor, and
still renders for a first-timer.

**Ticker:** built only from figures already computed on the page —
statewide total and penny split, median teacher turnover and salary, the
lever finding, and once a district is open its per-student spending, largest
peer gap in real dollars, score vs prediction, and turnover vs peers. If a
figure can't be computed the item is omitted; nothing is padded and no
number is editorialised into a headline. Pace scales with content length
(~71s live), pauses on hover/focus, drops animation under
`prefers-reduced-motion`, hidden in print, no horizontal overflow on a
390px phone.

**Gotchas:**
- **Anything that depends on `localStorage` for above-the-fold layout must
  be applied pre-paint**, via `<head>` + a class on `documentElement`. Doing
  it in `boot()` guarantees a flash, and the flash lasts as long as whatever
  `boot()` awaits first.
- The ticker track is rendered **twice** and animates to `translateX(-50%)`
  — that is what makes the loop seamless. Don't "optimise" the duplicate
  away.
- **Hiding the hero also hid the statewide penny grid**, which lived only
  there — returning visitors lost the best explanation of the whole site.
  It now renders in **Statewide context** as well (one definition, two
  containers, `['', '-2']`). Watch for this whenever the hero changes.
- The pre-paint rule was written as `html.has-district .hero-fig`, which
  matched **any** `.hero-fig` on the page and silently gave the new
  statewide copy zero height while all 100 pennies sat in the DOM. Scoped to
  `.hero` descendants. A selector written for one element can reach an
  element that doesn't exist yet.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted 2026-07-25.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, map keyboard/SR path,
outcomes lens on the state map, PR #2 review.

---

## 2026-07-26 — Loop closed: "what the money buys" is live on every district page

**What changed:** The TEA Snapshot join stopped being a markdown file and
became the product. New `#outcomes-section` on the district page, above the
peer insights, plus `GET /district/{id}/outcomes` and
`scripts/build_outcomes_data.py` → `static/outcomes_data.json`.

**The section, in order (deliberate):**
1. **Who the district teaches** comes first — % econ disadvantaged, emergent
   bilingual, special ed, each against the state. Districts serving more
   students in poverty score lower on average, so leading with this is what
   makes every comparison beneath it legitimate rather than misleading.
2. **Seven measures vs peers AND state**: teacher turnover, experience,
   STAAR, attendance, graduation, salary, students per teacher. Peers come
   from the same exogenous k-NN graph (`static/map_data.json`) the rest of
   the site uses, so "vs peers" means one thing everywhere.
3. **Scored against what its student population predicts**, with the model's
   42% R² inline and "treat it as a question, not a verdict" in bold.
4. **The statewide lever chart** — turnover 10.12% vs spending 0.01%.

Pittsburg ISD is the whole thesis on one screen: 77% economically
disadvantaged, pays teachers *less* than peers ($51k vs $55k), keeps them
anyway (13.9% turnover vs 24.8%), scores 18 points above prediction.

**Design decisions worth keeping:**
- Payload is **precomputed static**, not queried — none of it changes between
  annual TEA releases. Consequence: `/outcomes` works with **no database at
  all**, which `test_outcomes_served_without_a_database` asserts.
- Cached per warm instance and **sliced per request**. Shipping all 713 KB to
  a browser to render one district would be waste.
- Compact by construction: labels/units/state medians live once in `meta`
  instead of being repeated 1,205 times (1.7 MB → 713 KB). Per district a
  measure is just `[own value, peer median]`.

**Gotchas:**
- Rebuild `static/outcomes_data.json` after any new TEA release — it is a
  build artifact, and it IS committed (unlike `data/*.csv`) because the API
  serves it directly.
- `.vercelignore` must not exclude `static/` or the endpoint 503s in prod.
- Deploy verified the right way: rendered against **production** through
  `scratchpad/liveproxy.py`, desktop and phone, no page errors, no
  horizontal overflow.

**Open items:** 🔴 rotate the Vercel/Supabase/GitHub PATs pasted on
2026-07-25 — still outstanding, the Vercel one deploys to production.
Then: read-only DB role for NLP, `/query` threadpool + timeout, real rate
limiting, analytics, Supabase idle-pause keep-alive, map keyboard/SR path,
PR #2 review. Product-wise the obvious next step is an outcomes lens on the
state map (colour by "beats expectation") and a turnover early-warning.

---

## 2026-07-25 — DEPLOYED. Two failures found: a broken build and a seat block

**What changed:** Everything from this session is live and verified in a real
browser against production. `dpl_5AtjJ2nPd6jqdjdQA9KBJ4uRYAUf` + favicon deploy.

**Why nothing had deployed all session — two independent causes:**

1. 🔴 **Every build was failing.** Vercel's FastAPI preset now builds with
   `uv`, which needs a PEP 621 `[project]` table. Ours had only
   `[tool.ruff]`/`[tool.pytest]`, so every build died on
   `Failed to run "uv lock": No 'project' table found in pyproject.toml`.
   Fixed by adding `[project]` with the RUNTIME deps only (mirrors
   requirements-vercel.txt — no pandas/matplotlib/plotly/openpyxl) plus
   `[tool.uv] package = false` (it's an app, not a library). **`uv lock`
   locally is the pre-flight check** before any deploy now.
2. 🔴 **Deploys came back `BLOCKED`, which is NOT a build failure.**
   `readyStateReason: Git author noreply@anthropic.com must have access to
   the team TAG-ai`, `seatBlock.blockCode = TEAM_ACCESS_REQUIRED`. Vercel
   **Pro bills per seat and refuses deployments whose git commit author has
   no seat.** Commits were authored `Claude <noreply@anthropic.com>`. Fixed
   by setting `git config user.email` to the repo owner; the
   `Co-Authored-By` trailer still records the AI author. **Keep it that way
   or deploys silently block again.**

Also added `.vercelignore` — the CLI was uploading `data/` (~19 MB of CSVs)
on every deploy, which is what made the first attempt time out at 10 minutes.
Upload is now 1.6 KB. And an inline data-URI favicon (every page load was
404ing on `/favicon.ico`).

**Verified live, not assumed:** `/health` healthy+connected; `/dollar/texas`
returns $109,448,637,486 across 1,202 districts and 5,528,915 students,
pennies summing to exactly 100; `/district/043905/dollar` 200. Rendered in
headless Chromium: hero reads "Texas school districts spend $109.4 billion a
year"; hovering a penny fills the guide panel; the pinned atom card reads
"Frisco ISD puts 3¢ more of every dollar into debt payments than similar
districts — $34,726,731 a year". **The map runs**: canvas 1724×1068 with ink,
search pins Frisco ISD, panel populates. Zero page errors.

**Gotchas:**
- Headless Chromium still cannot TLS through the agent proxy. To browser-test
  *production*, run `scratchpad/liveproxy.py` — it fetches live over HTTPS
  server-side and re-serves on `127.0.0.1:8799`, so Chromium renders exactly
  what production returns.
- Deployment state must be read from the API (`readyStateReason`, `seatBlock`),
  not inferred from the CLI. `BLOCKED` looks like a build failure and isn't.
- Credentials were staged to a 0600 file, used, then `shred -u`'d; `.vercel/`
  is gitignored and was removed. Working tree verified clean of tokens.

**Open items:** 🔴 **rotate the Vercel, Supabase and GitHub PATs pasted into
chat on 2026-07-25** (they are in the transcript; the Vercel one has deploy
rights). Then: surface the TEA Snapshot findings in the product, read-only DB
role for NLP, `/query` threadpool + timeout, real rate limiting, analytics,
Supabase idle-pause keep-alive, map keyboard/SR path, PR #2 review.

---

## 2026-07-25 — TEA Snapshot ingested: the project now has outcomes, students and teachers

**What changed:** `scripts/ingest_tea_snapshot.py` (self-downloading) and
`scripts/analyze_outcomes.py`, plus `docs/WHAT_A_DOLLAR_BUYS.md` and
`docs/findings_outcomes.json`. 19,441 district-years, 44 fields, 2009–2024.

**Where the data comes from:** TEA Snapshot "District and Charter Detail".
The download page is a form, not links — `POST` to
`https://rptsvr1.tea.texas.gov/perfreport/snapshot/push.cgi` with
`level=district`, `set=<2-digit year>`, `suf=.dat|.lyt`. Years 1995–2024 are
available. `.lyt` is the layout/definition file and you need it.

**Why this is the unlock:** PEIMS says where money GOES. Snapshot adds who
the students are (% econ disadvantaged, emergent bilingual, special ed),
the workforce (teacher salary, students per teacher, experience, **turnover**),
the tax base (taxable value per pupil, adopted tax rate, % revenue state/
federal), and outcomes (STAAR, graduation, attendance, accountability
rating). Joined on district_number + year.

**Headline findings** (associations, not causation — see the doc):
- Student need explains **33.4%** of the STAAR spread between districts;
  spending per student adds **0.0%** on top of it.
- Same control applied to every lever: **teacher turnover explains 10.12%**
  of what need leaves unexplained, vs **0.01%** for spending per student.
  Teacher experience and % new teachers rank 2nd and 3rd. Every money
  variable is near the bottom.
- Richest fifth of districts by property value spend **15% more** per
  student than the poorest fifth while serving 19 points less economic
  disadvantage; the poorest fifth carries **28% teacher turnover**.

**Gotchas:**
- **Map fields by layout DESCRIPTION, never by column name.** TEA embeds the
  reporting year in every variable (`DDA00A001S24R` vs `DDA00A001S18R`) and
  renames measures. Name-based mapping silently returns nothing.
- Older years call the key `COUNTY-DISTRICT NUMBER`, not `DISTRICT NUMBER`;
  ELL is `ENGLISH LANGUAGE LEARNERS` pre-2018 and `ENGLISH LEARNERS` after.
  The first pass silently produced **0 rows for 2009–2012** because of this.
- **Testing standard breaks at 2018** (phase-in satisfactory → "Approaches").
  The ingest stamps `test_standard` per row. No trend line may cross it.
- No accountability ratings in 2023/24 (litigation); no STAAR before 2013;
  2020–21 are pandemic years.
- FERPA-masked cells (`.`, `-1`, `*`) are **missing, not zero**.
- Join validates at 94.1%, and TEA's own operating-spend-per-pupil agrees
  with ours to a median 2.9% (different enrollment denominators — don't mix
  the two sources inside one calculation).
- `data/*.csv` is gitignored, so the ingest downloads its own inputs.

**Open items:** surface this in the product — none of it is in the API or UI
yet. Everything from the previous entry still applies, deploy included.

---

## 2026-07-25 — Guided dollar (macro→micro→atom) + landing page rebuilt from a browser audit

**What changed:** **Committed and pushed but NOT DEPLOYED** — see Gotchas.

(0) 🔴 **`static/map.html` has been completely broken in production since
2026-07-24.** It declared `const a` twice in the same function scope — a
hard SyntaxError, so the whole script never parsed: no canvas, no panel,
no search. Introduced in `04a4385` and shipped, because that deploy was
"verified" by grepping the served HTML for strings, which proves bytes
arrived and nothing more. **Never verify a JS change by grepping HTML.**
Fixed and confirmed in a real browser (canvas sizes and draws, search
pins, panel and readout populate, no page errors). Its `.catch()` also
wrote to a `.support` element that does not exist on that page, so any
data failure threw inside the catch and hid the cause — now reports into
`#readout`. Emoji removed from both pages; district names title-cased on
the map too.

(a) *Guided dollar.* New `GET /district/{id}/dollar` is now the single
definition of the 100-penny dollar for every client: largest-remainder
shares (always exactly 100), peer + statewide median shares rescaled to a
whole dollar, and dollars-at-stake from median dollars *per student* so
they stay real money. `static/index.html` renders it as: hover/tap/focus
any penny → a guide panel giving contents in plain English, TEA codes,
peer + state comparison and the annual dollar difference; click → an atom
card with a 17-year share sparkline against the peer line, sub-components,
and the question a board member or reporter should ask; a TEXAS ›
DISTRICT › CATEGORY zoom ladder; three stacked 100¢ bars (you / peers /
all Texas). Two categories the old client-side split buried in the
residual — safety & technology, community services — are now named.

(b) *Landing page.* Audited live in headless Chromium and rebuilt: the
7-step tour no longer auto-opens over the page; real hero with the
statewide total in the headline; the hero *shows* the live statewide
dollar (new `GET /dollar/texas`, pooled — no rescaling needed); quick-pick
chips from `/stats.largest_districts` plus type-ahead; hero collapses once
a district is picked; serif display face against the sans body; district
names title-cased on entry to state; header count now read from `/stats`.

**Why:** User asked for hover guidance and a macro→micro→atom path that
answers the questions only this data can answer, then asked for a browser
audit of the landing page. The audit found the first impression was a grey
modal over a search box — no headline, no number, no picture — in an 892px
column on a 1440px screen, with 1,202 vs 1,310 districts contradicting
each other between header and stats.

**Gotchas:**
- 🔴 **Deploys are not automatic from this branch.** Pushing produced no
  new deployment (polled 4 min; `/district/{id}/dollar` still 404s live).
  Earlier deploys this session used the user's Vercel PAT, since shredded;
  the Vercel MCP tools need interactive approval. Everything above is on
  the branch and unverified in production.
- Headless Chromium cannot TLS through the agent proxy (`ERR_CONNECTION_RESET`,
  no relay failure logged). Workaround that worked: a local plain-HTTP
  harness on 127.0.0.1 serving the working-tree HTML and proxying the API
  server-side, with `/dollar` computed by importing the real functions from
  `src.api` — which validated the endpoint math on live data before deploy.
  Chromium path is `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
- **A page can serve 200 and still be entirely dead.** Extract the
  `<script>` block and `node --check` it in CI, and render the page in
  headless Chromium against the local harness before claiming a UI works.
  Both pages now parse clean; add this to the verify step in CLAUDE.md.
- Penny grid: dimming at .18 opacity destroyed the grid's shape, and
  `transform:scale()` on the highlighted squares made neighbours collide.
  Use ~.3 opacity and an outline instead.
- skills.sh pages for the five requested skills are discovery stubs, not
  skill text; only `anthropics/skills/frontend-design` returned usable
  principles. Installing them needs an interactive session.

**Open items:** unchanged, plus: get this deployed and re-verify live;
map keyboard/screen-reader path. Still open: credential rotation
(user-side, 🔴), read-only DB role for NLP, `/query` threadpool + timeout,
real rate limiting, analytics, Supabase idle-pause keep-alive, PR #2
awaiting review — do not merge.

---

## 2026-07-25 — Phones can use the map; portal renamed "Texas ISD Financial Resource Guide"

**What changed:** Two shipped pieces, both deployed and verified live.

(a) `static/map.html` — full touch support. Added `touchstart` /
`touchmove` / `touchend` handlers: one-finger drag pans, two-finger pinch
zooms (clamped `k` to 1–14), a tap that doesn't drag opens the district.
Moved `touch-action:none` off `.mapwrap` and onto `canvas` alone so the
page still scrolls normally around the map. `resize()` now uses a portrait
aspect on narrow screens (`h = w * 1.05` under 560px, `w * 0.62` above) —
a 16:10 letterbox on a phone was ~120px tall. Added a `.mobonly` gesture
hint line.

(b) `static/index.html` — Resource Guide framing. Brand renamed to
"Texas ISD Financial Resource Guide" (subtitle: official TEA data ·
fiscal 2009–2025 · 1,202 districts); intro rewritten to name every
audience by name. New **Methods & citation** section with four
collapsible blocks: where the data comes from (loaded unchanged from TEA
— no estimating, no modeling), how each number is calculated (per-student
divisor, why our total exceeds the nationally-quoted per-pupil figure,
the exact TEA function codes behind each category, why peer matching
excludes spending, what each flag threshold means), known limits — read
before citing, and a copy-paste citation with retrieval date.

**Why:** User: "then fix it! I want this to become the Texas ISD Financial
Resource Guide where it becomes such a resource guide that it starts to be
used for decisions to develop new policies." Two things blocked that. The
map was 100% non-functional on phones — no touch handlers at all, so the
audience most likely to arrive from a social link (parents, boosters) hit
a dead screen. And nobody cites a source that won't show its work: a
policy-grade reference has to state its provenance, its arithmetic, and
its limits in the same breath as its numbers.

**Gotchas:**
- `touch-action:none` on the wrapper killed page scroll around the map —
  it must be scoped to the canvas element only.
- Mouse and touch handlers both fire on hybrid devices; the touch path
  tracks its own `touchStart` state and calls `preventDefault()` inside a
  `{ passive:false }` listener, which is required or Chrome ignores it.
- The "known limits" block is deliberately blunt (no HVAC/technology
  isolation possible, fiscal-year timing differences, overlapping
  categories, the AI answer box can be wrong). Underselling here is the
  only thing that makes the rest citable.

**Open items:** unchanged plus map keyboard/screen-reader path (canvas has
no SR alternative; search-based access exists). Still open: credential
rotation (user-side, 🔴), dedicated read-only DB role for the NLP path,
`/query` needs `run_in_threadpool` + `asyncio.wait_for` (today it blocks
the event loop and can 200 on failure), real rate limiting
(X-Forwarded-For is spoofable), privacy-friendly analytics, DB keep-alive
against the Supabase free-tier 7-day idle pause, insight percentile/rank
context, PR #2 (`docs/complete-repo-blueprint`) awaiting user review —
do not merge.

---

## 2026-07-24 — Map rewritten for humans (landmarks, neighborhoods, plain axes)

**What changed:** `static/map.html` reframed from an analyst scatter into
"A seating chart for every school district in Texas." Added: plain-English
"What am I looking at?" explainer; NEIGHBORHOOD labels (the 6 archetype
clusters named in place on the canvas); LANDMARK labels (14 largest
districts, spread-filtered to avoid collisions) so the picture has
recognizable anchors; plain axis labels drawn on canvas ("smaller
districts ← → bigger", "shrinking ←→ growing"); search now finds/zooms/
pins a district on Enter and writes a full-sentence readout naming its
section, size, spending vs neighbors, and closest matches; legend in human
words. 32 tests green; deployed + verified live.

**Why:** User looked at the map and said "I can't decipher this... would a
mom understand?" Correct — it was 1,202 anonymous dots with PCA jargon
axes. A real map has landmarks; ours had none. This was the one screen
that failed the universal-comprehension test.

**Gotchas:** Neighborhood labels are suppressed while a district is
focused (otherwise they fight the ego-network). Landmark labels are
skipped in "Flagged only" mode and drawn with white backing rects for
legibility over dots. Landmark spread filter uses data-space distance
>0.55 so labels don't stack in the dense big-district corner.

**Open items:** unchanged — launch-hardening (rate limit, RO DB role, map
TOUCH support + keyboard a11y still outstanding, analytics), rotate creds,
PR #2 review, operating-vs-total per-student KPI labeling.

---

## 2026-07-24 — "The dollar" + audience lenses + AI disclosure + TAG contact (live)

**What changed:** (1) AI disclosure + data disclaimer + Technology
Automation Group / TAG ai contact (839-888-2424, ubntag.com) in the footer
of BOTH portal pages (index.html, map.html). (2) "Your dollar" hero: total
district spending rendered as 100 colored pennies by category, with a
computed headline ("Of every dollar X spends, N cents goes to classroom
teaching"). (3) Six audience lenses (parent / taxpayer-grandparent /
booster / business / press / admin) that re-narrate the SAME numbers for
the reader; choice persists in localStorage. (4) One-tap 1200x630
shareable social PNG with penny grid + TAG branding. 32 tests green,
deployed, verified live on both pages.

**Why:** User asked for a Steve Jobs "touch of magic" and universal
comprehension (single mother, 81-year-old grandad, superintendent, coach,
booster, press). The Jobs move is making the abstract concrete: pennies
are a unit everyone owns. Lenses solve "one dashboard can't speak to
everyone" without forking the data — same honest numbers, different
narration.

**Gotchas:** Pennies use LARGEST-REMAINDER rounding so they always sum to
exactly 100 (naive rounding gives 99 or 101). The dollar is of TOTAL
spending (not operating) deliberately — it visually explains why
per-student totals look high (Dallas FY2025: 33c classroom, 23c
construction, 15c debt). renderExec was slimmed to delegate to
lensStory(); dead locals removed.

**Open items:** unchanged — launch-hardening (real rate limit, RO DB role,
map touch/a11y, analytics), rotate creds, PR #2 review, operating-vs-total
per-student labeling on the KPI tile.

---

## 2026-07-24 — Actionable-intelligence engine live (peer-benchmarked $ findings)

**What changed:** New `GET /district/{id}/insights` + top-of-dashboard
"Actionable Intelligence" section. For each district it compares
operating/instruction/admin/facilities/debt per student and payroll/
contracted share against its SIMILARITY-GRAPH peers, fires only material
deviations (>20% AND >$100k/yr), quantifies each in $/year, ranks by
magnitude, returns top 6. Dashboard renders ranked cards ("<metric>: X%
above peers · $Y/year above peers") colored concern-vs-strength, framed as
review targets not verdicts. 32 tests green. Deployed + verified live:
Dallas debt 34% above = $128M/yr, admin 44% = $71.5M/yr; Houston admin 89%
= $181M/yr; San Antonio 4 findings.

**Why:** User asked for "actionable intelligence." This turns raw numbers
into decisions and is the app's most defensible feature — it leans on the
exogenous peer graph (the unique asset) to say "where you differ from
districts genuinely like you, in dollars."

**Gotchas:** admin = fct21+fct23+fct41_92 combined; large-district
deviations can be big and real but the copy hedges ("questions, not
verdicts"). Materiality floor (20% AND $100k) keeps tiny districts from
spamming findings; needs >=4 peers with data or returns empty. Endpoint
joins 3 views + district_similarity per request — fast enough (p95 <500ms).

**Open items:** unchanged — labeling fix (operating vs total per-student),
launch-hardening (rate limit, RO role, map a11y, analytics), rotate creds,
PR #2. Next data candidates researched: Urban Institute API (#1),
USAC E-rate (#2) — see prior turn; not yet ingested.

---

## 2026-07-24 — Tier-1 data enrichment (object + program dimensions) live + data roadmap

**What changed:** Surfaced two spending dimensions the summarized data
already carried but the dashboard never showed. New `v_spending_detail`
view (`sql/create_detail_view.sql`), `GET /district/{id}/spending-detail`,
two dashboard sections (object: payroll/contracted/supplies/other —
sums to operating total, 100% populated; program: regular/special-ed/
compensatory/bilingual/career-tech/gifted/athletics — 89-100%). Shared
`barChart()` renderer. `docs/DATA_ROADMAP.md` scopes Tier-2 (detailed
PEIMS function×object) and Tier-3 (vendor/check-register pilot — the only
path to real HVAC/technology numbers). 31 tests green; deployed + verified
(Dallas: 81% payroll, 12.3% special-ed).

**Why:** User asked whether HVAC/technology are inferable. Answer: no — the
summarized data's granularity ceiling is function+object+program, never a
named HVAC or total-tech line. Delivered the max the loaded data allows
(object+program) and documented the data layers needed to go deeper.

**Gotchas:** HVAC lives inside function 51 (plant maintenance & ops, also
utilities/custodial/repairs) — not separable without vendor data.
"Technology" is smeared across fct53 (IT-ops only), instruction devices,
capital, and E-rate — no single line. Program % overlaps object % (a
special-ed salary is both) — dashboard caption says so explicitly to avoid
double-count confusion. Rerun nothing extra; view is over base table.

**Open items:** unchanged — labeling fix (operating vs total per-student)
still recommended; launch-hardening list (rate limit, RO role, map a11y,
analytics); rotate creds; PR #2 review.

---

## 2026-07-24 — Multi-team audit + Monte Carlo robustness sim (scorecard)

**What changed:** Ran 5 parallel audit-team subagents (backend, data/graph
science, frontend/UX, security/ops, docs/business) + a quantitative Monte
Carlo (`scripts/monte_carlo_audit.py`, seed 20260724). Results in
`docs/AUDIT_SCORECARD.md` + `docs/monte_carlo_audit.json`. Scores (1-11):
backend 7, frontend 7, data-science 6, security 6, docs/business 5;
blended ~6.2.

**Why:** User asked to identify patterns/gaps/blindspots and score
everything with parallel teams. No fixes applied yet — this is assessment.

**Key findings (verified, not opinion):**
- 🔴 SECURITY: NLP path uses the privileged pooler role; RLS doesn't bind
  owners and include_tables only limits reflection → "read-only" is
  prompt-convention only, prompt-injection could mutate data. Documented
  mitigation SUPABASE_READONLY_URL does NOT exist in env_template.txt.
- 🔴 /query rate limit trusts spoofable X-Forwarded-For + per-instance →
  uncapped paid-OpenAI abuse (compounds unrotated-key item).
- MC corroborated: 38.4% archetype instability (k=6 silhouette 0.226 <
  k=4's 0.290); anomaly thresholds swing ±34% under ±5pp; local_tax 15.5%
  missing conflated by fillna(0); peers include rev/student (corr 0.65
  with spend) so "exogenous" claim is half-true.
- FRONTEND: map 100% broken on touch + keyboard + screen-reader (WCAG
  1.1.1/2.1.1 fail).
- DOC DRIFT (confirmed): CLAUDE.md says both 24 and 30 tests (real: 30);
  AUDIT.md still says 2008-2024; README lists 8 of 14 endpoints; blueprint
  docs (REPO_MAP etc.) stranded on unmerged PR #2 branch.

**Open items:** the 6 prioritized fixes in AUDIT_SCORECARD.md (top: RO DB
role for NLP; threadpool+timeout /query; map touch/a11y; instrument
analytics; re-select k; reconcile doc drift). Plus standing: rotate creds,
review PR #2. None applied yet — awaiting go.

---

## 2026-07-24 — 10x graph polish v2: archetypes + typicality centrality (live)

**What changed:** `scripts/graph_insights.py` now clusters districts into
6 archetypes (deterministic k-means, seed 0, on z-scored exogenous
features; named from median stats) and computes typicality = in-degree
centrality in the directed k-NN graph (0-100 percentile). Emitted per
node as `c`/`t` plus archetype metadata in `static/map_data.json`. Map
gains a "Color: spending / Color: archetype" toggle with a counted named
legend, and the selection panel shows archetype + typicality. Deployed +
verified live (6 archetypes, typicality spans 0-100).

**Why:** "Polish 10x" — the map positioned nodes but never revealed the
graph's structure. Archetypes turn 1,202 dots into a labeled taxonomy of
Texas district types; in-degree centrality gives a genuine "how typical
is this district" score (archetype vs structural outlier), distinct from
size.

**Gotchas:** k-means over-fragments if done as label-propagation
communities on mutual-kNN (got 31); k=6 k-means on the embedding is the
right grain for a *labeled* taxonomy. Archetype names come from median
enrollment/growth/local-share (interpretable, stable) not z-score
thresholds (which lumped everything "Mid-size"). Rerun graph_insights.py
after each TEA refresh.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-24 — 10x polish: interactive similarity map (edges, ego networks, zoom)

**What changed:** Rewrote `static/map.html` into a real graph
visualization. `scripts/graph_insights.py` now emits per-node neighbor
indices (top-6 from the committed edge list), canonicalized + bipolar-
labeled PCA axes, and a recent-flag layer into `static/map_data.json`.
Map features: ego-network edges drawn on hover/pin, click-to-pin
selection panel with clickable re-centering neighbor list, zoom
(scroll/pinch) + pan (drag), devicePixelRatio-aware retina rendering,
dollar-valued quintile legend, "Flagged only" layer (183 districts),
deep-link `/map?d=<district>`, dashboard button deep-links to current
district. 30 tests green; deployed + verified live.

**Why:** "Polish 10x" on the graph work. Prior map was a plain scatter
that hid the graph's edges, was blurry on high-DPI, and had unlabeled
axes (wasting PCA's interpretability). Axes now read as Texas-finance
spectrums: "leaner-funded ↔ bigger", "state-funded ↔ growing".

**Gotchas:** PCA sign is arbitrary — canonicalized (fix log_enroll
loading positive on PC1, growth5 positive on PC2) so the layout is
stable across rebuilds. Deploy payload must include static/map.html +
static/map_data.json. Rerun graph_insights.py after each TEA refresh.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-24 — Graph insight suite live: turnarounds, statewide map, co-occurrence

**What changed:** `scripts/graph_insights.py` (deterministic) produces:
PCA similarity-map coordinates (`static/map_data.json`, PC1+PC2 = 70%
variance), flag co-occurrence analysis, and temporal drift. New routes:
`/map` (explorable canvas map of all 1,202 districts — hover, search
highlight, click-through), `/map-data`, and
`GET /district/{id}/turnarounds` (graph walk finding peers that reversed
>=2-year deficits or >=3-year enrollment slides). Dashboard shows a
"Proof it's doable" section when peers have turnarounds, plus a State map
header link. Findings in `docs/GRAPH_INSIGHTS.md`. 30 tests green.
Deployed + verified live, including positive turnaround hits (South San
Antonio ISD enrollment reversal; Centerville ISD deficit reversal).

**Why:** Graph-lens roadmap items user approved with "Do it". Headline
analytical finding: revenue_drop + enrollment_decline co-occur at 6.1x
lift — enrollment decline is the leading indicator of fiscal stress.
Temporal drift shipped as analysis only (top movers are small-district
volatility; needs size-weighting to be a feature) — honest scope call.

**Gotchas:** Deploy payload must now include static/map.html and
static/map_data.json. Rerun graph_insights.py + build_similarity_graph.py
after each TEA refresh.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-23 — Peer comparison upgraded to a district similarity graph (live)

**What changed:** New k-NN similarity graph (1,202 nodes, k=12, 14,424
edges) built by `scripts/build_similarity_graph.py`; edges committed at
`docs/similarity_edges.csv` and loaded into new `district_similarity`
table (`sql/create_similarity_table.sql`). `GET /district/{id}/peers` now
walks the graph (fallback: enrollment window; response has `basis`
field). Deployed + verified live: Dallas peers = Houston, Austin,
Northside, Frisco, Plano.

**Why (the graph-engineering insight):** peers must be matched on
EXOGENOUS features (log enrollment, 5-yr growth, revenue/student,
local-tax share) — never on outcome metrics like spending, or the
benchmark becomes circular ("districts that spend like you spend like
you"). Enrollment-only matching missed funding structure; the graph
captures it.

**Gotchas:** rebuild + reload the graph after each annual TEA refresh
(documented in script + SQL comments). PostgREST upsert used
`Prefer: resolution=merge-duplicates` so reloads are idempotent.

**Open items:** credential rotation (user), review draft PR #2.

---

## 2026-07-23 — PR #1 merged to master

**What changed:** Merged PR #1 (all audit + launch + dashboard work) into
`master` with a merge commit to preserve the commit history. Work branch
restarts from master per protocol.

**Why:** master previously showed pre-audit code to repo visitors.

**Open items:** credential rotation (user-side) remains the only red item.

---

## 2026-07-23 — A+ pass: all report-card gaps closed; white-minimalist McKinsey/SWD redesign live

**What changed:** New `v_spending_breakdown` view (TEA function codes → 9
MECE categories) + `GET /district/{id}/breakdown`; anomaly cards show
before/after numbers; side-by-side district compare (orange series); PNG +
CSV export on every chart; per-section TEA citations; enrollment
multi-year-decline callout; in-app rate limit on /query (10/min/IP,
QUERY_RATE_LIMIT env). UI v3: pure white minimalism, McKinsey action
titles computed live from data, auto-generated executive summary (pyramid
principle), SWD gray-context/blue-focus charts, direct end labels, tables
behind disclosure toggles. 29 tests green. Deployed and verified live
(Dallas breakdown: 55% classroom instruction).

**Why:** User asked for A+ vs the demand-weighted report card and a
McKinsey/storytelling-with-data white design. Demand-weighted grade moved
≈3.5 → ≈3.96/4.0.

**Gotchas:** Rate limiter is per-serverless-instance (documented in code) —
CDN/WAF still recommended for a hard global cap. Light-only theme is a
deliberate user-pinned choice (white background), replacing the earlier
dark-mode support.

**Open items:** rotation + PR #1 merge still user-side; those two are what
separates product A from A+.

**Notes:**

---

## 2026-07-23 — Dashboard redesign driven by Monte Carlo user simulation; deployed live

**What changed:** Simulated 1,000 Texas school admins against the real
district population (`scripts/simulate_admin_usage.py`, seed 42 —
reproducible; results in `docs/simulation_results.json`). Findings drove a
full UI rebuild (`static/index.html`): KPI tiles with plain-English
captions, trend chart vs statewide median with metric tabs, similar-size
peer comparison, spending breakdown, per-district anomaly explainer cards,
guided first-run tutorial, disclaimer modal/footer, print + CSV export.
New endpoints: `GET /district/{id}/peers`, `GET /benchmarks`,
`district_number` filter on `/anomalies` (SQL validated on live DB via
management API before shipping). Docs: `docs/UX_RESEARCH.md`,
`docs/TUTORIAL.md`. 27 tests green. Deployed to Vercel production and
verified live (peers for Dallas: Cy-Fair/Houston/Northside/Katy, 70th
percentile, 2025 statewide median $19,314/student).

**Why:** User mandate: build what admins want, not what we want. The
simulation showed the old UI led with the LOWEST-demand feature (freeform
NLP, 2.3%) and had zero support for the top four demands (peer comparison
16.1%, trends 13.8%, board-ready output 11.5%, statewide context 10.6%).
Page order now mirrors the demand ranking.

**Gotchas:**
- Deploys still go through the Vercel REST API with the user-supplied PAT
  (re-staged temporarily from conversation, shredded after). Deploy payload
  swaps `requirements-vercel.txt` in as requirements.txt (comments
  stripped).
- Persona/task priors are modeled assumptions, documented honestly in
  UX_RESEARCH.md — replace with real analytics/interviews when available.

**Open items:** unchanged (rotation, rate limit, PR #1 merge) — see
CLAUDE.md status.

**Notes:**

---

## 2026-07-22 — Memory system created (/ariba skill, CLAUDE.md, this log)

**What changed:** Added `.claude/skills/ariba/SKILL.md` (catch-up / save /
note modes), `CLAUDE.md` boot file, and this log, seeded with the project's
full history below. All committed to `claude/audit-public-launch-ocd7ra`.

**Why:** Agent sessions are ephemeral containers with zero memory. The repo
is the only durable store, so project memory must be committed files that
every future session auto-loads (CLAUDE.md) or is instructed to read
(/ariba). Design principle: log decisions WITH rationale, verify live state
before trusting notes, never store secrets.

**Open items:** see Current Status block in CLAUDE.md.

**Notes:**

---

## 2026-07-22 — WENT LIVE: Supabase provisioned, TEA data loaded, Vercel production deploy, PR #1 opened

**What changed:**
- Created Supabase project `texas-isd-finances` (ref `zwhvabkvrexphlskubog`,
  us-east-1, org "GOAT-UIX") via Management API using the user's PAT.
- Downloaded TEA's current "Summarized PEIMS Actual Financial Data" release
  directly from tea.texas.gov (`/media/423296`, ~19 MB, sheet `DATAMART`) —
  fresher than the project ever had: fiscal 2009–2025.
- Ran `scripts/prepare_data.py` → 20,587 rows × 140 cols; loaded via
  PostgREST in 1,000-row batches (direct Postgres is blocked in the dev
  container — HTTPS only); applied `sql/create_tables.sql` via Management
  API query endpoint.
- Deployed to Vercel (project `texas-isd-finances`, account `tag-ai`) with
  env vars `SUPABASE_DB_URL` (transaction pooler, port 6543) and
  `OPENAI_API_KEY`. Live: https://txisd.dev
- Opened PR #1 (audit branch → master).
- Shredded all locally staged credentials after deploy.

**Why key decisions went the way they did:**
- Transaction pooler (6543) for serverless; asyncpg needs
  `statement_cache_size=0` with it (added in `src/api.py`).
- Vercel deploy uses `requirements-vercel.txt` (full API incl. NLP, minus
  pandas/matplotlib/etc.) to stay under the 500 MB bundle cap. NLP works in
  production — verified with a real Dallas ISD question.
- Restructured `sql/create_tables.sql` to run AFTER import: the old static
  CREATE TABLE defined only 21 of 140 real columns, so the documented
  schema-first order could never import.

**Gotchas (each cost real time — don't rediscover):**
- Live testing caught bugs static review missed: (1) pandas re-reading the
  clean CSV stripped leading zeros from district IDs — fixed in DB with
  `LPAD(...,6,'0')` and in `import_to_supabase.py` with
  `dtype={"district_number": str}`; (2) `/anomalies?year=X` returned
  unflagged rows — flag condition now always applied; (3) the real TEA
  column is `all_funds_instruction_transfer_expend_fct11_95`, not the
  invented `all_funds_instruction_expend`.
- The dev container cannot open raw TCP to Postgres; use Supabase
  Management API (`POST /v1/projects/{ref}/database/query`) for SQL and
  PostgREST (service_role key, `Prefer: return=minimal`) for bulk inserts.

**Open items:** credential rotation (user-side), `/query` rate limit,
merge PR #1, Supabase free-tier idle-pause watch.

---

## 2026-07-22 — Audit round 2: everything validated against current provider docs

**What changed:** Rewrote `src/nlp_engine.py` on LangChain 1.x
`create_agent` (pinned `langchain>=1.0,<2.0`); fixed `env_template.txt` to
lead with the Supabase session-pooler string; fixed `vercel.json`
(`excludeFiles`, not the unsupported `includeFiles`); removed dead Pydantic
models; added `tests/test_nlp_engine.py` (constructs the real agent against
SQLite so LangChain API drift fails CI); added `PROJECT_MAP.md`.

**Why:** User mandate: assume nothing, validate every assumption against
current docs. It paid off — three latent production-killers found.

**Gotchas:**
- `create_sql_agent` no longer exists in langchain 1.x — `/query` was dead
  on any fresh install and round-1 tests had masked it by not importing the
  module. Lesson: every module needs at least an import/construction test.
- Supabase direct host (`db.<ref>.supabase.co`) is IPv6-only without a paid
  add-on; Render/Railway/Vercel egress IPv4 → always use the pooler.
- `langchain-community` sunset June 2026 (still works; watch issue #674).
- SQLite dialect lacks materialized-view reflection → NLP engine takes an
  injected `SQLDatabase` in tests; Postgres path uses `view_support=True`.
- Git-history secret scan: no full secrets, but old Supabase project ref
  `emtwbizmorqwhboebgzw` visible in deleted internal docs → rotate that
  project's creds if still live.

---

## 2026-06-01 → 2026-07-19 — Audit round 1 and launch prep (branch created)

**What changed:** On branch `claude/audit-public-launch-ocd7ra`: fixed
broken relative import (app could never boot via documented command); made
NLP engine lazy so the app boots without credentials (data endpoints 503
cleanly, /health reports "degraded"); fixed CORS (wildcard+credentials
invalid), Plotly `update_xaxes`/`update_yaxes`, scatter trendline, SQL
column interpolation; enabled the RLS the README promised; migrated to
lifespan handler. Added `static/index.html` public portal, pytest suite,
enforcing CI, `Dockerfile`, `render.yaml`, `api/index.py`, `DEPLOYMENT.md`,
`AUDIT.md`. Earlier commits (pre-audit) sanitized credentials and added
LICENSE/CONTRIBUTING/SECURITY.

**Why:** Repo was a prototype: nothing had ever actually run end-to-end.
Goal was public-launch readiness with graceful degradation so deploy could
precede credential wiring.

**Gotchas:** CI previously used `ruff --exit-zero` (never fails) and a
"type check" that only printed a version — green CI proved nothing.

## 2026-08-11 (late) — The outreach machine: gift-first email per district

**Goal (user's words, condensed):** introduce TAG ai to every superintendent by
*giving* them their district's report — insights first, pitch second — with a
system that mass-sends personalised emails via the Resend API the moment the
user says go.

- `scripts/build_outreach_merge.py` now adds three insight columns per district
  (`insight_bonds`, `insight_debt`, `insight_trend`), drawn from the SAME
  committed artefacts the site serves (bond_data, debt_data, trend_data) — an
  email can never disagree with the page it links to. Coverage: 1,019/1,019
  bonds+debt, 1,018 trends. Greetings fixed: published honorific or
  "Superintendent {surname}", never a guessed Mr./Ms.
- `scripts/send_outreach.py` — renderer + Resend sender. Safe by default:
  bare run = dry run writing previews to `data/outreach_preview/`; `--test
  EMAIL` sends 2 samples to yourself; `--send` requires `--confirm GO` AND
  RESEND_API_KEY AND a Resend-verified sending domain (checked via /domains
  before message one) AND TAG_POSTAL_ADDRESS (CAN-SPAM). Sent log
  `data/outreach_sent.csv` makes re-runs idempotent; `data/outreach_optout.txt`
  honoured; List-Unsubscribe header + visible unsubscribe; ~1 msg/s throttle.
  All outreach files gitignored.
- Email content: "We built {district}'s report. It's yours." → greeting → 3
  insights → frame-honest hook → deep-link button → who TAG ai is → hosted
  pipeline graphic → reply-to-book-a-call → corrections invited → footer
  (source disclosure incl. where we got their address, postal, unsubscribe).
- Site: `static/tag_pipeline.png` (TAG intelligence-layer graphic, Texas ISD
  edition) served at `/static/tag-pipeline.png` — one-asset-one-route like
  design.css, hot-linked by the emails.
- `tests/test_outreach.py` (12): frame rules travel into the inbox (all-funds
  never without operating at ≥20% share, debt named as stock, absences as
  absences, state line beside district trend), CAN-SPAM bits present,
  "deficit" never appears, graphic route exists.
- Theme policy test updated: light default for everyone (owner request);
  `prefers-color-scheme` must NOT appear in index.html.

**To actually send:** user needs a Resend account + API key, DNS-verify the
sending domain (txisd.dev or a tagai domain) in Resend, set RESEND_FROM +
TAG_POSTAL_ADDRESS, then `--test` → pilot `--limit 50` → full send. Vercel
Hobby→Pro upgrade still recommended first (commercial traffic).

## 2026-08-12 — Parallel-agent wave: watchdogs, durability, distribution; plus the 10x metadata edge function

Four single-responsibility agents (Sentinel/Archivist/Broadcaster/Custodian)
built in parallel on disjoint files; integrated, 648 tests green, deployed.
Full detail in CLAUDE.md's 2026-08-12 snapshot. Highlights and traps:

- **Per-district head injection** (`src/og.py`) is the growth unlock: every
  /?d= URL previously served byte-identical HTML (homepage canonical!), so
  nothing could rank and every share previewed generic. Cards/meta lead with
  the OPERATING figure — economics `total_per_student` EXCLUDES construction
  and does NOT match the DB view's all-funds figure; reproducing all-funds
  from artefacts prints a number that contradicts the page ($15,509 vs
  $31,704 for Argyle). test_og.py bans it.
- **.vercelignore negation trap**: `!static/share/` does not re-include files
  excluded by `*.png` — you must negate the FILES (`!static/share/*.png`).
  And the Vercel CLI does not reliably upload gitignored files at all; the
  cards are committed.
- **Sentinel's first run exited 1 on purpose**: STAAR SY2026, recapture
  2026-27 and TIGER2025 are already published upstream. The daily nag is the
  design; acknowledge by bumping scripts/freshness_vintages.json with a note.
- **Sandbox egress policy blocks GitHub release creation** (reported, not
  worked around): the raw-data tarball awaits one command from a normal
  machine; the SHA manifest is committed so the vintage survives regardless.
- **Masthead rollout lessons**: shared-CSS changes need cache-busting
  (?v=N — design.css is cached 1h, the new header rendered unstyled);
  retiring old brand rows orphaned /map and /intel (zero inbound links) —
  found by a rendered link-graph audit, fixed with the More menu; canvas
  fillText paints raw `<svg>` markup as text (old emoji-migration leftovers).
- **Resend + Supabase Management APIs both 403 bare urllib via Cloudflare
  (error 1010)** — it is a User-Agent block, never an auth failure; send a
  UA or use curl.
