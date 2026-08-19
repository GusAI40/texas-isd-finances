# ISD Daily Intelligence — Operational Hardening

## Outcome

The daily `/api/cron/isd-intelligence` job now treats durable storage as part of
success, not as a best-effort side effect.

A successful run means all of the following are true:

1. the day's briefing was inserted into `public.isd_briefings`;
2. every human-review item was inserted into `public.isd_review_queue`;
3. both sets of writes committed in one Postgres transaction; and
4. `public.cron_runs` reports the number of durable rows written.

If any briefing/review write fails, the transaction rolls back and the endpoint
returns HTTP 503. It must never return HTTP 200 with `stored: false`.

## Why Postgres is the queue here

The repository already has the required durable primitive:

- `isd_briefings.run_date` is the one-run-per-UTC-day key.
- `isd_review_queue.run_date` references that briefing.
- `(run_date, content_hash)` is unique in the review queue.

That is enough for this workflow. Adding a message-queue product, webhook, or
edge worker would create more failure surfaces without improving the daily job's
correctness.

## Concurrency contract

The handler first performs a cheap same-day lookup so a normal Vercel retry does
not repeat network or optional LLM work.

That lookup is only an optimization. The actual race guard is the transaction's
briefing insert:

```sql
INSERT INTO public.isd_briefings (run_date, payload)
VALUES ($1, $2)
ON CONFLICT (run_date) DO NOTHING;
```

If two serverless instances both pass the lookup, the first committed insert
wins. The other returns `already_ran` and never writes duplicate review rows.

## Failure policy

| Condition | HTTP | Cron status | Research starts? |
|---|---:|---|---|
| CRON_SECRET missing | 503 | none | no |
| Wrong bearer token | 401 | none | no |
| Database unavailable | 503 | none | no |
| Idempotency preflight cannot read DB | 503 | error | no |
| Today's run already exists | 200 | skipped | no |
| Research raises | 500 | error | yes |
| Briefing/review transaction fails | 503 | error | yes |
| Concurrent run committed first | 200 | skipped | yes |
| Briefing + review queue committed | 200 | ok | yes |

## Required schema

The runtime expects the tables from `sql/create_isd_intel.sql` and the cron-run
telemetry table from `sql/create_cron_runs.sql`.

Do **not** assume schema presence from a successful build. Before a production
rollout, verify that both tables exist in the target database and that the app's
owner connection can write them. No migration is applied automatically by this
change.

## Verification

Run the focused regression suite:

```bash
pytest -q tests/test_isd_cron_runtime.py
```

Then run the full repository suite before merge.

Preview smoke test, with a non-production database and the preview cron secret:

```bash
curl -i -H "Authorization: Bearer $CRON_SECRET" \
  https://<preview-host>/api/cron/isd-intelligence
```

Expected first-run response:

```json
{
  "status": "ok",
  "stored": true,
  "review_queued": 0,
  "rows_written": 1
}
```

`review_queued` may be greater than zero. In that case `rows_written` must equal
`1 + review_queued`.

A second call on the same UTC day must return `already_ran` and must not add a
second briefing or duplicate review rows.

Finally inspect:

```text
GET /api/cron/runs?job=isd-intelligence
GET /briefing
```

The latest cron row should be `ok` for the committed run, and `/briefing` should
serve that same day's stored payload.

## Deployment boundary

This change does not merge itself, deploy itself, apply database DDL, enable
outbound sending, or enable LLM enrichment. Those remain explicit operator
choices.
