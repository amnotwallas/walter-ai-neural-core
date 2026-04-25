from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    GROQ_API_KEY: str
    MODEL_NAME: str = "llama3-8b-8192"
    APP_VERSION: str = "1.0.4"
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
