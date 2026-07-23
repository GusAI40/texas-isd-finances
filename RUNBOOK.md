# Runbook — Operating the Live System

For architecture see [ARCHITECTURE.md](ARCHITECTURE.md); for first-time
deployment see [DEPLOYMENT.md](DEPLOYMENT.md).

## Daily health check (30 seconds)

```bash
curl -s https://texas-isd-finances.vercel.app/health
# expect: {"status":"healthy","database":"connected"}
curl -s https://texas-isd-finances.vercel.app/stats
# expect: 1310 districts, 20587 records, 2009-2025
```

## Incident: portal shows "database not connected" / health says degraded

**Most likely cause (free tier):** Supabase pauses projects after ~7 days
of inactivity.
1. Log in at https://app.supabase.com → project `texas-isd-finances`.
2. If paused, click **Restore/Resume**. Recovery takes ~1–2 minutes.
3. Re-check `/health`.

**If not paused:** check Vercel env var `SUPABASE_DB_URL` still uses the
**transaction pooler** format (`...pooler.supabase.com:6543`). The direct
host will never work from Vercel (IPv6-only). If the DB password was
rotated, update this var and redeploy.

## Incident: /query returns 503

`OPENAI_API_KEY` missing/invalid in Vercel env, or the NLP engine failed
to init. Fix the key in Vercel → Settings → Environment Variables →
redeploy. Everything except `/query` works without it by design.

## Incident: /query returns 429 for legitimate users

Rate limit is 10/min/IP (`QUERY_RATE_LIMIT` env). Raise it in Vercel env
and redeploy, or add a CDN/WAF tier for smarter limiting.

## Routine: annual data refresh (when TEA publishes a new year)

1. Download the new "Summarized PEIMS Actual Financial Data" Excel from
   https://tea.texas.gov/finance-and-grants/state-funding/state-funding-reports-and-data/peims-financial-data-downloads
2. `python scripts/prepare_data.py` (point it at the new file)
3. Truncate and reload, or load only new years — then
   `python scripts/import_to_supabase.py`
4. Re-run `sql/create_tables.sql` and `sql/create_breakdown_view.sql`
5. `REFRESH MATERIALIZED VIEW v_anomaly_flags;`
6. Update `DATA_MAX_YEAR` env (and defaults in `src/api.py`), the year
   ranges in docs, and redeploy.
7. Verify: `/stats` shows the new end year; spot-check one district.

## Routine: deploy a code change

```bash
ruff check . && python -m pytest -q     # must be green
git push                                 # CI must be green
```
Then deploy to Vercel (API deploy swaps `requirements-vercel.txt` in as
requirements.txt — see DEPLOYMENT.md Option C). Verify `/health` and one
data endpoint after every deploy.

## Routine: credential rotation

1. Rotate in the provider dashboard (Supabase DB password / OpenAI key).
2. Update the matching Vercel env var.
3. Redeploy; verify `/health` (DB) and `/query` (OpenAI).

## Known gaps (accepted risks, tracked in REPO_MAP inventory)

- No automated uptime monitoring or alerting — checks are manual.
- No usage analytics.
- Rate limiting is per-serverless-instance, not global.
- Data refresh is manual (acceptable: source updates ~once a year).
