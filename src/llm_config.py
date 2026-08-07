"""Which language model the site talks to, and how.

One place decides the provider so the two callers — the /query SQL agent
(src/nlp_engine.py) and the optional news enrichment (scripts/isd_intel.py) —
can never drift apart and quietly bill two different accounts.

DeepSeek is OpenAI-SDK compatible: same request shape, same tool-calling
protocol, different base URL. So switching providers is configuration, not a
rewrite — `langchain_openai.ChatOpenAI` and the `openai` client both accept a
`base_url`.

How the provider is chosen
--------------------------
1. `NLP_PROVIDER=deepseek|openai` decides explicitly, if set.
2. Otherwise: DeepSeek if `DEEPSEEK_API_KEY` is present, else OpenAI.

That means adding DEEPSEEK_API_KEY is enough to switch, and removing it is
enough to switch back — no code change either way. Everything else
(`NLP_MODEL`, `NLP_BASE_URL`, `NLP_TEMPERATURE`) can override a default
without touching this file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Verified against api-docs.deepseek.com: OpenAI-compatible endpoint, and tool
# calling is supported — the SQL agent is useless without it.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class LLMConfig:
    provider: str          # 'deepseek' | 'openai'
    model: str
    api_key: str | None
    base_url: str | None   # None = the SDK's own default (OpenAI)
    temperature: float

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def key_env_name(self) -> str:
        return "DEEPSEEK_API_KEY" if self.provider == "deepseek" else "OPENAI_API_KEY"


def resolve_llm_config() -> LLMConfig:
    """Read the environment and decide which model to call."""
    provider = (os.getenv("NLP_PROVIDER") or "").strip().lower()
    if provider not in ("deepseek", "openai"):
        # No explicit choice: a DeepSeek key present means DeepSeek is intended.
        provider = "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "openai"

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        model = os.getenv("NLP_MODEL", DEEPSEEK_DEFAULT_MODEL)
        base_url = os.getenv("NLP_BASE_URL", DEEPSEEK_BASE_URL)
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("NLP_MODEL", OPENAI_DEFAULT_MODEL)
        base_url = os.getenv("NLP_BASE_URL") or None

    try:
        temperature = float(os.getenv("NLP_TEMPERATURE", "0"))
    except ValueError:
        temperature = 0.0

    return LLMConfig(provider=provider, model=model, api_key=api_key,
                     base_url=base_url, temperature=temperature)


def describe() -> str:
    """A one-line, key-free summary for logs and /health. Never prints the key."""
    c = resolve_llm_config()
    where = c.base_url or "api.openai.com"
    return (f"{c.provider}:{c.model} via {where} "
            f"({'configured' if c.configured else 'NO KEY SET'})")
