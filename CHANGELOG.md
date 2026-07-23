# Changelog

All notable changes, newest first. Full narrative history with reasoning
lives in [docs/ENGINEERING_LOG.md](docs/ENGINEERING_LOG.md).

## 2026-07-23 — v1.2 "A+ dashboard" (merged as PR #1)

- White-minimalist redesign: McKinsey action titles computed from live
  data, auto-generated executive summary, storytelling-with-data charts
- New: MECE spending breakdown (`v_spending_breakdown` +
  `GET /district/{id}/breakdown`), side-by-side district comparison,
  PNG + CSV export on every chart, per-section TEA citations, anomaly
  cards with before/after numbers, enrollment multi-year-decline callout
- New: rate limit on `POST /query` (10/min/IP, `QUERY_RATE_LIMIT`)
- Docs: complete repository blueprint (REPO_MAP, ARCHITECTURE, AGENTS,
  RUNBOOK, ENVIRONMENT), UX research, tutorial

## 2026-07-23 — v1.1 "Simulation-driven dashboard"

- Monte Carlo simulation of 1,000 Texas school administrators
  (`scripts/simulate_admin_usage.py`) drove a full UI rebuild
- New endpoints: `/district/{id}/peers`, `/benchmarks`,
  `district_number` filter on `/anomalies`
- Guided first-run tutorial, disclaimer, print/CSV export

## 2026-07-22 — v1.0 "Public launch"

- Production launch at https://texas-isd-finances.vercel.app
- Supabase provisioned; TEA's current release loaded (20,587 records,
  1,310 districts, fiscal 2009–2025)
- Fixes found by go-live testing: leading-zero district IDs, anomaly
  filter correctness, pooler-compatible asyncpg, import-first schema
- `/ariba` project-memory system (CLAUDE.md + engineering log + skill)

## 2026-07-22 — Audit round 2 (doc-validated)

- NLP engine rewritten on LangChain 1.x `create_agent` (legacy API was
  removed upstream); Supabase pooler connection guidance corrected
  (direct host is IPv6-only); Vercel config fixed (`excludeFiles`)
- Git-history secret scan (no complete secrets; old project ref noted)

## 2026-06-01 → 07-19 — Audit round 1 & launch prep

- Fixed boot-blocking import, crash-at-startup NLP init, invalid CORS,
  Plotly API misuse, SQL interpolation; enabled RLS the schema promised
- Added portal page, pytest suite, enforcing CI, Dockerfile,
  render.yaml, DEPLOYMENT.md, AUDIT.md

## Earlier — Initial commits

- Prototype: FastAPI + LangChain + Supabase design, credential
  sanitization, MIT license, CONTRIBUTING/SECURITY policies
