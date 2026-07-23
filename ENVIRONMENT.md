# Environment Variables

Copy `env_template.txt` to `.env` for local work. In production these live
**only** in the hosting provider's settings (Vercel → Settings →
Environment Variables). Never commit real values.

| Variable | Required | Default | Purpose / notes |
|---|---|---|---|
| `SUPABASE_DB_URL` | For all data endpoints | — | Postgres connection string. **Use the pooler**: serverless → transaction mode port `6543` (asyncpg statement cache is already disabled in code); long-running hosts → session mode port `5432`. The direct `db.[ref].supabase.co` host is IPv6-only — it will time out from Vercel/Render/Railway. |
| `OPENAI_API_KEY` | For `POST /query` only | — | Everything else works without it; `/query` returns 503 until set. |
| `QUERY_RATE_LIMIT` | No | `10` | Questions per minute per IP on `/query`. |
| `NLP_MODEL` | No | `gpt-4o-mini` | OpenAI model for the NLP agent. |
| `NLP_VERBOSE` | No | `false` | Log agent reasoning (dev only). |
| `CORS_ALLOW_ORIGINS` | No | `*` | Comma-separated allowed origins. Credentials are auto-disabled when wildcard. |
| `DATA_MIN_YEAR` / `DATA_MAX_YEAR` | No | `2009` / `2025` | Data coverage bounds used for input validation; bump after loading a new TEA year. |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | No (currently unused by the app) | — | Present in the template for PostgREST-based tooling; the API itself connects via `SUPABASE_DB_URL`. |

Degradation behavior is deliberate: with **no** variables set the app
still boots — dashboard, `/docs`, `/health` (reports `degraded`) — and
data endpoints return 503 with instructions.
