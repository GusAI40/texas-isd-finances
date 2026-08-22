# Texas ISD Finances — Agent Operating Guide

This file routes work; it does not replace the project's detailed runbooks.

## Read before changing anything

1. Read `CLAUDE.md` for production invariants and the current snapshot.
2. Read the newest two or three entries in `docs/ENGINEERING_LOG.md`.
3. Read `docs/TECH_STACK_AND_AGENT_SKILLS.md` for the evidence-backed stack,
   official skills map, trust tiers, and adoption rules.
4. Use `PROJECT_MAP.md`, `docs/USAGE.md`, and `DEPLOYMENT.md` for the affected
   surface. Check code/config when prose conflicts.
5. Run `git status`; preserve user changes and work on a branch through a PR.

Claude Code can invoke the repository-local `.claude/skills/ariba` catch-up/
save workflow and `.claude/skills/outreach` for outreach work. Codex does not
auto-discover those Claude skills in this documentation-only change; it should
read their `SKILL.md` files manually as project runbooks when relevant. No
external skill is installed merely because the stack guide lists it. Inspect,
pin, and load only the narrow skill needed for the current task; project rules
always win.

## Route work by surface

| Work | Primary paths | Candidate upstream guidance — not installed |
|---|---|---|
| API, models, middleware | `src/api.py`, `api/index.py`, API tests | version-matched FastAPI; optional Pydantic |
| Database, RLS, migrations | `sql/`, `src/migrations.py`, pool setup | Supabase + Postgres best practices |
| SQL agent and providers | `src/nlp_engine.py`, `src/llm_config.py` | pinned LangChain; OpenAI only for alternate-provider work |
| Email and outreach | `src/outreach_*`, outreach scripts/workflows | Resend + email best practices; local outreach skill |
| Hosting, cron, caching | `vercel.json`, `.vercelignore`, `api/` | Vercel optimization; deployment skills only with authority |
| CI and repository safety | `.github/workflows/` | reviewed GitHub Actions hardening/efficiency |
| Optional heatmap | `static/heatmap.html`, `/mapbox-token` | Mapbox token, integration, performance, visualization |
| MCP | `src/mcp_protocol.py`, `src/mcp_tools.py`, `docs/MCP.md` | Anthropic `mcp-builder` for review only |
| Data artifacts | `scripts/`, `src/sources.py`, `static/*.json` | project builders and provenance tests are authoritative |

## Non-negotiable boundaries

- Never commit or publicly expose credentials, recipient email/contact
  details, private operational addresses, correspondence, or recipient-level
  telemetry. Public reply logs contain aggregate counts only. The configured
  business postal address is intentionally included in outbound mail for
  compliance; keep it out of logs and public telemetry.
- District numbers are six-character strings; preserve leading zeros.
- Vercel uses the Supabase transaction pooler on port 6543 with asyncpg
  statement caching disabled. `NLP_DB_URL` is mandatory for `/query`;
  model-authored SQL never falls back to the owner. Preserve the exact SQLGlot
  AST/function allowlist, two-view resolution, non-recursive CTE rule,
  `public.*` qualification, `pg_catalog` search path, and read-only DB role;
  “SELECT-only” by itself does not block session-affecting functions.
- `pyproject.toml` and `uv.lock` are the reproducible dependency authority.
  CI, Docker, and Render must use `uv sync --locked`; Vercel installs the
  base project only, so offline/server extras must not leak into its bundle.
- Durable opt-outs and send-time suppression fail closed. Public reply logs
  expose aggregates only. An uncertain send must not become a duplicate.
- `static/*.json` files are committed runtime artifacts, not disposable build
  output. Preserve required `.vercelignore` re-includes and the no-rewrites
  Vercel rule.
- Treat configured fallbacks and alternate hosts as inactive until directly
  verified. Merges, deploys, production SQL, sends, secrets, workflow
  dispatches, and releases require explicit authority and target verification.

## Minimum verification

```bash
ruff check .
python -m pytest -q
python scripts/check_static_js.py
```

Add focused tests for the changed surface. A 200 response does not prove the
browser JavaScript works, and a green secret-dependent workflow may have
skipped. For runtime/deployment changes and after a deployment, run
`python scripts/verify_live.py --require-network --expect-revision <40-char-git-sha>`;
add `--with-query` when the NLP path changed. A network-error skip is not
verification, so inspect output as well as the exit code. Record durable
decisions and new gotchas in the engineering log.
