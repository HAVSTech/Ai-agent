from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

app = FastAPI(title="AI Print Agent Cloud API", version="0.2.0")

EXPECTED_TOKEN = os.getenv("AGENT_SHARED_TOKEN", "")
LOCK = threading.Lock()
AGENTS: dict[str, dict[str, Any]] = {}
JOBS: dict[str, dict[str, Any]] = {}


def check_auth(authorization: str | None) -> None:
    if not EXPECTED_TOKEN:
        raise HTTPException(500, "AGENT_SHARED_TOKEN is not configured")
    if authorization != f"Bearer {EXPECTED_TOKEN}":
        raise HTTPException(401, "Unauthorized")


class AgentRequest(BaseModel):
    agent_id: str = Field(min_length=3, max_length=120)


class CreateJob(BaseModel):
    agent_id: str
    folder: str
    extensions: list[str] = Field(default_factory=lambda: [".pdf"])
    exclude_contains: list[str] = Field(default_factory=list)


class ReportJob(BaseModel):
    agent_id: str
    job_id: str
    status: str
    result: Any = None
    error: str | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/agents/heartbeat")
def heartbeat(body: AgentRequest, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    with LOCK:
        AGENTS[body.agent_id] = {"last_seen": datetime.now(timezone.utc).isoformat()}
    return {"ok": True, "agent_id": body.agent_id}


@app.post("/api/jobs")
def create_job(body: CreateJob, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    with LOCK:
        if body.agent_id not in AGENTS:
            raise HTTPException(400, "Agent has not connected yet")
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            **body.model_dump(),
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        JOBS[job_id] = job
    return {"job": job}


@app.post("/api/agents/jobs/claim")
def claim_job(body: AgentRequest, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    with LOCK:
        if body.agent_id not in AGENTS:
            raise HTTPException(400, "Unknown agent")
        for job in JOBS.values():
            if job["agent_id"] == body.agent_id and job["status"] == "queued":
                job["status"] = "processing"
                return {"job": job}
    return Response(status_code=204)


@app.post("/api/agents/jobs/report")
def report_job(body: ReportJob, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    with LOCK:
        job = JOBS.get(body.job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job["agent_id"] != body.agent_id:
            raise HTTPException(403, "Agent does not own this job")
        job["status"] = body.status
        job["result"] = body.result
        job["error"] = body.error
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
    return {"ok": True}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {"job": job}
