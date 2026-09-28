from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from services.document_analyzer import DocumentAnalyzer
from services.file_manager import FileManager
from services.printer import WindowsPrinter
from services.queue_manager import JobStatus, PrintItem, PrintQueue

LOG = logging.getLogger("ai_print_agent")


class CloudTransport:
    def __init__(self, base_url: str, token: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )

    def heartbeat(self, agent_id: str) -> None:
        response = self.client.post(
            f"{self.base_url}/api/agents/heartbeat",
            json={"agent_id": agent_id},
        )
        response.raise_for_status()

    def claim_job(self, agent_id: str) -> dict[str, Any] | None:
        response = self.client.post(
            f"{self.base_url}/api/agents/jobs/claim",
            json={"agent_id": agent_id},
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json().get("job")

    def report(self, agent_id: str, job_id: str, status: str, result: Any = None, error: str | None = None) -> None:
        response = self.client.post(
            f"{self.base_url}/api/agents/jobs/report",
            json={
                "agent_id": agent_id,
                "job_id": job_id,
                "status": status,
                "result": result,
                "error": error,
            },
        )
        response.raise_for_status()


class PrintAgent:
    def __init__(self, config_path: str = "config.json") -> None:
        with open(config_path, "r", encoding="utf-8") as file:
            config = json.load(file)

        self.config = config
        self.agent_id = config["agent_id"]
        self.file_manager = FileManager(
            config["allowed_roots"],
            config.get("max_files_per_job", 10),
        )
        self.analyzer = DocumentAnalyzer()
        self.printer = WindowsPrinter(config.get("printer_name"))
        self.transport = CloudTransport(
            config["cloud_url"],
            config["agent_token"],
            config.get("request_timeout_seconds", 20),
        )

    def settings_for(self, path: Path, analysis: dict[str, Any]) -> dict[str, Any]:
        if path.suffix.lower() == ".pdf":
            orientation = analysis.get("orientation")
            return {
                "paper": "A4",
                "duplex": True,
                "edge": "short" if orientation == "landscape" else "long",
            }
        return {}

    def execute_job(self, job: dict[str, Any]) -> list[dict[str, Any]]:
        paths = self.file_manager.list_files(
            job["folder"],
            set(job.get("extensions", [".pdf"])),
            job.get("exclude_contains", []),
        )

        queue = PrintQueue()
        for path in paths:
            analysis = self.analyzer.analyze(path)
            queue.add(PrintItem(path=path, settings=self.settings_for(path, analysis)))

        queue.run(lambda item: self.printer.print_file(item.path, item.settings))

        return [
            {
                "file": str(item.path),
                "status": item.status.value,
                "settings": item.settings,
                "error": item.error,
            }
            for item in queue.items
        ]

    def run_forever(self) -> None:
        LOG.info("Starting local print agent: %s", self.agent_id)
        while True:
            try:
                self.transport.heartbeat(self.agent_id)
                job = self.transport.claim_job(self.agent_id)
                if job:
                    job_id = job["job_id"]
                    LOG.info("Claimed print job %s", job_id)
                    try:
                        result = self.execute_job(job)
                        failed = any(item["status"] == JobStatus.FAILED.value for item in result)
                        self.transport.report(
                            self.agent_id,
                            job_id,
                            "failed" if failed else "completed",
                            result=result,
                        )
                    except Exception as exc:
                        LOG.exception("Print job failed")
                        self.transport.report(
                            self.agent_id,
                            job_id,
                            "failed",
                            error=str(exc),
                        )
            except Exception:
                LOG.exception("Cloud communication failed")

            time.sleep(max(1, int(self.config.get("poll_seconds", 5))))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    PrintAgent().run_forever()


if __name__ == "__main__":
    main()
