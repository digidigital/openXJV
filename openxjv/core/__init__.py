"""Core business logic modules for openXJV.

Migration Status:
    ✅ DatabaseManager - ACTIVELY USED in openXJV_modular.py (Phase 1 complete)
    ✅ OCRHandler - ACTIVELY USED in openXJV_modular.py (Phase 3 complete)
    ✅ pdf_operations - ACTIVELY USED in openXJV_modular.py (Phase 5 complete)
    ✅ PDFocr - Migrated from helperScripts/OCR.py
"""

from .database import DatabaseManager
from .ocr_handler import OCRHandler
from .ocr import PDFocr
from .pdf_operations import (
    PDFExportConfig,
    PDFExportError,
    export_pdf,
    export_notes_to_pdf,
)
from .pdf_cover_page_template import CreateDeckblatt

__all__ = [
    'DatabaseManager',
    'OCRHandler',
    'PDFocr',
    'PDFExportConfig',
    'PDFExportError',
    'export_pdf',
    'export_notes_to_pdf',
    'CreateDeckblatt',
]
