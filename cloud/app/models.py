from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


FileExtension = Literal[".pdf", ".docx", ".doc", ".xlsx", ".xls", ".xlsm", ".csv", ".txt", ".png", ".jpg", ".jpeg"]
PaperSize = Literal["auto", "A4", "Legal"]
Edge = Literal["auto", "long", "short"]
SortOrder = Literal["name", "modified", "created"]


class AgentHeartbeat(BaseModel):
    agent_id: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    agent_version: str = Field(default="unknown", max_length=40)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class AgentRequest(BaseModel):
    agent_id: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")


class PrintSettings(BaseModel):
    paper: PaperSize = "auto"
    duplex: bool | None = None
    edge: Edge = "auto"
    copies: int = Field(default=1, ge=1, le=20)


class CreateJob(BaseModel):
    agent_id: str = Field(min_length=3, max_length=120)
    folder: str = Field(min_length=1, max_length=4000)
    extensions: list[FileExtension] = Field(default_factory=lambda: [".pdf"])
    exclude_contains: list[str] = Field(default_factory=list, max_length=50)
    recursive: bool = False
    sort_order: SortOrder = "name"
    settings: PrintSettings = Field(default_factory=PrintSettings)
    idempotency_key: str | None = Field(default=None, max_length=200)

    @field_validator("extensions")
    @classmethod
    def normalize_extensions(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(v.lower() for v in values))


class CommandRequest(BaseModel):
    agent_id: str = Field(min_length=3, max_length=120)
    command: str = Field(min_length=1, max_length=2000)
    folder_hint: str | None = Field(default=None, max_length=4000)
    idempotency_key: str | None = Field(default=None, max_length=200)


class ReportJob(BaseModel):
    agent_id: str = Field(min_length=3, max_length=120)
    job_id: str
    status: Literal["completed", "failed", "cancelled"]
    result: Any = None
    error: str | None = Field(default=None, max_length=4000)


class PrintIntent(BaseModel):
    folder: str | None = Field(default=None, max_length=4000)
    extensions: list[FileExtension] = Field(default_factory=lambda: [".pdf"])
    exclude_contains: list[str] = Field(default_factory=list)
    recursive: bool = False
    sort_order: SortOrder = "name"
    paper: PaperSize = "auto"
    duplex: bool | None = None
    edge: Edge = "auto"
    copies: int = Field(default=1, ge=1, le=20)
    clarification_needed: bool = False
    clarification: str | None = None


class Job(BaseModel):
    job_id: str
    agent_id: str
    folder: str
    extensions: list[str]
    exclude_contains: list[str]
    recursive: bool
    sort_order: str
    settings: dict[str, Any]
    status: str
    created_at: str
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    attempts: int = 0
    result: Any = None
    error: str | None = None
