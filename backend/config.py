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
    neo4j_uri: str = "bolt://127.0.0.1:7687"
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
    openai_timeout: float = Field(default=45, ge=1, le=180)
    openai_max_output_tokens: int = Field(default=2000, ge=128, le=10000)
    footprint_assist_max_output_tokens: int = Field(default=6000, ge=1000, le=10000)
    footprint_assist_concurrency: int = Field(default=2, ge=1, le=4)
    ai_user_concurrency: int = Field(default=1, ge=1, le=10)
    ai_global_concurrency: int = Field(default=2, ge=1, le=10)
    conversation_history_limit: int = Field(default=12, ge=2, le=50)
    conversation_evidence_limit: int = Field(default=8, ge=1, le=20)
    conversation_summary_trigger: int = Field(default=12, ge=4, le=50)
    conversation_summary_chars_trigger: int = Field(default=12000, ge=2000, le=50000)
    conversation_prompt_max_chars: int = Field(default=24000, ge=18000, le=50000)
    vision_model: str = ""
    media_root: str = "data/media"
    media_upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    media_max_pixels: int = Field(default=50_000_000, ge=1_000_000, le=100_000_000)
    media_max_dimension: int = Field(default=2048, ge=512, le=4096)
    media_image_max_bytes: int = Field(default=512 * 1024, ge=16 * 1024)
    media_thumbnail_max_bytes: int = Field(default=64 * 1024, ge=1024)
    media_user_quota_bytes: int = Field(default=250 * 1024 * 1024, ge=1024)
    media_global_quota_bytes: int = Field(default=5 * 1024 * 1024 * 1024, ge=1024)
    media_poll_seconds: float = Field(default=3, ge=0.1, le=300)
    media_orphan_seconds: int = Field(default=3600, ge=60)
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_revision: str = Field(
        default="614241f622f53c4eeff9890bdc4f31cfecc418b3", pattern=r"^[0-9a-f]{40}$"
    )
    embedding_model_dir: str = "data/models/multilingual-e5-small"
    embedding_poll_seconds: float = Field(default=3, ge=0.1, le=300)
    embedding_retry_seconds: float = Field(default=60, ge=1, le=3600)
    retrieval_top_k: int = Field(default=50, ge=1, le=200)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    relation_weight: float = Field(default=0.5, ge=0, le=1)
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
        if self.vision_model:
            vision_match = re.match(r"^gpt-(\d+)(?:[.-]|$)", self.vision_model)
            if not vision_match or int(vision_match.group(1)) < 5:
                raise ValueError("VISION_MODEL must be GPT-5 or newer")
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
