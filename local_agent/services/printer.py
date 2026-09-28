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

        # Windows PowerShell needs paths containing spaces to be quoted.
        # Use single-quoted PowerShell literals and escape embedded apostrophes.
        file_path = str(path).replace("'", "''")
        printer_name = self.printer_name.replace("'", "''")

        command = (
            f"Start-Process -FilePath '{file_path}' "
            f"-Verb PrintTo -ArgumentList @('{printer_name}') "
            f"-PassThru | ForEach-Object {{ $_.WaitForExit() }}"
        )

        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            check=True,
        )
