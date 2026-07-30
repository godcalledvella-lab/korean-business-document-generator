"""Azure Document Intelligence adapter stub."""

from pathlib import Path

from .base import OCRProvider, OCRResult


class AzureDocumentIntelligenceProvider(OCRProvider):
    provider_name = "azure"

    def extract(self, path: Path) -> OCRResult:
        raise NotImplementedError(
            "AzureDocumentIntelligenceProvider is a Phase 2B stub."
        )
