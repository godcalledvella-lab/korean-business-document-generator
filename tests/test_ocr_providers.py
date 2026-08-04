from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from extraction.cli import main as extraction_main
from extraction.normalizer import normalize_tax_invoice
from extraction.providers import (
    DEFAULT_PROVIDER_REGISTRY,
    BoundingBox,
    DetectedTable,
    OCRResult,
    OCRTableCell,
    OCRTaxInvoiceExtractor,
    OCRTextRegion,
    ProviderRegistry,
    UnsupportedProviderError,
)
from extraction.providers.mock_provider import MockProvider
from extraction.providers.paddleocr_provider import (
    PaddleOCRDependencyError,
    PaddleOCRProvider,
)
from extraction.service import TaxInvoiceExtractionService


ROOT = Path(__file__).resolve().parents[1]
MOCK_FIXTURE = ROOT / "tests/fixtures/tax_invoice/clean_single_item.json"
EXPECTED_NAMES = (
    "apple-vision",
    "azure",
    "claude",
    "easyocr",
    "google",
    "mock",
    "openai",
    "paddle",
    "tesseract",
)


def test_default_provider_registration():
    assert DEFAULT_PROVIDER_REGISTRY.names() == EXPECTED_NAMES
    assert DEFAULT_PROVIDER_REGISTRY.provider_class("mock") is MockProvider
    assert DEFAULT_PROVIDER_REGISTRY.provider_class("paddle") is PaddleOCRProvider
    assert DEFAULT_PROVIDER_REGISTRY.provider_class(" MOCK ") is MockProvider


def test_custom_provider_registration_and_duplicate_protection():
    registry = ProviderRegistry()
    registry.register("mock", MockProvider)
    assert registry.create("mock", fixture_path=MOCK_FIXTURE).name == "mock"

    with pytest.raises(ValueError, match="already registered"):
        registry.register("mock", MockProvider)


def test_unsupported_provider_lookup():
    with pytest.raises(UnsupportedProviderError, match="Unsupported OCR provider"):
        DEFAULT_PROVIDER_REGISTRY.provider_class("unknown")


def test_mock_provider_returns_unified_ocr_result(tmp_path):
    input_path = tmp_path / "invoice.png"
    Image.new("RGB", (100, 100), "white").save(input_path)

    result = MockProvider(MOCK_FIXTURE).extract(input_path)

    assert isinstance(result, OCRResult)
    assert result.provider_name == "mock"
    assert result.page_count == 1
    assert result.language == "ko"
    assert result.raw_text
    assert result.detected_tables == ()
    assert result.text_regions == ()
    assert result.confidence is not None
    assert result.provider_metadata["mode"] == "deterministic-fixture"
    assert result.tax_invoice_data is not None
    assert result.tax_invoice_data.provider == "mock"
    assert result.tax_invoice_data.supplier.company_name.value == (
        "알엠엔티씨 주식회사"
    )


def test_unified_result_supports_tables_boxes_and_regions():
    box = BoundingBox(page=1, x=10, y=20, width=100, height=30)
    cell = OCRTableCell(
        row=0,
        column=0,
        text="공급가액",
        bounding_box=box,
        confidence=0.9,
    )
    table = DetectedTable(
        page=1,
        row_count=1,
        column_count=1,
        cells=(cell,),
        bounding_box=box,
        confidence=0.9,
    )
    region = OCRTextRegion("전자세금계산서", box, 0.95)
    result = OCRResult(
        page_count=1,
        language="ko",
        raw_text="전자세금계산서",
        detected_tables=(table,),
        text_regions=(region,),
        confidence=0.93,
        provider_name="mock",
        provider_metadata={"fixture": True},
    )

    assert result.detected_tables[0].cells[0].text == "공급가액"
    assert result.text_regions[0].bounding_box == box


@pytest.mark.parametrize(
    "name",
    ("tesseract", "easyocr", "google", "azure", "openai", "claude"),
)
def test_real_provider_adapters_are_explicit_stubs(name, tmp_path):
    provider = DEFAULT_PROVIDER_REGISTRY.create(name)
    with pytest.raises(NotImplementedError, match="Phase 2B stub"):
        provider.extract(tmp_path / "invoice.png")


class _FakePaddlePipeline:
    def __init__(self, results):
        self.results = results
        self.inputs = []

    def predict(self, path):
        self.inputs.append(path)
        return iter(self.results)


def _paddle_page():
    return {
        "page_index": 0,
        "page_count": 1,
        "overall_ocr_res": {
            "rec_texts": ["전자세금계산서", "공급가액", "1,000"],
            "rec_scores": [0.99, 0.95, 0.94],
            "rec_polys": [
                [[10, 10], [110, 10], [110, 30], [10, 30]],
                [[10, 50], [70, 50], [70, 70], [10, 70]],
                [[80, 50], [130, 50], [130, 70], [80, 70]],
            ],
        },
        "table_res_list": [
            {
                "pred_html": (
                    "<table><tr><th>공급가액</th><th>세액</th></tr>"
                    "<tr><td>1,000</td><td>100</td></tr></table>"
                ),
                "cell_box_list": [
                    [10, 50, 70, 70],
                    [80, 50, 130, 70],
                    [10, 80, 70, 100],
                    [80, 80, 130, 100],
                ],
                "table_ocr_pred": {
                    "rec_texts": ["공급가액", "세액", "1,000", "100"],
                    "rec_scores": [0.95, 0.96, 0.97, 0.98],
                },
            }
        ],
    }


