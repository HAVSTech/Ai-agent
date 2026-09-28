from __future__ import annotations

from pathlib import Path
from typing import Iterable


class FileManager:
    def __init__(self, allowed_roots: Iterable[str], max_files_per_job: int = 50) -> None:
        roots = [Path(p).expanduser().resolve() for p in allowed_roots]
        if not roots:
            raise ValueError("At least one allowed root is required")
        self.allowed_roots = roots
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
        recursive: bool = False,
        sort_order: str = "name",
    ) -> list[Path]:
        root = self._validate_folder(folder)
        normalized = {
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in (extensions or set())
        }
        exclusions = [x.lower() for x in (exclude_contains or [])]

        iterator = root.rglob("*") if recursive else root.iterdir()
        files: list[Path] = []
        for path in iterator:
            if not path.is_file():
                continue
            if normalized and path.suffix.lower() not in normalized:
                continue
            if any(token in path.name.lower() for token in exclusions):
                continue
            files.append(path)

        if sort_order == "modified":
            files.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))
        elif sort_order == "created":
            files.sort(key=lambda p: (p.stat().st_ctime, p.name.lower()))
        else:
            files.sort(key=lambda p: p.name.lower())

        if len(files) > self.max_files_per_job:
            raise ValueError(
                f"Found {len(files)} files, above the safety limit of {self.max_files_per_job}"
            )
        return files
