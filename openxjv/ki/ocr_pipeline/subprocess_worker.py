"""
OCR-Subprocess-Worker für multiprocessing (spawn).

Läuft in einem eigenen Python-Prozess, vollständig isoliert von Qt und
llama_cpp, um Threading-Konflikte mit OpenMP / onnxruntime zu vermeiden.

Kommunikationsprotokoll (multiprocessing.Queue):
  ("progress", nachricht: str)          — Statusmeldung
  ("result",   text: str,
               summary: str,
               warnings: list[str],
               page1_conf: float)       — Erfolg
  ("error",    nachricht: str)          — fataler Fehler
"""
from __future__ import annotations

# Nachrichtentypen (werden vom Aufrufer importiert)
PROGRESS = "progress"
RESULT   = "result"
ERROR    = "error"


def run(pdf_path: str, dpi: int, queue, debug: bool = False) -> None:
    """
    Einstiegspunkt für den OCR-Subprozess.

    Muss eine Top-Level-Funktion sein, damit multiprocessing sie für den
    spawn-Startmodus picken kann.  Niemals als Methode oder Closure verwenden.
    """
    import logging
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.CRITICAL,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        queue.put((PROGRESS, "OCR: Initialisiere Engine …"))

        from .engine import OcrEngine, _detect_provider
        from . import ocr_pdf

        detected = _detect_provider()
        queue.put((PROGRESS, f"OCR: Inferenz-Backend: {detected}"))

        engine = OcrEngine()
        actual = engine.active_provider
        if actual != detected:
            queue.put((PROGRESS,
                f"OCR: Fallback auf {actual} (angefordert: {detected})."))

        import pypdfium2 as _pdfium
        _doc = _pdfium.PdfDocument(pdf_path)
        n_pages_est = len(_doc)
        _doc.close()

        queue.put((PROGRESS,
            f"OCR: Starte Erkennung (Provider: {actual}, DPI: {dpi}, {n_pages_est} Seite(n)) …"))

        import time
        t0 = time.monotonic()
        result = ocr_pdf(pdf_path, dpi=dpi, engine=engine)
        elapsed = time.monotonic() - t0

        n_pages = len(result.page_results)
        avg_per_page = elapsed / n_pages if n_pages else 0.0
        queue.put((PROGRESS,
            f"OCR: Gesamtzeit {elapsed:.1f} s  |  "
            f"Ø {avg_per_page:.1f} s/Seite  |  {n_pages} Seite(n)"))

        page1_conf = (
            result.page_results[0].avg_confidence
            if result.page_results else -1.0
        )
        queue.put((RESULT, result.text, result.summary(),
                   result.warnings, page1_conf))

    except Exception as exc:
        import traceback
        queue.put((ERROR, f"{exc}\n{traceback.format_exc()}"))
