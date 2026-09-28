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

AGENT_VERSION = "1.0.0"
LOG = logging.getLogger("ai_print_agent")


class CloudTransport:
    def __init__(self, base_url: str, token: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"Authorization": f"Bearer {token}"},
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.request(method, url, **kwargs)
                if response.status_code >= 500 and attempt < 2:
                    time.sleep(0.5 * (2**attempt))
                    continue
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"Cloud request failed: {last_error}")

    def heartbeat(self, agent_id: str, capabilities: dict[str, Any]) -> None:
        response = self._request(
            "POST",
            f"{self.base_url}/api/agents/heartbeat",
            json={
                "agent_id": agent_id,
                "agent_version": AGENT_VERSION,
                "capabilities": capabilities,
            },
        )
        response.raise_for_status()

    def claim_job(self, agent_id: str) -> dict[str, Any] | None:
        response = self._request(
            "POST",
            f"{self.base_url}/api/agents/jobs/claim",
            json={"agent_id": agent_id},
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json().get("job")

    def report(
        self,
        agent_id: str,
        job_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        response = self._request(
            "POST",
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
        config_file = Path(config_path).resolve()
        with config_file.open("r", encoding="utf-8") as file:
            config = json.load(file)

        required = ["agent_id", "cloud_url", "agent_token", "allowed_roots"]
        missing = [key for key in required if not config.get(key)]
        if missing:
            raise ValueError(f"Missing required config fields: {', '.join(missing)}")

        self.config = config
        self.agent_id = config["agent_id"]
        self.file_manager = FileManager(
            config["allowed_roots"],
            int(config.get("max_files_per_job", 50)),
        )
        self.analyzer = DocumentAnalyzer()
        self.printer = WindowsPrinter(
            config.get("printer_name"),
            int(config.get("spool_wait_seconds", 120)),
        )
        self.transport = CloudTransport(
            config["cloud_url"],
            config["agent_token"],
            float(config.get("request_timeout_seconds", 20)),
        )
        self.poll_seconds = max(1, int(config.get("poll_seconds", 5)))
        self.heartbeat_interval = max(10, int(config.get("heartbeat_interval_seconds", 30)))
        self.last_heartbeat = 0.0

    def capabilities(self) -> dict[str, Any]:
        return {
            "platform": "windows",
            "pdf": True,
            "word": True,
            "excel": True,
            "supported_extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm"],
            "printer": self.printer.printer_name,
            "job_settings": ["A4", "Legal", "simplex", "duplex-long", "duplex-short"],
        }

    def settings_for(
        self,
        path: Path,
        analysis: dict[str, Any],
        requested: dict[str, Any],
    ) -> dict[str, Any]:
        suffix = path.suffix.lower()
        rules = self.config.get("default_print_rules", {})

        if suffix == ".pdf":
            defaults = rules.get("pdf", {})
        elif suffix in {".xlsx", ".xls", ".xlsm"}:
            defaults = rules.get("xlsx", {})
        elif suffix in {".doc", ".docx"}:
            defaults = rules.get("docx", {})
        else:
            defaults = {}

        paper = requested.get("paper")
        if not paper or paper == "auto":
            paper = defaults.get("paper", "A4")

        duplex = requested.get("duplex")
        if duplex is None:
            duplex = defaults.get("duplex", False)

        edge = requested.get("edge")
        if not edge or edge == "auto":
            if analysis.get("orientation") == "landscape":
                edge = defaults.get("landscape_edge", defaults.get("edge", "short"))
            else:
                edge = defaults.get("portrait_edge", defaults.get("edge", "long"))

        return {
            "paper": paper,
            "duplex": bool(duplex),
            "edge": edge,
            "copies": int(requested.get("copies", 1)),
        }

    def execute_job(self, job: dict[str, Any]) -> list[dict[str, Any]]:
        paths = self.file_manager.list_files(
            job["folder"],
            set(job.get("extensions", [".pdf"])),
            job.get("exclude_contains", []),
            recursive=bool(job.get("recursive", False)),
            sort_order=job.get("sort_order", "name"),
        )
        if not paths:
            raise ValueError("No matching files were found")

        requested = job.get("settings") or {}
        queue = PrintQueue()

        for path in paths:
            analysis = self.analyzer.analyze(path)
            settings = self.settings_for(path, analysis, requested)
            queue.add(PrintItem(path=path, settings=settings))

        queue.run(lambda item: self.printer.print_file(item.path, item.settings))

        return [
            {
                "file": str(item.path),
                "status": item.status.value,
                "settings": item.settings,
                "printer_job_id": item.printer_job_id,
                "error": item.error,
            }
            for item in queue.items
        ]

    def run_forever(self) -> None:
        LOG.info("Starting local print agent: %s v%s", self.agent_id, AGENT_VERSION)
        try:
            while True:
                try:
                    now = time.monotonic()
                    if now - self.last_heartbeat >= self.heartbeat_interval:
                        self.transport.heartbeat(self.agent_id, self.capabilities())
                        self.last_heartbeat = now

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
                                error="One or more files failed" if failed else None,
                            )
                            LOG.info("Finished print job %s", job_id)
                        except Exception as exc:
                            LOG.exception("Print job %s failed", job_id)
                            try:
                                self.transport.report(
                                    self.agent_id,
                                    job_id,
                                    "failed",
                                    error=str(exc),
                                )
                            except Exception:
                                LOG.exception("Could not report failed job %s", job_id)
                except Exception:
                    LOG.exception("Agent loop error")

                time.sleep(self.poll_seconds)
        finally:
            self.transport.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    PrintAgent().run_forever()


if __name__ == "__main__":
    main()
