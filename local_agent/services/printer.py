from __future__ import annotations

from pathlib import Path
from typing import Any

from .office_converter import OfficeConverter
from .print_engine import WindowsPrintEngine


class WindowsPrinter:
    def __init__(self, printer_name: str | None = None, spool_wait_seconds: int = 120):
        if not printer_name:
            import win32print
            printer_name = win32print.GetDefaultPrinter()
        self.printer_name = printer_name
        self.engine = WindowsPrintEngine(printer_name, spool_wait_seconds)
        self.office = OfficeConverter()

    def printer_status(self) -> dict[str, Any]:
        import win32print
        handle = win32print.OpenPrinter(self.printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
            return {
                "name": self.printer_name,
                "status": info.get("Status", 0),
                "jobs": info.get("cJobs", 0),
                "port": info.get("pPortName"),
            }
        finally:
            win32print.ClosePrinter(handle)

    def print_file(self, path: Path, settings: dict[str, Any]) -> int:
        suffix = path.suffix.lower()
        pdf_path = path
        converted = False
        try:
            if suffix in {".doc", ".docx", ".xls", ".xlsx", ".xlsm"}:
                pdf_path = self.office.convert(path)
                converted = True
            elif suffix != ".pdf":
                raise ValueError(f"Unsupported print type: {suffix}")

            return self.engine.print_pdf(pdf_path, settings)
        finally:
            if converted:
                self.office.cleanup(pdf_path)
