from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader

from extraction.providers import BoundingBox, OCRResult, OCRTextRegion
from extraction.providers.mock_provider import MockProvider
from pipeline.mapper import OCRInvoiceMapper, PAYMENT_METHOD_LABELS
from pipeline.service import PipelineError, RmntcGenerationPipeline


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/tax_invoice/clean_single_item.json"
REFERENCE = ROOT / "reference/rmntc/rmntc_reference.pdf"
CORRECTED_LAYOUT = (
    ROOT / "tests/fixtures/ocr/korean_corrected_tax_invoice_layout.json"
)
PUNCTUATION_LAYOUT = (
    ROOT / "tests/fixtures/ocr/korean_punctuation_multiline_layout.json"
)


def _image(path: Path) -> Path:
    Image.new("RGB", (100, 100), "white").save(path)
    return path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_end_to_end_pipeline_generates_workbooks_and_fixed_assets(tmp_path):
    source = _image(tmp_path / "invoice.png")
    output = tmp_path / "output"
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["supplier"]["phone"] = {
        "value": "02-1234-5678",
        "confidence": 0.99,
    }
    fixture = tmp_path / "complete.json"
    fixture.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    template_paths = tuple(
        (ROOT / "reference/rmntc/templates").glob("*.xlsx")
    )
    before = {path: _hash(path) for path in (*template_paths, REFERENCE)}

    report = RmntcGenerationPipeline(
        MockProvider(fixture), project_root=ROOT
    ).run(source, output)

    assert report.provider == "mock"
    assert report.invoice_draft == output / "invoice_draft.json"
    assert report.review_report == output / "review_report.md"
    assert set(path.name for path in report.workbooks.values()) == {
        "statement.xlsx",
        "quotation.xlsx",
        "comparison.xlsx",
    }
    for path in report.workbooks.values():
        workbook = load_workbook(path)
        workbook.close()
    assert set(path.name for path in report.fixed_assets.values()) == {
        "business_registration.pdf",
        "bank_account.pdf",
    }
    assert all(len(PdfReader(path).pages) == 1 for path in report.fixed_assets.values())
    assert {path: _hash(path) for path in before} == before
    assert json.loads(report.invoice_draft.read_text(encoding="utf-8"))[
        "document"
    ]["totals"]["total"] == 1650000


def test_invalid_ocr_draft_publishes_review_but_no_excel_or_assets(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["totals"]["grand_total"]["value"] = "1,700,000"
    invalid_fixture = tmp_path / "invalid.json"
    invalid_fixture.write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )
    output = tmp_path / "output"

    with pytest.raises(PipelineError, match="OCR validation failed"):
        RmntcGenerationPipeline(
            MockProvider(invalid_fixture), project_root=ROOT
        ).run(_image(tmp_path / "invoice.jpg"), output)

    assert (output / "invoice_draft.json").is_file()
    report = (output / "review_report.md").read_text(encoding="utf-8")
    assert "totals.grand_total" in report
    for name in (
        "statement.xlsx",
        "quotation.xlsx",
        "comparison.xlsx",
        "business_registration.pdf",
        "bank_account.pdf",
    ):
        assert not (output / name).exists()


def test_renderer_required_missing_field_fails_before_excel_generation(tmp_path):
    output = tmp_path / "output"
    with pytest.raises(PipelineError, match="missing data required"):
        RmntcGenerationPipeline(
            MockProvider(FIXTURE), project_root=ROOT
        ).run(_image(tmp_path / "invoice.jpeg"), output)

    assert "document.seller.contact.phone" in (
        output / "review_report.md"
    ).read_text(encoding="utf-8")
    assert not (output / "statement.xlsx").exists()


