import os
import pathlib
from functools import lru_cache
from typing import Optional, List, Any
import dotenv
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, field_validator

# Load dotenv at start to export keys to os.environ for LiteLLM
dotenv.load_dotenv()

@lru_cache()
def _load_llm_yaml() -> dict:
    path = pathlib.Path("app/config/config.yml")
    if not path.exists():
        path = pathlib.Path("app/config/config.yml.example")
    if not path.exists():
        raise FileNotFoundError("Neither app/config/config.yml nor app/config/config.yml.example was found.")
    with path.open() as f:
        data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

class Settings(BaseSettings):
    """
    Application settings and environment configuration.
    Uses Pydantic BaseSettings to automatically load variables from .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    API_KEY: str  # Secret token to secure the API access
    APP_VERSION: str = "1.0.4"
    
    # Optional provider keys - LiteLLM picks up whichever matches the active model prefix
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    CORS_ORIGINS: Any = ["https://amnotwallas.github.io", "http://localhost:4200"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    return json.loads(v)
                except Exception:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def validate_llm_keys(self) -> 'Settings':
        import sys
        if "pytest" in sys.modules and os.getenv("FORCE_ENV_VALIDATION") != "1":
            return self
            
        for model in filter(None, [self.llm_model, self.llm_fallback]):
            if model.startswith("groq/") and not self.GROQ_API_KEY:
                raise ValueError(f"Missing GROQ_API_KEY in environment for model '{model}'")
            elif model.startswith("openai/") and not self.OPENAI_API_KEY:
                raise ValueError(f"Missing OPENAI_API_KEY in environment for model '{model}'")
            elif model.startswith("anthropic/") and not self.ANTHROPIC_API_KEY:
                raise ValueError(f"Missing ANTHROPIC_API_KEY in environment for model '{model}'")
        return self

    @property
    def llm_model(self) -> str:
        llm_config = _load_llm_yaml().get("llm") or {}
        return llm_config.get("model") or "groq/meta-llama/llama-4-scout-17b-16e-instruct"

    @property
    def llm_temperature(self) -> float:
        llm_config = _load_llm_yaml().get("llm") or {}
        val = llm_config.get("temperature")
        return float(val) if val is not None else 0.5

    @property
    def llm_fallback(self) -> str:
        llm_config = _load_llm_yaml().get("llm") or {}
        return llm_config.get("fallback") or ""

    @property
    def llm_max_failures(self) -> int:
        llm_config = _load_llm_yaml().get("llm") or {}
        val = llm_config.get("max_failures")
        return int(val) if val is not None else 3

@lru_cache()
def get_settings():
    """
    Returns a cached instance of the settings.
    LRU Cache ensures the settings are only loaded once.
    """
    return Settings()

