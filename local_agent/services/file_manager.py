from __future__ import annotations

from pathlib import Path
from typing import Iterable


class FileManager:
    def __init__(self, allowed_roots: Iterable[str], max_files_per_job: int = 50) -> None:
        self.allowed_roots = [Path(p).expanduser().resolve() for p in allowed_roots]
        self.max_files_per_job = max_files_per_job

    def _validate_folder(self, folder: str) -> Path:
        path = Path(folder).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Folder does not exist: {path}")

        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return path
            except ValueError:
                continue

        raise PermissionError("Requested folder is outside the configured allowed roots")

    def list_files(
        self,
        folder: str,
        extensions: set[str] | None = None,
        exclude_contains: list[str] | None = None,
    ) -> list[Path]:
        root = self._validate_folder(folder)
        extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or set())}
        exclude_contains = [x.lower() for x in (exclude_contains or [])]

        files = []
        for path in root.iterdir():
            if not path.is_file():
                continue
            if extensions and path.suffix.lower() not in extensions:
                continue
            if any(token in path.name.lower() for token in exclude_contains):
                continue
            files.append(path)

        files.sort(key=lambda p: p.name.lower())

        if len(files) > self.max_files_per_job:
            raise ValueError(
                f"Found {len(files)} files, above the safety limit of {self.max_files_per_job}"
            )

        return files
