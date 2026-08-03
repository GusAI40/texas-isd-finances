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
- **19 tests** in `tests/test_isd_intel.py` and `tests/test_api.py`.

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

## Cost and safety, on purpose

- **$0 by default.** Rule-based extraction over RSS titles needs no LLM. We just
  spent real effort bounding `/query`'s OpenAI spend; a 1,200-district LLM
  fan-out would undo that. An `extract_with_llm` hook exists as a seam but is
  off, and the code says how to switch it on responsibly (per-run token budget +
  injection isolation).
- **No new secret.** Google News RSS is keyless.
- **Priority districts, not all 1,200.** `ISD_PRIORITY_QUERIES` and
  `ISD_MAX_QUERIES` bound each run. Default: statewide + the takeover-watch set
  (Beaumont, Fort Worth, Lake Worth, Connally, Houston).
- **Idempotent.** One briefing per UTC day; a replay is free.

## Deploying it

1. Apply `sql/create_isd_intel.sql` to Supabase (creates the two tables).
2. Set `CRON_SECRET` in the Vercel project — Vercel auto-injects it as the
   cron's bearer token. Generate a strong one (`openssl rand -base64 32`).
3. `vercel.json` already declares the schedule (`0 11 * * *` = 11:00 UTC ≈
   5–6am Central). **Note:** Vercel Hobby allows only once-daily crons; this
   project's Pro team is fine. And production deploys from a working tree, not
   `master`, so the cron only exists after a fresh `vercel deploy --prod`.
4. Optional: tune `ISD_PRIORITY_QUERIES`, `ISD_MAX_QUERIES`.

Trigger a run by hand to verify:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://txisd.dev/api/cron/isd-intelligence
```

## What is deliberately NOT built yet

Naming these so nobody mistakes the slice for the platform:

- **Source breadth.** Only Google News RSS today. TEA feeds, board-agenda
  scraping, and official district sites are the next adapters (the code has a
  clean seam for them).
- **LLM extraction.** The rule-based path handles headlines well; nuanced
  facts (a bond *amount*, an *effective date*) need the LLM hook wired with a
  budget.
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
| Accuracy | 3 | Resolution and comparison are sound and tested; rule-based extraction misses nuance an LLM would catch. |
| Reliability | 3 | Idempotent, fails soft per-feed. One serverless request per day; heavy fan-out would need a queue. |
| Scalability | 2 | Priority-district design bounds it deliberately; statewide daily coverage needs batching. |
| Clarity | 4 | The briefing leads with what-changed / why / our-data / source. |
| Observability | 2 | Run status returned; no metrics dashboard yet. |

Not production-verified until it has run once against live feeds in the deploy.
