"""OCR provider adapters and registry."""

from .base import (
    BoundingBox,
    DetectedTable,
    OCRProvider,
    OCRResult,
    OCRTableCell,
    OCRTaxInvoiceExtractor,
    OCRTextRegion,
)
from .apple_vision_provider import (
    AppleVisionAvailability,
    AppleVisionProvider,
    AppleVisionUnavailableError,
)
from .paddleocr_provider import PaddleOCRDependencyError, PaddleOCRProvider
from .registry import (
    DEFAULT_PROVIDER_REGISTRY,
    ProviderRegistry,
    UnsupportedProviderError,
)

__all__ = [
    "BoundingBox",
    "AppleVisionAvailability",
    "AppleVisionProvider",
    "AppleVisionUnavailableError",
    "DEFAULT_PROVIDER_REGISTRY",
    "DetectedTable",
    "OCRProvider",
    "OCRResult",
    "OCRTableCell",
    "OCRTaxInvoiceExtractor",
    "OCRTextRegion",
    "PaddleOCRDependencyError",
    "PaddleOCRProvider",
    "ProviderRegistry",
    "UnsupportedProviderError",
]
