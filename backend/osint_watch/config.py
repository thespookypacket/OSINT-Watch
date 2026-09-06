from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WATCH_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://watch:watch@localhost:5432/watch"
    gis_password: str = ""
    admin_username: str = "admin"
    admin_password: str = ""
    public_url: str = "http://localhost:8080"
    secure_cookies: bool = False
    firms_key: str = ""
    user_agent: str = "OSINT-Watch/0.1 (self-hosted public hazard monitor)"
    source_config: str = "config/sources.yaml"
    raw_retention_days: int = 7
    retention_days: int = 90
    ollama_url: str = ""
    ollama_model: str = "qwen2.5:3b"
    spiderfoot_url: str = ""
    spiderfoot_token: str = ""
    # Outgoing user-configured feeds and webhooks must be public unless explicitly allowed.
    allowed_outbound_hosts: str = ""
    basemap_url: str = "https://tiles.openfreemap.org/styles/liberty"
    netbox_url: str = ""
    netbox_token: str = ""
    netbox_interval_seconds: int = Field(default=3600, ge=0, le=86400)
    job_kinds: str = "collect,webhook,netbox"


@lru_cache
def settings() -> Settings:
    return Settings()
