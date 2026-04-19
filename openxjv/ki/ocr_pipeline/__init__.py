"""
ocr_pipeline – PDF OCR module (embedded in KI-Labor).

Usage::

    from ocr_pipeline import ocr_pdf

    result = ocr_pdf("document.pdf", dpi=200)
    print(result.text)
    print(result.summary())
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .engine import OcrEngine
from .renderer import render_pdf_pages
from .result import OcrResult, PageResult, PageStatus

__all__ = ["ocr_pdf", "OcrResult", "PageResult", "PageStatus", "OcrEngine"]

logger = logging.getLogger(__name__)

_PAGE_PARTIAL_THRESHOLD = 0.7
_PAGE_FAIL_RATIO = 0.3


def ocr_pdf(
    pdf_path: str,
    dpi: int = 200,
    engine: Optional[OcrEngine] = None,
) -> OcrResult:
    """
    Extract text from every page of a PDF via OCR.

    Args:
        pdf_path: Path to the PDF file.
        dpi:      Render resolution (default 200 DPI).
        engine:   Optional pre-initialised OcrEngine.  If None, a new engine
                  is created with bundled models and automatic provider selection.

    Returns:
        OcrResult with full text and per-page statistics.
    """
    pdf_path = str(pdf_path)
    if not Path(pdf_path).is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if engine is None:
        engine = OcrEngine()

    doc_warnings: list[str] = []
    page_results: list[PageResult] = []
    doc_texts: list[str] = []

    try:
        with render_pdf_pages(pdf_path, dpi=dpi) as pages:
            for page_idx, image in pages:
                page_no = page_idx + 1
                text, avg_conf, block_count, page_warnings = engine.run(image)
                doc_warnings.extend(f"Page {page_no}: {w}" for w in page_warnings)

                if block_count == 0:
                    status = PageStatus.FAILED
                elif avg_conf < _PAGE_PARTIAL_THRESHOLD:
                    low = sum(1 for w in page_warnings if w.startswith("Low"))
                    ratio_ok = 1.0 - (low / block_count)
                    status = PageStatus.PARTIAL if ratio_ok >= _PAGE_FAIL_RATIO else PageStatus.FAILED
                else:
                    status = PageStatus.SUCCESS

                if status == PageStatus.FAILED and not page_warnings:
                    doc_warnings.append(f"Page {page_no}: No text detected")

                page_results.append(PageResult(
                    page_number=page_no,
                    status=status,
                    text=text,
                    avg_confidence=avg_conf,
                    block_count=block_count,
                ))
                doc_texts.append(text)

    except Exception as exc:
        logger.error("OCR rendering/inference error: %s", exc, exc_info=True)
        doc_warnings.append(f"Rendering error: {exc}")

    full_text = "\n\n".join(t for t in doc_texts if t)

    failed = [p for p in page_results if p.status == PageStatus.FAILED]
    if failed and len(failed) == len(page_results):
        doc_warnings.insert(0, "OCR failed on ALL pages — check image quality or DPI")
    elif failed:
        nums = ", ".join(str(p.page_number) for p in failed)
        doc_warnings.insert(0, f"OCR failed on page(s): {nums}")

    return OcrResult(
        text=full_text,
        page_results=page_results,
        warnings=doc_warnings,
    )
