from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
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
    campaign_preview_secret: SecretStr | None = Field(
        default=None,
        validation_alias="PULSE_CAMPAIGN_PREVIEW_SECRET",
    )
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_tool_rounds: int = Field(default=5, ge=1, le=20)
    llm_history_limit: int = Field(default=50, ge=1, le=500)
    email_delivery_mode: str = "mock"
    pulse_hosted_demo: bool = False
    demo_auth_enabled: bool = False
    demo_auth_username: str = ""
    demo_auth_password: SecretStr | None = None
    frontend_dist: str | None = None
    demo_seed_on_start: bool = False
    campaign_retrieval_secret: SecretStr | None = Field(
        default=None, validation_alias="PULSE_CAMPAIGN_RETRIEVAL_SECRET"
    )
    gwm_email_base_url: str | None = None
    gwm_email_send_path: str = "/EmailNotification/SendEmail"
    gwm_email_sender: str | None = None
    gwm_email_api_key: SecretStr | None = None
    gwm_email_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

    @model_validator(mode="after")
    def validate_demo(self):
        if self.demo_auth_enabled:
            if (
                not self.demo_auth_username.strip()
                or ":" in self.demo_auth_username
                or not self.demo_auth_password
                or len(self.demo_auth_password.get_secret_value()) < 20
            ):
                raise ValueError("Demo authentication requires a username and a password of at least 20 characters")
        if self.pulse_hosted_demo:
            if not self.demo_auth_enabled or self.email_delivery_mode != "mock":
                raise ValueError("Hosted demo requires authentication and mock email")
            if not self.database_url or not self.llm_configured or not self.frontend_dist:
                raise ValueError("Hosted demo requires database, model key and frontend assets")
            if self.mcp_server_url != "http://127.0.0.1:8001/mcp":
                raise ValueError("Hosted MCP must use loopback")
            for secret in (self.campaign_preview_secret, self.campaign_retrieval_secret):
                if not secret or len(secret.get_secret_value()) < 32:
                    raise ValueError("Hosted demo requires stable signing secrets of at least 32 characters")
        return self

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.groq_api_key
            and self.groq_api_key.get_secret_value().strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
