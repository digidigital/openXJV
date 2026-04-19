"""
Result types for the OCR pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PageStatus(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"   # Some text blocks had low confidence
    FAILED = "failed"     # No text detected on this page


@dataclass
class PageResult:
    page_number: int          # 1-based
    status: PageStatus
    text: str
    avg_confidence: float     # 0.0 – 1.0; -1.0 if no blocks detected
    block_count: int


@dataclass
class OcrResult:
    text: str                          # Full concatenated document text
    page_results: List[PageResult]
    warnings: List[str] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return len(self.page_results)

    @property
    def successful_pages(self) -> int:
        return sum(1 for p in self.page_results if p.status == PageStatus.SUCCESS)

    @property
    def partial_pages(self) -> int:
        return sum(1 for p in self.page_results if p.status == PageStatus.PARTIAL)

    @property
    def failed_pages(self) -> int:
        return sum(1 for p in self.page_results if p.status == PageStatus.FAILED)

    def summary(self) -> str:
        parts = [f"{self.total_pages} page(s) total"]
        if self.successful_pages:
            parts.append(f"{self.successful_pages} OK")
        if self.partial_pages:
            parts.append(f"{self.partial_pages} partial")
        if self.failed_pages:
            parts.append(f"{self.failed_pages} failed")
        s = ", ".join(parts)
        if self.warnings:
            s += f"; {len(self.warnings)} warning(s)"
        return s