def test_pipeline_mapper_uses_only_explicit_labels():
    box = BoundingBox(page=1, x=0, y=0, width=100, height=10)
    result = OCRResult(
        page_count=1,
        language="ko",
        raw_text="\n".join(
            (
                "작성일자: 2026년 07월 29일",
                "승인번호: 20260729-12345678",
                "공급자 사업자등록번호: 123-45-67890",
                "공급자 상호: 알엠엔티씨",
                "공급받는자 사업자등록번호: 987-65-43210",
                "공급받는자 상호: 한빛상사",
                "표시되지 않은 값",
            )
        ),
        text_regions=(
            OCRTextRegion("작성일자: 2026년 07월 29일", box, 0.98),
        ),
        confidence=0.95,
        provider_name="paddle",
    )

    raw = OCRInvoiceMapper().map(result)

    assert raw.issue_date.value == "2026년 07월 29일"
    assert raw.supplier.company_name.value == "알엠엔티씨"
    assert raw.buyer.company_name.value == "한빛상사"
    assert raw.supplier.address.value is None
    assert raw.items == ()


def _layout_result(path: Path) -> OCRResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    regions = tuple(
        OCRTextRegion(
            text,
            BoundingBox(page=1, x=x, y=y, width=width, height=height),
            confidence,
        )
        for text, x, y, width, height, confidence in payload["regions"]
    )
    return OCRResult(
        page_count=payload["page_count"],
        language=payload["language"],
        raw_text="\n".join(region.text for region in regions),
        text_regions=regions,
        confidence=0.95,
        provider_name=payload["provider_name"],
    )


def _corrected_layout_result() -> OCRResult:
    return _layout_result(CORRECTED_LAYOUT)


def test_corrected_invoice_uses_spatial_amounts_not_payment_labels():
    raw = OCRInvoiceMapper().map(_corrected_layout_result())

    assert raw.totals.supply_amount.value == "1,420,000"
    assert raw.totals.vat.value == "142,000"
    assert raw.totals.grand_total.value == "1,562,000"
    assert raw.totals.grand_total.value != "현금"
    assert [item.item_name.value for item in raw.items] == [
        "품목A",
        "품목B",
        "품목C",
    ]
    assert [item.supply_amount.value for item in raw.items] == [
        "1,200,000",
        "150,000",
        "70,000",
    ]


def test_korean_punctuation_and_multiline_fields_survive_spatial_mapping():
    result = _layout_result(PUNCTUATION_LAYOUT)
    raw = OCRInvoiceMapper().map(result)

    assert "Eco(K-Style)" in [region.text for region in result.text_regions]
    assert "/ 세트；Blue" in [region.text for region in result.text_regions]
    assert raw.supplier.business_registration_number.value == "102-21-34572"
    assert raw.buyer.business_registration_number.value == "809-82-00077"
    assert raw.supplier.address.value == (
        "경상남도 창원시 성산구 외동반림로126번길 57, 1층(중앙동)"
    )
    assert raw.buyer.address.value == (
        "서울특별시 송파구 올림픽로 424, 올림픽회관 신관 213호 (방이동)"
    )
    assert raw.buyer.email.value == "koreasquash@sports.or.kr"
    assert raw.supplier.email.value == "bigthumbdesigner@gmail com"
    assert raw.supplier.email.source_text == "이메일 bigthumbdesigner@gmail com"
    assert raw.supplier.email.confidence == 0.79
    assert [item.item_name.value for item in raw.items] == [
        "Eco(K-Style) / 세트；Blue",
        "리본-Blue",
    ]
    assert raw.items[0].item_name.confidence == 0.72
    assert all(item.item_name.value not in PAYMENT_METHOD_LABELS for item in raw.items)


def test_pipeline_cli_generates_expected_outputs(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["supplier"]["phone"] = {
        "value": "02-1234-5678",
        "confidence": 0.99,
    }
    fixture = tmp_path / "complete.json"
    fixture.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    source = _image(tmp_path / "invoice.png")
    output = tmp_path / "output"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipeline.cli",
            str(source),
            "--provider",
            "mock",
            "--mock-json",
            str(fixture),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Pipeline succeeded." in completed.stdout
    assert {path.name for path in output.iterdir()} == {
        "statement.xlsx",
        "quotation.xlsx",
        "comparison.xlsx",
        "business_registration.pdf",
        "bank_account.pdf",
        "invoice_draft.json",
        "review_report.md",
    }
