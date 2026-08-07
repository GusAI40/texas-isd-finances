"""Tests for provider selection (DeepSeek vs OpenAI).

The point of these: switching providers must be a configuration change that
cannot half-apply. If the /query agent moved to DeepSeek but the news
enrichment kept calling OpenAI, the site would quietly bill two accounts and
one of them would fail.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm_config import (  # noqa: E402
    DEEPSEEK_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    describe,
    resolve_llm_config,
)

ALL = ("NLP_PROVIDER", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
       "NLP_MODEL", "NLP_BASE_URL", "NLP_TEMPERATURE")


def clear(monkeypatch):
    for k in ALL:
        monkeypatch.delenv(k, raising=False)


# --- choosing a provider ----------------------------------------------------

def test_a_deepseek_key_is_enough_to_switch(monkeypatch):
    """Adding DEEPSEEK_API_KEY switches the site over — no code change."""
    clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    c = resolve_llm_config()
    assert c.provider == "deepseek"
    assert c.model == DEEPSEEK_DEFAULT_MODEL == "deepseek-v4-flash"
    assert c.base_url == DEEPSEEK_BASE_URL == "https://api.deepseek.com"
    assert c.api_key == "sk-ds-test"
    assert c.configured


def test_removing_the_deepseek_key_switches_back(monkeypatch):
    clear(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa-test")
    c = resolve_llm_config()
    assert c.provider == "openai"
    assert c.model == OPENAI_DEFAULT_MODEL
    assert c.base_url is None          # the SDK's own default endpoint
    assert c.api_key == "sk-oa-test"


def test_explicit_provider_wins_over_key_detection(monkeypatch):
    """With both keys present, NLP_PROVIDER decides — no ambiguity."""
    clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa")
    monkeypatch.setenv("NLP_PROVIDER", "openai")
    assert resolve_llm_config().provider == "openai"
    monkeypatch.setenv("NLP_PROVIDER", "deepseek")
    assert resolve_llm_config().provider == "deepseek"


def test_unknown_provider_falls_back_to_key_detection(monkeypatch):
    clear(monkeypatch)
    monkeypatch.setenv("NLP_PROVIDER", "not-a-provider")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    assert resolve_llm_config().provider == "deepseek"


# --- overrides --------------------------------------------------------------

def test_model_and_base_url_can_be_overridden(monkeypatch):
    """A new DeepSeek model can be adopted without shipping code."""
    clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("NLP_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("NLP_BASE_URL", "https://example.test/v1")
    c = resolve_llm_config()
    assert c.model == "deepseek-v4-pro"
    assert c.base_url == "https://example.test/v1"


def test_temperature_defaults_to_zero_and_survives_garbage(monkeypatch):
    """SQL generation wants determinism; a typo must not crash the engine."""
    clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    assert resolve_llm_config().temperature == 0.0
    monkeypatch.setenv("NLP_TEMPERATURE", "not-a-number")
    assert resolve_llm_config().temperature == 0.0
    monkeypatch.setenv("NLP_TEMPERATURE", "0.4")
    assert resolve_llm_config().temperature == 0.4


# --- operator-facing --------------------------------------------------------

def test_missing_key_is_reported_against_the_right_variable(monkeypatch):
    """Telling a DeepSeek deploy to 'set OPENAI_API_KEY' sends someone in circles."""
    clear(monkeypatch)
    monkeypatch.setenv("NLP_PROVIDER", "deepseek")
    c = resolve_llm_config()
    assert not c.configured
    assert c.key_env_name == "DEEPSEEK_API_KEY"
    monkeypatch.setenv("NLP_PROVIDER", "openai")
    assert resolve_llm_config().key_env_name == "OPENAI_API_KEY"


def test_describe_never_leaks_the_key(monkeypatch):
    """/health reports this string publicly."""
    clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-SUPERSECRET-value")
    text = describe()
    assert "SUPERSECRET" not in text
    assert "deepseek" in text and "deepseek-v4-flash" in text
    assert "configured" in text


def test_both_callers_resolve_the_same_provider(monkeypatch):
    """The /query agent and the news enrichment must never split across two
    providers — that would bill two accounts and half-fail."""
    clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    engine_src = (Path(__file__).resolve().parent.parent / "src" / "nlp_engine.py").read_text()
    intel_src = (Path(__file__).resolve().parent.parent / "scripts" / "isd_intel.py").read_text()
    assert "resolve_llm_config" in engine_src
    assert "resolve_llm_config" in intel_src
    # Neither may read a provider key directly any more.
    assert 'getenv("OPENAI_API_KEY")' not in engine_src
    assert 'getenv("OPENAI_API_KEY")' not in intel_src
