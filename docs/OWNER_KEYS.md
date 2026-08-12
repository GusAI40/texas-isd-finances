# OWNER KEYS — what only you can turn

Everything the system needs that no agent, cron, or test can do for you.
Each item says **what it is, why it matters, and the exact steps**. Work top
to bottom; the first section is the only urgent one.

No secret values appear in this file. Never add any.

---

## 1. 🔴 ROTATE SEVEN CREDENTIALS (urgent — pasted into chat)

Seven live credentials were pasted into chat sessions (2026-07-22 → 2026-08-12)
and must be treated as exposed. Chat transcripts are not a secret store.
Rotating means: **generate a new value → update where it's used → revoke the old one.**

| # | Credential | Rotate here | Then update |
|---|---|---|---|
| 1 | Vercel personal access token (`vcp_…`) | https://vercel.com/account/tokens → delete the old, create new | Anywhere you deploy from (`VERCEL_TOKEN=…`), and the `VERCEL_TOKEN` GitHub Actions secret if you set it up (§7) |
| 2 | Supabase personal access token (`sbp_…`) | https://supabase.com/dashboard/account/tokens | `SUPABASE_PAT` wherever you run `sync_outreach_state.py` / `apply` scripts |
| 3 | GitHub personal access token (`ghp_…`) | https://github.com/settings/tokens → revoke, regenerate | Wherever you run `archive_raw_data.py` (§4) |
| 4 | DeepSeek API key (`sk-…`) | https://platform.deepseek.com/api_keys | Vercel env var `DEEPSEEK_API_KEY` (see below), then redeploy |
| 5 | tryopendata key (`od_live_…`) | https://tryopendata.ai account settings | Nowhere — used read-only in one session, never stored |
| 6 | Resend API key (`re_…`) | https://resend.com/api-keys → revoke, create new | Vercel env var `RESEND_API_KEY`, and your local env when sending outreach (§5) |
| 7 | `GITHUB_TOKEN` that was present in the dev container's shell env | Same as #3 if it's a PAT you own; if it was injected by the platform it expires on its own | — |

**Updating a Vercel env var** (the portal reads secrets ONLY from here):

1. https://vercel.com/tag-ai-projects/texas-isd-finances/settings/environment-variables
2. Edit the variable → paste the new value → Save (keep "Sensitive" checked).
3. Redeploy so running functions pick it up: from the repo,
   `VERCEL_TOKEN=<new token> vercel --prod --yes --scope tag-ai-projects`
   (or press "Redeploy" on the latest Production deployment in the dashboard).
4. Verify: `curl -s https://txisd.dev/health` → `"status":"healthy"`, and the
   `llm` field still names the provider you expect.

---

## 2. 💵 SET A DEEPSEEK MONTHLY SPEND CAP

The `/query` endpoint has a per-minute and per-day **call** ceiling enforced in
the database, but calls are not dollars. Set a hard monthly cap at the
provider so a surprise can never exceed a number you chose:
https://platform.deepseek.com → Billing → usage limit. Pick a number you'd
be comfortable losing entirely (e.g. $10–20/mo covers current traffic ~100×).

---

## 3. 📈 UPGRADE PLANS BEFORE PURSUING REVENUE

Two free tiers carry the site today; both have terms or failure modes that
bite a commercial project:

- **Vercel Hobby → Pro** — Hobby is licensed for non-commercial use. The
  moment TAG ai pitches this commercially, upgrade:
  https://vercel.com/tag-ai-projects/~/settings/billing. Commits must be
  authored by a seat holder or deploys return `BLOCKED` (this is documented
  in CLAUDE.md; keep `git config user.email` on the repo owner).
- **Supabase free tier pauses after ~7 days idle** — the portal survives it
  (every page is served from committed JSON), but `/query` and live figures
  degrade. Upgrade at https://supabase.com/dashboard/project/zwhvabkvrexphlskubog/settings/billing
  or just wake it in the dashboard when the daily monitor complains.

---

## 4. 📦 PUBLISH THE RAW-DATA ARCHIVE (one command, from your machine)

Every published number re-derives from 11 source files (48.8 MB) whose
SHA-256 manifest is committed in `docs/RAW_DATA_ARCHIVE.md` — but the files
themselves can't be uploaded from the sandbox (org policy blocks release
creation). From any normal machine with the repo cloned and the data present:

```bash
GITHUB_TOKEN=<your new PAT, repo scope> python scripts/archive_raw_data.py
```

