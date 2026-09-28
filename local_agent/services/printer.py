from __future__ import annotations

import os
import subprocess
from pathlib import Path

try:
    import win32print
except ImportError:  # pragma: no cover
    win32print = None


class WindowsPrinter:
    def __init__(self, printer_name: str | None = None) -> None:
        self.printer_name = printer_name or self.default_printer()

    @staticmethod
    def default_printer() -> str:
        if win32print is None:
            return "DEFAULT"
        return win32print.GetDefaultPrinter()

    def printer_status(self) -> dict:
        return {
            "name": self.printer_name,
            "platform": os.name,
            "ready_check": "basic",
        }

    def print_file(self, path: Path, settings: dict) -> None:
        if os.name != "nt":
            raise RuntimeError("The print engine must run on Windows")

        # MVP: ask Windows to use the installed application's default print action.
        # We intentionally keep this simple until printer-specific settings are
        # verified against the Brother driver installed on the target machine.
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Start-Process", "-FilePath", str(path), "-Verb", "PrintTo",
             "-ArgumentList", self.printer_name],
            check=True,
        )
