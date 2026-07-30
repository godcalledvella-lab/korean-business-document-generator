"""Google Document AI adapter stub."""

from pathlib import Path

from .base import OCRProvider, OCRResult


class GoogleDocumentAIProvider(OCRProvider):
    provider_name = "google"

    def extract(self, path: Path) -> OCRResult:
        raise NotImplementedError("GoogleDocumentAIProvider is a Phase 2B stub.")
