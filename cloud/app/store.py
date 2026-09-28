from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings


class StoreError(RuntimeError):
    pass


class SupabaseStore:
    def __init__(self, settings: Settings):
        if not settings.database_configured:
            raise StoreError("Supabase database is not configured")
        self.base = f"{settings.supabase_url}/rest/v1"
        self.headers = {
            "apikey": settings.supabase_secret_key,
            "Authorization": f"Bearer {settings.supabase_secret_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.Client(timeout=15.0, headers=self.headers)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.client.request(method, f"{self.base}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise StoreError(f"Database request failed: {exc}") from exc
        if response.status_code >= 400:
            raise StoreError(f"Supabase {response.status_code}: {response.text[:1000]}")
        return response

    def health(self) -> bool:
        self._request("GET", "/agents?select=agent_id&limit=1")
        return True

    def heartbeat(self, agent_id: str, agent_version: str, capabilities: dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self._request(
            "POST",
            "/agents?on_conflict=agent_id",
            headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={
                "agent_id": agent_id,
                "agent_version": agent_version,
                "capabilities": capabilities,
                "last_seen": timestamp,
                "status": "online",
                "updated_at": timestamp,
            },
        )

    def agent_exists(self, agent_id: str) -> bool:
        value = quote(agent_id, safe="")
        response = self._request("GET", f"/agents?select=agent_id&agent_id=eq.{value}&limit=1")
        return bool(response.json())

    def create_job(self, job: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/jobs",
            headers={**self.headers, "Prefer": "return=representation"},
            json=job,
        )
        rows = response.json()
        if not rows:
            raise StoreError("Job was created but no row was returned")
        return rows[0]

    def find_by_idempotency(self, agent_id: str, key: str) -> dict[str, Any] | None:
        agent = quote(agent_id, safe="")
        encoded = quote(key, safe="")
        response = self._request(
            "GET",
            f"/jobs?select=*&agent_id=eq.{agent}&idempotency_key=eq.{encoded}&limit=1",
        )
        rows = response.json()
        return rows[0] if rows else None

    def claim_job(self, agent_id: str, lease_seconds: int) -> dict[str, Any] | None:
        response = self._request(
            "POST",
            "/rpc/claim_next_job",
            json={"p_agent_id": agent_id, "p_lease_seconds": lease_seconds},
        )
        data = response.json()
        if not data:
            return None
        return data[0] if isinstance(data, list) else data

    def report_job(self, agent_id: str, job_id: str, status: str, result: Any, error: str | None) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self._request(
            "PATCH",
            f"/jobs?id=eq.{quote(job_id, safe='')}&agent_id=eq.{quote(agent_id, safe='')}",
            headers={**self.headers, "Prefer": "return=minimal"},
            json={
                "status": status,
                "result": result,
                "error": error,
                "completed_at": timestamp,
                "updated_at": timestamp,
                "locked_at": None,
            },
        )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            f"/jobs?select=*&id=eq.{quote(job_id, safe='')}&limit=1",
        )
        rows = response.json()
        return rows[0] if rows else None
