"""EasyOCR adapter stub."""

from pathlib import Path

from .base import OCRProvider, OCRResult


class EasyOCRProvider(OCRProvider):
    provider_name = "easyocr"

    def extract(self, path: Path) -> OCRResult:
        raise NotImplementedError("EasyOCRProvider is a Phase 2B stub.")
