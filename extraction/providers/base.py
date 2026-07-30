"""Provider-neutral OCR models and abstract provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from extraction.models import RawTaxInvoiceData


@dataclass(frozen=True)
class BoundingBox:
    """Provider-neutral box in source page coordinates."""

    page: int
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class OCRTextRegion:
    text: str
    bounding_box: BoundingBox
    confidence: float | None = None


@dataclass(frozen=True)
class OCRTableCell:
    row: int
    column: int
    text: str
    bounding_box: BoundingBox | None = None
    confidence: float | None = None
    row_span: int = 1
    column_span: int = 1


@dataclass(frozen=True)
class DetectedTable:
    page: int
    row_count: int
    column_count: int
    cells: tuple[OCRTableCell, ...] = ()
    bounding_box: BoundingBox | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class OCRResult:
    """Unified OCR result; no provider SDK object may cross this boundary."""

    page_count: int
    language: str | None
    raw_text: str
    detected_tables: tuple[DetectedTable, ...] = ()
    text_regions: tuple[OCRTextRegion, ...] = ()
    confidence: float | None = None
    provider_name: str = "unknown"
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    tax_invoice_data: RawTaxInvoiceData | None = None

    def __post_init__(self) -> None:
        if self.page_count < 1:
            raise ValueError("OCRResult page_count must be positive.")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("OCRResult confidence must be between 0 and 1.")


class OCRProvider(ABC):
    """Abstract OCR engine adapter."""

    provider_name: str

    @property
    def name(self) -> str:
        return self.provider_name

    @abstractmethod
    def extract(self, path: Path) -> OCRResult:
        """Return one provider-neutral OCRResult."""


class OCRTaxInvoiceExtractor:
    """Bridge OCRResult into the existing RawTaxInvoiceData pipeline boundary."""

    def __init__(self, provider: OCRProvider) -> None:
        self.provider = provider
        self.name = provider.name
        self.last_result: OCRResult | None = None

    def extract(self, input_path: str | Path) -> RawTaxInvoiceData:
        result = self.provider.extract(Path(input_path).resolve())
        self.last_result = result
        if result.tax_invoice_data is None:
            raise ValueError(
                f"OCR provider {self.provider.name!r} returned no structured "
                "tax-invoice data."
            )
        return result.tax_invoice_data
