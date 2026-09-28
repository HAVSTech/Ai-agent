from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


class JobStatus(str, Enum):
    QUEUED = "queued"
    PRINTING = "printing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PrintItem:
    path: Path
    settings: dict
    status: JobStatus = JobStatus.QUEUED
    error: str | None = None


@dataclass
class PrintQueue:
    items: list[PrintItem] = field(default_factory=list)

    def add(self, item: PrintItem) -> None:
        self.items.append(item)

    def run(self, print_one: Callable[[PrintItem], None]) -> None:
        for item in self.items:
            if item.status == JobStatus.CANCELLED:
                continue

            item.status = JobStatus.PRINTING
            try:
                print_one(item)
                item.status = JobStatus.COMPLETED
            except Exception as exc:
                item.status = JobStatus.FAILED
                item.error = str(exc)
                break
