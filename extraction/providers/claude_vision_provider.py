"""Anthropic Claude vision adapter stub."""

from pathlib import Path

from .base import OCRProvider, OCRResult


class ClaudeVisionProvider(OCRProvider):
    provider_name = "claude"

    def extract(self, path: Path) -> OCRResult:
        raise NotImplementedError("ClaudeVisionProvider is a Phase 2B stub.")
