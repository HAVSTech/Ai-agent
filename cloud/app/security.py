from __future__ import annotations

import hmac

from fastapi import Header, HTTPException


def _check(authorization: str | None, expected: str, name: str) -> None:
    if not expected:
        raise HTTPException(status_code=503, detail=f"{name} is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    supplied = authorization[7:].strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_agent_token(authorization: str | None = Header(default=None)) -> None:
    from .config import Settings
    _check(authorization, Settings.from_env().agent_api_token, "AGENT_API_TOKEN")


def require_command_token(authorization: str | None = Header(default=None)) -> None:
    from .config import Settings
    _check(authorization, Settings.from_env().command_api_token, "COMMAND_API_TOKEN")
