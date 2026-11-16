import re
from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    public_url: str = "http://localhost:5173"
    allowed_emails: str = ""
    session_secret: str = Field(min_length=32, repr=False)
    session_days: int = Field(default=7, ge=1, le=30)
    cookie_secure: bool = False
    trusted_proxy_ips: str = ""
    otp_seconds: int = Field(default=600, ge=60)
    resend_seconds: int = Field(default=60, ge=1)
    otp_attempts: int = Field(default=5, ge=1, le=10)
    email_hourly_limit: int = Field(default=5, ge=1)
    ip_hourly_limit: int = Field(default=20, ge=1)
    verify_ip_hourly_limit: int = Field(default=100, ge=1)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(default="", repr=False)
    neo4j_database: str = "neo4j"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls: str = "starttls"
    smtp_user: str = ""
    smtp_auth: bool = True
    smtp_password: str = Field(default="", repr=False)
    smtp_from: str = "TravelMemo <noreply@example.com>"
    smtp_timeout: float = 10
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-6-luna"
    cloudflare_tunnel_id: str = ""
    cloudflare_tunnel_token: str = Field(default="", repr=False)

    @property
    def emails(self):
        return {
            value.strip().casefold() for value in self.allowed_emails.split(",") if value.strip()
        }

    @property
    def origin(self):
        parsed = urlsplit(self.public_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @model_validator(mode="after")
    def validate_environment(self):
        for value in self.trusted_proxy_ips.split(","):
            if value.strip():
                ip_address(value.strip())
        match = re.match(r"^gpt-(\d+)(?:[.-]|$)", self.openai_model)
        if not match or int(match.group(1)) < 5:
            raise ValueError("OPENAI_MODEL must be GPT-5 or newer")
        if self.smtp_tls not in {"starttls", "ssl", "none"}:
            raise ValueError("SMTP_TLS must be starttls, ssl or none")
        if self.app_env not in {"development", "production"}:
            raise ValueError("APP_ENV must be development or production")
        if self.app_env == "production":
            if not self.cookie_secure or not self.public_url.startswith("https://"):
                raise ValueError("Production requires HTTPS PUBLIC_URL and COOKIE_SECURE=true")
            if not self.emails or not self.smtp_host or self.smtp_tls == "none":
                raise ValueError("Production requires allowed emails and encrypted SMTP")
        return self


@lru_cache
def get_settings():
    return Settings()
