"""OCR provider registration and lookup."""

from __future__ import annotations

import os
from typing import Any, Type

from .azure_document_intelligence_provider import (
    AzureDocumentIntelligenceProvider,
)
from .apple_vision_provider import AppleVisionProvider
from .base import OCRProvider
from .claude_vision_provider import ClaudeVisionProvider
from .easyocr_provider import EasyOCRProvider
from .google_document_ai_provider import GoogleDocumentAIProvider
from .mock_provider import MockProvider
from .openai_vision_provider import OpenAIVisionProvider
from .paddleocr_provider import PaddleOCRProvider
from .tesseract_provider import TesseractProvider


class UnsupportedProviderError(LookupError):
    """Raised for an unregistered OCR provider name."""


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Type[OCRProvider]] = {}

    def register(
        self,
        name: str,
        provider_class: Type[OCRProvider],
        *,
        replace: bool = False,
    ) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("OCR provider name must not be blank.")
        if normalized in self._providers and not replace:
            raise ValueError(f"OCR provider {normalized!r} is already registered.")
        if not issubclass(provider_class, OCRProvider):
            raise TypeError("Registered provider must inherit OCRProvider.")
        self._providers[normalized] = provider_class

    def provider_class(self, name: str) -> Type[OCRProvider]:
        normalized = name.strip().lower()
        try:
            return self._providers[normalized]
        except KeyError as error:
            supported = ", ".join(self.names())
            raise UnsupportedProviderError(
                f"Unsupported OCR provider {name!r}; choose one of: {supported}."
            ) from error

    def create(self, name: str, **kwargs: Any) -> OCRProvider:
        return self.provider_class(name)(**kwargs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


def _default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for name, provider in (
        ("apple-vision", AppleVisionProvider),
        ("mock", MockProvider),
        ("tesseract", TesseractProvider),
        ("easyocr", EasyOCRProvider),
        ("google", GoogleDocumentAIProvider),
        ("azure", AzureDocumentIntelligenceProvider),
        ("openai", OpenAIVisionProvider),
        ("claude", ClaudeVisionProvider),
    ):
        registry.register(name, provider)
    if _legacy_paddle_enabled():
        registry.register("paddle", PaddleOCRProvider)
    return registry


def _legacy_paddle_enabled() -> bool:
    return os.environ.get("RMNTC_ENABLE_LEGACY_PADDLE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


DEFAULT_PROVIDER_REGISTRY = _default_registry()
