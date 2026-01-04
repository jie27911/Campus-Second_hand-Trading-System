"""Configuration module for CampuSwap backend."""
from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application runtime settings."""

    app_name: str = "CampuSwap"
    environment: str = Field("local", alias="CAMPUSWAP_ENV")
    api_v1_prefix: str = "/api/v1"
    debug: bool = Field(default=True)

    # When enabled, the monitoring simulator may seed synthetic rows into Hub MySQL.
    # Default off to keep database contents real.
    enable_simulated_data: bool = Field(default=False, alias="ENABLE_SIMULATED_DATA")

    mysql_dsn: str = Field(..., alias="MYSQL_DSN")
    mariadb_dsn: str = Field(..., alias="MARIADB_DSN")
    postgres_dsn: str = Field(..., alias="POSTGRES_DSN")
    jwt_secret_key: str = Field("campuswap-secret", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Conflict email link tokens
    conflict_token_expire_minutes: int = Field(1440, alias="CONFLICT_TOKEN_EXPIRE_MINUTES")
    conflict_link_base_url: str = Field("http://localhost:8000", alias="CONFLICT_LINK_BASE_URL")
    frontend_base_url: str = Field("http://localhost:5173", alias="FRONTEND_BASE_URL")

    cors_origins: List[AnyHttpUrl] = []

    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    alert_sender: str | None = Field(default=None, alias="ALERT_SENDER")
    alert_recipients: List[str] = Field(default_factory=list, alias="ALERT_RECIPIENTS")

    # GLM AI 配置
    glm_api_key: str | None = Field(default=None, alias="GLM_API_KEY")
    glm_api_base: str = Field(default="https://open.bigmodel.cn/api/paas/v4", alias="GLM_API_BASE")
    glm_model: str = Field(default="glm-4-flash", alias="GLM_MODEL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"
    }


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
