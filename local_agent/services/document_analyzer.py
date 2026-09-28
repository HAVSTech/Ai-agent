from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import pymupdf
except ImportError:  # pragma: no cover
    pymupdf = None


def _pdf_orientation(width: float, height: float) -> str:
    return "landscape" if width > height else "portrait"


class DocumentAnalyzer:
    def analyze(self, path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._analyze_pdf(path)

        return {
            "file": str(path),
            "extension": suffix,
            "pages": None,
            "orientation": None,
        }

    def _analyze_pdf(self, path: Path) -> dict[str, Any]:
        if pymupdf is None:
            raise RuntimeError("PyMuPDF is required for PDF analysis")

        with pymupdf.open(path) as document:
            pages = len(document)
            if pages:
                rect = document[0].rect
                orientation = _pdf_orientation(rect.width, rect.height)
                width = round(rect.width, 2)
                height = round(rect.height, 2)
            else:
                orientation = None
                width = height = None

        return {
            "file": str(path),
            "extension": ".pdf",
            "pages": pages,
            "orientation": orientation,
            "width_points": width,
            "height_points": height,
        }
