"""Vercel serverless entrypoint.

Vercel's Python runtime auto-detects `api/index.py` and loads the top-level
ASGI `app`; all routes are rewritten here via vercel.json. Python bundles
are capped at 500 MB uncompressed — if the full dependency set (pandas,
matplotlib, langchain) exceeds that, use the slim requirements documented
in DEPLOYMENT.md; the portal and data endpoints work either way.
"""
from src.api import app  # noqa: F401
