from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pymupdf
import win32con
import win32gui
import win32print
import win32ui
from PIL import ImageWin


PAPER_CODES = {"A4": win32con.DMPAPER_A4, "Legal": win32con.DMPAPER_LEGAL}
DUPLEX_CODES = {"long": win32con.DMDUP_VERTICAL, "short": win32con.DMDUP_HORIZONTAL}
TERMINAL_JOB_FLAGS = (
    win32print.JOB_STATUS_COMPLETE
    | win32print.JOB_STATUS_PRINTED
    | win32print.JOB_STATUS_DELETED
)


class WindowsPrintEngine:
    """Render PDF pages through a Windows printer DC with per-job DEVMODE settings."""

    def __init__(self, printer_name: str, spool_wait_seconds: int = 120):
        self.printer_name = printer_name
        self.spool_wait_seconds = max(5, spool_wait_seconds)

    def _devmode(self, paper: str, duplex: bool, edge: str, orientation: str):
        handle = win32print.OpenPrinter(self.printer_name)
        try:
            dm = win32print.GetPrinter(handle, 2)["pDevMode"]
            if paper in PAPER_CODES:
                dm.PaperSize = PAPER_CODES[paper]
                dm.Fields |= win32con.DM_PAPERSIZE

            dm.Orientation = (
                win32con.DMORIENT_LANDSCAPE
                if orientation == "landscape"
                else win32con.DMORIENT_PORTRAIT
            )
            dm.Fields |= win32con.DM_ORIENTATION

            dm.Duplex = (
                DUPLEX_CODES.get(edge, win32con.DMDUP_VERTICAL)
                if duplex
                else win32con.DMDUP_SIMPLEX
            )
            dm.Fields |= win32con.DM_DUPLEX

            win32print.DocumentProperties(
                0,
                handle,
                self.printer_name,
                dm,
                dm,
                win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER,
            )
            return dm
        finally:
            win32print.ClosePrinter(handle)

    def _fit_rect(self, dc, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
        page_w = dc.GetDeviceCaps(win32con.HORZRES)
        page_h = dc.GetDeviceCaps(win32con.VERTRES)
        src_w, src_h = image_size
        scale = min(page_w / src_w, page_h / src_h)
        dst_w = max(1, int(src_w * scale))
        dst_h = max(1, int(src_h * scale))
        left = max(0, (page_w - dst_w) // 2)
        top = max(0, (page_h - dst_h) // 2)
        return left, top, left + dst_w, top + dst_h

    def _wait_for_spooler(self, job_id: int) -> None:
        deadline = time.monotonic() + self.spool_wait_seconds
        handle = win32print.OpenPrinter(self.printer_name)
        try:
            while time.monotonic() < deadline:
                try:
                    info = win32print.GetJob(handle, job_id, 1)
                    status = int(info.get("Status", 0))
                    if status & (win32print.JOB_STATUS_ERROR | win32print.JOB_STATUS_OFFLINE | win32print.JOB_STATUS_PAPEROUT | win32print.JOB_STATUS_USER_INTERVENTION):
                        raise RuntimeError(f"Printer job {job_id} entered error state: {status}")
                    if status & TERMINAL_JOB_FLAGS:
                        return
                except Exception as exc:
                    # The spooler can remove a successfully submitted job before
                    # the next GetJob call. Treat a missing job as completion.
                    if "The system cannot find the file specified" in str(exc) or "not found" in str(exc).lower():
                        return
                    if isinstance(exc, RuntimeError):
                        raise
                time.sleep(1)
        finally:
            win32print.ClosePrinter(handle)

        raise TimeoutError(f"Printer job {job_id} did not leave the spooler within {self.spool_wait_seconds} seconds")

    def print_pdf(self, pdf_path: Path, settings: dict[str, Any]) -> int:
        paper = settings.get("paper") or "A4"
        duplex = bool(settings.get("duplex", False))
        edge = settings.get("edge") or "long"
        copies = int(settings.get("copies", 1))

        if paper not in PAPER_CODES:
            raise ValueError(f"Unsupported paper size: {paper}")
        if duplex and edge not in DUPLEX_CODES:
            raise ValueError(f"Unsupported duplex edge: {edge}")
        if copies < 1 or copies > 20:
            raise ValueError("Copies must be between 1 and 20")

        with pymupdf.open(pdf_path) as document:
            if len(document) == 0:
                raise ValueError("PDF contains no pages")

            orientations = {
                "landscape" if page.rect.width > page.rect.height else "portrait"
                for page in document
            }
            if len(orientations) > 1:
                raise ValueError("Mixed-orientation PDFs are not supported by the current duplex renderer")

            orientation = next(iter(orientations))
            dm = self._devmode(paper, duplex, edge, orientation)
            hdc = win32gui.CreateDC("WINSPOOL", self.printer_name, dm)
            dc = win32ui.CreateDCFromHandle(hdc)

            try:
                job_id = dc.StartDoc(pdf_path.name)
                try:
                    for _ in range(copies):
                        for page in document:
                            dc.StartPage()
                            pix = page.get_pixmap(dpi=150, alpha=False)
                            image = pix.pil_image().convert("RGB")
                            rect = self._fit_rect(dc, image.size)
                            ImageWin.Dib(image).draw(dc.GetHandleOutput(), rect)
                            dc.EndPage()
                    dc.EndDoc()
                except Exception:
                    try:
                        dc.AbortDoc()
                    except Exception:
                        pass
                    raise
            finally:
                dc.DeleteDC()

            self._wait_for_spooler(int(job_id))
            return int(job_id)
