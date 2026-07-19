"""Vercel serverless entrypoint.

Vercel's Python runtime looks for an ASGI `app` in this module; all routes
are rewritten here via vercel.json. The full dependency set (pandas,
matplotlib, langchain) exceeds serverless size limits, so Vercel deploys
use the slim `requirements.txt` documented in DEPLOYMENT.md — the portal
and data endpoints work; /query returns 503 unless the NLP extras fit.
"""
from src.api import app  # noqa: F401
