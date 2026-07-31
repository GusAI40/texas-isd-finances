"""Vercel serverless entrypoint.

Vercel's `fastapi` framework preset routes every request to this file on its
own and loads the top-level ASGI `app`.

⚠️ Do NOT add a `rewrites` block to vercel.json to "make routing work". It
does the opposite. Vercel changed backend-framework routing so an internal
rewrite passes the DESTINATION path to the app — the old
`/(.*) → /api/index` rule made FastAPI receive `/api/index` for every request
and 404 the entire site, while the build still reported READY. vercel.json
must stay empty of rewrites. (This docstring used to claim the rewrite was
how routing worked, which is exactly how that outage would come back.)

Python bundles are capped at 500 MB uncompressed — if the full dependency set
(pandas, matplotlib, langchain) exceeds that, use the slim requirements
documented in DEPLOYMENT.md; the portal and data endpoints work either way.
"""
from src.api import app  # noqa: F401
