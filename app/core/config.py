from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    GROQ_API_KEY: str
    API_KEY: str  # El token secreto para blindar tu API
    MODEL_NAME: str = "llama-3.1-8b-instant"
    APP_VERSION: str = "1.0.4"
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
