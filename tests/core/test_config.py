import os
import pytest
from unittest.mock import patch
from pydantic import ValidationError
from app.core.config import Settings, _load_llm_yaml

@pytest.fixture(autouse=True)
def clear_yaml_cache():
    _load_llm_yaml.cache_clear()
    yield
    _load_llm_yaml.cache_clear()

def test_settings_validation_missing_groq_key():
    with patch("app.core.config._load_llm_yaml") as mock_load:
        mock_load.return_value = {"llm": {"model": "groq/meta-llama/llama-4-scout-17b-16e-instruct"}}
        with patch.dict(os.environ, {
            "API_KEY": "test_token", 
            "FORCE_ENV_VALIDATION": "1",
            "GROQ_API_KEY": ""
        }, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "Missing GROQ_API_KEY" in str(exc_info.value)

def test_settings_validation_missing_openai_key():
    with patch("app.core.config._load_llm_yaml") as mock_load:
        mock_load.return_value = {"llm": {"model": "openai/gpt-4o-mini"}}
        with patch.dict(os.environ, {
            "API_KEY": "test_token", 
            "FORCE_ENV_VALIDATION": "1",
            "OPENAI_API_KEY": ""
        }, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "Missing OPENAI_API_KEY" in str(exc_info.value)

def test_settings_validation_missing_anthropic_key():
    with patch("app.core.config._load_llm_yaml") as mock_load:
        mock_load.return_value = {"llm": {"model": "anthropic/claude-3-5-sonnet"}}
        with patch.dict(os.environ, {
            "API_KEY": "test_token", 
            "FORCE_ENV_VALIDATION": "1",
            "ANTHROPIC_API_KEY": ""
        }, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "Missing ANTHROPIC_API_KEY" in str(exc_info.value)

def test_settings_validation_missing_fallback_key():
    with patch("app.core.config._load_llm_yaml") as mock_load:
        mock_load.return_value = {
            "llm": {"model": "groq/llama-3.1-8b-instant", "fallback": "openai/gpt-4o-mini"}
        }
        with patch.dict(os.environ, {
            "API_KEY": "test_token",
            "FORCE_ENV_VALIDATION": "1",
            "GROQ_API_KEY": "valid_groq_key",
            "OPENAI_API_KEY": ""
        }, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "Missing OPENAI_API_KEY" in str(exc_info.value)

def test_settings_validation_success():
    with patch("app.core.config._load_llm_yaml") as mock_load:
        mock_load.return_value = {"llm": {"model": "groq/meta-llama/llama-4-scout-17b-16e-instruct"}}
        with patch.dict(os.environ, {
            "API_KEY": "test_token", 
            "FORCE_ENV_VALIDATION": "1",
            "GROQ_API_KEY": "valid_groq_key"
        }, clear=True):
            settings = Settings()
            assert settings.GROQ_API_KEY == "valid_groq_key"

def test_settings_cors_origins_parsing():
    # 1. Test default value
    with patch.dict(os.environ, {"API_KEY": "test_token"}, clear=True):
        settings = Settings()
        assert settings.CORS_ORIGINS == ["https://amnotwallas.github.io", "http://localhost:4200"]

    # 2. Test comma separated string
    with patch.dict(os.environ, {
        "API_KEY": "test_token",
        "CORS_ORIGINS": "http://example1.com,  http://example2.com"
    }, clear=True):
        settings = Settings()
        assert settings.CORS_ORIGINS == ["http://example1.com", "http://example2.com"]

    # 3. Test JSON array string
    with patch.dict(os.environ, {
        "API_KEY": "test_token",
        "CORS_ORIGINS": '["http://example3.com", "http://example4.com"]'
    }, clear=True):
        settings = Settings()
        assert settings.CORS_ORIGINS == ["http://example3.com", "http://example4.com"]
