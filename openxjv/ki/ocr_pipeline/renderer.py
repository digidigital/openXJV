"""
PDF-to-image renderer using pypdfium2.

Each page is rendered at the specified DPI and returned as a numpy array
(H x W x 3, uint8, RGB) suitable for direct use with RapidOCR.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Iterator, Tuple

import numpy as np

try:
    import pypdfium2 as pdfium
except ImportError as exc:  # pragma: no cover
    raise ImportError("pypdfium2 is required: pip install pypdfium2") from exc


@contextmanager
def render_pdf_pages(
    pdf_path: str,
    dpi: int = 200,
) -> Generator[Iterator[Tuple[int, np.ndarray]], None, None]:
    """
    Context manager that yields an iterator of (page_index, image_array) tuples.

    Pages are rendered one at a time so each bitmap is freed immediately after
    the caller processes it — avoiding holding all page images in RAM at once.
    """
    scale = dpi / 72.0
    doc = pdfium.PdfDocument(pdf_path)
    try:
        def _pages() -> Iterator[Tuple[int, np.ndarray]]:
            for i in range(len(doc)):
                page = doc[i]
                try:
                    bitmap = page.render(scale=scale, rotation=0)
                    try:
                        img = bitmap.to_numpy()
                        if img.shape[2] == 4:
                            img = img[:, :, :3]
                        yield i, img.astype(np.uint8)
                    finally:
                        bitmap.close()
                finally:
                    page.close()

        yield _pages()
    finally:
        doc.close()