@pytest.mark.parametrize("suffix", (".pdf", ".png", ".jpg", ".jpeg"))
def test_paddle_provider_accepts_supported_inputs_and_converts_result(
    tmp_path, suffix
):
    input_path = tmp_path / f"invoice{suffix}"
    input_path.write_bytes(b"%PDF-1.4" if suffix == ".pdf" else b"image")
    pipeline = _FakePaddlePipeline([_paddle_page()])

    result = PaddleOCRProvider(pipeline=pipeline).extract(input_path)

    assert pipeline.inputs == [str(input_path.resolve())]
    assert result.provider_name == "paddle"
    assert result.page_count == 1
    assert result.language == "ko"
    assert result.raw_text == "전자세금계산서\n공급가액 1,000"
    assert len(result.text_regions) == 3
    assert result.text_regions[0].bounding_box == BoundingBox(
        page=1, x=10, y=10, width=100, height=20
    )
    assert result.confidence is not None
    assert result.detected_tables[0].row_count == 2
    assert result.detected_tables[0].column_count == 2
    assert result.detected_tables[0].cells[3].text == "100"
    assert result.detected_tables[0].cells[3].row == 1
    assert result.detected_tables[0].bounding_box == BoundingBox(
        page=1, x=10, y=50, width=120, height=50
    )
    assert result.tax_invoice_data is None
    assert result.provider_metadata["pipeline"] == "PP-StructureV3"
    assert result.provider_metadata["language"] == "korean"


def test_paddle_provider_rejects_unsupported_input(tmp_path):
    path = tmp_path / "invoice.tiff"
    path.write_bytes(b"image")
    with pytest.raises(ValueError, match="Unsupported PaddleOCR input type"):
        PaddleOCRProvider(pipeline=_FakePaddlePipeline([])).extract(path)


def test_paddle_provider_reconstructs_lines_and_preserves_punctuation(tmp_path):
    path = tmp_path / "invoice.png"
    path.write_bytes(b"image")
    page = {
        "page_index": 0,
        "page_count": 1,
        "overall_ocr_res": {
            "rec_texts": [
                "이메일",
                "sample@example.co.kr",
                "품목",
                "Eco(K-Style)",
                "/ 세트；Blue",
                "공급받는자",
            ],
            "rec_scores": [0.99, 0.97, 0.99, 0.95, 0.72, 0.98],
            "rec_polys": [
                [[10, 10], [55, 10], [55, 25], [10, 25]],
                [[65, 10], [205, 10], [205, 25], [65, 25]],
                [[10, 40], [45, 40], [45, 55], [10, 55]],
                [[55, 40], [145, 40], [145, 55], [55, 55]],
                [[150, 40], [235, 40], [235, 55], [150, 55]],
                [[400, 40], [475, 40], [475, 55], [400, 55]],
            ],
        },
    }

    result = PaddleOCRProvider(pipeline=_FakePaddlePipeline([page])).extract(path)

    assert result.raw_text.splitlines() == [
        "이메일 sample@example.co.kr",
        "품목 Eco(K-Style) / 세트；Blue",
        "공급받는자",
    ]
    assert result.text_regions[4].text == "/ 세트；Blue"
    assert result.text_regions[4].confidence == 0.72


def test_paddle_provider_reports_missing_optional_dependency(tmp_path, monkeypatch):
    path = tmp_path / "invoice.png"
    path.write_bytes(b"image")

    def unavailable():
        raise PaddleOCRDependencyError("PaddleOCR is not installed.")

    provider = PaddleOCRProvider()
    monkeypatch.setattr(provider, "_build_pipeline", unavailable)
    with pytest.raises(PaddleOCRDependencyError, match="not installed"):
        provider.extract(path)


def test_cli_runs_paddle_provider_in_ocr_only_mode(tmp_path, monkeypatch, capsys):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"%PDF-1.4")
    pipeline = _FakePaddlePipeline([_paddle_page()])
    monkeypatch.setattr(
        PaddleOCRProvider,
        "_build_pipeline",
        lambda self: pipeline,
    )

    exit_code = extraction_main([str(path), "--provider", "paddle"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert output.err == ""
    assert "Provider: paddle" in output.out
    assert "Pages: 1" in output.out
    assert "Tables: 1" in output.out
    assert "전자세금계산서" in output.out
    assert "Document generation triggered: no" in output.out


def test_mock_provider_is_downstream_compatible(tmp_path):
    input_path = tmp_path / "invoice.png"
    Image.new("RGB", (100, 100), "white").save(input_path)
    extractor = OCRTaxInvoiceExtractor(MockProvider(MOCK_FIXTURE))
    raw = extractor.extract(input_path)
    normalized = normalize_tax_invoice(raw)

    assert normalized.draft["document"]["seller"]["name"] == (
        "알엠엔티씨 주식회사"
    )
    assert normalized.draft["document"]["totals"]["total"] == 1650000
    assert extractor.last_result is not None
    assert extractor.last_result.provider_name == "mock"


def test_mock_provider_runs_through_existing_extraction_service(tmp_path):
    input_path = tmp_path / "invoice.png"
    Image.new("RGB", (100, 100), "white").save(input_path)
    report = TaxInvoiceExtractionService(
        OCRTaxInvoiceExtractor(MockProvider(MOCK_FIXTURE))
    ).run(
        input_path,
        tmp_path / "raw.json",
        tmp_path / "draft.json",
        tmp_path / "review.md",
    )
    draft = json.loads(report.draft_output.read_text(encoding="utf-8"))

    assert report.provider == "mock"
    assert report.validation.schema_conformant
    assert draft["document"]["buyer"]["name"] == "주식회사 한빛상사"
