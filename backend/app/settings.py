from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore", case_sensitive=False)

    database_url: SecretStr = SecretStr("")
    app_environment: Literal["development", "test", "production"] = "development"
    app_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    public_demo_mode: bool = True
    visitor_demo_enabled: bool = True
    visitor_hours: int = Field(default=2, ge=1, le=24)
    visitor_active_limit: int = Field(default=100, ge=1, le=1000)
    visitor_retained_limit: int = Field(default=500, ge=1, le=5000)
    visitor_mutation_limit: int = Field(default=200, ge=10, le=1000)
    visitor_job_limit: int = Field(default=12, ge=6, le=60)
    invite_hours: int = Field(default=48, ge=1, le=168)
    recovery_minutes: int = Field(default=30, ge=5, le=60)
    privacy_tombstone_days: int = Field(default=90, ge=1, le=365)
    session_hours: int = Field(default=12, ge=1, le=168)
    max_upload_bytes: int = Field(default=1_000_000, ge=1024, le=10_000_000)
    max_chunks: int = Field(default=1500, ge=1, le=5000)
    max_outcomes: int = Field(default=500, ge=1, le=2000)
    db_pool_size: int = Field(default=5, ge=1, le=30)
    db_pool_timeout: int = Field(default=10, ge=1, le=60)
    embed_provider: Literal["hash", "sentence-transformers"] = "hash"
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ollama_timeout_seconds: int = Field(default=120, ge=5, le=300)
    github_token: SecretStr = SecretStr("")
    github_allowed_repos: str = ""
    mcp_api_token: SecretStr = SecretStr("")
    linkedin_client_id: str = ""
    linkedin_client_secret: SecretStr = SecretStr("")
    linkedin_redirect_uri: str = ""
    linkedin_scopes: str = "openid profile"
    linkedin_publishing_enabled: bool = False
    linkedin_api_version: str = Field(default="202609", pattern=r"^20[0-9]{2}(0[1-9]|1[0-2])$")
    provider_encryption_key: SecretStr = SecretStr("")
    jira_client_id: str = ""
    jira_client_secret: SecretStr = SecretStr("")
    slack_client_id: str = ""
    slack_client_secret: SecretStr = SecretStr("")
    slack_app_id: str = Field(default="", pattern=r"^(?:A[A-Z0-9]{7,63})?$")
    slack_signing_secret: SecretStr = SecretStr("")
    slack_interactions_enabled: bool = False
    google_meet_client_id: str = ""
    google_meet_client_secret: SecretStr = SecretStr("")

    @property
    def google_meet_configured(self) -> bool:
        return bool(
            self.google_meet_client_id
            and self.google_meet_client_secret.get_secret_value()
            and self.provider_encryption_key.get_secret_value()
        )

    @property
    def google_meet_redirect_uri(self) -> str:
        return self.app_origin + "/api/integrations/google-meet/callback"

    @property
    def slack_configured(self) -> bool:
        return bool(
            self.slack_client_id
            and self.slack_client_secret.get_secret_value()
            and self.provider_encryption_key.get_secret_value()
        )

    @property
    def slack_redirect_uri(self) -> str:
        return self.app_origin + "/api/integrations/slack/callback"

    @field_validator("provider_encryption_key")
    @classmethod
    def validate_provider_key(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value():
            import base64

            try:
                decoded = base64.b64decode(value.get_secret_value(), altchars=b"-_", validate=True)
            except ValueError as exc:
                raise ValueError("Provider encryption key must be URL-safe base64") from exc
            if len(decoded) != 32:
                raise ValueError("Provider encryption key must encode 32 random bytes")
        return value

    @property
    def jira_configured(self) -> bool:
        return bool(
            self.jira_client_id
            and self.jira_client_secret.get_secret_value()
            and self.provider_encryption_key.get_secret_value()
        )

    @property
    def jira_redirect_uri(self) -> str:
        return self.app_origin + "/api/integrations/jira/callback"

    @field_validator("linkedin_redirect_uri")
    @classmethod
    def validate_redirect(cls, value):
        if not value:
            return value
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LinkedIn redirect must be an exact HTTP(S) callback URL")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Remote LinkedIn callbacks require HTTPS")
        return value

    @model_validator(mode="after")
    def production_security(self):
        if self.app_environment == "production" and (
            not self.cookie_secure or not self.app_origin.startswith("https://")
        ):
            raise ValueError("Production requires secure cookies and an HTTPS application origin")
        return self

    @field_validator("app_origin", "ollama_url")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("A valid HTTP(S) origin is required")
        if parsed.query or parsed.fragment:
            raise ValueError("Origins cannot contain a query or fragment")
        return value.rstrip("/")

    @field_validator("linkedin_scopes")
    @classmethod
    def validate_linkedin_scopes(cls, value: str) -> str:
        scopes = set(value.split())
        if not {"openid", "profile"}.issubset(scopes) or not scopes.issubset({"openid", "profile", "email"}):
            raise ValueError("LinkedIn requires openid profile; email is optional")
        return " ".join(sorted(scopes))

    @property
    def linkedin_configured(self) -> bool:
        return bool(
            self.linkedin_client_id
            and self.linkedin_client_secret.get_secret_value()
            and self.linkedin_redirect_uri
        )

    @property
    def linkedin_publishing_configured(self) -> bool:
        return bool(
            self.linkedin_publishing_enabled
            and self.linkedin_client_id
            and self.linkedin_client_secret.get_secret_value()
            and self.provider_encryption_key.get_secret_value()
        )

    @property
    def linkedin_publishing_redirect_uri(self) -> str:
        return self.app_origin + "/api/integrations/linkedin/publishing/callback"


settings = Settings()
