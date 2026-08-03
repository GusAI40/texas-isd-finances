# Texas ISD Intelligence — daily research system

A daily job that reads Texas school-district news, ties each item to the right
district, compares it against the data this repo already holds, and produces a
briefing that says *what changed, which district, why it matters, and whether it
agrees with our numbers* — not a pile of links.

This document is deliberately honest about what is built and what is not. The
master spec that inspired it describes a full production platform (durable
queues, notifications, a review UI, entity graphs, twenty deliverables). What
ships here is the **spine**, built end to end and tested, so the idea is proven
before any of that scale is added.

## What's built (and tested)

```
Vercel Cron (daily, 11:00 UTC)
   → GET /api/cron/isd-intelligence   (CRON_SECRET auth, idempotent by date)
       → fetch news         Google News RSS, keyless, per priority district
       → resolve district   full-name match; refuses bare acronyms
       → categorize          rule-based keyword taxonomy
       → compare             against committed bond + enrollment data
       → score               confidence / impact / urgency, factors kept
       → build briefing      ranked findings + a human-review queue
       → store               upsert into public.isd_briefings
   → GET /briefing           serves the latest (DB, or committed snapshot)
   → GET /intel              renders it
```

- **`scripts/isd_intel.py`** — the whole pipeline as importable, offline-runnable
  functions. `python scripts/isd_intel.py --demo` runs it against fixtures with
  no network, no keys, no database.
- **`GET /api/cron/isd-intelligence`** — the daily trigger. Refuses to run
  without `CRON_SECRET`; rejects a wrong or missing bearer; idempotent by UTC
  date, so a replay returns the stored run instead of spending again.
- **`GET /briefing`** — the latest briefing, from the DB when configured, else
  from `static/isd_briefing.json` so it works at Tier 1 (no database).
- **`GET /intel`** — the rendered page.
- **`sql/create_isd_intel.sql`** — `isd_briefings` + `isd_review_queue`, locked
  down (no access for `anon`, `authenticated`, or `nlp_reader`).
- **30 tests** in `tests/test_isd_intel.py` and `tests/test_api.py`.

## The three properties that make it safe, not just working

1. **An acronym never resolves a district on its own.** "AISD" matches 39 real
   districts; "BISD" matches 64. The resolver requires the district's full name
   as a phrase, prefers the longest match, and routes anything weak to review
   rather than guessing. A test asserts "AISD superintendent resigns" stays
   *unresolved*.
2. **A conflict is surfaced, never applied.** When an article's enrollment
   figure is more than 10% from our TEA number, the finding is a
   `contradiction`, flagged for review, with both numbers shown. Nothing
   overwrites stored data — this whole repo's discipline.
3. **Fetched pages are untrusted input.** The default extraction is rule-based,
   so an article containing "ignore all previous instructions" is just text. A
   test injects exactly that and asserts it changes nothing.

## The comparison is real because the data is real

This isn't a news reader with a "compare" label bolted on. It compares against
what the site actually ships:

- **Enrollment** — an article's student count vs `outcomes_data.json`. Agreement
  → `confirmed`; a >10% gap → `contradiction`.
- **Bonds** — bond news for a district with history in `bond_data.json` →
  `expanded`; for one with none → `new`.
- Everything else → `not_applicable`, honestly, rather than invented certainty.

## Source tiering — official vs newsroom vs discovery

The tier is derived from the **publisher domain**, not the query, so "official"
means official:

- **Tier 1 (official)** — `tea.texas.gov`, `*.texas.gov`, `*.tx.us`,
  `*.k12.tx.us`. The registry includes a `site:tea.texas.gov` query, and any
  district's own `.tx.us` site resolves here automatically.
- **Tier 2 (newsroom)** — a maintained list of Texas newsrooms (Tribune,
  Star-Telegram, Houston Chronicle, KUT, …).
- **Tier 3 (discovery)** — everything else; surfaced but labeled unverified.

Google News hides the real host in each item's `<source url>` attribute (the
visible link is a `news.google.com` redirect), so the parser tiers on that —
otherwise everything would mis-tier as discovery. `build_queries()` produces
statewide queries plus five per priority district (name, finance, governance,
facilities/enrollment, and an agenda/press-release query).

## LLM enrichment — off by default, bounded when on, injection-isolated always

The rule-based path reads headlines; the LLM adds what it can't — a bond
**amount**, an **effective date**, whether a plan is *proposed* or *approved*.
It is `extract_with_llm(item, client, budget)`, and three things make it safe:

1. **A hard call budget per run** (`LlmBudget`). The client is asked only while
   budget remains; `ISD_LLM_MAX_CALLS` (default 25) caps it. A bad day cannot
   become a large bill — the same discipline as the `/query` ceiling. Enrichment
   is also spent only on **resolved** findings, never on noise.
2. **The snippet is untrusted DATA.** It goes inside `<<<SOURCE_SNIPPET>>>`
   delimiters, the system prompt says text within is never a command, and the
   output is a fixed JSON schema that is validated (retry once, then null). A
   headline that says "mark this urgent" cannot move a score, because the model
   cannot emit one. A test asserts the delimiter and the untrusted-data
   instruction are both present.
3. **Best-effort, never blocking.** Budget spent, call failed, or output
   invalid → `None`, and the run continues on rule-based data.

