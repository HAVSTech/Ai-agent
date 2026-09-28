from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Response

from .ai import PrintPlanner
from .config import Settings
from .models import AgentHeartbeat, AgentRequest, CommandRequest, CreateJob, ReportJob
from .security import require_agent_token, require_command_token
from .store import StoreError, SupabaseStore

LOG = logging.getLogger("ai_print_cloud")
app = FastAPI(title="AI Print Agent Cloud API", version="1.0.0")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_store() -> SupabaseStore:
    try:
        return SupabaseStore(Settings.from_env())
    except StoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict:
    current = Settings.from_env()
    db_ok = False
    if current.database_configured:
        try:
            db_ok = get_store().health()
        except Exception:
            db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "ai-print-agent-cloud",
        "database": db_ok,
        "ai_configured": current.ai_configured,
        "environment": current.environment,
        "timestamp": now_iso(),
    }


@app.post("/api/agents/heartbeat")
def heartbeat(
    body: AgentHeartbeat,
    _: None = Depends(require_agent_token),
) -> dict:
    try:
        get_store().heartbeat(body.agent_id, body.agent_version, body.capabilities)
    except StoreError as exc:
        LOG.exception("Heartbeat failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "agent_id": body.agent_id, "server_time": now_iso()}


@app.post("/api/jobs")
def create_job(
    body: CreateJob,
    _: None = Depends(require_command_token),
) -> dict:
    db = get_store()
    if not db.agent_exists(body.agent_id):
        raise HTTPException(status_code=400, detail="Agent has not connected yet")

    if body.idempotency_key:
        existing = db.find_by_idempotency(body.agent_id, body.idempotency_key)
        if existing:
            return {"job": existing, "deduplicated": True}

    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "agent_id": body.agent_id,
        "folder": body.folder,
        "extensions": body.extensions,
        "exclude_contains": body.exclude_contains,
        "recursive": body.recursive,
        "sort_order": body.sort_order,
        "settings": body.settings.model_dump(),
    }
    row = db.create_job({
        "id": job_id,
        "agent_id": body.agent_id,
        "status": "queued",
        "payload": payload,
        "idempotency_key": body.idempotency_key,
    })
    return {"job": row, "deduplicated": False}


@app.post("/api/commands")
def command(
    body: CommandRequest,
    _: None = Depends(require_command_token),
) -> dict:
    current = Settings.from_env()
    if len(body.command) > current.max_command_length:
        raise HTTPException(status_code=413, detail="Command is too long")

    db = get_store()
    if not db.agent_exists(body.agent_id):
        raise HTTPException(status_code=400, detail="Agent has not connected yet")

    try:
        intent = PrintPlanner(current).plan(body.command, body.folder_hint)
    except Exception as exc:
        LOG.exception("AI planning failed")
        raise HTTPException(status_code=502, detail=f"AI planning failed: {exc}") from exc

    if intent.clarification_needed or not intent.folder:
        return {
            "status": "clarification_required",
            "message": intent.clarification or "Please provide the folder to print from.",
            "plan": intent.model_dump(),
        }

    if body.idempotency_key:
        existing = db.find_by_idempotency(body.agent_id, body.idempotency_key)
        if existing:
            return {"status": "queued", "job": existing, "deduplicated": True, "plan": intent.model_dump()}

    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "agent_id": body.agent_id,
        "folder": intent.folder,
        "extensions": intent.extensions,
        "exclude_contains": intent.exclude_contains,
        "recursive": intent.recursive,
        "sort_order": intent.sort_order,
        "settings": {
            "paper": intent.paper,
            "duplex": intent.duplex,
            "edge": intent.edge,
            "copies": intent.copies,
        },
        "source_command": body.command,
    }
    row = db.create_job({
        "id": job_id,
        "agent_id": body.agent_id,
        "status": "queued",
        "payload": payload,
        "idempotency_key": body.idempotency_key,
    })
    return {"status": "queued", "job": row, "plan": intent.model_dump(), "deduplicated": False}


@app.post("/api/agents/jobs/claim")
def claim_job(
    body: AgentRequest,
    _: None = Depends(require_agent_token),
) -> Response:
    current = Settings.from_env()
    try:
        job = get_store().claim_job(body.agent_id, current.job_lease_seconds)
    except StoreError as exc:
        LOG.exception("Job claim failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not job:
        return Response(status_code=204)
    return {"job": job}


@app.post("/api/agents/jobs/report")
def report_job(
    body: ReportJob,
    _: None = Depends(require_agent_token),
) -> dict:
    try:
        get_store().report_job(body.agent_id, body.job_id, body.status, body.result, body.error)
    except StoreError as exc:
        LOG.exception("Job report failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: str,
    _: None = Depends(require_command_token),
) -> dict:
    try:
        job = get_store().get_job(job_id)
    except StoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}