It is idempotent: builds the tar.gz, verifies every hash against the
committed manifest, creates release `raw-data-2026-08-12` if absent, uploads
if the asset is missing, and does nothing if it's already there.

---

## 5. ✉️ THE OUTREACH GO BUTTON (~948 superintendents, held for your word)

71 emails are already sent (50 pilot + 21 of the halted wave); the sent log
and opt-outs live in Supabase (`outreach_sent` / `outreach_optout`) so no
machine can double-send. The rest go only when you say go:

```bash
export RESEND_API_KEY=<from resend.com, rotated>
export RESEND_FROM='Gus Sanchez <gus@ubntag.com>'   # optional — this is the default
export RESEND_REPLY_TO='wirelessgus@gmail.com'
# every client email is BCC'd to gus@ubntag.com by default (TAG_BCC to change)
export TAG_POSTAL_ADDRESS='100 Plaza Place, Suite 300, Northlake, TX 76226'
export SUPABASE_PAT=<from supabase, rotated>   # remote sent-log — required, fails closed without it

python scripts/send_outreach.py --send --confirm GO
```

Useful variants: `--limit 50` (a wave), `--only 061910` (one district),
`--test you@example.com` (render to yourself). Every email carries its own
identity gate (a district's email can only contain that district's name and
deep-link), the AI disclosure footer, the postal address, and a working
opt-out. After a run: `python scripts/sync_outreach_state.py --push`.

---

## 6. 🗓️ FRESHNESS ACKNOWLEDGMENTS (the daily monitor is nagging on purpose)

`.github/workflows/monitor.yml` runs daily and **fails while upstream data is
newer than what the site serves**. Three are pending right now:

| Upstream release | What it feeds | To ingest |
|---|---|---|
| STAAR SY2026 | equity layer (currently SY2024+2025) | `scripts/ingest_tea_snapshot.py --download` → rebuild artifacts |
| Recapture 2026–27 xlsx | economics "who pays" | `scripts/ingest_tea_property.py` → `build_economics_data.py` |
| TIGER 2025 boundaries | `/geomap` (currently TIGER2024) | `scripts/build_district_geo.py` with the new zip |

If you decide *not* to ingest one yet, acknowledge it so the monitor goes
green: bump that source's `vintage` in `scripts/freshness_vintages.json` and
commit. Bumping the vintage **is** the acknowledgment — it records "a human
saw this release and chose the current data on purpose."

To enable the monitor: it needs no secrets, but scheduled workflows only run
after you've confirmed Actions are enabled for the repo
(https://github.com/GusAI40/texas-isd-finances/actions — press enable if
prompted; a first manual "Run workflow" also arms the schedule).

---

## 7. 🚀 GITHUB-ACTIONS DEPLOYS (optional — only after master is current)

`.github/workflows/deploy.yml` deploys master on push **if** the secrets
exist. Master now matches production (merged 2026-08-12) and the workflow's
post-deploy step runs `scripts/verify_live.py` — so a bad deploy fails loudly
instead of silently rolling back. To arm it:

1. https://github.com/GusAI40/texas-isd-finances/settings/secrets/actions
2. Add `VERCEL_TOKEN` (your rotated token), `VERCEL_ORG_ID` and
   `VERCEL_PROJECT_ID` (both printed by `vercel link --scope tag-ai-projects`
   into `.vercel/project.json` — run it in a scratch clone; it rewrites
   `vercel.json`, so `git checkout vercel.json` after).

Until you do this, deploys stay manual:
`VERCEL_TOKEN=… vercel --prod --yes --scope tag-ai-projects` — and the CLI
often prints `Error: fetch failed` AFTER creating the deployment; check
`vercel ls --scope tag-ai-projects` before retrying, and `vercel promote <url>`
if it landed as Preview.

---

## 8. 🔒 THE RELOCK SWITCH

The site is public. To put it back behind a password (e.g. during an
incident): add env var `SITE_PASSWORD` in Vercel (§1 step 1) and redeploy —
the whole site locks except `/health` and `/api/cron/*` (monitoring and the
daily feed keep working by design). Remove the var + redeploy to go public
again. Username is `txisd`.

---

## Daily heartbeat — how you know it's all still true

- **GitHub → Actions → "monitor"** (daily 12:00 UTC): health + database,
  cron-run gaps, `verify_live.py` (production serves what git says), and
  upstream freshness. Green = the whole chain holds. Red names the link.
- `curl -s https://txisd.dev/health` — 5-second manual check.
- `python scripts/usage_report.py` — who's visiting, what they're asking.
