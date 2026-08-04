from __future__ import annotations

import platform

import pytest

from extraction import ExtractedField
from extraction.providers import (
    AppleVisionProvider,
    AppleVisionUnavailableError,
    BoundingBox,
    DEFAULT_PROVIDER_REGISTRY,
    OCRResult,
)
from extraction.providers.apple_vision_provider import AppleVisionObservation
from extraction.providers.registry import _default_registry
from pipeline.mapper import OCRInvoiceMapper


class FakeVisionEngine:
    def __init__(self, observations=()):
        self.observations = observations
        self.calls = []

    def recognize(self, path, languages):
        self.calls.append((path, tuple(languages)))
        return 1, self.observations


def test_apple_vision_provider_is_registered_without_changing_paddle():
    assert (
        DEFAULT_PROVIDER_REGISTRY.provider_class("apple-vision")
        is AppleVisionProvider
    )
    assert "paddle" in DEFAULT_PROVIDER_REGISTRY.names()


def test_legacy_paddle_registration_is_feature_flagged(monkeypatch):
    monkeypatch.setenv("RMNTC_ENABLE_LEGACY_PADDLE", "false")
    registry = _default_registry()

    assert "apple-vision" in registry.names()
    assert "paddle" not in registry.names()


def test_apple_vision_construction_and_normalized_top_left_boxes(tmp_path):
    source = tmp_path / "invoice.png"
    source.write_bytes(b"fixture")
    engine = FakeVisionEngine(
        (
            AppleVisionObservation(
                1, "전자세금계산서", 0.1, 0.7, 0.4, 0.1, 0.97
            ),
        )
    )

    result = AppleVisionProvider(engine=engine).extract(source)

    assert isinstance(result, OCRResult)
    assert result.provider_name == "apple-vision"
    assert result.raw_text == "전자세금계산서"
    assert result.detected_tables == ()
    assert result.text_regions[0].bounding_box == BoundingBox(
        page=1, x=0.1, y=pytest.approx(0.2), width=0.4, height=0.1
    )
    assert result.text_regions[0].confidence == 0.97
    assert result.provider_metadata["normalized_bounding_boxes"] is True
    assert result.provider_metadata["table_recognition"] is False


def test_apple_vision_empty_text_returns_controlled_review_warning(tmp_path):
    source = tmp_path / "invoice.jpg"
    source.write_bytes(b"fixture")

    result = AppleVisionProvider(engine=FakeVisionEngine()).extract(source)
    raw = OCRInvoiceMapper().map(result)

    assert result.raw_text == ""
    assert result.provider_metadata["warnings"]
    assert isinstance(raw.issue_date, ExtractedField)
    assert raw.issue_date.value is None
    assert raw.issue_date.confidence is None
    assert raw.issue_date.source_text is None
    assert raw.items == ()
    assert raw.provider == "apple-vision"


def test_apple_vision_preserves_review_mapper_contract(tmp_path):
    source = tmp_path / "invoice.jpeg"
    source.write_bytes(b"fixture")
    engine = FakeVisionEngine(
        (
            AppleVisionObservation(1, "작성일자", 0.05, 0.80, 0.12, 0.03, 0.99),
            AppleVisionObservation(
                1, "2026-05-18", 0.18, 0.80, 0.14, 0.03, 0.98
            ),
            AppleVisionObservation(1, "합계금액", 0.05, 0.10, 0.12, 0.03, 0.99),
            AppleVisionObservation(
                1, "1,562,000", 0.18, 0.10, 0.14, 0.03, 0.98
            ),
        )
    )

    result = AppleVisionProvider(engine=engine).extract(source)
    raw = OCRInvoiceMapper().map(result)
    payload = raw.to_dict()

    assert payload["provider"] == "apple-vision"
    assert set(payload) >= {
        "issue_date",
        "supplier",
        "buyer",
        "items",
        "totals",
    }
    assert payload["issue_date"]["value"] == "2026-05-18"
    assert payload["totals"]["grand_total"]["value"] == "1,562,000"


def test_apple_vision_reports_unavailable_platform_without_fallback(
    tmp_path, monkeypatch
):
    source = tmp_path / "invoice.png"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    with pytest.raises(
        AppleVisionUnavailableError, match="available only on macOS"
    ):
        AppleVisionProvider().extract(source)


def test_apple_vision_rejects_non_normalized_boxes(tmp_path):
    source = tmp_path / "invoice.png"
    source.write_bytes(b"fixture")
    engine = FakeVisionEngine(
        (AppleVisionObservation(1, "text", 1.1, 0.1, 0.1, 0.1, 0.9),)
    )

    with pytest.raises(ValueError, match="non-normalized bounding box"):
        AppleVisionProvider(engine=engine).extract(source)
