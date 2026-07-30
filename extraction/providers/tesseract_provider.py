"""Tesseract OCR adapter stub."""

from pathlib import Path

from .base import OCRProvider, OCRResult


class TesseractProvider(OCRProvider):
    provider_name = "tesseract"

    def extract(self, path: Path) -> OCRResult:
        raise NotImplementedError("TesseractProvider is a Phase 2B stub.")
