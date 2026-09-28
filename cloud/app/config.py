from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str
    agent_api_token: str
    command_api_token: str
    supabase_url: str
    supabase_secret_key: str
    gemini_api_key: str
    gemini_model: str
    max_command_length: int
    job_lease_seconds: int
    agent_stale_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        agent_token = os.getenv("AGENT_API_TOKEN") or os.getenv("AGENT_SHARED_TOKEN", "")
        command_token = os.getenv("COMMAND_API_TOKEN", "")
        supabase_secret = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        return cls(
            environment=os.getenv("ENVIRONMENT", "production").lower(),
            agent_api_token=agent_token,
            command_api_token=command_token,
            supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
            supabase_secret_key=supabase_secret,
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            max_command_length=int(os.getenv("MAX_COMMAND_LENGTH", "2000")),
            job_lease_seconds=int(os.getenv("JOB_LEASE_SECONDS", "900")),
            agent_stale_seconds=int(os.getenv("AGENT_STALE_SECONDS", "120")),
        )

    @property
    def database_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def validate_production(self) -> None:
        if self.environment != "production":
            return
        missing = []
        if not self.agent_api_token:
            missing.append("AGENT_API_TOKEN")
        if not self.command_api_token:
            missing.append("COMMAND_API_TOKEN")
        if not self.database_configured:
            missing.append("SUPABASE_URL/SUPABASE_SECRET_KEY")
        if not self.ai_configured:
            missing.append("GEMINI_API_KEY")
        if missing:
            raise RuntimeError("Missing production environment variables: " + ", ".join(missing))
