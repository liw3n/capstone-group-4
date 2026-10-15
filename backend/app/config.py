from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = None
    groq_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-20b"
    mcp_server_url: str = "http://127.0.0.1:8001/mcp"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_tool_rounds: int = Field(default=5, ge=1, le=20)
    llm_history_limit: int = Field(default=50, ge=1, le=500)
    email_delivery_mode: str = "mock"
    gwm_email_base_url: str | None = None
    gwm_email_send_path: str = "/EmailNotification/SendEmail"
    gwm_email_sender: str | None = None
    gwm_email_api_key: SecretStr | None = None
    gwm_email_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.groq_api_key
            and self.groq_api_key.get_secret_value().strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
