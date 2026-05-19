from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmConfig(BaseModel):
    provider: str = "ollama"
    api_key: str = ""
    model_name: str = "qwen2.5:7b"
    base_url: str = "http://127.0.0.1:11434/v1"
    temperature: float = 0.2
    max_tokens: int = 2048


class Settings(BaseSettings):
    app_name: str = "Testcase Agent"
    api_v1_prefix: str = "/api/v1"

    llm: LlmConfig = LlmConfig()

    model_config = SettingsConfigDict(
        env_prefix="TCASE_",
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="_",
        env_nested_max_split=1,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
