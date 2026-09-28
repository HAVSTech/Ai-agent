from __future__ import annotations

import tempfile
from pathlib import Path

import pythoncom
import win32com.client


class OfficeConverter:
    """Convert Word/Excel files to PDF using installed Microsoft Office."""

    def convert(self, source: Path) -> Path:
        suffix = source.suffix.lower()
        if suffix in {".doc", ".docx"}:
            return self._word_to_pdf(source)
        if suffix in {".xls", ".xlsx", ".xlsm"}:
            return self._excel_to_pdf(source)
        raise ValueError(f"Unsupported Office file: {source}")

    def _output_path(self, source: Path) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="ai-print-"))
        return directory / f"{source.stem}.pdf"

    def _word_to_pdf(self, source: Path) -> Path:
        pythoncom.CoInitialize()
        app = document = None
        output = self._output_path(source)
        try:
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            document = app.Documents.Open(
                str(source.resolve()),
                ReadOnly=True,
                AddToRecentFiles=False,
                ConfirmConversions=False,
                NoEncodingDialog=True,
            )
            document.ExportAsFixedFormat(str(output), 17)
            if not output.exists():
                raise RuntimeError("Word did not create the PDF")
            return output
        finally:
            if document is not None:
                try:
                    document.Close(SaveChanges=False)
                except Exception:
                    pass
            if app is not None:
                try:
                    app.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def _excel_to_pdf(self, source: Path) -> Path:
        pythoncom.CoInitialize()
        app = workbook = None
        output = self._output_path(source)
        try:
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            app.AskToUpdateLinks = False
            workbook = app.Workbooks.Open(
                str(source.resolve()),
                UpdateLinks=0,
                ReadOnly=True,
                IgnoreReadOnlyRecommended=True,
                AddToMru=False,
            )
            workbook.ExportAsFixedFormat(0, str(output))
            if not output.exists():
                raise RuntimeError("Excel did not create the PDF")
            return output
        finally:
            if workbook is not None:
                try:
                    workbook.Close(SaveChanges=False)
                except Exception:
                    pass
            if app is not None:
                try:
                    app.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def cleanup(self, pdf_path: Path) -> None:
        try:
            parent = pdf_path.parent
            pdf_path.unlink(missing_ok=True)
            if parent.name.startswith("ai-print-"):
                parent.rmdir()
        except OSError:
            pass
