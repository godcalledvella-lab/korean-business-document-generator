"""OpenAI vision adapter stub."""

from pathlib import Path

from .base import OCRProvider, OCRResult


class OpenAIVisionProvider(OCRProvider):
    provider_name = "openai"

    def extract(self, path: Path) -> OCRResult:
        raise NotImplementedError("OpenAIVisionProvider is a Phase 2B stub.")
