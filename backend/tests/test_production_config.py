"""Production must never fall back to an external provider by accident.

The dangerous case is silent: LLM_PROVIDER absent from the environment, the code
default ("groq") takes over, and a local GPT-OSS deployment quietly starts calling
Groq. In production the provider must be declared explicitly.
"""

import pytest

from app.config import ConfigurationError, Settings, validate_production_settings

LOCAL_URL = "http://host.docker.internal:8001/v1"
SECRET = "x" * 40


def settings(**overrides) -> Settings:
    base = dict(app_env="production", secret_key=SECRET, llm_provider="local",
                local_llm_base_url=LOCAL_URL, local_llm_model="openai/gpt-oss-20b",
                llm_fallback_enabled=False, groq_api_key="")
    return Settings(**{**base, **overrides})


def test_development_is_never_blocked():
    """Dev/test behaviour must stay exactly as it was."""
    validate_production_settings(settings(app_env="development", llm_provider="groq"), {})
    validate_production_settings(Settings(app_env="development", secret_key=""), {})


def test_valid_local_production_config_starts():
    validate_production_settings(settings(), {"LLM_PROVIDER": "local"})


def test_missing_llm_provider_env_fails_fast():
    """The exact silent-Groq scenario this guard exists for."""
    with pytest.raises(ConfigurationError) as error:
        validate_production_settings(settings(llm_provider="groq"), {})
    assert "LLM_PROVIDER" in str(error.value)


def test_invalid_provider_value_fails_fast():
    with pytest.raises(ConfigurationError) as error:
        validate_production_settings(settings(), {"LLM_PROVIDER": "openai"})
    assert "noto‘g‘ri" in str(error.value)


@pytest.mark.parametrize("override,missing", [
    ({"local_llm_base_url": ""}, "LOCAL_LLM_BASE_URL"),
    ({"local_llm_model": "", "local_llm_models": ""}, "LOCAL_LLM_MODEL"),
])
def test_local_provider_requires_its_own_settings(override, missing):
    with pytest.raises(ConfigurationError) as error:
        validate_production_settings(settings(**override), {"LLM_PROVIDER": "local"})
    assert missing in str(error.value)


def test_groq_in_production_requires_an_intentional_key():
    with pytest.raises(ConfigurationError) as error:
        validate_production_settings(settings(llm_provider="groq"), {"LLM_PROVIDER": "groq"})
    assert "GROQ_API_KEY" in str(error.value)
    # Explicitly configured Groq remains allowed.
    validate_production_settings(
        settings(llm_provider="groq", groq_api_key="real-key"), {"LLM_PROVIDER": "groq"})


def test_enabled_fallback_without_a_key_fails_fast():
    with pytest.raises(ConfigurationError) as error:
        validate_production_settings(settings(llm_fallback_enabled=True),
                                     {"LLM_PROVIDER": "local"})
    assert "LLM_FALLBACK_ENABLED" in str(error.value)


def test_weak_secret_key_is_rejected_in_production():
    with pytest.raises(ConfigurationError) as error:
        validate_production_settings(settings(secret_key="short"), {"LLM_PROVIDER": "local"})
    assert "SECRET_KEY" in str(error.value)
