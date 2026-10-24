from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore", case_sensitive=False, populate_by_name=True, hide_input_in_errors=True,
    )
    groq_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    redis_url: SecretStr = SecretStr("")
    redis_token: SecretStr = SecretStr("")
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY", "SERVICE_ROLE_KEY"),
    )
    jwt_secret: SecretStr = SecretStr("")
    allowed_origins: str = "http://localhost:3000"
    cookie_secure: bool = False
    session_hours: int = 24
    provider_timeout: float = 25.0
    storage_timeout: float = 5.0
    silence_seconds: float = 4.5
    watchdog_interval: float = 0.25
    bubble_delay_scale: float = 1.0
    archive_poll_seconds: float = 30.0
    room_retention_seconds: float = 3600.0
    rate_limit_enabled: bool = True
    max_active_rooms_per_user: int = 2
    redis_prefix: str = "backchannel"

    @field_validator("jwt_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value() and len(value.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 bytes")
        return value

    @property
    def origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def redis_scheme(self) -> str:
        return urlparse(self.redis_url.get_secret_value()).scheme
