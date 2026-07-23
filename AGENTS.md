# Agents & Automation Inventory

Everything in this repository that acts autonomously or semi-autonomously.
Verified 2026-07-23.

## 1. NLP Query Agent — ✅ working & verified

| Field | Value |
|---|---|
| Name | `TexasFinanceNLPEngine` |
| Purpose | Convert a plain-English question about Texas district finances into SELECT-only SQL, run it, and answer in prose |
| Prompt location | `SYSTEM_PROMPT` constant in `src/nlp_engine.py` (schema of the two views + rules: SELECT only, ILIKE matching, LIMIT 100, rounding) |
| Model / provider | OpenAI `gpt-4o-mini` (override: `NLP_MODEL` env), temperature 0 |
| Framework | LangChain 1.x `langchain.agents.create_agent` (pin `>=1.0,<2.0`) |
| Tools | `SQLDatabaseToolkit.get_tools()` — list tables, fetch schema, query-check, execute SQL |
| Input | `POST /query {"question": str}` — length 3–500 enforced by Pydantic |
| Output | `{success, question, answer | error, timestamp}` |
| Data access | **Only** `v_finance_summary` and `v_anomaly_flags` via `include_tables` allowlist; DB role privileges add a second fence (base table revoked + RLS) |
| Guardrails | Rate limit 10/min/IP (`_rate_limited`, `src/api.py`) · `recursion_limit=15` · lazy init so a missing key degrades to 503 instead of crashing · SELECT-only instruction · connection via read-committed pooler |
| Trigger | User request only (no autonomous operation) |
| Dependencies | `langchain`, `langchain-community` (sunset upstream — watch issue #674), `langchain-openai`, `sqlalchemy`, `psycopg2` |
| Status | ✅ Verified live (e.g. Dallas ISD per-student 2024/2025 answered correctly in production) |
| Business outcome | Answers the long tail of questions the fixed dashboard can't |
| Revenue contribution | 🔵 None today (costs ~$0.001/question); the differentiator feature for a future paid API tier |
| Files | `src/nlp_engine.py`, `src/api.py` (`/query`), `tests/test_nlp_engine.py` |

## 2. `/ariba` project-memory skill — ✅ working & verified

Not a runtime agent — an **agent instruction set** for AI coding sessions.

| Field | Value |
|---|---|
| Purpose | Persistent memory across amnesiac agent sessions: catch-up (read state + verify live health), save (append engineering log + push), quick note |
| Location | `.claude/skills/ariba/SKILL.md` · memory files `CLAUDE.md` + `docs/ENGINEERING_LOG.md` |
| Guardrails | Never log secrets; append-only history; verify live health before briefing; unpushed memory = no memory |
| Trigger | `/ariba` typed by the maintainer in a Claude session |
| Revenue contribution | Indirect — development velocity and continuity |

## 3. CI pipeline — ✅ working & verified

| Field | Value |
|---|---|
| Location | `.github/workflows/ci.yml` |
| Trigger | Every push and pull request to `master` |
| Actions | `ruff check .` + `pytest` on Python 3.10, 3.11, 3.12 |
| Status | ✅ Green on master (verified via GitHub check runs) |

## 4. Monte Carlo user simulator — ✅ working (design-time tool)

| Field | Value |
|---|---|
| Location | `scripts/simulate_admin_usage.py` (seed 42, reproducible) |
| Purpose | Simulates 1,000 Texas school administrators against the real district population to measure feature demand; drove the dashboard design |
| Output | `docs/simulation_results.json` + findings in `docs/UX_RESEARCH.md` |
| Trigger | Manual, at design time |

## Explicitly absent (verified — not hidden, just not built)

- 🔴 Schedulers / cron jobs (data refresh is manual, once per TEA release)
- 🔴 Queues, webhooks, background workers
- 🔴 Email/communication automations
- 🔴 Autonomous monitoring agents (only manual `/health` checks)
