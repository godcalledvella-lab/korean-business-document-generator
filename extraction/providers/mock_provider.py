"""Implemented deterministic OCR provider for development and tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extraction.models import RawTaxInvoiceData

from .base import OCRProvider, OCRResult


class MockProvider(OCRProvider):
    """Load deterministic structured output from an explicit JSON fixture."""

    provider_name = "mock"

    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path).resolve()

    def extract(self, path: Path) -> OCRResult:
        try:
            payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ValueError(
                f"Could not read mock OCR fixture {self.fixture_path}: {error}"
            ) from error
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Mock OCR fixture is invalid JSON at line {error.lineno}, "
                f"column {error.colno}: {self.fixture_path}"
            ) from error
        if not isinstance(payload, dict):
            raise ValueError("Mock OCR fixture must contain a JSON object.")
        structured_payload: dict[str, Any] = dict(payload)
        structured_payload["provider"] = self.provider_name
        raw = RawTaxInvoiceData.from_dict(
            structured_payload,
            provider=self.provider_name,
        )
        confidences = _field_confidences(raw.to_dict())
        overall = sum(confidences) / len(confidences) if confidences else None
        return OCRResult(
            page_count=1,
            language="ko",
            raw_text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            detected_tables=(),
            text_regions=(),
            confidence=overall,
            provider_name=self.provider_name,
            provider_metadata={
                "fixture_path": str(self.fixture_path),
                "input_path": str(path),
                "mode": "deterministic-fixture",
            },
            tax_invoice_data=raw,
        )


def _field_confidences(value: Any) -> list[float]:
    scores: list[float] = []
    if isinstance(value, dict):
        if "value" in value and "confidence" in value:
            confidence = value.get("confidence")
            if confidence is not None:
                scores.append(float(confidence))
        else:
            for item in value.values():
                scores.extend(_field_confidences(item))
    elif isinstance(value, list):
        for item in value:
            scores.extend(_field_confidences(item))
    return scores