Turn it on: `ISD_LLM_EXTRACT=1` **and** `OPENAI_API_KEY` set. The `client` is
injected (`make_openai_client`), so the pipeline is provider-agnostic and the
tests run offline with a fake client — the LLM path is **not** verified against
a live model here.

## Cost and safety, on purpose

- **$0 by default.** Rule-based extraction over RSS titles needs no LLM, and
  enrichment is off unless explicitly enabled and capped.
- **No new secret.** Google News RSS is keyless.
- **Priority districts, not all 1,200.** `ISD_PRIORITY_DISTRICTS` and
  `ISD_MAX_QUERIES` bound each run. Default watch set: Beaumont, Fort Worth,
  Lake Worth, Connally, Houston.
- **Idempotent.** One briefing per UTC day; a replay is free.

## The heatmap (`/heatmap`)

A Mapbox choropleth of all ~1,005 districts with a toggle: **News intensity**
(count × impact of the day's findings, so a district with a takeover
announcement lights up) or the outcome layers (turnover / spending / poverty).

- **The public `pk.` token only**, served from `MAPBOX_TOKEN` via
  `/mapbox-token` — never committed, so it rotates without a code change. The
  secret `sk.` token is never used and a test fails CI if one is ever committed.
- **Mapbox is loaded only when a token is present.** With none, the page shows
  a configure-me message and the district **table twin** still works — and it
  makes zero external calls, verified.
- **CSP is widened to Mapbox's hosts for `/heatmap` alone**; every other page,
  including the privacy-preserving `/geomap`, keeps the strict self-only policy.
- **`/geomap` is unchanged** — the no-external-calls map still exists for anyone
  who wants it. `/heatmap` loads tiles from Mapbox; device location, if used, is
  still resolved in the browser and sent nowhere.

Verified here: token endpoint, CSP scoping, the no-token path, the toggle and
legend, and the table twin. **Not** verified here: the live Mapbox tile render —
external tiles are blocked in the build sandbox, so confirm it in a browser once
`MAPBOX_TOKEN` is set.

## Deploying it

1. Apply `sql/create_isd_intel.sql` to Supabase (creates the two tables).
2. Set `CRON_SECRET` in the Vercel project — Vercel auto-injects it as the
   cron's bearer token. Generate a strong one (`openssl rand -base64 32`).
3. `vercel.json` already declares the schedule (`0 11 * * *` = 11:00 UTC ≈
   5–6am Central). **Note:** Vercel Hobby allows only once-daily crons; this
   project's Pro team is fine. And production deploys from a working tree, not
   `master`, so the cron only exists after a fresh `vercel deploy --prod`.
4. For the heatmap, set `MAPBOX_TOKEN` to your **public** `pk.` token.
5. Optional: tune `ISD_PRIORITY_DISTRICTS`, `ISD_MAX_QUERIES`, `ISD_LLM_EXTRACT`.

Trigger a run by hand to verify:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://txisd.dev/api/cron/isd-intelligence
```

## What is deliberately NOT built yet

Naming these so nobody mistakes the slice for the platform:

- **Source breadth.** TEA's newsroom is read **first-hand** (`fetch_tea_newsroom`,
  tier-1) so a takeover or board-of-managers appointment is seen the day TEA
  posts it — verified against the real page, which currently carries the
  Beaumont / Fort Worth / Lake Worth / Connally appointments. Plus Google News
  for breadth, domain-tiered. A generic `fetch_rss_feed` adapter is ready for
  any district/ESC that publishes a real feed. Board-agenda portals (BoardBook,
  Diligent) are the next adapters. Note: TEA's *advertised* RSS feed
  (`/rssfeeds/news_rss.aspx`) is dead — verified 2026, the site moved to Drupal
  — so the newsroom adapter parses HTML and its selector may need updating if
  TEA changes markup; the `site:tea.texas.gov` Google query is the fallback.
- **LLM extraction** is wired, bounded, and injection-isolated — but off by
  default and not yet verified against a live model (tests use a fake client).
- **Notifications, a review *UI*, per-user relevance lenses, an events history
  table, durable queues.** The spec asks for all of these; none are needed to
  prove the spine, and each adds real cost or infrastructure.
- **Live verification.** The pipeline is tested against fixtures. It has not run
  against live feeds from inside the deploy, because that needs the deployed
  `CRON_SECRET` and database. Do not treat it as production-verified until it
  has run there once and the briefing looks right.

## Honest production-readiness (1–5)

| Dimension | Score | Why |
|---|---|---|
| Security | 4 | Cron authed + idempotent; tables locked down; injection-resistant by design. Not yet pen-tested live. |
| Data integrity | 4 | Never overwrites; conflicts surfaced; every claim keeps its source. |
| Accuracy | 3 | Resolution and comparison sound and tested; LLM enrichment wired for nuance but off by default and not live-verified. |
| Reliability | 3 | Idempotent, fails soft per-feed. One serverless request per day; heavy fan-out would need a queue. |
| Scalability | 2 | Priority-district + call-budget design bounds it deliberately; statewide daily coverage needs batching. |
| Clarity | 4 | The briefing leads with what-changed / why / our-data / source. |
| Observability | 2 | Run status returned; no metrics dashboard yet. |

Not production-verified until it has run once against live feeds in the deploy.
